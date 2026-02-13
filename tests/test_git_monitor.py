"""Tests for git_monitor module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Group
from rich.panel import Panel

from cctmux.git_monitor import (
    CommitInfo,
    DiffStat,
    FileChange,
    FileStatus,
    GitStatus,
    _run_git_command,
    build_branch_panel,
    build_diff_panel,
    build_display,
    build_log_panel,
    build_status_panel,
    collect_git_status,
    parse_diff_stat,
    parse_log_output,
    parse_porcelain_status,
)


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_staged_file(self) -> None:
        change = FileChange(path="src/main.py", status=FileStatus.STAGED_MODIFIED)
        assert change.path == "src/main.py"
        assert change.status == FileStatus.STAGED_MODIFIED

    def test_untracked_file(self) -> None:
        change = FileChange(path="new_file.py", status=FileStatus.UNTRACKED)
        assert change.status == FileStatus.UNTRACKED

    def test_default_original_path(self) -> None:
        change = FileChange(path="file.py", status=FileStatus.MODIFIED)
        assert change.original_path == ""

    def test_renamed_with_original(self) -> None:
        change = FileChange(path="new.py", status=FileStatus.RENAMED, original_path="old.py")
        assert change.path == "new.py"
        assert change.original_path == "old.py"


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_commit_info(self) -> None:
        commit = CommitInfo(
            short_hash="abc1234",
            relative_time="5 minutes ago",
            message="feat: add feature",
            author="John Doe",
        )
        assert commit.short_hash == "abc1234"
        assert commit.relative_time == "5 minutes ago"
        assert commit.message == "feat: add feature"
        assert commit.author == "John Doe"


class TestDiffStat:
    """Tests for DiffStat dataclass."""

    def test_diff_stat(self) -> None:
        stat = DiffStat(path="src/main.py", insertions=10, deletions=3)
        assert stat.path == "src/main.py"
        assert stat.insertions == 10
        assert stat.deletions == 3


class TestGitStatus:
    """Tests for GitStatus dataclass."""

    def test_default_values(self) -> None:
        status = GitStatus()
        assert status.branch == ""
        assert status.upstream == ""
        assert status.ahead == 0
        assert status.behind == 0
        assert status.files == []
        assert status.stash_count == 0
        assert status.commits == []
        assert status.staged_diff == []
        assert status.unstaged_diff == []
        assert status.last_commit_hash == ""
        assert status.last_commit_message == ""
        assert status.last_commit_author == ""
        assert status.last_commit_time == ""


class TestParsePorcelainStatus:
    """Tests for parsing git status --porcelain=v2 --branch output."""

    def test_clean_repo(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -0\n"
        status = parse_porcelain_status(output)
        assert status.branch == "main"
        assert status.upstream == "origin/main"
        assert status.ahead == 0
        assert status.behind == 0
        assert status.files == []

    def test_modified_file(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n1 .M N... 100644 100644 100644 abc123 def456 src/main.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].path == "src/main.py"
        assert status.files[0].status == FileStatus.MODIFIED

    def test_staged_file(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n1 M. N... 100644 100644 100644 abc123 def456 src/main.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].status == FileStatus.STAGED_MODIFIED

    def test_untracked_file(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n? new_file.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].path == "new_file.py"
        assert status.files[0].status == FileStatus.UNTRACKED

    def test_added_file(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n1 A. N... 000000 100644 100644 0000000 abc123 new.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].status == FileStatus.STAGED_ADDED

    def test_deleted_file(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n1 D. N... 100644 000000 000000 abc123 0000000 old.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].status == FileStatus.STAGED_DELETED

    def test_unstaged_deleted_file(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n1 .D N... 100644 100644 000000 abc123 0000000 removed.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].status == FileStatus.DELETED

    def test_both_staged_and_unstaged(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n1 MM N... 100644 100644 100644 abc123 def456 src/main.py\n"
        status = parse_porcelain_status(output)
        assert len(status.files) == 2
        assert status.files[0].status == FileStatus.STAGED_MODIFIED
        assert status.files[1].status == FileStatus.MODIFIED
        assert status.files[0].path == "src/main.py"
        assert status.files[1].path == "src/main.py"

    def test_ahead_behind(self) -> None:
        output = "# branch.oid abc123\n# branch.head feature\n# branch.upstream origin/feature\n# branch.ab +3 -1\n"
        status = parse_porcelain_status(output)
        assert status.ahead == 3
        assert status.behind == 1

    def test_no_upstream(self) -> None:
        output = "# branch.oid abc123\n# branch.head feature\n"
        status = parse_porcelain_status(output)
        assert status.upstream == ""
        assert status.ahead == 0
        assert status.behind == 0

    def test_renamed_file(self) -> None:
        output = (
            "# branch.oid abc123\n"
            "# branch.head main\n"
            "2 R. N... 100644 100644 100644 abc123 def456 R100 new.py\told.py\n"
        )
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].status == FileStatus.STAGED_RENAMED
        assert status.files[0].path == "new.py"
        assert status.files[0].original_path == "old.py"

    def test_copied_file(self) -> None:
        output = (
            "# branch.oid abc123\n"
            "# branch.head main\n"
            "2 C. N... 100644 100644 100644 abc123 def456 C100 copy.py\toriginal.py\n"
        )
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].status == FileStatus.STAGED_COPIED
        assert status.files[0].path == "copy.py"
        assert status.files[0].original_path == "original.py"

    def test_multiple_files(self) -> None:
        output = (
            "# branch.oid abc123\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +1 -0\n"
            "1 M. N... 100644 100644 100644 abc123 def456 staged.py\n"
            "1 .M N... 100644 100644 100644 abc123 def456 modified.py\n"
            "? untracked.py\n"
        )
        status = parse_porcelain_status(output)
        assert len(status.files) == 3
        assert status.files[0].status == FileStatus.STAGED_MODIFIED
        assert status.files[0].path == "staged.py"
        assert status.files[1].status == FileStatus.MODIFIED
        assert status.files[1].path == "modified.py"
        assert status.files[2].status == FileStatus.UNTRACKED
        assert status.files[2].path == "untracked.py"

    def test_empty_output(self) -> None:
        status = parse_porcelain_status("")
        assert status.branch == ""
        assert status.files == []

    def test_ignored_lines_skipped(self) -> None:
        output = "# branch.oid abc123\n# branch.head main\n! ignored_file.pyc\n"
        status = parse_porcelain_status(output)
        assert status.files == []

    def test_path_with_spaces(self) -> None:
        output = (
            "# branch.oid abc123\n# branch.head main\n1 .M N... 100644 100644 100644 abc123 def456 src/my file.py\n"
        )
        status = parse_porcelain_status(output)
        assert len(status.files) == 1
        assert status.files[0].path == "src/my file.py"


class TestParseDiffStat:
    """Tests for parsing git diff --stat output."""

    def test_empty_diff(self) -> None:
        stats = parse_diff_stat("")
        assert stats == []

    def test_single_file(self) -> None:
        output = " src/main.py | 10 ++++------\n 1 file changed, 4 insertions(+), 6 deletions(-)\n"
        stats = parse_diff_stat(output)
        assert len(stats) == 1
        assert stats[0].path == "src/main.py"
        assert stats[0].insertions == 4
        assert stats[0].deletions == 6

    def test_multiple_files(self) -> None:
        output = " src/a.py | 5 +++--\n src/b.py | 3 +--\n 2 files changed, 4 insertions(+), 4 deletions(-)\n"
        stats = parse_diff_stat(output)
        assert len(stats) == 2
        assert stats[0].path == "src/a.py"
        assert stats[0].insertions == 3
        assert stats[0].deletions == 2
        assert stats[1].path == "src/b.py"
        assert stats[1].insertions == 1
        assert stats[1].deletions == 2

    def test_binary_file(self) -> None:
        output = " image.png | Bin 0 -> 1234 bytes\n 1 file changed, 0 insertions(+), 0 deletions(-)\n"
        stats = parse_diff_stat(output)
        assert len(stats) == 1
        assert stats[0].path == "image.png"
        assert stats[0].insertions == 0
        assert stats[0].deletions == 0

    def test_only_insertions(self) -> None:
        output = " new_file.py | 20 ++++++++++++++++++++\n 1 file changed, 20 insertions(+)\n"
        stats = parse_diff_stat(output)
        assert len(stats) == 1
        assert stats[0].insertions == 20
        assert stats[0].deletions == 0

    def test_only_deletions(self) -> None:
        output = " old_file.py | 15 ---------------\n 1 file changed, 15 deletions(-)\n"
        stats = parse_diff_stat(output)
        assert len(stats) == 1
        assert stats[0].insertions == 0
        assert stats[0].deletions == 15

    def test_path_with_arrow(self) -> None:
        output = " src/{old.py => new.py} | 5 +++--\n 1 file changed, 3 insertions(+), 2 deletions(-)\n"
        stats = parse_diff_stat(output)
        assert len(stats) == 1
        assert "old.py" in stats[0].path or "new.py" in stats[0].path


class TestParseLogOutput:
    """Tests for parsing git log output."""

    def test_empty_log(self) -> None:
        commits = parse_log_output("")
        assert commits == []

    def test_single_commit(self) -> None:
        output = "abc1234|5 minutes ago|feat: add feature|John Doe\n"
        commits = parse_log_output(output)
        assert len(commits) == 1
        assert commits[0].short_hash == "abc1234"
        assert commits[0].relative_time == "5 minutes ago"
        assert commits[0].message == "feat: add feature"
        assert commits[0].author == "John Doe"

    def test_multiple_commits(self) -> None:
        output = "abc1234|5 minutes ago|feat: add X|Alice\ndef5678|2 hours ago|fix: bug Y|Bob\n"
        commits = parse_log_output(output)
        assert len(commits) == 2
        assert commits[0].short_hash == "abc1234"
        assert commits[0].author == "Alice"
        assert commits[1].short_hash == "def5678"
        assert commits[1].author == "Bob"

    def test_commit_message_with_pipes(self) -> None:
        output = "abc1234|5 minutes ago|feat: add X | Y support|Alice\n"
        commits = parse_log_output(output)
        assert len(commits) == 1
        assert commits[0].message == "feat: add X | Y support"

    def test_blank_lines_skipped(self) -> None:
        output = "abc1234|5 minutes ago|feat: add X|Alice\n\ndef5678|2 hours ago|fix: Y|Bob\n"
        commits = parse_log_output(output)
        assert len(commits) == 2

    def test_short_line_skipped(self) -> None:
        output = "malformed line\nabc1234|5 minutes ago|feat: add X|Alice\n"
        commits = parse_log_output(output)
        assert len(commits) == 1
        assert commits[0].short_hash == "abc1234"


class TestRunGitCommand:
    """Tests for _run_git_command helper."""

    def test_successful_command(self, tmp_path: Path) -> None:
        with patch("cctmux.git_monitor.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="output\n", stderr="")
            result = _run_git_command(["status"], tmp_path)
            assert result == "output\n"

    def test_failed_command_returns_empty(self, tmp_path: Path) -> None:
        with patch("cctmux.git_monitor.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repo")
            result = _run_git_command(["status"], tmp_path)
            assert result == ""

    def test_exception_returns_empty(self, tmp_path: Path) -> None:
        with patch("cctmux.git_monitor.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            result = _run_git_command(["status"], tmp_path)
            assert result == ""

    def test_timeout_returns_empty(self, tmp_path: Path) -> None:
        with patch("cctmux.git_monitor.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
            result = _run_git_command(["status"], tmp_path)
            assert result == ""


class TestCollectGitStatus:
    """Tests for collect_git_status function."""

    def test_collects_all_data(self, tmp_path: Path) -> None:
        """Should call all git commands and assemble GitStatus."""
        porcelain = "# branch.oid abc123\n# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -0\n"
        log_line = "abc1234|5 min ago|init|Author\n"

        def mock_run(args: list[str], **kwargs: object) -> MagicMock:
            cmd_str = " ".join(str(a) for a in args)
            if "status --porcelain" in cmd_str:
                return MagicMock(returncode=0, stdout=porcelain, stderr="")
            if "stash list" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "log -1" in cmd_str:
                return MagicMock(returncode=0, stdout=log_line, stderr="")
            if "log --format" in cmd_str:
                return MagicMock(returncode=0, stdout=log_line, stderr="")
            if "diff --cached" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "diff --stat" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("cctmux.git_monitor.subprocess.run", side_effect=mock_run):
            status = collect_git_status(tmp_path, max_commits=10)
            assert status.branch == "main"
            assert status.upstream == "origin/main"


def _make_status(**kwargs: object) -> GitStatus:
    """Helper to create GitStatus with defaults."""
    defaults: dict[str, object] = {
        "branch": "main",
        "upstream": "origin/main",
        "ahead": 0,
        "behind": 0,
        "files": [],
        "stash_count": 0,
        "commits": [],
        "staged_diff": [],
        "unstaged_diff": [],
        "last_commit_hash": "abc1234",
        "last_commit_message": "init commit",
        "last_commit_author": "Author",
        "last_commit_time": "5 minutes ago",
    }
    defaults.update(kwargs)
    return GitStatus(**defaults)  # type: ignore[arg-type]


class TestBuildBranchPanel:
    """Tests for build_branch_panel."""

    def test_returns_panel(self) -> None:
        status = _make_status()
        panel = build_branch_panel(status)
        assert isinstance(panel, Panel)


class TestBuildStatusPanel:
    """Tests for build_status_panel."""

    def test_empty_status(self) -> None:
        status = _make_status(files=[])
        panel = build_status_panel(status)
        assert isinstance(panel, Panel)

    def test_with_files(self) -> None:
        files = [
            FileChange(path="a.py", status=FileStatus.MODIFIED),
            FileChange(path="b.py", status=FileStatus.UNTRACKED),
        ]
        status = _make_status(files=files)
        panel = build_status_panel(status)
        assert isinstance(panel, Panel)


class TestBuildLogPanel:
    """Tests for build_log_panel."""

    def test_empty_log(self) -> None:
        status = _make_status(commits=[])
        panel = build_log_panel(status)
        assert isinstance(panel, Panel)

    def test_with_commits(self) -> None:
        commits = [
            CommitInfo(
                short_hash="abc1234",
                relative_time="5 min ago",
                message="feat: x",
                author="A",
            ),
        ]
        status = _make_status(commits=commits)
        panel = build_log_panel(status)
        assert isinstance(panel, Panel)


class TestBuildDiffPanel:
    """Tests for build_diff_panel."""

    def test_empty_diff(self) -> None:
        status = _make_status()
        panel = build_diff_panel(status)
        assert isinstance(panel, Panel)

    def test_with_diffs(self) -> None:
        diffs = [DiffStat(path="a.py", insertions=10, deletions=3)]
        status = _make_status(unstaged_diff=diffs)
        panel = build_diff_panel(status)
        assert isinstance(panel, Panel)


class TestBuildDisplay:
    """Tests for build_display."""

    def test_returns_group(self) -> None:
        status = _make_status()
        display = build_display(status)
        assert isinstance(display, Group)

    def test_respects_show_flags(self) -> None:
        status = _make_status()
        display = build_display(status, show_log=False, show_diff=False, show_status=False)
        assert isinstance(display, Group)
