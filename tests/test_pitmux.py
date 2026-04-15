"""Tests for pitmux functionality."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cctmux.__main__ import _sync_pi_skill, pi_app
from cctmux.utils import sanitize_session_name


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


class TestPitmuxCLI:
    """End-to-end tests for the pitmux CLI callback."""

    def test_dry_run_uses_default_prefix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Session name should start with default 'pi-' prefix."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "-v"])
        assert result.exit_code == 0, result.output
        # Session names are sanitized (underscores -> hyphens)
        expected_prefix = sanitize_session_name(f"pi-{tmp_path.name}")
        assert expected_prefix in result.output

    def test_dry_run_includes_pi_launch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dry-run output should show a pi launch command, not claude."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run"])
        assert result.exit_code == 0, result.output
        assert "send-keys" in result.output
        assert " pi " in result.output or " pi\n" in result.output or " pi Enter" in result.output
        assert "claude" not in result.output

    def test_dry_run_continue_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-c/--continue should append --continue to pi command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "-c"])
        assert result.exit_code == 0, result.output
        assert "pi --continue" in result.output

    def test_dry_run_resume_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-r/--resume should append --resume to pi command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "-r"])
        assert result.exit_code == 0, result.output
        assert "pi --resume" in result.output

    def test_dry_run_pi_args(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--pi-args should be passed through to the pi command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "--pi-args", "--model x"])
        assert result.exit_code == 0, result.output
        assert "pi --model x" in result.output

    def test_refuses_when_inside_tmux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should exit non-zero if $TMUX is set."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("TMUX", "/tmp/tmux-fake,1234,0")

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run"])
        assert result.exit_code != 0
        assert "Already inside a tmux session" in result.output

    def test_version(self) -> None:
        """--version should print the version and exit 0."""
        runner = CliRunner()
        result = runner.invoke(pi_app, ["--version"])
        assert result.exit_code == 0
        assert "cctmux" in result.output
