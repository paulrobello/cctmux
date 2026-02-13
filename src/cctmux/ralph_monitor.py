"""Real-time Ralph Loop monitor dashboard."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cctmux.ralph_runner import (
    RalphState,
    RalphStatus,
    load_ralph_state,
)
from cctmux.utils import compress_paths_in_text


def _get_nested_int(data: dict[str, Any], outer_key: str, inner_key: str) -> int:
    """Safely extract a nested int from iteration dict data.

    Args:
        data: The iteration dictionary.
        outer_key: Key for the outer dict (e.g. "tasks_before").
        inner_key: Key for the inner value (e.g. "completed").

    Returns:
        The integer value, or 0 if not found.
    """
    try:
        outer = data.get(outer_key, {})
        if isinstance(outer, dict) and inner_key in outer:
            return int(f"{outer[inner_key]}")  # type: ignore[index]
    except (ValueError, TypeError):
        pass
    return 0


@dataclass
class RalphMonitorConfig:
    """Configuration for Ralph monitor display."""

    show_table: bool = True
    show_timeline: bool = True
    show_prompt: bool = False
    show_task_progress: bool = True
    max_iterations_visible: int = 20


def _format_tokens(count: int) -> str:
    """Format token count for display.

    Args:
        count: Number of tokens.

    Returns:
        Formatted string like "1.2K" or "1.5M".
    """
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable form.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string like "5m 12s" or "1h 2m".
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


_STATUS_SYMBOLS: dict[str, tuple[str, str]] = {
    RalphStatus.WAITING: ("○", "dim"),
    RalphStatus.ACTIVE: ("◐", "yellow"),
    RalphStatus.COMPLETED: ("●", "green"),
    RalphStatus.CANCELLED: ("✗", "red"),
    RalphStatus.MAX_REACHED: ("⊘", "cyan"),
    RalphStatus.ERROR: ("✗", "red"),
}


def build_ralph_status_panel(state: RalphState) -> Panel:
    """Build the status and progress panel.

    Shows status indicator, iteration count, elapsed time,
    task progress bar, promise text, and token/cost totals.

    Args:
        state: Current Ralph state.

    Returns:
        Rich Panel with status display.
    """
    text = Text()

    # Status symbol and label
    symbol, color = _STATUS_SYMBOLS.get(state.status, ("?", "white"))
    text.append(f"{symbol} ", style=color)
    text.append(state.status.upper(), style=f"bold {color}")

    # Iteration count
    max_str = f"/{state.max_iterations}" if state.max_iterations > 0 else ""
    text.append(f"  Iteration: {state.iteration}{max_str}", style="bold")

    # Elapsed time
    if state.started_at:
        try:
            started = datetime.fromisoformat(state.started_at)
            ended = datetime.fromisoformat(state.ended_at) if state.ended_at else datetime.now(UTC)
            elapsed = (ended - started).total_seconds()
            text.append(f"  Elapsed: {_format_duration(elapsed)}", style="dim")
        except ValueError:
            pass

    text.append("\n")

    # Task progress bar
    total = state.tasks_total
    completed = state.tasks_completed
    if total > 0:
        pct = (completed / total) * 100
        bar_width = 20
        filled = int(bar_width * completed / total)
        bar = "█" * filled + "░" * (bar_width - filled)
        text.append("Tasks: ", style="dim")
        text.append(f"[{bar}]", style="bold green" if completed == total else "bold yellow")
        text.append(f" {completed}/{total} ({pct:.0f}%)", style="bold")
    else:
        text.append("Tasks: ", style="dim")
        text.append("none detected", style="dim")

    # Promise
    if state.completion_promise:
        text.append("\n")
        text.append("Promise: ", style="dim")
        text.append(f'"{state.completion_promise}"', style="italic cyan")

    # Token/cost totals
    total_input = sum(it.get("input_tokens", 0) for it in state.iterations)
    total_output = sum(it.get("output_tokens", 0) for it in state.iterations)
    total_cost = sum(it.get("cost_usd", 0.0) for it in state.iterations)
    total_tools = sum(it.get("tool_calls", 0) for it in state.iterations)

    text.append("\n")
    text.append("Tokens: ", style="dim")
    text.append(f"{_format_tokens(total_input)} in / {_format_tokens(total_output)} out", style="bold")
    text.append("  Cost: ", style="dim")
    text.append(f"${total_cost:.2f}", style="bold yellow")
    text.append("  Tools: ", style="dim")
    text.append(str(total_tools), style="bold cyan")

    return Panel(text, title="Ralph Loop", border_style="blue")


def build_task_progress_panel(state: RalphState, project_file: Path | None = None) -> Panel:
    """Show the task checklist from the project file.

    Reads the actual project file to show current task states.
    Completed tasks in green, pending in yellow.

    Args:
        state: Current Ralph state.
        project_file: Path to project file (falls back to state.project_file).

    Returns:
        Rich Panel with task checklist.
    """
    text = Text()

    file_path = project_file or (Path(state.project_file) if state.project_file else None)
    if not file_path or not file_path.exists():
        text.append("No project file found", style="dim")
        return Panel(text, title="Task Progress", border_style="green")

    content = file_path.read_text(encoding="utf-8")
    task_count = 0

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            task_count += 1
            task_text = stripped[5:].strip()
            text.append("● ", style="green")
            text.append(f"{task_text}\n", style="green")
        elif stripped.startswith("- [ ]"):
            task_count += 1
            task_text = stripped[5:].strip()
            text.append("○ ", style="yellow")
            text.append(f"{task_text}\n", style="yellow")

    if task_count == 0:
        text.append("No checklist items found", style="dim")

    return Panel(text, title="Task Progress", border_style="green")


def build_iteration_timeline(state: RalphState) -> Panel:
    """Build ASCII timeline proportional to iteration duration.

    Args:
        state: Current Ralph state.

    Returns:
        Rich Panel with timeline visualization.
    """
    text = Text()

    if not state.iterations:
        text.append("No iterations yet", style="dim")
        return Panel(text, title="Timeline", border_style="cyan")

    # Get durations
    durations: list[float] = []
    for it in state.iterations:
        d = float(it.get("duration_seconds", 0.0) or 0.0)
        durations.append(d)

    max_duration = max(durations) if durations else 1.0
    if max_duration == 0:
        max_duration = 1.0

    # Determine available width for bars (leave room for labels)
    max_bar_width = 40

    # Top line: bars
    bar_parts: list[str] = []
    for i, d in enumerate(durations):
        num = i + 1
        is_last = i == len(durations) - 1
        is_running = is_last and state.status == RalphStatus.ACTIVE

        bar_width = max(1, int((d / max_duration) * max_bar_width))

        bar_char = "▓" if is_running else "█"

        bar_parts.append(f"[{num}{bar_char * bar_width}]")

    text.append("".join(bar_parts), style="bold blue")
    text.append("\n")

    # Bottom line: durations
    dur_parts: list[str] = []
    for i, d in enumerate(durations):
        is_last = i == len(durations) - 1
        is_running = is_last and state.status == RalphStatus.ACTIVE
        if is_running:
            dur_parts.append(" running...")
        else:
            dur_parts.append(f" {_format_duration(d)}")

    text.append("  ".join(dur_parts), style="dim")

    return Panel(text, title="Timeline", border_style="cyan")


def build_iteration_table(state: RalphState, max_visible: int = 20) -> Panel:
    """Build per-iteration table.

    Columns: #, Duration, Tools, Tokens, Cost, Tasks (+N), Outcome

    Args:
        state: Current Ralph state.
        max_visible: Maximum number of rows to show.

    Returns:
        Rich Panel with iteration table.
    """
    table = Table(box=None, padding=(0, 1), expand=True)
    table.add_column("#", style="bold", width=4)
    table.add_column("Duration", width=8)
    table.add_column("Tools", width=6)
    table.add_column("Tokens", width=12)
    table.add_column("Cost", width=8)
    table.add_column("Tasks", width=8)
    table.add_column("Outcome", width=10)

    iterations = state.iterations
    if len(iterations) > max_visible:
        iterations = iterations[-max_visible:]

    for it in iterations:
        num = str(it.get("number", "?"))
        duration = it.get("duration_seconds")
        dur_str = _format_duration(float(duration)) if duration else "-"
        tools = str(it.get("tool_calls", 0))

        in_tok = _format_tokens(int(it.get("input_tokens", 0)))
        out_tok = _format_tokens(int(it.get("output_tokens", 0)))
        tokens = f"{in_tok}→{out_tok}"

        cost = it.get("cost_usd", 0.0)
        cost_str = f"${float(cost):.2f}" if cost else "-"

        # Calculate tasks completed in this iteration
        before_completed = _get_nested_int(it, "tasks_before", "completed")
        after_completed = _get_nested_int(it, "tasks_after", "completed")
        delta = after_completed - before_completed
        tasks_str = f"+{delta}" if delta > 0 else "0"

        # Determine outcome
        promise_found = it.get("promise_found", False)
        exit_code = it.get("exit_code", 0)
        if promise_found:
            outcome = "[green]promise[/]"
        elif exit_code != 0:
            outcome = f"[red]error({exit_code})[/]"
        else:
            outcome = "[dim]continued[/]"

        # Check if this is the running iteration (last one, active state, no ended_at)
        is_running = it == state.iterations[-1] and state.status == RalphStatus.ACTIVE and not it.get("ended_at")
        if is_running:
            dur_str = "-"
            cost_str = "-"
            outcome = "[yellow]running[/]"

        table.add_row(num, dur_str, tools, tokens, cost_str, tasks_str, outcome)

    return Panel(table, title="Iterations", border_style="yellow")


def build_ralph_display(
    state: RalphState | None,
    config: RalphMonitorConfig,
    project_file: Path | None = None,
) -> Group:
    """Assemble all Ralph monitor panels.

    Args:
        state: Current Ralph state (None if no state file).
        config: Monitor display configuration.
        project_file: Path to project file.

    Returns:
        Rich Group with all panels.
    """
    panels: list[Panel | Text] = []

    if state is None:
        text = Text()
        text.append("Waiting for Ralph Loop to start...\n", style="dim")
        text.append("Run ", style="dim")
        text.append("cctmux-ralph start <project-file>", style="bold cyan")
        text.append(" to begin.", style="dim")
        panels.append(Panel(text, title="Ralph Loop", border_style="dim"))
        return Group(*panels)

    # Always show status panel
    panels.append(build_ralph_status_panel(state))

    # Task progress panel
    if config.show_task_progress:
        panels.append(build_task_progress_panel(state, project_file))

    # Timeline
    if config.show_timeline and state.iterations:
        panels.append(build_iteration_timeline(state))

    # Iteration table
    if config.show_table:
        panels.append(build_iteration_table(state, config.max_iterations_visible))

    return Group(*panels)


def run_ralph_monitor(
    project_path: Path | None = None,
    poll_interval: float = 1.0,
    config: RalphMonitorConfig | None = None,
) -> None:
    """Rich Live polling loop for Ralph Loop state.

    Watches ralph-state.json and optionally the project file.

    Args:
        project_path: Project directory (defaults to cwd).
        poll_interval: How often to poll for changes.
        config: Display configuration.
    """
    console = Console()

    if config is None:
        config = RalphMonitorConfig()

    proj_path = (project_path or Path.cwd()).resolve()
    state_file = proj_path / ".claude" / "ralph-state.json"

    console.clear()
    console.print("[bold cyan]Ralph Monitor[/] - Watching for Ralph Loop state")
    console.print(f"[dim]Project: {compress_paths_in_text(str(proj_path))}[/]")
    console.print("[dim]Press Ctrl+C to exit[/]\n")

    last_mtime: float = 0.0
    last_project_mtime: float = 0.0

    def _get_project_file(state: RalphState | None) -> Path | None:
        """Resolve project file path from state."""
        if state and state.project_file:
            p = Path(state.project_file)
            if p.exists():
                return p
        return None

    try:
        # Initial load
        state = load_ralph_state(proj_path)
        project_file = _get_project_file(state)

        with Live(
            build_ralph_display(state, config, project_file),
            console=console,
            refresh_per_second=1,
        ) as live:
            while True:
                time.sleep(poll_interval)

                changed = False

                # Check state file for changes
                try:
                    if state_file.exists():
                        mtime = state_file.stat().st_mtime
                        if mtime != last_mtime:
                            last_mtime = mtime
                            state = load_ralph_state(proj_path)
                            project_file = _get_project_file(state)
                            changed = True
                except OSError:
                    pass

                # Check project file for changes
                if project_file:
                    try:
                        pf_mtime = project_file.stat().st_mtime
                        if pf_mtime != last_project_mtime:
                            last_project_mtime = pf_mtime
                            changed = True
                    except OSError:
                        pass

                if changed:
                    live.update(build_ralph_display(state, config, project_file))

    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")
