"""Tests for cctmux.layouts module."""

import pytest

from cctmux.config import LayoutType
from cctmux.layouts import (
    _validate_pane_id,
    apply_cc_mon_layout,
    apply_dashboard_layout,
    apply_default_layout,
    apply_editor_layout,
    apply_full_monitor_layout,
    apply_git_mon_layout,
    apply_layout,
    apply_monitor_layout,
    apply_ralph_full_layout,
    apply_ralph_layout,
    apply_triple_layout,
)


class TestApplyLayout:
    """Tests for apply_layout function."""

    def test_default_layout_dispatch(self) -> None:
        """Should dispatch to default layout handler."""
        commands = apply_layout("test-session", LayoutType.DEFAULT, dry_run=True)
        assert commands == []

    def test_editor_layout_dispatch(self) -> None:
        """Should dispatch to editor layout handler."""
        commands = apply_layout("test-session", LayoutType.EDITOR, dry_run=True)
        assert len(commands) == 1
        assert "split-window" in commands[0]
        assert "-h" in commands[0]
        assert "-d" in commands[0]

    def test_monitor_layout_dispatch(self) -> None:
        """Should dispatch to monitor layout handler."""
        commands = apply_layout("test-session", LayoutType.MONITOR, dry_run=True)
        assert len(commands) == 1
        assert "split-window" in commands[0]
        assert "-v" in commands[0]
        assert "-d" in commands[0]

    def test_triple_layout_dispatch(self) -> None:
        """Should dispatch to triple layout handler."""
        commands = apply_layout("test-session", LayoutType.TRIPLE, dry_run=True)
        assert len(commands) == 2  # 2 splits, -d flag keeps focus on main pane

    def test_cc_mon_layout_dispatch(self) -> None:
        """Should dispatch to cc-mon layout handler."""
        commands = apply_layout("test-session", LayoutType.CC_MON, dry_run=True)
        assert len(commands) == 5
        assert "cctmux-session" in commands[1]
        assert "cctmux-tasks" in commands[3]

    def test_full_monitor_layout_dispatch(self) -> None:
        """Should dispatch to full-monitor layout handler."""
        commands = apply_layout("test-session", LayoutType.FULL_MONITOR, dry_run=True)
        assert len(commands) == 7
        assert "cctmux-session" in commands[1]
        assert "cctmux-tasks" in commands[3]
        assert "cctmux-activity" in commands[5]

    def test_dashboard_layout_dispatch(self) -> None:
        """Should dispatch to dashboard layout handler."""
        commands = apply_layout("test-session", LayoutType.DASHBOARD, dry_run=True)
        assert len(commands) == 5
        assert "cctmux-session" in commands[1]
        assert "cctmux-activity" in commands[3]

    def test_ralph_layout_dispatch(self) -> None:
        """Should dispatch to ralph layout handler."""
        commands = apply_layout("test-session", LayoutType.RALPH, dry_run=True)
        assert len(commands) == 3
        assert "cctmux-ralph" in commands[1]

    def test_ralph_full_layout_dispatch(self) -> None:
        """Should dispatch to ralph-full layout handler."""
        commands = apply_layout("test-session", LayoutType.RALPH_FULL, dry_run=True)
        assert len(commands) == 5
        assert "cctmux-ralph" in commands[1]
        assert "cctmux-tasks" in commands[3]

    def test_git_mon_layout_dispatch(self) -> None:
        """Should dispatch to git-mon layout handler."""
        commands = apply_layout("test-session", LayoutType.GIT_MON, dry_run=True)
        assert len(commands) == 3
        assert "cctmux-git" in commands[1]


class TestApplyDefaultLayout:
    """Tests for apply_default_layout function."""

    def test_returns_empty_commands(self) -> None:
        """Should return empty list (no splits)."""
        commands = apply_default_layout("test-session", dry_run=True)
        assert commands == []


class TestApplyEditorLayout:
    """Tests for apply_editor_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return commands without executing in dry run."""
        commands = apply_editor_layout("test-session", dry_run=True)
        assert len(commands) == 1
        # Horizontal split with -d to keep focus on original pane
        assert commands[0] == "tmux split-window -d -t test-session -h -p 30"


class TestApplyMonitorLayout:
    """Tests for apply_monitor_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return commands without executing in dry run."""
        commands = apply_monitor_layout("test-session", dry_run=True)
        assert len(commands) == 1
        # Vertical split with -d to keep focus on original pane
        assert commands[0] == "tmux split-window -d -t test-session -v -p 20"


class TestApplyTripleLayout:
    """Tests for apply_triple_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return commands without executing in dry run."""
        commands = apply_triple_layout("test-session", dry_run=True)
        assert len(commands) == 2  # 2 splits, -d flag keeps focus on main pane
        # First: horizontal split with -d -P to capture pane ID and keep focus
        assert "-d" in commands[0]
        assert "-P" in commands[0]
        assert "-h -p 50" in commands[0]
        # Second: vertical split of the right pane (uses :0.1 in dry run)
        assert "-d" in commands[1]
        assert "-v -p 50" in commands[1]
        assert "test-session:0.1" in commands[1]


