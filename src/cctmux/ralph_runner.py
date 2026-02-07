"""Ralph Loop runner engine for automated iterative Claude Code execution."""

from __future__ import annotations

import json
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from rich.console import Console

err_console = Console(stderr=True)


class RalphStatus(StrEnum):
    """Status of a Ralph Loop execution."""

    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MAX_REACHED = "max_reached"
    ERROR = "error"


@dataclass
class TaskProgress:
    """Progress of checklist tasks in a Ralph project file."""

    total: int
    completed: int

    @property
    def percentage(self) -> float:
        """Return completion percentage."""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100.0

    @property
    def is_all_done(self) -> bool:
        """Return True if all tasks are completed."""
        return self.total > 0 and self.completed >= self.total


@dataclass
class IterationResult:
    """Result from a single Ralph Loop iteration."""

    number: int
    started_at: str
    ended_at: str
    duration_seconds: float
    exit_code: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    tool_calls: int
    model: str
    result_text: str
    promise_found: bool
    tasks_before: TaskProgress
    tasks_after: TaskProgress

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "number": self.number,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_usd": self.cost_usd,
            "tool_calls": self.tool_calls,
            "model": self.model,
            "result_text": self.result_text,
            "promise_found": self.promise_found,
            "tasks_before": {"total": self.tasks_before.total, "completed": self.tasks_before.completed},
            "tasks_after": {"total": self.tasks_after.total, "completed": self.tasks_after.completed},
        }


class RalphState(BaseModel):
    """Persisted state for a Ralph Loop execution."""

    status: str = "active"
    iteration: int = 0
    max_iterations: int = 0
    completion_promise: str = ""
    permission_mode: str = "acceptEdits"
    model: str | None = None
    max_budget_usd: float | None = None
    started_at: str = ""
    ended_at: str | None = None
    project_file: str = ""
    tasks_total: int = 0
    tasks_completed: int = 0
    iterations: list[dict[str, Any]] = []


# Regex for markdown checklist items
_CHECKED_RE = re.compile(r"^\s*-\s*\[x\]", re.IGNORECASE)
_UNCHECKED_RE = re.compile(r"^\s*-\s*\[ \]")
_PROMISE_RE = re.compile(r"<promise>(.*?)</promise>", re.DOTALL)


def parse_task_progress(project_file: Path) -> TaskProgress:
    """Parse markdown checklist items from a project file.

    Counts `- [ ]` (incomplete) and `- [x]` (complete) items.

    Args:
        project_file: Path to the markdown project file.

    Returns:
        TaskProgress with total and completed counts.
    """
    if not project_file.exists():
        return TaskProgress(total=0, completed=0)

    content = project_file.read_text(encoding="utf-8")
    completed = 0
    total = 0

    for line in content.splitlines():
        if _CHECKED_RE.match(line):
            completed += 1
            total += 1
        elif _UNCHECKED_RE.match(line):
            total += 1

    return TaskProgress(total=total, completed=completed)


def build_system_prompt(
    iteration: int,
    max_iterations: int,
    project_file_path: str,
    completion_promise: str,
) -> str:
    """Build the --append-system-prompt with Ralph instructions.

    Args:
        iteration: Current iteration number (1-based).
        max_iterations: Maximum iterations (0 = unlimited).
        project_file_path: Path to the project file.
        completion_promise: Text to output inside <promise> tags when done.

    Returns:
        System prompt addition string.
    """
    max_str = str(max_iterations) if max_iterations > 0 else "unlimited"
    lines = [
        f"You are executing iteration {iteration}/{max_str} of a Ralph Loop automation.",
        "",
        "INSTRUCTIONS:",
        "1. Read the project file content above. Tasks marked `- [ ]` are incomplete.",
        "   Tasks marked `- [x]` are complete.",
        "2. Work on the next incomplete task(s). Focus on quality over quantity.",
        f"3. After completing a task, update the project file ({project_file_path}) by",
        "   changing `- [ ]` to `- [x]` for that task.",
        "4. Run verification steps (tests, linting) as appropriate.",
    ]

    if completion_promise:
        lines.extend(
            [
                f"5. When ALL tasks are complete, output exactly: <promise>{completion_promise}</promise>",
                "",
                "CRITICAL: Only output the promise tag when the statement is genuinely true.",
                "Do not output false promises to exit the loop.",
            ]
        )

    return "\n".join(lines)


