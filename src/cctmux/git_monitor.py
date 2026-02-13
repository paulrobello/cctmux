"""Git monitor data models and parsing functions.

Provides dataclasses and parsers for git status, diff stats, and log output,
plus subprocess-based data collection.
"""

import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class FileStatus(StrEnum):
    """Git file status categories."""

    STAGED_ADDED = "staged_added"
    STAGED_MODIFIED = "staged_modified"
    STAGED_DELETED = "staged_deleted"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNTRACKED = "untracked"
    RENAMED = "renamed"
    COPIED = "copied"
    STAGED_RENAMED = "staged_renamed"
    STAGED_COPIED = "staged_copied"


@dataclass
class FileChange:
    """A changed file in the working tree."""

    path: str
    status: FileStatus
    original_path: str = ""


@dataclass
class CommitInfo:
    """A recent commit."""

    short_hash: str
    relative_time: str
    message: str
    author: str


@dataclass
class DiffStat:
    """Diff statistics for a file."""

    path: str
    insertions: int
    deletions: int


@dataclass
class GitStatus:
    """Complete git repository status."""

    branch: str = ""
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    files: list[FileChange] = field(default_factory=list[FileChange])
    stash_count: int = 0
    commits: list[CommitInfo] = field(default_factory=list[CommitInfo])
    staged_diff: list[DiffStat] = field(default_factory=list[DiffStat])
    unstaged_diff: list[DiffStat] = field(default_factory=list[DiffStat])
    last_commit_hash: str = ""
    last_commit_message: str = ""
    last_commit_author: str = ""
    last_commit_time: str = ""


# Mapping from git porcelain status chars to FileStatus for staged changes (X position)
_STAGED_STATUS_MAP: dict[str, FileStatus] = {
    "A": FileStatus.STAGED_ADDED,
    "M": FileStatus.STAGED_MODIFIED,
    "D": FileStatus.STAGED_DELETED,
}

# Mapping from git porcelain status chars to FileStatus for unstaged changes (Y position)
_UNSTAGED_STATUS_MAP: dict[str, FileStatus] = {
    "M": FileStatus.MODIFIED,
    "D": FileStatus.DELETED,
}


def parse_porcelain_status(output: str) -> GitStatus:
    """Parse git status --porcelain=v2 --branch output.

    Args:
        output: Raw output from git status --porcelain=v2 --branch.

    Returns:
        GitStatus with branch info and file changes populated.
    """
    status = GitStatus()

    for line in output.splitlines():
        if not line:
            continue

        if line.startswith("# branch.head "):
            status.branch = line[len("# branch.head ") :]

        elif line.startswith("# branch.upstream "):
            status.upstream = line[len("# branch.upstream ") :]

        elif line.startswith("# branch.ab "):
            # Format: # branch.ab +N -M
            parts = line[len("# branch.ab ") :].split()
            if len(parts) >= 2:
                status.ahead = int(parts[0].lstrip("+"))
                status.behind = abs(int(parts[1]))

        elif line.startswith("1 "):
            # Ordinary changed entry
            # Format: 1 XY sub mH mI mW hH hI path
            parts = line.split(" ", 8)
            if len(parts) < 9:
                continue
            xy = parts[1]
            path = parts[8]
            x_status = xy[0]  # Staged status
            y_status = xy[1]  # Unstaged status

            # A file can have both staged and unstaged changes
            if x_status != ".":
                staged = _STAGED_STATUS_MAP.get(x_status)
                if staged is not None:
                    status.files.append(FileChange(path=path, status=staged))

            if y_status != ".":
                unstaged = _UNSTAGED_STATUS_MAP.get(y_status)
                if unstaged is not None:
                    status.files.append(FileChange(path=path, status=unstaged))

        elif line.startswith("2 "):
            # Renamed or copied entry
            # Format: 2 XY sub mH mI mW hH hI Xscore path\toriginal_path
            parts = line.split(" ", 9)
            if len(parts) < 10:
                continue
            xy = parts[1]
            x_status = xy[0]
            y_status = xy[1]
            # The last field contains path\toriginal_path
            path_field = parts[9]
            tab_parts = path_field.split("\t", 1)
            new_path = tab_parts[0]
            original_path = tab_parts[1] if len(tab_parts) > 1 else ""

            if x_status == "R":
                file_status = FileStatus.STAGED_RENAMED if y_status == "." else FileStatus.RENAMED
            elif x_status == "C":
                file_status = FileStatus.STAGED_COPIED if y_status == "." else FileStatus.COPIED
            else:
                # Fallback for unstaged rename/copy
                if y_status == "R":
                    file_status = FileStatus.RENAMED
                elif y_status == "C":
                    file_status = FileStatus.COPIED
                else:
                    continue

            status.files.append(
                FileChange(
                    path=new_path,
                    status=file_status,
                    original_path=original_path,
                )
            )

        elif line.startswith("? "):
            # Untracked file
            path = line[2:]
            status.files.append(FileChange(path=path, status=FileStatus.UNTRACKED))

        # Skip ignored files (lines starting with !)

    return status


