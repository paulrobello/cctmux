"""Tests for gemtmux functionality."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cctmux.__main__ import gem_app
from cctmux.utils import sanitize_session_name


def _flatten(output: str) -> str:
    """Collapse Rich's line-wrapped console output back to single-spaced text.

    Needed because assertions check multi-word command substrings that Rich
    may wrap across lines depending on terminal width.
    """
    return " ".join(output.split())


class TestGemtmuxCLI:
    """End-to-end tests for the gemtmux CLI callback."""

    def test_dry_run_uses_default_prefix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Session name should start with default 'gem-' prefix."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "-v"])
        assert result.exit_code == 0, result.output
        # Session names are sanitized (underscores -> hyphens)
        expected_prefix = sanitize_session_name(f"gem-{tmp_path.name}")
        assert expected_prefix in result.output

    def test_dry_run_includes_gemini_launch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dry-run output should show a gemini launch command, not claude/codex."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run"])
        assert result.exit_code == 0, result.output
        output = _flatten(result.output)
        assert "send-keys" in output
        assert "gemini Enter" in output
        assert "claude" not in output
        assert "codex" not in output

    def test_dry_run_continue_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-c/--continue should append `--resume latest` to the gemini command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "-c"])
        assert result.exit_code == 0, result.output
        assert "gemini --resume latest" in _flatten(result.output)

    def test_dry_run_resume_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-r/--resume should append `--resume latest` to the gemini command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "-r"])
        assert result.exit_code == 0, result.output
        assert "gemini --resume latest" in _flatten(result.output)

    def test_dry_run_gemini_args(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--gemini-args should be passed through to the gemini command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "--gemini-args", "--model gemini-2.5-pro"])
        assert result.exit_code == 0, result.output
        assert "gemini --model gemini-2.5-pro" in _flatten(result.output)

    def test_dry_run_yolo_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-y/--yolo should append --yolo to the gemini command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "-y"])
        assert result.exit_code == 0, result.output
        assert "gemini --yolo" in _flatten(result.output)

    def test_unknown_layout_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unrecognized layout name should exit non-zero with a clear error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "--layout", "does-not-exist"])
        assert result.exit_code != 0
        assert "Unknown layout" in result.output

    def test_refuses_when_inside_tmux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should exit non-zero if $TMUX is set."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("TMUX", "/tmp/tmux-fake,1234,0")

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run"])
        assert result.exit_code != 0
        assert "Already inside a tmux session" in result.output

    def test_version(self) -> None:
        """--version should print the version and exit 0."""
        runner = CliRunner()
        result = runner.invoke(gem_app, ["--version"])
        assert result.exit_code == 0
        assert "cctmux" in result.output


class TestGemtmuxConfigMerging:
    """Tests for project-config default flag merging."""

    def test_config_default_gemini_args_used(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """default_gemini_args from .cctmux.yaml should be used when no CLI flag given."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)
        (tmp_path / ".cctmux.yaml").write_text("default_gemini_args: '--from-config'\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run"])
        assert result.exit_code == 0, result.output
        assert "gemini --from-config" in _flatten(result.output)

    def test_cli_gemini_args_overrides_config_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--gemini-args on the CLI should fully override the config default, not merge with it."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)
        (tmp_path / ".cctmux.yaml").write_text("default_gemini_args: '--from-config'\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(gem_app, ["--dry-run", "--gemini-args", "--from-cli"])
        assert result.exit_code == 0, result.output
        output = _flatten(result.output)
        assert "gemini --from-cli" in output
        assert "--from-config" not in output