class TestApplyCcMonLayout:
    """Tests for apply_cc_mon_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return commands without executing in dry run."""
        commands = apply_cc_mon_layout("test-session", dry_run=True)
        assert len(commands) == 5
        # First: horizontal split 50% with -P to capture pane ID
        assert "-P" in commands[0]
        assert "-h -p 50" in commands[0]
        # Second: launch cctmux-session in right pane
        assert "cctmux-session" in commands[1]
        assert "send-keys" in commands[1]
        # Third: vertical split of right pane
        assert "-v -p 50" in commands[2]
        # Fourth: launch cctmux-tasks -g in bottom-right pane
        assert "cctmux-tasks -g" in commands[3]
        # Fifth: focus the main (left) pane
        assert commands[4] == "tmux select-pane -t test-session:0.0"


class TestApplyFullMonitorLayout:
    """Tests for apply_full_monitor_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return correct commands in dry run."""
        commands = apply_full_monitor_layout("test-session", dry_run=True)
        assert len(commands) == 7
        # 1: horizontal split with 40% right
        assert "-h -p 40" in commands[0]
        assert "-P" in commands[0]
        # 2: cctmux-session in top-right
        assert "cctmux-session" in commands[1]
        assert "send-keys" in commands[1]
        # 3: vertical split of right pane (70%)
        assert "-v -p 70" in commands[2]
        # 4: cctmux-tasks -g in middle-right
        assert "cctmux-tasks -g" in commands[3]
        # 5: vertical split of middle pane (50%)
        assert "-v -p 50" in commands[4]
        # 6: cctmux-activity in bottom-right
        assert "cctmux-activity" in commands[5]
        # 7: focus main pane
        assert commands[6] == "tmux select-pane -t test-session:0.0"

    def test_session_name_in_commands(self) -> None:
        """Should use session name in all commands."""
        commands = apply_full_monitor_layout("my-project", dry_run=True)
        assert all("my-project" in cmd for cmd in commands)


class TestApplyDashboardLayout:
    """Tests for apply_dashboard_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return correct commands in dry run."""
        commands = apply_dashboard_layout("test-session", dry_run=True)
        assert len(commands) == 5
        # 1: horizontal split with 30% right
        assert "-h -p 30" in commands[0]
        assert "-P" in commands[0]
        # 2: cctmux-session in top-right
        assert "cctmux-session" in commands[1]
        # 3: vertical split of right pane (50%)
        assert "-v -p 50" in commands[2]
        # 4: cctmux-activity in main (left) pane
        assert "cctmux-activity --show-hourly" in commands[3]
        assert "test-session:0.0" in commands[3]
        # 5: focus bottom-right pane
        assert "select-pane" in commands[4]
        assert "test-session:0.2" in commands[4]


class TestApplyRalphLayout:
    """Tests for apply_ralph_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return correct commands in dry run."""
        commands = apply_ralph_layout("test-session", dry_run=True)
        assert len(commands) == 3
        # 1: horizontal split with 40% right
        assert "-h -p 40" in commands[0]
        assert "-P" in commands[0]
        # 2: cctmux-ralph in right pane
        assert "cctmux-ralph" in commands[1]
        assert "send-keys" in commands[1]
        # 3: focus main (left) pane
        assert commands[2] == "tmux select-pane -t test-session:0.0"


class TestApplyRalphFullLayout:
    """Tests for apply_ralph_full_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return correct commands in dry run."""
        commands = apply_ralph_full_layout("test-session", dry_run=True)
        assert len(commands) == 5
        # 1: horizontal split with 40% right
        assert "-h -p 40" in commands[0]
        assert "-P" in commands[0]
        # 2: cctmux-ralph in right pane
        assert "cctmux-ralph" in commands[1]
        # 3: vertical split of right pane (50%)
        assert "-v -p 50" in commands[2]
        # 4: cctmux-tasks -g in bottom-right
        assert "cctmux-tasks -g" in commands[3]
        # 5: focus main (left) pane
        assert commands[4] == "tmux select-pane -t test-session:0.0"


class TestApplyGitMonLayout:
    """Tests for apply_git_mon_layout function."""

    def test_dry_run_returns_commands(self) -> None:
        """Should return correct commands in dry run."""
        commands = apply_git_mon_layout("test-session", dry_run=True)
        assert len(commands) == 3
        # 1: horizontal split with 40% right
        assert "-h -p 40" in commands[0]
        assert "-P" in commands[0]
        # 2: cctmux-git in right pane
        assert "cctmux-git" in commands[1]
        assert "send-keys" in commands[1]
        # 3: focus main (left) pane
        assert commands[2] == "tmux select-pane -t test-session:0.0"


class TestValidatePaneId:
    """Tests for _validate_pane_id helper."""

    def test_valid_pane_id(self) -> None:
        """Should accept valid pane IDs starting with %."""
        _validate_pane_id("%0")
        _validate_pane_id("%15")
        _validate_pane_id("%123")

    def test_empty_string_raises(self) -> None:
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid pane ID"):
            _validate_pane_id("")

    def test_no_percent_prefix_raises(self) -> None:
        """Should raise ValueError for ID without % prefix."""
        with pytest.raises(ValueError, match="Invalid pane ID"):
            _validate_pane_id("15")

    def test_positional_index_raises(self) -> None:
        """Should raise ValueError for positional indices."""
        with pytest.raises(ValueError, match="Invalid pane ID"):
            _validate_pane_id("0.1")

    def test_context_in_error_message(self) -> None:
        """Should include context label in error message."""
        with pytest.raises(ValueError, match="main_pane"):
            _validate_pane_id("", context="main_pane")
