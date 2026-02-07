"""Tests for cctmux.utils module."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from cctmux.utils import (
    compress_path,
    compress_paths_in_text,
    get_project_name,
    is_fzf_available,
    sanitize_session_name,
    select_with_fzf,
)


class TestSanitizeSessionName:
    """Tests for sanitize_session_name function."""

    def test_lowercase(self) -> None:
        """Should convert to lowercase."""
        assert sanitize_session_name("MyProject") == "myproject"

    def test_underscores_to_hyphens(self) -> None:
        """Should replace underscores with hyphens."""
        assert sanitize_session_name("my_project") == "my-project"

    def test_spaces_to_hyphens(self) -> None:
        """Should replace spaces with hyphens."""
        assert sanitize_session_name("my project") == "my-project"

    def test_removes_special_chars(self) -> None:
        """Should remove special characters."""
        assert sanitize_session_name("my@project!") == "myproject"

    def test_collapses_multiple_hyphens(self) -> None:
        """Should collapse multiple hyphens into one."""
        assert sanitize_session_name("my---project") == "my-project"
        assert sanitize_session_name("my__project") == "my-project"

    def test_strips_leading_trailing_hyphens(self) -> None:
        """Should strip leading and trailing hyphens."""
        assert sanitize_session_name("-myproject-") == "myproject"
        assert sanitize_session_name("---myproject---") == "myproject"

    def test_empty_string_fallback(self) -> None:
        """Should return 'session' for empty result."""
        assert sanitize_session_name("") == "session"
        assert sanitize_session_name("@#$%") == "session"

    def test_preserves_numbers(self) -> None:
        """Should preserve numbers."""
        assert sanitize_session_name("project123") == "project123"
        assert sanitize_session_name("123project") == "123project"

    def test_complex_name(self) -> None:
        """Should handle complex names correctly."""
        assert sanitize_session_name("My_Cool Project! (v2)") == "my-cool-project-v2"


class TestGetProjectName:
    """Tests for get_project_name function."""

    def test_simple_path(self) -> None:
        """Should return folder name from path."""
        assert get_project_name(Path("/home/user/projects/myproject")) == "myproject"

    def test_relative_path(self) -> None:
        """Should resolve relative path and return name."""
        # This will resolve to the actual directory name
        name = get_project_name(Path("."))
        assert isinstance(name, str)
        assert len(name) > 0

    def test_path_with_trailing_slash(self) -> None:
        """Should handle paths correctly regardless of trailing slash."""
        # Path normalizes this anyway
        assert get_project_name(Path("/home/user/projects/myproject/")) == "myproject"


class TestCompressPath:
    """Tests for compress_path function."""

    def test_empty_path(self) -> None:
        """Should return empty string for empty input."""
        assert compress_path("") == ""

    def test_home_directory_replaced_with_tilde(self) -> None:
        """Home directory should be replaced with ~."""
        with patch.object(Path, "home", return_value=Path("/home/user")):
            result = compress_path("/home/user/projects/file.txt")
            assert result == "~/projects/file.txt"

    def test_short_path_unchanged(self) -> None:
        """Short paths should be returned as-is after home replacement."""
        with patch.object(Path, "home", return_value=Path("/home/user")):
            result = compress_path("/tmp/short.txt")
            assert result == "/tmp/short.txt"

    def test_long_path_truncated_from_beginning(self) -> None:
        """Long paths should be truncated from the beginning."""
        with patch.object(Path, "home", return_value=Path("/home/user")):
            long_path = "/home/user/" + "a" * 100 + "/file.txt"
            result = compress_path(long_path, max_len=30)
            assert result.startswith("...")
            assert len(result) == 30

    def test_non_home_path_not_modified(self) -> None:
        """Paths not under home should not get ~ prefix."""
        with patch.object(Path, "home", return_value=Path("/home/user")):
            result = compress_path("/var/log/test.log")
            assert result == "/var/log/test.log"


class TestCompressPathsInText:
    """Tests for compress_paths_in_text function."""

    def test_empty_text(self) -> None:
        """Should return empty string for empty input."""
        assert compress_paths_in_text("") == ""

    def test_text_without_paths_unchanged(self) -> None:
        """Text without home paths should be unchanged."""
        text = "This is some regular text without paths"
        assert compress_paths_in_text(text) == text

    def test_home_path_replaced_in_text(self) -> None:
        """Home directory paths in text should be replaced with ~."""
        with patch.object(Path, "home", return_value=Path("/home/user")):
            text = "Reading file /home/user/projects/test.py"
            result = compress_paths_in_text(text)
            assert result == "Reading file ~/projects/test.py"

    def test_multiple_home_paths_replaced(self) -> None:
        """Multiple home paths should all be replaced."""
        with patch.object(Path, "home", return_value=Path("/home/user")):
            text = "Copying /home/user/a.txt to /home/user/b.txt"
            result = compress_paths_in_text(text)
            assert result == "Copying ~/a.txt to ~/b.txt"


class TestSelectWithFzf:
    """Tests for select_with_fzf function."""

    def test_empty_entries_returns_none(self) -> None:
        """Should return None when entries list is empty."""
        assert select_with_fzf([]) is None

    def test_successful_selection(self) -> None:
        """Should return selected entry on success."""
        mock_result = subprocess.CompletedProcess(args=["fzf"], returncode=0, stdout="selected-item\n", stderr="")
        with patch("cctmux.utils.subprocess.run", return_value=mock_result):
            result = select_with_fzf(["item1", "item2", "selected-item"])
            assert result == "selected-item"

    def test_cancelled_selection_returns_none(self) -> None:
        """Should return None when fzf exits with non-zero code (user cancelled)."""
        mock_result = subprocess.CompletedProcess(args=["fzf"], returncode=130, stdout="", stderr="")
        with patch("cctmux.utils.subprocess.run", return_value=mock_result):
            result = select_with_fzf(["item1", "item2"])
            assert result is None

    def test_fzf_not_installed_returns_none(self) -> None:
        """Should return None when fzf is not installed."""
        with patch("cctmux.utils.subprocess.run", side_effect=FileNotFoundError):
            result = select_with_fzf(["item1"])
            assert result is None

    def test_passes_custom_prompt(self) -> None:
        """Should pass custom prompt to fzf."""
        mock_result = subprocess.CompletedProcess(args=["fzf"], returncode=0, stdout="item1\n", stderr="")
        with patch("cctmux.utils.subprocess.run", return_value=mock_result) as mock_run:
            select_with_fzf(["item1"], prompt="Pick one: ")
            call_args = mock_run.call_args[0][0]
            assert "--prompt" in call_args
            idx = call_args.index("--prompt")
            assert call_args[idx + 1] == "Pick one: "


class TestIsFzfAvailable:
    """Tests for is_fzf_available function."""

    def test_fzf_available(self) -> None:
        """Should return True when fzf is installed."""
        mock_result = subprocess.CompletedProcess(args=["fzf", "--version"], returncode=0, stdout="0.50.0", stderr="")
        with patch("cctmux.utils.subprocess.run", return_value=mock_result):
            assert is_fzf_available() is True

    def test_fzf_not_found(self) -> None:
        """Should return False when fzf is not installed."""
        with patch("cctmux.utils.subprocess.run", side_effect=FileNotFoundError):
            assert is_fzf_available() is False

    def test_fzf_check_fails(self) -> None:
        """Should return False when fzf --version fails."""
        with patch("cctmux.utils.subprocess.run", side_effect=subprocess.CalledProcessError(1, "fzf")):
            assert is_fzf_available() is False