# Pattern for diff stat file lines: path | number +++---
_DIFF_STAT_PATTERN = re.compile(r"^\s*(.+?)\s*\|\s*(\d+)\s*(\+*)(-*)")
_DIFF_STAT_BINARY_PATTERN = re.compile(r"^\s*(.+?)\s*\|\s*Bin")
_DIFF_STAT_SUMMARY_PATTERN = re.compile(r"files?\s+changed")


def parse_diff_stat(output: str) -> list[DiffStat]:
    """Parse git diff --stat output.

    Args:
        output: Raw output from git diff --stat.

    Returns:
        List of DiffStat entries, one per changed file.
    """
    stats: list[DiffStat] = []

    for line in output.splitlines():
        if not line.strip():
            continue

        # Skip summary line (e.g., "2 files changed, 4 insertions(+), 4 deletions(-)")
        if _DIFF_STAT_SUMMARY_PATTERN.search(line):
            continue

        # Check for binary files
        binary_match = _DIFF_STAT_BINARY_PATTERN.match(line)
        if binary_match:
            stats.append(
                DiffStat(
                    path=binary_match.group(1).strip(),
                    insertions=0,
                    deletions=0,
                )
            )
            continue

        # Check for regular file changes
        match = _DIFF_STAT_PATTERN.match(line)
        if match:
            path = match.group(1).strip()
            insertions = len(match.group(3))
            deletions = len(match.group(4))
            stats.append(
                DiffStat(
                    path=path,
                    insertions=insertions,
                    deletions=deletions,
                )
            )

    return stats


def parse_log_output(output: str) -> list[CommitInfo]:
    """Parse pipe-delimited git log output.

    Expects output from: git log --format='%h|%cr|%s|%an'

    Args:
        output: Raw output from git log with pipe-delimited format.

    Returns:
        List of CommitInfo entries.
    """
    commits: list[CommitInfo] = []

    for line in output.splitlines():
        if not line.strip():
            continue

        # Split from the left for hash and relative_time (first 2 fields),
        # and from the right for author (last field). Everything in between
        # is the commit message, which may itself contain pipe characters.
        first_pipe = line.find("|")
        if first_pipe < 0:
            continue
        second_pipe = line.find("|", first_pipe + 1)
        if second_pipe < 0:
            continue
        last_pipe = line.rfind("|")
        if last_pipe <= second_pipe:
            continue

        short_hash = line[:first_pipe].strip()
        relative_time = line[first_pipe + 1 : second_pipe].strip()
        message = line[second_pipe + 1 : last_pipe].strip()
        author = line[last_pipe + 1 :].strip()

        commits.append(
            CommitInfo(
                short_hash=short_hash,
                relative_time=relative_time,
                message=message,
                author=author,
            )
        )

    return commits