def build_claude_command(
    prompt: str,
    system_prompt_addition: str,
    permission_mode: str,
    model: str | None,
    max_budget_usd: float | None,
) -> list[str]:
    """Build the claude CLI command for one iteration.

    Args:
        prompt: The main prompt content (project file content).
        system_prompt_addition: Content for --append-system-prompt.
        permission_mode: Permission mode flag value.
        model: Model to use (None for default).
        max_budget_usd: Max budget per iteration (None for no limit).

    Returns:
        Command as a list of strings.
    """
    cmd = [
        "claude",
        "-p",
        prompt,
        "--append-system-prompt",
        system_prompt_addition,
        "--output-format",
        "json",
        "--permission-mode",
        permission_mode,
    ]

    if model:
        cmd.extend(["--model", model])

    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])

    return cmd


def parse_claude_json_output(output: str) -> dict[str, Any]:
    """Parse claude --output-format json response.

    Extracts: result text, token counts, cost, model, tool_calls count.

    Args:
        output: Raw JSON output from claude CLI.

    Returns:
        Dict with parsed fields. Missing fields default to zero/empty.
    """
    result: dict[str, Any] = {
        "result_text": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "cost_usd": 0.0,
        "tool_calls": 0,
        "model": "",
    }

    try:
        raw = json.loads(output)
    except json.JSONDecodeError, ValueError:
        result["result_text"] = output[:500] if output else ""
        return result

    # Extract result text from the response
    if isinstance(raw, dict):
        data = cast(dict[str, Any], raw)
        result["result_text"] = str(data.get("result", ""))[:500]
        result["model"] = str(data.get("model", ""))
        result["cost_usd"] = float(data.get("cost_usd", 0.0))
        result["input_tokens"] = int(data.get("input_tokens", 0))
        result["output_tokens"] = int(data.get("output_tokens", 0))
        result["cache_read_tokens"] = int(data.get("cache_read_tokens", 0))
        result["cache_creation_tokens"] = int(data.get("cache_creation_tokens", 0))
        result["tool_calls"] = int(data.get("num_turns", 0))

    return result


def check_completion_promise(text: str, promise: str) -> bool:
    """Check for <promise>TEXT</promise> in output.

    Args:
        text: The text to search.
        promise: The expected promise text.

    Returns:
        True if the promise is found.
    """
    if not promise or not text:
        return False

    match = _PROMISE_RE.search(text)
    if match:
        found = match.group(1).strip()
        return found == promise.strip()
    return False


