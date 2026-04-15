"""Tests for pitmux functionality."""

from pathlib import Path
from unittest.mock import patch

from cctmux.__main__ import _sync_pi_skill


class TestSyncPiSkill:
    """Tests for _sync_pi_skill function."""

    def test_creates_destination_tree_and_copies_skill(self, tmp_path: Path) -> None:
        """Should create ~/.pi/agent/skills/ if missing and copy bundled skills."""
        fake_home = tmp_path / "home"
        # Destination tree does NOT pre-exist.
        with patch("cctmux.__main__.Path.home", return_value=fake_home):
            _sync_pi_skill()
        dest = fake_home / ".pi" / "agent" / "skills" / "pi-tmux" / "SKILL.md"
        assert dest.exists(), f"Expected {dest} to exist after sync"
        content = dest.read_text(encoding="utf-8")
        assert "name: pi-tmux" in content

    def test_noop_when_already_in_sync(self, tmp_path: Path) -> None:
        """Second call should not rewrite files when content matches."""
        fake_home = tmp_path / "home"
        with patch("cctmux.__main__.Path.home", return_value=fake_home):
            _sync_pi_skill()
            dest = fake_home / ".pi" / "agent" / "skills" / "pi-tmux" / "SKILL.md"
            mtime_first = dest.stat().st_mtime_ns
            # Call again — should be a no-op.
            _sync_pi_skill()
            mtime_second = dest.stat().st_mtime_ns
        assert mtime_first == mtime_second, "Sync should not touch file when hashes match"

    def test_rewrites_on_content_change(self, tmp_path: Path) -> None:
        """Should rewrite the destination when source hash differs."""
        fake_home = tmp_path / "home"
        with patch("cctmux.__main__.Path.home", return_value=fake_home):
            _sync_pi_skill()
            dest = fake_home / ".pi" / "agent" / "skills" / "pi-tmux" / "SKILL.md"
            # Simulate drift: corrupt the installed copy.
            dest.write_text("stale content\n", encoding="utf-8")
            _sync_pi_skill()
        content = dest.read_text(encoding="utf-8")
        assert "name: pi-tmux" in content
        assert "stale content" not in content
