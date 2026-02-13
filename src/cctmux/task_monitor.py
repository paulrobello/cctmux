"""Real-time Claude Code task monitor with ASCII dependency visualization."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _empty_str_list() -> list[str]:
    return []


def _empty_str_dict() -> dict[str, Any]:
    return {}


@dataclass
class Task:
    """Represents a Claude Code task."""

    id: str
    subject: str
    description: str = ""
    active_form: str = ""
    status: str = "pending"
    blocks: list[str] = field(default_factory=_empty_str_list)
    blocked_by: list[str] = field(default_factory=_empty_str_list)
    owner: str = ""
    metadata: dict[str, Any] = field(default_factory=_empty_str_dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Task:
        """Create Task from JSON data."""
        return cls(
            id=str(data.get("id", "")),
            subject=str(data.get("subject", "")),
            description=str(data.get("description", "")),
            active_form=str(data.get("activeForm", "")),
            status=str(data.get("status", "pending")),
            blocks=[str(b) for b in data.get("blocks", [])],
            blocked_by=[str(b) for b in data.get("blockedBy", [])],
            owner=str(data.get("owner", "")),
            metadata=dict(data.get("metadata", {})),
        )

    @property
    def status_symbol(self) -> str:
        """Get status symbol for display."""
        symbols = {
            "pending": "○",
            "in_progress": "◐",
            "completed": "●",
        }
        return symbols.get(self.status, "?")

    @property
    def status_color(self) -> str:
        """Get color for status."""
        colors = {
            "pending": "dim white",
            "in_progress": "yellow",
            "completed": "green",
        }
        return colors.get(self.status, "white")


@dataclass
class SessionInfo:
    """Information about a Claude Code session."""

    session_id: str
    project_path: str
    summary: str
    modified: datetime
    task_path: Path | None = None

    @classmethod
    def from_index_entry(cls, entry: dict[str, Any], tasks_root: Path) -> SessionInfo:
        """Create SessionInfo from sessions-index.json entry."""
        session_id = str(entry.get("sessionId", ""))
        modified_str = str(entry.get("modified", ""))

        # Parse ISO datetime
        try:
            modified = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
        except ValueError:
            modified = datetime.min

        # Check if task folder exists
        task_path = tasks_root / session_id
        if not task_path.exists() or not any(task_path.glob("*.json")):
            task_path = None

        return cls(
            session_id=session_id,
            project_path=str(entry.get("projectPath", "")),
            summary=str(entry.get("summary", "")),
            modified=modified,
            task_path=task_path,
        )


def encode_project_path(project_path: Path) -> str:
    """Encode project path to Claude's folder naming convention.

    Claude Code encodes paths by replacing / with - and removing the leading slash.
    Example: /Users/foo/project -> -Users-foo-project
    """
    return str(project_path.resolve()).replace("/", "-")


def find_project_sessions(project_path: Path) -> list[SessionInfo]:
    """Find all Claude Code sessions for a project.

    Args:
        project_path: Path to the project directory.

    Returns:
        List of SessionInfo sorted by modified time (most recent first).
    """
    claude_projects = Path.home() / ".claude" / "projects"
    tasks_root = Path.home() / ".claude" / "tasks"

    if not claude_projects.exists():
        return []

    # Find the project folder
    encoded = encode_project_path(project_path)
    project_folder = claude_projects / encoded

    if not project_folder.exists():
        return []

    # Read sessions-index.json
    index_file = project_folder / "sessions-index.json"
    if not index_file.exists():
        return []

    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
    except (json.JSONDecodeError, OSError):
        return []

    # Convert to SessionInfo objects
    sessions = [SessionInfo.from_index_entry(entry, tasks_root) for entry in entries]

    # Sort by modified time, most recent first
    return sorted(sessions, key=lambda s: s.modified, reverse=True)


def find_project_task_sessions(project_path: Path) -> list[SessionInfo]:
    """Find Claude Code sessions for a project that have tasks.

    Args:
        project_path: Path to the project directory.

    Returns:
        List of SessionInfo with tasks, sorted by modified time (most recent first).
    """
    sessions = find_project_sessions(project_path)
    return [s for s in sessions if s.task_path is not None]


def load_tasks_from_dir(tasks_dir: Path) -> list[Task]:
    """Load all tasks from a session directory."""
    tasks: list[Task] = []

    if not tasks_dir.exists():
        return tasks

    for json_file in tasks_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            tasks.append(Task.from_json(data))
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by ID (numeric first, then alphabetic)
    def sort_key(task: Task) -> tuple[int, str]:
        try:
            return (0, str(int(task.id)).zfill(10))
        except ValueError:
            return (1, task.id)

    return sorted(tasks, key=sort_key)


def find_session_dirs() -> list[tuple[str, Path]]:
    """Find all session directories with tasks."""
    tasks_root = Path.home() / ".claude" / "tasks"
    if not tasks_root.exists():
        return []

    sessions: list[tuple[str, Path]] = []
    for item in tasks_root.iterdir():
        if item.is_dir() and any(item.glob("*.json")):
            sessions.append((item.name, item))

    return sorted(sessions, key=lambda x: x[0])


@dataclass
class TaskWindow:
    """Represents a windowed view of tasks for virtual scrolling."""

    tasks: list[Task]
    start_index: int
    end_index: int
    total_count: int
    active_index: int | None

    @property
    def has_tasks_above(self) -> bool:
        """Check if there are tasks above the visible window."""
        return self.start_index > 0

    @property
    def has_tasks_below(self) -> bool:
        """Check if there are tasks below the visible window."""
        return self.end_index < self.total_count

    @property
    def tasks_above_count(self) -> int:
        """Number of tasks above the visible window."""
        return self.start_index

    @property
    def tasks_below_count(self) -> int:
        """Number of tasks below the visible window."""
        return self.total_count - self.end_index


def calculate_task_window(
    tasks: list[Task],
    max_visible: int = 15,
) -> TaskWindow:
    """Calculate a window of tasks with active task near the top.

    Args:
        tasks: All tasks to display.
        max_visible: Maximum number of tasks to show in the window.

    Returns:
        TaskWindow with the visible subset of tasks.
    """
    total = len(tasks)

    if total <= max_visible:
        # All tasks fit, no windowing needed
        return TaskWindow(
            tasks=tasks,
            start_index=0,
            end_index=total,
            total_count=total,
            active_index=next((i for i, t in enumerate(tasks) if t.status == "in_progress"), None),
        )

    # Find the first in_progress task
    active_index: int | None = None
    for i, task in enumerate(tasks):
        if task.status == "in_progress":
            active_index = i
            break

    # If no in_progress, find the first pending task
    if active_index is None:
        for i, task in enumerate(tasks):
            if task.status == "pending":
                active_index = i
                break

    # If still none, use the first task
    if active_index is None:
        active_index = 0

    # Keep active task near the top (show 2-3 tasks above it for context)
    context_above = 2
    start = max(0, active_index - context_above)
    end = min(total, start + max_visible)

    # Adjust start if we hit the end
    if end == total:
        start = max(0, total - max_visible)

    return TaskWindow(
        tasks=tasks[start:end],
        start_index=start,
        end_index=end,
        total_count=total,
        active_index=active_index - start if start <= active_index < end else None,
    )


def get_terminal_size() -> tuple[int, int]:
    """Get terminal width and height."""
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except (AttributeError, ValueError):
        return 80, 24  # Fallback


def get_visible_task_count(show_table: bool = True) -> int:
    """Calculate how many tasks can fit in the terminal.

    Args:
        show_table: Whether the table panel is shown.

    Returns:
        Maximum number of tasks to display.
    """
    _, terminal_height = get_terminal_size()

    # Reserve space for:
    # - Stats panel (3 lines with borders)
    # - Dependency graph panel borders + title/subtitle (4)
    # - "N more above/below" indicators (2)
    # - Footer/exit message (2)
    reserved = 11

    if show_table:
        # Table panel borders and header (4)
        reserved += 4

    available = terminal_height - reserved

    if show_table:
        # Split between graph and table
        return max(5, available // 2)
    else:
        # All space for graph
        return max(5, available)


def resolve_task_path(
    session_or_path: str | None = None,
    project_path: Path | None = None,
) -> tuple[Path | None, str]:
    """Resolve the task directory to monitor.

    Args:
        session_or_path: Session ID, partial session ID, or direct path to task folder.
        project_path: Project directory to find sessions for.

    Returns:
        Tuple of (task_path, display_name) or (None, error_message).
    """
    tasks_root = Path.home() / ".claude" / "tasks"

    # Case 0: Check CLAUDE_CODE_TASK_LIST_ID environment variable first
    # (only if no explicit session_or_path provided)
    if session_or_path is None:
        env_task_id = os.environ.get("CLAUDE_CODE_TASK_LIST_ID")
        if env_task_id:
            env_task_path = tasks_root / env_task_id
            if env_task_path.exists() and any(env_task_path.glob("*.json")):
                return env_task_path, f"{env_task_id} (from env)"

    # Case 1: Direct path provided
    if session_or_path:
        path = Path(session_or_path)

        # Check if it's an absolute path that exists
        if path.is_absolute() and path.exists() and path.is_dir():
            return path, path.name

        # Check if it's a relative path from cwd
        if not path.is_absolute():
            cwd_path = Path.cwd() / path
            if cwd_path.exists() and cwd_path.is_dir():
                return cwd_path, cwd_path.name

        # Try as session ID in tasks root
        session_path = tasks_root / session_or_path
        if session_path.exists() and any(session_path.glob("*.json")):
            return session_path, session_or_path

        # Try partial match on session ID
        if tasks_root.exists():
            for item in tasks_root.iterdir():
                if item.is_dir() and session_or_path in item.name and any(item.glob("*.json")):
                    return item, item.name

        return None, f"No task folder found for: {session_or_path}"

    # Case 2: Project path provided, find most recent session with tasks
    if project_path:
        sessions = find_project_task_sessions(project_path)
        if sessions:
            session = sessions[0]
            if session.task_path:
                display = f"{session.session_id[:8]}... ({session.summary[:30]})"
                return session.task_path, display
        return None, f"No sessions with tasks found for project: {project_path}"

    # Case 3: Try current directory as project
    cwd = Path.cwd()
    sessions = find_project_task_sessions(cwd)
    if sessions:
        session = sessions[0]
        if session.task_path:
            display = f"{session.session_id[:8]}... ({session.summary[:30]})"
            return session.task_path, display

    # Case 4: Check for task folder matching project directory name
    # This handles custom-named task folders like "par-term" or "partower"
    project_name = cwd.name
    custom_task_folder = tasks_root / project_name
    if custom_task_folder.exists() and any(custom_task_folder.glob("*.json")):
        return custom_task_folder, project_name

    # Case 5: No project context - fall back to most recently modified session
    # Only do this if we're not in a recognizable project directory
    # (i.e., if there's no .git folder and no Claude project folder for cwd)
    claude_projects = Path.home() / ".claude" / "projects"
    encoded_cwd = encode_project_path(cwd)
    is_known_project = (cwd / ".git").exists() or (claude_projects / encoded_cwd).exists()

    if not is_known_project and tasks_root.exists():
        best_session: tuple[Path, float] | None = None
        for item in tasks_root.iterdir():
            if item.is_dir():
                json_files = list(item.glob("*.json"))
                if json_files:
                    # Get most recent file mtime
                    try:
                        max_mtime = max(f.stat().st_mtime for f in json_files)
                        if best_session is None or max_mtime > best_session[1]:
                            best_session = (item, max_mtime)
                    except OSError:
                        continue

        if best_session:
            return best_session[0], best_session[0].name

    # If we're in a known project but found no tasks, be explicit
    if is_known_project:
        return None, f"No task sessions found for project: {cwd.name}"

    return None, "No task sessions found"


def build_dependency_graph(
    tasks: list[Task],
    max_width: int | None = None,
    max_indent_depth: int = 6,
) -> Text:
    """Build an ASCII representation of the task dependency graph.

    Args:
        tasks: List of tasks to display.
        max_width: Maximum width in characters. If None, uses terminal width.
        max_indent_depth: Maximum indentation depth (prevents deep nesting from
            eating all horizontal space).

    Returns:
        Rich Text object with the dependency graph.
    """
    if not tasks:
        return Text("No tasks found", style="dim")

    # Get terminal width if not specified
    if max_width is None:
        term_width, _ = get_terminal_size()
        max_width = term_width - 4  # Account for panel borders

    task_map = {t.id: t for t in tasks}
    result = Text()

    # Find root tasks (no blockedBy) and build levels
    levels: dict[str, int] = {}
    visited: set[str] = set()

    def assign_level(task_id: str, level: int) -> None:
        if task_id in visited:
            levels[task_id] = max(levels.get(task_id, 0), level)
            return
        visited.add(task_id)
        levels[task_id] = level
        task = task_map.get(task_id)
        if task:
            for blocked_id in task.blocks:
                if blocked_id in task_map:
                    assign_level(blocked_id, level + 1)

    # Assign levels from roots
    roots = [t for t in tasks if not t.blocked_by]
    for root in roots:
        assign_level(root.id, 0)

    # Handle orphaned tasks
    for task in tasks:
        if task.id not in levels:
            levels[task.id] = 0

    # Group by level
    level_groups: dict[int, list[Task]] = {}
    for task_id, level in levels.items():
        level_groups.setdefault(level, []).append(task_map[task_id])

    max_level = max(level_groups.keys()) if level_groups else 0

    for level in range(max_level + 1):
        tasks_at_level = level_groups.get(level, [])

        for task in tasks_at_level:
            # Cap indentation depth to preserve label space
            display_level = min(level, max_indent_depth)
            indent = "  " * display_level

            # Show overflow indicator if we hit max depth
            overflow_marker = "» " if level > max_indent_depth else ""

            # Connection from parent
            if task.blocked_by:
                result.append(f"{indent}└─ {overflow_marker}", style="dim cyan")
            elif level > 0:
                result.append(f"{indent}   {overflow_marker}", style="dim cyan" if overflow_marker else None)
            else:
                result.append(indent)

            # Status symbol and ID
            result.append(f"{task.status_symbol} ", style=task.status_color)
            result.append(f"[{task.id}] ", style="bold cyan")

            # Calculate remaining space for subject
            prefix_len = (
                len(indent) + len(overflow_marker) + 3 + 2 + len(task.id) + 3
            )  # indent + connector + symbol + [id]
            max_subject = max(20, max_width - prefix_len - 5)  # Reserve some space, min 20 chars

            subject = task.subject[:max_subject] + "..." if len(task.subject) > max_subject else task.subject
            result.append(subject, style=task.status_color)

            # Active form for in-progress
            if task.status == "in_progress" and task.active_form:
                remaining = max_width - prefix_len - len(subject) - 5
                if remaining > 10:
                    active_display = (
                        task.active_form[:remaining] + "..." if len(task.active_form) > remaining else task.active_form
                    )
                    result.append(f" ({active_display})", style="dim yellow")

            # Owner
            if task.owner:
                result.append(f" @{task.owner}", style="dim magenta")

            result.append("\n")

    return result


def _format_acceptance_criteria(metadata: dict[str, Any], max_items: int = 3) -> list[str]:
    """Format acceptance criteria from task metadata.

    Args:
        metadata: Task metadata dictionary.
        max_items: Maximum number of criteria to show.

    Returns:
        List of formatted strings for display.
    """
    result: list[str] = []
    criteria_raw = metadata.get("acceptance_criteria")
    if not criteria_raw:
        return result

    # Convert to list explicitly for type checker
    criteria_list: list[dict[str, Any] | str] = []
    try:
        for item in criteria_raw:  # type: ignore[union-attr]
            criteria_list.append(item)
    except TypeError:
        return result

    for item in criteria_list[:max_items]:
        marker = "☐"
        text = ""
        if isinstance(item, dict):
            done_val = item.get("done", False)
            marker = "☑" if done_val else "☐"
            text_val = item.get("text", "")
            text = str(text_val if text_val else item)[:50]
        else:
            text = str(item)[:50]
        result.append(f"  {marker} {text}")

    return result


def _format_work_log(metadata: dict[str, Any], max_entries: int = 3) -> list[str]:
    """Format work log entries from task metadata.

    Work log entries are expected to be in format:
    - List of strings (simple entries)
    - List of dicts with 'timestamp', 'action', and optional 'details' keys

    Args:
        metadata: Task metadata dictionary.
        max_entries: Maximum number of log entries to show.

    Returns:
        List of formatted strings for display.
    """
    result: list[str] = []
    work_log_raw = metadata.get("work_log")
    if not work_log_raw:
        return result

    # Convert to list explicitly for type checker
    log_list: list[dict[str, Any] | str] = []
    try:
        for item in work_log_raw:  # type: ignore[union-attr]
            log_list.append(item)
    except TypeError:
        return result

    # Show most recent entries first (reverse order)
    for item in reversed(log_list[-max_entries:]):
        if isinstance(item, dict):
            timestamp = str(item.get("timestamp", ""))[:16]  # Trim to HH:MM
            action = str(item.get("action", ""))[:40]
            if timestamp:
                result.append(f"  [{timestamp}] {action}")
            else:
                result.append(f"  • {action}")
        else:
            result.append(f"  • {str(item)[:50]}")

    return result


def get_acceptance_completion(metadata: dict[str, Any]) -> tuple[int, int]:
    """Calculate acceptance criteria completion.

    Args:
        metadata: Task metadata dictionary.

    Returns:
        Tuple of (completed_count, total_count).
    """
    criteria_raw = metadata.get("acceptance_criteria")
    if not criteria_raw:
        return (0, 0)

    completed = 0
    total = 0

    try:
        for item in criteria_raw:  # type: ignore[union-attr]
            total += 1
            if isinstance(item, dict) and item.get("done", False):  # type: ignore[union-attr]
                completed += 1
    except TypeError:
        return (0, 0)

    return (completed, total)


def build_task_table(
    tasks: list[Task],
    show_owner: bool = True,
    show_metadata: bool = False,
    show_description: bool = True,
    show_acceptance: bool = False,
    show_work_log: bool = False,
) -> Table:
    """Build a task table.

    Args:
        tasks: List of tasks to display.
        show_owner: Whether to show the owner column.
        show_metadata: Whether to show custom metadata.
        show_description: Whether to show task descriptions.
        show_acceptance: Whether to show acceptance criteria from metadata.
        show_work_log: Whether to show work log entries from metadata.

    Returns:
        Rich Table with task information.
    """
    table = Table(show_header=True, header_style="bold magenta", border_style="dim", expand=True)

    table.add_column("", width=2)
    table.add_column("ID", width=4, style="cyan")
    table.add_column("Subject", ratio=2)
    table.add_column("Status", width=11)
    if show_owner:
        table.add_column("Owner", width=12)
    table.add_column("Blocked By", width=12)
    table.add_column("Blocks", width=12)

    for task in tasks:
        blocked_by = ",".join(task.blocked_by) if task.blocked_by else "-"
        blocks = ",".join(task.blocks) if task.blocks else "-"

        # Build subject with optional description and completion percentage
        subject_display = task.subject[:40] + "..." if len(task.subject) > 40 else task.subject

        # Add acceptance criteria completion indicator if present
        completed, total = get_acceptance_completion(task.metadata)
        if total > 0:
            pct = int((completed / total) * 100)
            subject_display = f"{subject_display} [{completed}/{total} {pct}%]"

        if show_description and task.description:
            desc_preview = task.description[:30].replace("\n", " ")
            if len(task.description) > 30:
                desc_preview += "..."
            subject_display = f"{subject_display}\n[dim]{desc_preview}[/]"

        # Build row based on which columns are enabled
        row_data: list[str | Text] = [
            Text(task.status_symbol, style=task.status_color),
            task.id,
            subject_display,
            Text(task.status, style=task.status_color),
        ]

        if show_owner:
            owner_display = task.owner if task.owner else "-"
            row_data.append(Text(owner_display, style="magenta" if task.owner else "dim"))

        row_data.extend([blocked_by, blocks])

        table.add_row(*row_data)

        # Show metadata if requested (exclude internal keys)
        if show_metadata and task.metadata:
            internal_keys = {"acceptance_criteria", "work_log"}
            metadata_str = "  ".join(f"{k}={v}" for k, v in task.metadata.items() if k not in internal_keys)
            if metadata_str:
                table.add_row("", "", Text(f"  [metadata: {metadata_str[:60]}]", style="dim"), "", "", "")

        # Show acceptance criteria if requested
        if show_acceptance:
            criteria_display = _format_acceptance_criteria(task.metadata, 3)
            for line in criteria_display:
                if show_owner:
                    table.add_row("", "", Text(line, style="dim cyan"), "", "", "", "")
                else:
                    table.add_row("", "", Text(line, style="dim cyan"), "", "", "")

        # Show work log if requested
        if show_work_log:
            log_display = _format_work_log(task.metadata, 3)
            for line in log_display:
                if show_owner:
                    table.add_row("", "", Text(line, style="dim yellow"), "", "", "", "")
                else:
                    table.add_row("", "", Text(line, style="dim yellow"), "", "", "")

    return table


def build_stats(tasks: list[Task], session_name: str, window: TaskWindow | None = None) -> Text:
    """Build statistics line.

    Args:
        tasks: All tasks (for total counts).
        session_name: Session display name.
        window: Optional TaskWindow for showing window info.

    Returns:
        Rich Text with stats.
    """
    total = len(tasks)
    pending = sum(1 for t in tasks if t.status == "pending")
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    completed = sum(1 for t in tasks if t.status == "completed")

    text = Text()
    text.append("Session: ", style="dim")
    text.append(f"{session_name}  ", style="bold cyan")
    text.append(f"Total: {total}  ", style="bold")
    text.append(f"○ {pending}  ", style="dim white")
    text.append(f"◐ {in_progress}  ", style="yellow")
    text.append(f"● {completed}", style="green")

    if total > 0:
        pct = (completed / total) * 100
        text.append(f"  [{pct:.0f}% complete]", style="dim")

    # Show window info if windowed
    if window and (window.has_tasks_above or window.has_tasks_below):
        text.append(f"  (showing {len(window.tasks)} of {window.total_count})", style="dim")

    return text


def build_windowed_graph(window: TaskWindow, max_width: int | None = None) -> Text:
    """Build dependency graph with window indicators.

    Args:
        window: TaskWindow with visible tasks.
        max_width: Maximum width in characters.

    Returns:
        Rich Text with graph and indicators.
    """
    result = Text()

    # Show "N more above" indicator
    if window.has_tasks_above:
        result.append(f"  ▲ {window.tasks_above_count} more task(s) above\n", style="dim yellow")

    # Build graph for visible tasks
    graph = build_dependency_graph(window.tasks, max_width=max_width)
    result.append(graph)

    # Show "N more below" indicator
    if window.has_tasks_below:
        result.append(f"  ▼ {window.tasks_below_count} more task(s) below", style="dim yellow")

    return result


def build_display(
    tasks: list[Task],
    session_name: str,
    show_table: bool = True,
    show_graph: bool = True,
    max_visible: int | None = None,
    show_owner: bool = True,
    show_metadata: bool = False,
    show_description: bool = True,
    show_acceptance: bool = False,
    show_work_log: bool = False,
) -> Group:
    """Build the complete display with optional windowing.

    Args:
        tasks: All tasks to display.
        session_name: Session display name.
        show_table: Whether to show the task table.
        show_graph: Whether to show the dependency graph.
        max_visible: Maximum tasks to show (None for auto-detect).
        show_owner: Whether to show the owner column.
        show_metadata: Whether to show custom metadata.
        show_description: Whether to show task descriptions.
        show_acceptance: Whether to show acceptance criteria from metadata.
        show_work_log: Whether to show work log entries from metadata.

    Returns:
        Rich Group with all display components.
    """
    # Calculate visible count if not specified
    if max_visible is None:
        max_visible = get_visible_task_count(show_table)

    # Calculate window
    window = calculate_task_window(tasks, max_visible)

    components = [
        Panel(build_stats(tasks, session_name, window), border_style="blue"),
    ]

    if show_graph:
        components.append(
            Panel(
                build_windowed_graph(window),
                title="Dependency Graph",
                subtitle="○ pending  ◐ in progress  ● completed",
                border_style="cyan",
            )
        )

    if show_table:
        components.append(
            Panel(
                build_task_table(
                    window.tasks,
                    show_owner=show_owner,
                    show_metadata=show_metadata,
                    show_description=show_description,
                    show_acceptance=show_acceptance,
                    show_work_log=show_work_log,
                ),
                title="Task List",
                border_style="green",
            )
        )

    return Group(*components)


def list_sessions(project_path: Path | None = None) -> None:
    """List available task sessions.

    Args:
        project_path: Optional project path to filter sessions.
    """
    console = Console()

    if project_path:
        # Show sessions for specific project
        sessions = find_project_task_sessions(project_path)

        # Also show all task folders (since custom names don't match session IDs)
        all_task_folders = find_session_dirs()

        if not sessions and not all_task_folders:
            console.print(f"[yellow]No sessions with tasks found for project: {project_path}[/]")
            return

        if sessions:
            console.print(f"[bold]Sessions for project: {project_path}[/]\n")
            for session in sessions:
                task_count = len(list(session.task_path.glob("*.json"))) if session.task_path else 0
                console.print(f"  [cyan]{session.session_id[:12]}...[/]")
                console.print(f"    Summary: {session.summary[:50]}")
                console.print(f"    Modified: {session.modified.strftime('%Y-%m-%d %H:%M')}")
                console.print(f"    Tasks: {task_count}")
                console.print()

        # Show other task folders that might be relevant
        session_ids = {s.session_id for s in sessions}
        other_folders = [(name, path) for name, path in all_task_folders if name not in session_ids]
        if other_folders:
            console.print("[bold]Other task folders (custom names):[/]\n")
            for name, path in other_folders:
                task_count = len(list(path.glob("*.json")))
                console.print(f"  [cyan]{name}[/] ({task_count} tasks)")
    else:
        # Show all sessions with tasks
        sessions = find_session_dirs()
        if not sessions:
            console.print("[yellow]No task sessions found.[/]")
            return

        console.print("[bold]Available task sessions:[/]\n")
        for name, path in sessions:
            task_count = len(list(path.glob("*.json")))
            console.print(f"  [cyan]{name}[/] ({task_count} tasks)")


def _find_most_recent_task_folder(
    tasks_root: Path,
    project_path: Path | None = None,
) -> tuple[Path, float] | None:
    """Find the most recently modified task folder.

    Args:
        tasks_root: Root path for task folders (~/.claude/tasks/).
        project_path: If provided, only consider sessions for this project.

    Returns:
        Tuple of (path, mtime) or None if no task folders found.
    """
    if not tasks_root.exists():
        return None

    # If project_path provided, get valid session IDs for that project
    # Also include custom-named folder matching project directory name
    valid_folder_names: set[str] | None = None
    if project_path:
        sessions = find_project_sessions(project_path)
        valid_folder_names = {s.session_id for s in sessions}
        # Also allow custom-named folder matching project name
        valid_folder_names.add(project_path.name)

    best: tuple[Path, float] | None = None
    for item in tasks_root.iterdir():
        if not item.is_dir():
            continue

        # If filtering by project, check if this folder belongs to it
        if valid_folder_names is not None and item.name not in valid_folder_names:
            continue

        json_files = list(item.glob("*.json"))
        if not json_files:
            continue

        # Get most recent file mtime in this folder
        try:
            max_mtime = max(f.stat().st_mtime for f in json_files)
            if best is None or max_mtime > best[1]:
                best = (item, max_mtime)
        except OSError:
            continue

    return best


def _build_waiting_display(project_name: str) -> Panel:
    """Build a display panel for when waiting for tasks."""
    text = Text()
    text.append("Waiting for tasks...\n\n", style="yellow")
    text.append(f"Project: {project_name}\n", style="dim")
    text.append("Tasks will appear when Claude creates them.", style="dim")
    return Panel(text, title="Task Monitor", border_style="yellow")


def run_monitor(
    session_or_path: str | None = None,
    project_path: Path | None = None,
    poll_interval: float = 1.0,
    show_table: bool = True,
    show_graph: bool = True,
    max_visible: int | None = None,
    show_owner: bool = True,
    show_metadata: bool = False,
    show_description: bool = True,
    show_acceptance: bool = False,
    show_work_log: bool = False,
) -> None:
    """Run the task monitor with Rich Live.

    Args:
        session_or_path: Session ID, partial ID, or direct path to task folder.
        project_path: Project directory to find sessions for (uses current dir if None).
        poll_interval: How often to poll for changes (seconds).
        show_table: Whether to show the task table in addition to the graph.
        show_graph: Whether to show the dependency graph.
        max_visible: Maximum tasks to display (None for auto-detect based on terminal size).
        show_owner: Whether to show the owner column.
        show_metadata: Whether to show custom metadata.
        show_description: Whether to show task descriptions.
        show_acceptance: Whether to show acceptance criteria from metadata.
        show_work_log: Whether to show work log from metadata.
    """
    console = Console()
    tasks_root = Path.home() / ".claude" / "tasks"
    effective_project = project_path if project_path else Path.cwd()

    # Resolve the task path (may be None if no tasks exist yet)
    task_path, display_name = resolve_task_path(session_or_path, project_path)

    # Determine if we should auto-follow new sessions
    # Only auto-follow if no explicit session/path was provided
    auto_follow = session_or_path is None
    current_task_folder: Path | None = task_path

    # Track whether we're in "waiting" mode (no tasks found yet)
    waiting_for_tasks = task_path is None

    console.clear()

    last_mtimes: dict[Path, float] = {}
    last_session_check = 0.0
    session_check_interval = 2.0  # Check for new sessions every 2 seconds

    def check_for_changes() -> bool:
        """Check if any task files changed."""
        nonlocal last_mtimes
        if current_task_folder is None:
            return False

        current_mtimes: dict[Path, float] = {}
        changed = False

        for json_file in current_task_folder.glob("*.json"):
            try:
                mtime = json_file.stat().st_mtime
                current_mtimes[json_file] = mtime
                if json_file not in last_mtimes or last_mtimes[json_file] != mtime:
                    changed = True
            except OSError:
                continue

        # Check for deleted files
        if set(last_mtimes.keys()) - set(current_mtimes.keys()):
            changed = True

        last_mtimes = current_mtimes
        return changed

    def check_for_new_session() -> Path | None:
        """Check if a new session with tasks appeared."""
        nonlocal last_session_check
        current_time = time.time()

        # Only check periodically
        if current_time - last_session_check < session_check_interval:
            return None
        last_session_check = current_time

        result = _find_most_recent_task_folder(tasks_root, effective_project)
        if result is None:
            return None

        newest_folder, _ = result
        if newest_folder != current_task_folder:
            return newest_folder
        return None

    def make_display(tasks: list[Task], display_name: str) -> Group:
        """Build display with current configuration settings."""
        return build_display(
            tasks,
            display_name,
            show_table=show_table,
            show_graph=show_graph,
            max_visible=max_visible,
            show_owner=show_owner,
            show_metadata=show_metadata,
            show_description=show_description,
            show_acceptance=show_acceptance,
            show_work_log=show_work_log,
        )

    try:
        # Initial display
        if waiting_for_tasks:
            initial_display = _build_waiting_display(effective_project.name)
            tasks: list[Task] = []
        else:
            assert current_task_folder is not None
            tasks = load_tasks_from_dir(current_task_folder)
            initial_display = make_display(tasks, display_name)

        with Live(
            initial_display,
            console=console,
            refresh_per_second=1,
        ) as live:
            while True:
                time.sleep(poll_interval)

                # Check for new session (or first session if waiting)
                if auto_follow or waiting_for_tasks:
                    new_session = check_for_new_session()
                    if new_session:
                        current_task_folder = new_session
                        last_mtimes = {}  # Reset mtime tracking
                        display_name = new_session.name
                        waiting_for_tasks = False
                        tasks = load_tasks_from_dir(current_task_folder)
                        live.update(make_display(tasks, display_name))
                        continue

                # If still waiting, keep showing waiting display
                if waiting_for_tasks:
                    continue

                if check_for_changes():
                    assert current_task_folder is not None
                    tasks = load_tasks_from_dir(current_task_folder)
                    live.update(make_display(tasks, display_name))

    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")