def save_ralph_state(state: RalphState, project_path: Path) -> None:
    """Atomic write to .claude/ralph-state.json.

    Args:
        state: The state to save.
        project_path: Project root directory.
    """
    state_dir = project_path / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "ralph-state.json"

    # Atomic write via temp file
    data = state.model_dump_json(indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(state_dir), suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            f.write(data)
        Path(tmp_path).replace(state_file)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def load_ralph_state(project_path: Path) -> RalphState | None:
    """Load state from .claude/ralph-state.json.

    Args:
        project_path: Project root directory.

    Returns:
        RalphState if file exists and is valid, None otherwise.
    """
    state_file = project_path / ".claude" / "ralph-state.json"
    if not state_file.exists():
        return None

    try:
        content = state_file.read_text(encoding="utf-8")
        return RalphState.model_validate_json(content)
    except json.JSONDecodeError, ValueError:
        return None


def cancel_ralph_loop(project_path: Path) -> bool:
    """Set status to 'cancelled' in state file.

    Args:
        project_path: Project root directory.

    Returns:
        True if state was updated, False if no active loop.
    """
    state = load_ralph_state(project_path)
    if state is None:
        return False

    if state.status != RalphStatus.ACTIVE:
        return False

    state.status = RalphStatus.CANCELLED
    state.ended_at = datetime.now(UTC).isoformat()
    save_ralph_state(state, project_path)
    return True


def init_project_file(output_path: Path, name: str = "") -> None:
    """Generate a template Ralph project file.

    Args:
        output_path: Where to write the template.
        name: Project name for the header (optional).
    """
    project_name = name or "My Project"
    content = f"""# Ralph Project: {project_name}

## Description
Describe what you're building and any high-level context.

## Tasks
- [ ] First task
- [ ] Second task
- [ ] Third task

## Notes
Additional context, constraints, or preferences for Claude.
"""
    output_path.write_text(content, encoding="utf-8")


def run_ralph_loop(
    project_file: Path,
    max_iterations: int = 0,
    completion_promise: str = "",
    permission_mode: str = "acceptEdits",
    model: str | None = None,
    max_budget_usd: float | None = None,
    project_path: Path | None = None,
) -> None:
    """Main loop runner. Blocks until loop completes.

    Signal handling: Ctrl+C sets state to cancelled and exits cleanly.
    Between iterations: checks state file for 'cancelled' status.

    Args:
        project_file: Path to the Ralph project markdown file.
        max_iterations: Maximum iterations (0 = unlimited).
        completion_promise: Text to match in <promise> tags.
        permission_mode: Claude permission mode.
        model: Claude model to use.
        max_budget_usd: Max budget per iteration.
        project_path: Project root (defaults to project_file parent).
    """
    proj_path = project_path or project_file.parent
    proj_path = proj_path.resolve()
    project_file = project_file.resolve()

    if not project_file.exists():
        err_console.print(f"[red]Error:[/] Project file not found: {project_file}")
        return

    # Initialize state
    initial_progress = parse_task_progress(project_file)
    state = RalphState(
        status=RalphStatus.ACTIVE,
        iteration=0,
        max_iterations=max_iterations,
        completion_promise=completion_promise,
        permission_mode=permission_mode,
        model=model,
        max_budget_usd=max_budget_usd,
        started_at=datetime.now(UTC).isoformat(),
        project_file=str(project_file),
        tasks_total=initial_progress.total,
        tasks_completed=initial_progress.completed,
    )
    save_ralph_state(state, proj_path)

    console = Console()
    cancelled = False

    def _signal_handler(signum: int, frame: Any) -> None:
        nonlocal cancelled
        cancelled = True
        console.print("\n[yellow]Cancelling Ralph Loop...[/]")

    old_handler = signal.signal(signal.SIGINT, _signal_handler)

    try:
        iteration = 0
        while True:
            iteration += 1

            # Check max iterations
            if max_iterations > 0 and iteration > max_iterations:
                state.status = RalphStatus.MAX_REACHED
                state.ended_at = datetime.now(UTC).isoformat()
                save_ralph_state(state, proj_path)
                console.print(f"[cyan]Max iterations ({max_iterations}) reached.[/]")
                break

            # Check for external cancellation
            current_state = load_ralph_state(proj_path)
            if current_state and current_state.status == RalphStatus.CANCELLED:
                console.print("[yellow]Loop cancelled externally.[/]")
                state.status = RalphStatus.CANCELLED
                state.ended_at = datetime.now(UTC).isoformat()
                save_ralph_state(state, proj_path)
                break

            # Check for Ctrl+C
            if cancelled:
                state.status = RalphStatus.CANCELLED
                state.ended_at = datetime.now(UTC).isoformat()
                save_ralph_state(state, proj_path)
                break

            # Read project file and check tasks
            tasks_before = parse_task_progress(project_file)
            if tasks_before.is_all_done:
                state.status = RalphStatus.COMPLETED
                state.ended_at = datetime.now(UTC).isoformat()
                state.tasks_total = tasks_before.total
                state.tasks_completed = tasks_before.completed
                save_ralph_state(state, proj_path)
                console.print("[green]All tasks completed![/]")
                break

            # Build prompt
            prompt_content = project_file.read_text(encoding="utf-8")
            system_prompt = build_system_prompt(
                iteration=iteration,
                max_iterations=max_iterations,
                project_file_path=str(project_file),
                completion_promise=completion_promise,
            )

            # Build command
            cmd = build_claude_command(
                prompt=prompt_content,
                system_prompt_addition=system_prompt,
                permission_mode=permission_mode,
                model=model,
                max_budget_usd=max_budget_usd,
            )

            # Update state for this iteration
            state.iteration = iteration
            state.tasks_total = tasks_before.total
            state.tasks_completed = tasks_before.completed
            save_ralph_state(state, proj_path)

            max_str = f"/{max_iterations}" if max_iterations > 0 else ""
            console.print(
                f"\n[bold blue]━━━ Iteration {iteration}{max_str} ━━━[/]"
                f"  Tasks: {tasks_before.completed}/{tasks_before.total}"
            )

            # Run Claude
            started_at = datetime.now(UTC)
            exit_code = 0
            output = ""

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(proj_path),
                )
                exit_code = result.returncode
                output = result.stdout
                if result.stderr:
                    err_console.print(f"[dim]{result.stderr[:200]}[/]")
            except Exception as e:
                exit_code = 1
                output = str(e)
                err_console.print(f"[red]Error running claude:[/] {e}")

            ended_at = datetime.now(UTC)
            duration = (ended_at - started_at).total_seconds()

            # Parse output
            parsed = parse_claude_json_output(output)

            # Check for promise
            promise_found = check_completion_promise(parsed["result_text"], completion_promise)

            # Re-read task progress after iteration
            tasks_after = parse_task_progress(project_file)

            # Build iteration result
            iter_result = IterationResult(
                number=iteration,
                started_at=started_at.isoformat(),
                ended_at=ended_at.isoformat(),
                duration_seconds=round(duration, 1),
                exit_code=exit_code,
                input_tokens=parsed["input_tokens"],
                output_tokens=parsed["output_tokens"],
                cache_read_tokens=parsed["cache_read_tokens"],
                cache_creation_tokens=parsed["cache_creation_tokens"],
                cost_usd=parsed["cost_usd"],
                tool_calls=parsed["tool_calls"],
                model=parsed["model"],
                result_text=parsed["result_text"],
                promise_found=promise_found,
                tasks_before=tasks_before,
                tasks_after=tasks_after,
            )

            # Update state
            state.iterations.append(iter_result.to_dict())
            state.tasks_total = tasks_after.total
            state.tasks_completed = tasks_after.completed

            tasks_delta = tasks_after.completed - tasks_before.completed
            delta_str = f" (+{tasks_delta})" if tasks_delta > 0 else ""
            console.print(
                f"  Duration: {duration:.1f}s  "
                f"Cost: ${parsed['cost_usd']:.2f}  "
                f"Tasks: {tasks_after.completed}/{tasks_after.total}{delta_str}"
            )

            # Check completion conditions
            if promise_found:
                state.status = RalphStatus.COMPLETED
                state.ended_at = ended_at.isoformat()
                save_ralph_state(state, proj_path)
                console.print(f"[green]Promise fulfilled:[/] {completion_promise}")
                break

            if tasks_after.is_all_done:
                state.status = RalphStatus.COMPLETED
                state.ended_at = ended_at.isoformat()
                save_ralph_state(state, proj_path)
                console.print("[green]All tasks completed![/]")
                break

            if exit_code != 0:
                state.status = RalphStatus.ERROR
                state.ended_at = ended_at.isoformat()
                save_ralph_state(state, proj_path)
                console.print(f"[red]Claude exited with code {exit_code}[/]")
                break

            save_ralph_state(state, proj_path)

            # Small pause between iterations
            time.sleep(1)

    finally:
        signal.signal(signal.SIGINT, old_handler)

    # Print summary
    total_cost = sum(it.get("cost_usd", 0.0) for it in state.iterations)
    total_tokens_in = sum(it.get("input_tokens", 0) for it in state.iterations)
    total_tokens_out = sum(it.get("output_tokens", 0) for it in state.iterations)
    console.print(
        f"\n[bold]Ralph Loop finished:[/] {state.status}  "
        f"Iterations: {len(state.iterations)}  "
        f"Cost: ${total_cost:.2f}  "
        f"Tokens: {total_tokens_in}→{total_tokens_out}"
    )
