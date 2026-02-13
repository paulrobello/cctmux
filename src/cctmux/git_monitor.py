"""Git monitor data models and parsing functions.

Provides dataclasses and parsers for git status, diff stats, and log output.
No display or subprocess code - only data models and pure parsing functions.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum


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
