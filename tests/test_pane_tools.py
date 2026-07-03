"""Tests for pane_tools: pane listing, JSON output, and idle detection."""

import json
import subprocess
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cctmux.__main__ import app
from cctmux.pane_tools import (
    DEFAULT_BUSY_PATTERN,
    PaneInfo,
    WaitResult,
    list_panes,
    panes_to_json,
    wait_for_idle,
)

runner = CliRunner()

_PANE_LINE = "%1\t1.0\t1\tclaude\t120\t40\t/Users/foo/project\tmy-title"
_PANE_LINE_2 = "%2\t1.1\t0\tzsh\t120\t20\t/Users/foo/project\tother title with spaces"


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestListPanes:
    def test_parses_panes(self) -> None:
        with patch("cctmux.pane_tools.subprocess.run", return_value=_completed(f"{_PANE_LINE}\n{_PANE_LINE_2}\n")):
            panes = list_panes("mysession")
        assert len(panes) == 2
        assert panes[0] == PaneInfo(
            pane_id="%1",
            index="1.0",
            active=True,
            command="claude",
            width=120,
            height=40,
            path="/Users/foo/project",
            title="my-title",
        )
        assert panes[1].active is False
        assert panes[1].title == "other title with spaces"

    def test_targets_requested_session(self) -> None:
        with patch("cctmux.pane_tools.subprocess.run", return_value=_completed(_PANE_LINE)) as mock_run:
            list_panes("mysession")
        cmd = mock_run.call_args[0][0]
        assert "list-panes" in cmd
        assert "mysession" in cmd
        assert "-s" in cmd

    def test_tmux_failure_raises(self) -> None:
        with (
            patch(
                "cctmux.pane_tools.subprocess.run",
                return_value=_completed(returncode=1, stderr="no such session: nope"),
            ),
            pytest.raises(RuntimeError, match="no such session"),
        ):
            list_panes("nope")

    def test_skips_malformed_lines(self) -> None:
        with patch("cctmux.pane_tools.subprocess.run", return_value=_completed(f"garbage\n{_PANE_LINE}\n")):
            panes = list_panes("mysession")
        assert len(panes) == 1


class TestPanesToJson:
    def test_round_trips(self) -> None:
        panes = [
            PaneInfo(
                pane_id="%1",
                index="1.0",
                active=True,
                command="claude",
                width=120,
                height=40,
                path="/p",
                title="t",
            )
        ]
        data = json.loads(panes_to_json(panes))
        assert data == [
            {
                "pane_id": "%1",
                "index": "1.0",
                "active": True,
                "command": "claude",
                "width": 120,
                "height": 40,
                "path": "/p",
                "title": "t",
            }
        ]


class TestBusyPattern:
    @pytest.mark.parametrize(
        "text",
        [
            "✻ Pondering… (12s · esc to interrupt)",
            "(48s · ↓ 2.7k tokens · thinking with high effort)",
            "esc to interrupt",
            "✽ working",
            "12.3k tokens",
            "· Implementing commands… (5m 22s · ↓ 20.6k tokens)",
        ],
    )
    def test_busy_signatures_match(self, text: str) -> None:
        import re

        assert re.search(DEFAULT_BUSY_PATTERN, text)

    @pytest.mark.parametrize(
        "text",
        [
            "$ ",
            '> Try "fix the bug"',
            "Welcome to Claude Code",
            "❯ 1. Yes\n  2. No",
        ],
    )
    def test_idle_content_does_not_match(self, text: str) -> None:
        import re

        assert not re.search(DEFAULT_BUSY_PATTERN, text)


class TestWaitForIdle:
    def _run(self, captures: list[str], **kwargs: Any) -> WaitResult:
        outputs = [_completed(c) for c in captures]
        with (
            patch("cctmux.pane_tools.subprocess.run", side_effect=outputs),
            patch("cctmux.pane_tools.time.sleep"),
        ):
            return wait_for_idle("%1", **kwargs)

    def test_idle_after_silence(self) -> None:
        # busy once, then quiet: with silence=2 and interval=1, two quiet polls confirm idle
        result = self._run(
            ["✻ working (5s · esc to interrupt)", "$ done", "$ done"],
            timeout=60,
            interval=1,
            silence=2,
        )
        assert result.state == "idle"
        assert result.tail == ["$ done"]

    def test_timeout_while_busy(self) -> None:
        result = self._run(
            ["✻ (1s", "✻ (2s", "✻ (3s", "✻ (4s"],
            timeout=3,
            interval=1,
            silence=2,
        )
        assert result.state == "timeout"
        assert result.elapsed == 3

    def test_busy_resets_silence_clock(self) -> None:
        # quiet, busy, quiet, quiet — the busy capture must reset the miss count.
        # Without the reset, idle would be declared at elapsed=1 (two straight misses).
        result = self._run(
            ["$", "✻ (9s", "$", "$"],
            timeout=60,
            interval=1,
            silence=2,
        )
        assert result.state == "idle"
        assert result.elapsed == 3

    def test_custom_pattern(self) -> None:
        result = self._run(
            ["MYSPINNER", "quiet", "quiet"],
            timeout=60,
            interval=1,
            silence=2,
            pattern="MYSPINNER",
        )
        assert result.state == "idle"

    def test_pane_gone_raises(self) -> None:
        with (
            patch(
                "cctmux.pane_tools.subprocess.run",
                return_value=_completed(returncode=1, stderr="can't find pane: %9"),
            ),
            pytest.raises(RuntimeError, match="can't find pane"),
        ):
            wait_for_idle("%9", timeout=1, interval=1)