def _run_git_command(args: list[str], repo_path: Path) -> str:
    """Run a git command and return stdout.

    Args:
        args: Git subcommand and arguments (without 'git').
        repo_path: Path to the git repository.

    Returns:
        stdout string, or empty string on failure.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def collect_git_status(repo_path: Path, max_commits: int = 10) -> GitStatus:
    """Collect git status by running git commands.

    Args:
        repo_path: Path to the git repository.
        max_commits: Maximum number of recent commits to fetch.

    Returns:
        GitStatus with all collected data.
    """
    # Parse porcelain status (branch + files)
    porcelain = _run_git_command(["status", "--porcelain=v2", "--branch"], repo_path)
    status = parse_porcelain_status(porcelain)

    # Stash count
    stash_output = _run_git_command(["stash", "list"], repo_path)
    status.stash_count = len([line for line in stash_output.strip().splitlines() if line])

    # Last commit info
    last_commit = _run_git_command(["log", "-1", "--format=%h|%cr|%s|%an"], repo_path)
    if last_commit.strip():
        parts = last_commit.strip().split("|", 3)
        if len(parts) == 4:
            status.last_commit_hash = parts[0]
            status.last_commit_time = parts[1]
            status.last_commit_message = parts[2]
            status.last_commit_author = parts[3]

    # Recent commits
    log_output = _run_git_command(["log", "--format=%h|%cr|%s|%an", f"-{max_commits}"], repo_path)
    status.commits = parse_log_output(log_output)

    # Diff stats
    unstaged = _run_git_command(["diff", "--stat"], repo_path)
    status.unstaged_diff = parse_diff_stat(unstaged)

    staged = _run_git_command(["diff", "--cached", "--stat"], repo_path)
    status.staged_diff = parse_diff_stat(staged)

    return status


# Mapping from FileStatus to (icon, color) for display
_STATUS_DISPLAY: dict[FileStatus, tuple[str, str]] = {
    FileStatus.STAGED_ADDED: ("A", "green"),
    FileStatus.STAGED_MODIFIED: ("M", "green"),
    FileStatus.STAGED_DELETED: ("D", "green"),
    FileStatus.STAGED_RENAMED: ("R", "green"),
    FileStatus.STAGED_COPIED: ("C", "green"),
    FileStatus.MODIFIED: ("M", "yellow"),
    FileStatus.DELETED: ("D", "red"),
    FileStatus.UNTRACKED: ("?", "dim"),
    FileStatus.RENAMED: ("R", "yellow"),
    FileStatus.COPIED: ("C", "yellow"),
}


def build_branch_panel(status: GitStatus) -> Panel:
    """Build a Rich panel showing branch information.

    Args:
        status: Collected git status data.

    Returns:
        Panel with branch name, upstream info, stash count, and last commit.
    """
    text = Text()

    # Branch name
    text.append(status.branch or "(detached)", style="bold cyan")

    # Upstream with ahead/behind
    if status.upstream:
        text.append("  ")
        text.append(status.upstream, style="dim")
        arrows: list[str] = []
        if status.ahead > 0:
            arrows.append(f"\u2191{status.ahead}")
        if status.behind > 0:
            arrows.append(f"\u2193{status.behind}")
        if arrows:
            text.append("  ")
            text.append(" ".join(arrows), style="bold yellow")

    text.append("\n")

    # Stash count
    if status.stash_count > 0:
        text.append(f"Stash: {status.stash_count}\n", style="dim yellow")

    # Last commit
    if status.last_commit_hash:
        text.append(status.last_commit_hash, style="cyan")
        text.append(" ")
        text.append(status.last_commit_message)
        text.append(" (", style="dim")
        text.append(status.last_commit_author, style="dim magenta")
        text.append(", ", style="dim")
        text.append(status.last_commit_time, style="dim")
        text.append(")", style="dim")

    return Panel(text, title="Branch", border_style="cyan")


def build_status_panel(status: GitStatus) -> Panel:
    """Build a Rich panel showing file status.

    Args:
        status: Collected git status data.

    Returns:
        Panel with a table of changed files grouped by status.
    """
    if not status.files:
        return Panel(
            Text("Working tree clean", style="dim"),
            title="Files",
            border_style="green",
        )

    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
    table.add_column("Status", width=2, no_wrap=True)
    table.add_column("File")

    # Count by category for subtitle
    staged_count = 0
    unstaged_count = 0
    untracked_count = 0

    for f in status.files:
        icon, color = _STATUS_DISPLAY.get(f.status, ("?", "dim"))
        display_path = f.path
        if f.original_path:
            display_path = f"{f.original_path} -> {f.path}"
        table.add_row(
            Text(icon, style=color),
            Text(display_path),
        )
        if f.status in (
            FileStatus.STAGED_ADDED,
            FileStatus.STAGED_MODIFIED,
            FileStatus.STAGED_DELETED,
            FileStatus.STAGED_RENAMED,
            FileStatus.STAGED_COPIED,
        ):
            staged_count += 1
        elif f.status == FileStatus.UNTRACKED:
            untracked_count += 1
        else:
            unstaged_count += 1

    parts: list[str] = []
    if staged_count:
        parts.append(f"{staged_count} staged")
    if unstaged_count:
        parts.append(f"{unstaged_count} unstaged")
    if untracked_count:
        parts.append(f"{untracked_count} untracked")
    subtitle = ", ".join(parts) if parts else None

    return Panel(table, title="Files", subtitle=subtitle, border_style="green")


def build_log_panel(status: GitStatus) -> Panel:
    """Build a Rich panel showing recent commits.

    Args:
        status: Collected git status data.

    Returns:
        Panel with a list of recent commits.
    """
    if not status.commits:
        return Panel(
            Text("No commits", style="dim"),
            title="Recent Commits",
            border_style="yellow",
        )

    text = Text()
    for i, commit in enumerate(status.commits):
        if i > 0:
            text.append("\n")
        text.append(commit.short_hash, style="cyan")
        text.append(" ")
        text.append(commit.message)
        text.append(" (", style="dim")
        text.append(commit.author, style="dim")
        text.append(", ", style="dim")
        text.append(commit.relative_time, style="dim")
        text.append(")", style="dim")

    return Panel(text, title="Recent Commits", border_style="yellow")


def build_diff_panel(status: GitStatus) -> Panel:
    """Build a Rich panel showing diff statistics.

    Args:
        status: Collected git status data.

    Returns:
        Panel with staged and unstaged diff stats including visual bars.
    """
    if not status.staged_diff and not status.unstaged_diff:
        return Panel(
            Text("No changes", style="dim"),
            title="Diff Stats",
            border_style="blue",
        )

    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
    table.add_column("File")
    table.add_column("Changes", justify="right", no_wrap=True)
    table.add_column("Bar", no_wrap=True)

    max_bar_width = 30

    def _add_diff_rows(diffs: list[DiffStat]) -> None:
        """Add diff stat rows to the table."""
        for diff in diffs:
            total = diff.insertions + diff.deletions
            changes_text = Text(str(total), style="bold")

            # Build visual bar
            bar = Text()
            if total > 0:
                scale = min(max_bar_width, total) / total if total > 0 else 0
                plus_count = max(1, round(diff.insertions * scale)) if diff.insertions > 0 else 0
                minus_count = max(1, round(diff.deletions * scale)) if diff.deletions > 0 else 0
                bar.append("+" * plus_count, style="green")
                bar.append("-" * minus_count, style="red")
            table.add_row(Text(diff.path), changes_text, bar)

    if status.staged_diff:
        table.add_row(Text("Staged", style="bold green"), Text(""), Text(""))
        _add_diff_rows(status.staged_diff)

    if status.unstaged_diff:
        table.add_row(Text("Unstaged", style="bold yellow"), Text(""), Text(""))
        _add_diff_rows(status.unstaged_diff)

    return Panel(table, title="Diff Stats", border_style="blue")


def build_display(
    status: GitStatus,
    show_log: bool = True,
    show_diff: bool = True,
    show_status: bool = True,
) -> Group:
    """Compose git status panels into a Rich Group.

    Args:
        status: Collected git status data.
        show_log: Whether to include the recent commits panel.
        show_diff: Whether to include the diff stats panel.
        show_status: Whether to include the file status panel.

    Returns:
        Group of Rich panels for display.
    """
    panels: list[Panel] = [build_branch_panel(status)]

    if show_status:
        panels.append(build_status_panel(status))

    if show_log:
        panels.append(build_log_panel(status))

    if show_diff:
        panels.append(build_diff_panel(status))

    return Group(*panels)


def run_git_monitor(
    repo_path: Path | None = None,
    poll_interval: float = 2.0,
    max_commits: int = 10,
    show_log: bool = True,
    show_diff: bool = True,
    show_status: bool = True,
) -> None:
    """Run the git monitor with Rich Live.

    Args:
        repo_path: Path to git repository (default: cwd).
        poll_interval: How often to poll for changes (seconds).
        max_commits: Maximum recent commits to show.
        show_log: Whether to show recent commits panel.
        show_diff: Whether to show diff stats panel.
        show_status: Whether to show file status panel.
    """
    import time

    from rich.console import Console
    from rich.live import Live

    console = Console()
    effective_path = repo_path or Path.cwd()

    # Verify it's a git repo
    test = _run_git_command(["rev-parse", "--git-dir"], effective_path)
    if not test:
        console.print(f"[red]Not a git repository:[/] {effective_path}")
        return

    console.clear()
    console.print(f"[bold cyan]Git Monitor[/] - {effective_path.name}")
    console.print("[dim]Press Ctrl+C to exit[/]\n")

    try:
        status = collect_git_status(effective_path, max_commits)
        display = build_display(
            status,
            show_log=show_log,
            show_diff=show_diff,
            show_status=show_status,
        )

        with Live(display, console=console, refresh_per_second=1) as live:
            while True:
                time.sleep(poll_interval)
                status = collect_git_status(effective_path, max_commits)
                live.update(
                    build_display(
                        status,
                        show_log=show_log,
                        show_diff=show_diff,
                        show_status=show_status,
                    )
                )
    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")
