"""Tests for cctmux.tmux_manager module."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from cctmux.config import LayoutType
from cctmux.tmux_manager import (
    attach_session,
    configure_status_bar,
    create_session,
    is_inside_tmux,
    list_panes,
    session_exists,
)


class TestIsInsideTmux:
    """Tests for is_inside_tmux function."""

    def test_returns_true_when_tmux_set(self) -> None:
        """Should return True when TMUX env var is set."""
        with patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}):
            assert is_inside_tmux() is True

    def test_returns_false_when_tmux_not_set(self) -> None:
        """Should return False when TMUX env var is not set."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_inside_tmux() is False


class TestSessionExists:
    """Tests for session_exists function."""

    def test_session_exists_true(self) -> None:
        """Should return True when tmux has-session returns 0."""
        mock_result = subprocess.CompletedProcess[str](args=[], returncode=0)
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            assert session_exists("my-session") is True

    def test_session_exists_false(self) -> None:
        """Should return False when tmux has-session returns non-zero."""
        mock_result = subprocess.CompletedProcess[str](args=[], returncode=1)
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            assert session_exists("nonexistent") is False


class TestCreateSession:
    """Tests for create_session function."""

    def test_dry_run_default_layout(self, tmp_path: Path) -> None:
        """Should return commands without executing in dry run."""
        commands = create_session(
            session_name="test-session",
            project_dir=tmp_path,
            dry_run=True,
        )
        # Should include: new-session, 2x set-environment, send-keys(export), send-keys(claude), attach
        assert len(commands) >= 5
        assert "new-session" in commands[0]
        assert "test-session" in commands[0]
        assert str(tmp_path.resolve()) in commands[0]
        assert "CCTMUX_SESSION" in commands[1]
        assert "CCTMUX_PROJECT_DIR" in commands[2]
        assert "claude" in commands[4]
        assert "attach-session" in commands[-1]

    def test_dry_run_with_claude_args(self, tmp_path: Path) -> None:
        """Should include claude args in command."""
        commands = create_session(
            session_name="test-session",
            project_dir=tmp_path,
            claude_args="--model opus",
            dry_run=True,
        )
        # Find the command that launches claude with args
        claude_cmds = [c for c in commands if "claude --model opus" in c]
        assert len(claude_cmds) >= 1

    def test_dry_run_with_task_list_id(self, tmp_path: Path) -> None:
        """Should set CLAUDE_CODE_TASK_LIST_ID when task_list_id is True."""
        commands = create_session(
            session_name="test-session",
            project_dir=tmp_path,
            task_list_id=True,
            dry_run=True,
        )
        env_cmds = [c for c in commands if "CLAUDE_CODE_TASK_LIST_ID" in c]
        assert len(env_cmds) >= 1

    def test_dry_run_with_status_bar(self, tmp_path: Path) -> None:
        """Should include status bar commands when enabled."""
        commands = create_session(
            session_name="test-session",
            project_dir=tmp_path,
            status_bar=True,
            dry_run=True,
        )
        status_cmds = [c for c in commands if "status-style" in c or "status-left" in c or "status-right" in c]
        assert len(status_cmds) >= 3

    def test_dry_run_with_editor_layout(self, tmp_path: Path) -> None:
        """Should include layout commands."""
        commands = create_session(
            session_name="test-session",
            project_dir=tmp_path,
            layout=LayoutType.EDITOR,
            dry_run=True,
        )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 1


class TestAttachSession:
    """Tests for attach_session function."""

    def test_dry_run_returns_command(self) -> None:
        """Should return attach command without executing."""
        commands = attach_session("test-session", dry_run=True)
        assert len(commands) == 1
        assert commands[0] == "tmux attach-session -t test-session"


class TestConfigureStatusBar:
    """Tests for configure_status_bar function."""

    def test_dry_run_with_git_branch(self, tmp_path: Path) -> None:
        """Should include git branch in status bar."""
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="main\n", stderr="")
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            commands = configure_status_bar("test-session", tmp_path, dry_run=True)

        assert len(commands) == 3
        assert "status-style" in commands[0]
        assert "status-left" in commands[1]
        assert tmp_path.name in commands[1]
        assert "main" in commands[1]
        assert "status-right" in commands[2]

    def test_dry_run_without_git(self, tmp_path: Path) -> None:
        """Should work without git."""
        mock_result = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not a git repo")
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            commands = configure_status_bar("test-session", tmp_path, dry_run=True)

        assert len(commands) == 3
        # status-left should not contain branch brackets
        assert "[" not in commands[1] or "main" not in commands[1]

    def test_dry_run_git_not_installed(self, tmp_path: Path) -> None:
        """Should handle git not being installed."""
        with patch("cctmux.tmux_manager.subprocess.run", side_effect=FileNotFoundError):
            commands = configure_status_bar("test-session", tmp_path, dry_run=True)

        assert len(commands) == 3


class TestListPanes:
    """Tests for list_panes function."""

    def test_parses_pane_output(self) -> None:
        """Should parse tmux list-panes output."""
        mock_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="%0:0:120x40\n%1:1:60x40\n%2:2:60x20\n",
            stderr="",
        )
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            panes = list_panes("test-session")

        assert len(panes) == 3
        assert panes[0] == {"id": "%0", "index": "0", "size": "120x40"}
        assert panes[1] == {"id": "%1", "index": "1", "size": "60x40"}
        assert panes[2] == {"id": "%2", "index": "2", "size": "60x20"}

    def test_no_session_returns_empty(self) -> None:
        """Should return empty list when session doesn't exist."""
        mock_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="can't find session")
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            panes = list_panes("nonexistent")

        assert panes == []

    def test_handles_empty_output(self) -> None:
        """Should handle empty output gracefully."""
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("cctmux.tmux_manager.subprocess.run", return_value=mock_result):
            panes = list_panes("test-session")

        assert panes == []