class TestPanesCommand:
    def test_json_output(self) -> None:
        with patch("cctmux.pane_tools.subprocess.run", return_value=_completed(f"{_PANE_LINE}\n")):
            result = runner.invoke(app, ["panes", "--session", "mysession", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["pane_id"] == "%1"
        assert data[0]["command"] == "claude"

    def test_table_output(self) -> None:
        with patch("cctmux.pane_tools.subprocess.run", return_value=_completed(f"{_PANE_LINE}\n")):
            result = runner.invoke(app, ["panes", "--session", "mysession"])
        assert result.exit_code == 0
        assert "%1" in result.output
        assert "claude" in result.output

    def test_session_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CCTMUX_SESSION", "env-session")
        with patch("cctmux.pane_tools.subprocess.run", return_value=_completed(f"{_PANE_LINE}\n")) as mock_run:
            result = runner.invoke(app, ["panes", "--json"])
        assert result.exit_code == 0
        assert "env-session" in mock_run.call_args[0][0]

    def test_no_session_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CCTMUX_SESSION", raising=False)
        monkeypatch.delenv("TMUX", raising=False)
        result = runner.invoke(app, ["panes"])
        assert result.exit_code == 1
        assert "No session" in result.output

    def test_unknown_session_errors(self) -> None:
        with patch(
            "cctmux.pane_tools.subprocess.run",
            return_value=_completed(returncode=1, stderr="no such session: nope"),
        ):
            result = runner.invoke(app, ["panes", "--session", "nope"])
        assert result.exit_code == 1
        assert "no such session" in result.output

    def test_subcommand_skips_skill_sync(self) -> None:
        """Inspection subcommands must not trigger skill auto-sync.

        ``_sync_skill`` prints a one-line notice to stdout when it applies an
        update; if it ran for ``panes``, that notice would prefix the ``--json``
        output and break JSON consumers (agents parsing ``cctmux panes --json``).
        This regressed on fresh installs where the skill was absent.
        """
        with (
            patch("cctmux.pane_tools.subprocess.run", return_value=_completed(f"{_PANE_LINE}\n")),
            patch("cctmux.__main__._sync_skill_dir") as mock_sync_dir,
        ):
            result = runner.invoke(app, ["panes", "--session", "mysession", "--json"])
        assert result.exit_code == 0
        mock_sync_dir.assert_not_called()


class TestWaitIdleCommand:
    def test_idle_exit_zero(self) -> None:
        fake = WaitResult(state="idle", elapsed=60.0, tail=["$ prompt"])
        with patch("cctmux.__main__.wait_for_idle", return_value=fake) as mock_wait:
            result = runner.invoke(app, ["wait-idle", "%1"])
        assert result.exit_code == 0
        assert "IDLE" in result.output
        assert mock_wait.call_args[0][0] == "%1"

    def test_timeout_exit_two(self) -> None:
        fake = WaitResult(state="timeout", elapsed=300.0, tail=["✻ still going"])
        with patch("cctmux.__main__.wait_for_idle", return_value=fake):
            result = runner.invoke(app, ["wait-idle", "%1"])
        assert result.exit_code == 2
        assert "HEARTBEAT" in result.output

    def test_json_output(self) -> None:
        fake = WaitResult(state="idle", elapsed=60.0, tail=["$ prompt"])
        with patch("cctmux.__main__.wait_for_idle", return_value=fake):
            result = runner.invoke(app, ["wait-idle", "%1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {"state": "idle", "elapsed": 60.0, "tail": ["$ prompt"]}

    def test_options_forwarded(self) -> None:
        fake = WaitResult(state="idle", elapsed=1.0, tail=[])
        with patch("cctmux.__main__.wait_for_idle", return_value=fake) as mock_wait:
            result = runner.invoke(
                app,
                ["wait-idle", "%1", "--timeout", "30", "--interval", "2", "--silence", "6", "--lines", "50"],
            )
        assert result.exit_code == 0
        kwargs = mock_wait.call_args[1]
        assert kwargs["timeout"] == 30
        assert kwargs["interval"] == 2
        assert kwargs["silence"] == 6
        assert kwargs["lines"] == 50

    def test_pane_gone_exit_one(self) -> None:
        with patch("cctmux.__main__.wait_for_idle", side_effect=RuntimeError("can't find pane: %9")):
            result = runner.invoke(app, ["wait-idle", "%9"])
        assert result.exit_code == 1
        assert "can't find pane" in result.output
