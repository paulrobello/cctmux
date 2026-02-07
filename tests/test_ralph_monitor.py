"""Tests for ralph_monitor module."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from cctmux.ralph_monitor import (
    RalphMonitorConfig,
    _format_tokens,
    _get_nested_int,
    build_iteration_table,
    build_iteration_timeline,
    build_ralph_display,
    build_ralph_status_panel,
    build_task_progress_panel,
)
from cctmux.ralph_runner import RalphState, RalphStatus


def _make_state(**kwargs: object) -> RalphState:
    """Helper to create a RalphState with defaults."""
    defaults: dict[str, object] = {
        "status": RalphStatus.ACTIVE,
        "iteration": 3,
        "max_iterations": 20,
        "completion_promise": "All tests passing",
        "started_at": "2025-01-15T14:30:00+00:00",
        "project_file": "ralph-project.md",
        "tasks_total": 8,
        "tasks_completed": 3,
        "iterations": [],
    }
    defaults.update(kwargs)
    return RalphState.model_validate(defaults)


def _make_iteration(number: int = 1, **kwargs: object) -> dict[str, object]:
    """Helper to create an iteration dict."""
    defaults: dict[str, object] = {
        "number": number,
        "started_at": "2025-01-15T14:30:00+00:00",
        "ended_at": "2025-01-15T14:30:42+00:00",
        "duration_seconds": 42.3,
        "exit_code": 0,
        "input_tokens": 12340,
        "output_tokens": 5670,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "cost_usd": 0.45,
        "tool_calls": 12,
        "model": "claude-sonnet-4-5-20250929",
        "result_text": "I completed the task.",
        "promise_found": False,
        "tasks_before": {"total": 8, "completed": 0},
        "tasks_after": {"total": 8, "completed": 2},
    }
    defaults.update(kwargs)
    return defaults


def _render_to_str(panel: Panel | Text) -> str:
    """Render a Rich Panel/Text to string for assertions."""
    console = Console(file=None, force_terminal=True, width=80)
    with console.capture() as capture:
        console.print(panel)
    return capture.get()


class TestBuildRalphStatusPanel:
    """Tests for status panel rendering."""

    def test_active_status(self) -> None:
        """Test active status display."""
        state = _make_state(status=RalphStatus.ACTIVE)
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "ACTIVE" in output
        assert "3/20" in output

    def test_completed_status(self) -> None:
        """Test completed status display."""
        state = _make_state(
            status=RalphStatus.COMPLETED,
            ended_at="2025-01-15T14:35:00+00:00",
        )
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "COMPLETED" in output

    def test_cancelled_status(self) -> None:
        """Test cancelled status display."""
        state = _make_state(status=RalphStatus.CANCELLED)
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "CANCELLED" in output

    def test_max_reached_status(self) -> None:
        """Test max_reached status display."""
        state = _make_state(status=RalphStatus.MAX_REACHED)
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "MAX_REACHED" in output

    def test_task_progress_bar(self) -> None:
        """Test task progress bar display."""
        state = _make_state(tasks_total=8, tasks_completed=3)
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "3/8" in output
        assert "38%" in output

    def test_no_tasks(self) -> None:
        """Test display with no tasks."""
        state = _make_state(tasks_total=0, tasks_completed=0)
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "none detected" in output

    def test_promise_display(self) -> None:
        """Test promise text display."""
        state = _make_state(completion_promise="All tests passing")
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "All tests passing" in output

    def test_token_totals(self) -> None:
        """Test token/cost totals with iterations."""
        state = _make_state(
            iterations=[
                _make_iteration(1, cost_usd=0.45, input_tokens=5000, output_tokens=2000, tool_calls=10),
                _make_iteration(2, cost_usd=1.20, input_tokens=8000, output_tokens=3000, tool_calls=15),
            ],
        )
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "$1.65" in output
        assert "25" in output  # total tools

    def test_unlimited_iterations(self) -> None:
        """Test display with unlimited iterations."""
        state = _make_state(max_iterations=0, iteration=5)
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        # Should not show "/0"
        assert "/0" not in output


class TestBuildIterationTable:
    """Tests for iteration table rendering."""

    def test_empty_iterations(self) -> None:
        """Test table with no iterations."""
        state = _make_state(iterations=[])
        panel = build_iteration_table(state)
        output = _render_to_str(panel)
        assert "Iterations" in output

    def test_populated_table(self) -> None:
        """Test table with iterations."""
        state = _make_state(
            iterations=[
                _make_iteration(1, duration_seconds=42.3, cost_usd=0.45, tool_calls=12),
                _make_iteration(2, duration_seconds=68.0, cost_usd=1.82, tool_calls=18),
            ],
        )
        panel = build_iteration_table(state)
        output = _render_to_str(panel)
        assert "42s" in output
        assert "$0.45" in output
        assert "1m 8s" in output
        assert "$1.82" in output

    def test_windowed_table(self) -> None:
        """Test table windowing when too many iterations."""
        iterations = [_make_iteration(i) for i in range(1, 30)]
        state = _make_state(iterations=iterations)
        panel = build_iteration_table(state, max_visible=5)
        output = _render_to_str(panel)
        # Should show last 5 iterations
        assert "29" in output
        assert "25" in output

    def test_tasks_completed_column(self) -> None:
        """Test tasks completed delta column."""
        state = _make_state(
            iterations=[
                _make_iteration(
                    1,
                    tasks_before={"total": 8, "completed": 0},
                    tasks_after={"total": 8, "completed": 2},
                ),
            ],
        )
        panel = build_iteration_table(state)
        output = _render_to_str(panel)
        assert "+2" in output

    def test_promise_outcome(self) -> None:
        """Test promise found outcome in table."""
        state = _make_state(
            iterations=[_make_iteration(1, promise_found=True)],
        )
        panel = build_iteration_table(state)
        output = _render_to_str(panel)
        assert "promise" in output

    def test_error_outcome(self) -> None:
        """Test error outcome in table."""
        state = _make_state(
            iterations=[_make_iteration(1, exit_code=1)],
        )
        panel = build_iteration_table(state)
        output = _render_to_str(panel)
        assert "error" in output


class TestBuildIterationTimeline:
    """Tests for timeline visualization."""

    def test_empty_timeline(self) -> None:
        """Test timeline with no iterations."""
        state = _make_state(iterations=[])
        panel = build_iteration_timeline(state)
        output = _render_to_str(panel)
        assert "No iterations yet" in output

    def test_proportional_widths(self) -> None:
        """Test that timeline renders bars."""
        state = _make_state(
            status=RalphStatus.COMPLETED,
            iterations=[
                _make_iteration(1, duration_seconds=30.0),
                _make_iteration(2, duration_seconds=60.0),
            ],
        )
        panel = build_iteration_timeline(state)
        output = _render_to_str(panel)
        assert "30s" in output
        assert "1m 0s" in output

    def test_in_progress_indicator(self) -> None:
        """Test running iteration shows 'running...'."""
        state = _make_state(
            status=RalphStatus.ACTIVE,
            iterations=[
                _make_iteration(1, duration_seconds=30.0),
                _make_iteration(2, duration_seconds=10.0),
            ],
        )
        panel = build_iteration_timeline(state)
        output = _render_to_str(panel)
        assert "running" in output


class TestBuildTaskProgressPanel:
    """Tests for task checklist rendering."""

    def test_renders_checklist(self, tmp_path: Path) -> None:
        """Test rendering checklist from project file."""
        project = tmp_path / "project.md"
        project.write_text(
            "# Project\n- [x] Done task\n- [ ] Pending task\n",
            encoding="utf-8",
        )
        state = _make_state(project_file=str(project))
        panel = build_task_progress_panel(state, project)
        output = _render_to_str(panel)
        assert "Done task" in output
        assert "Pending task" in output

    def test_no_file(self) -> None:
        """Test rendering when no project file exists."""
        state = _make_state(project_file="/nonexistent/file.md")
        panel = build_task_progress_panel(state, Path("/nonexistent/file.md"))
        output = _render_to_str(panel)
        assert "No project file found" in output

    def test_no_checklist_items(self, tmp_path: Path) -> None:
        """Test rendering file without checklist items."""
        project = tmp_path / "project.md"
        project.write_text("# Just a heading\n", encoding="utf-8")
        state = _make_state(project_file=str(project))
        panel = build_task_progress_panel(state, project)
        output = _render_to_str(panel)
        assert "No checklist items found" in output


class TestBuildRalphDisplay:
    """Tests for full display assembly."""

    def test_no_state(self) -> None:
        """Test display when no state is available."""
        config = RalphMonitorConfig()
        display = build_ralph_display(None, config)
        console = Console(file=None, force_terminal=True, width=80)
        with console.capture() as capture:
            console.print(display)
        output = capture.get()
        assert "Waiting for Ralph Loop" in output

    def test_with_state(self) -> None:
        """Test display with valid state."""
        state = _make_state(
            iterations=[_make_iteration(1)],
        )
        config = RalphMonitorConfig()
        display = build_ralph_display(state, config)
        console = Console(file=None, force_terminal=True, width=80)
        with console.capture() as capture:
            console.print(display)
        output = capture.get()
        assert "Ralph Loop" in output
        assert "ACTIVE" in output

    def test_config_hides_panels(self) -> None:
        """Test that config toggles hide panels."""
        state = _make_state(iterations=[_make_iteration(1)])
        config = RalphMonitorConfig(
            show_table=False,
            show_timeline=False,
            show_task_progress=False,
        )
        display = build_ralph_display(state, config)
        console = Console(file=None, force_terminal=True, width=80)
        with console.capture() as capture:
            console.print(display)
        output = capture.get()
        # Should only have the status panel
        assert "Ralph Loop" in output
        assert "Iterations" not in output
        assert "Timeline" not in output


class TestLoadRalphState:
    """Tests for state loading via the monitor."""

    def test_missing_file(self, tmp_path: Path) -> None:
        """Test loading when state file doesn't exist."""
        from cctmux.ralph_runner import load_ralph_state

        result = load_ralph_state(tmp_path)
        assert result is None

    def test_valid_file(self, tmp_path: Path) -> None:
        """Test loading valid state file."""
        from cctmux.ralph_runner import load_ralph_state, save_ralph_state

        state = _make_state()
        save_ralph_state(state, tmp_path)
        loaded = load_ralph_state(tmp_path)
        assert loaded is not None
        assert loaded.status == RalphStatus.ACTIVE

    def test_corrupted_file(self, tmp_path: Path) -> None:
        """Test loading corrupted state file."""
        from cctmux.ralph_runner import load_ralph_state

        state_dir = tmp_path / ".claude"
        state_dir.mkdir()
        (state_dir / "ralph-state.json").write_text("{{bad json", encoding="utf-8")
        result = load_ralph_state(tmp_path)
        assert result is None


class TestGetNestedInt:
    """Tests for _get_nested_int helper."""

    def test_valid_nested_int(self) -> None:
        """Test happy path returns correct int."""
        data = {"tasks_before": {"total": 8, "completed": 3}}
        assert _get_nested_int(data, "tasks_before", "completed") == 3

    def test_missing_outer_key(self) -> None:
        """Test returns 0 when outer key is missing."""
        data: dict[str, object] = {"other_key": {"completed": 3}}
        assert _get_nested_int(data, "tasks_before", "completed") == 0  # type: ignore[arg-type]

    def test_missing_inner_key(self) -> None:
        """Test returns 0 when inner key is missing."""
        data = {"tasks_before": {"total": 8}}
        assert _get_nested_int(data, "tasks_before", "completed") == 0  # type: ignore[arg-type]

    def test_non_dict_outer_value(self) -> None:
        """Test returns 0 when outer value is not a dict."""
        data: dict[str, object] = {"tasks_before": "not_a_dict"}
        assert _get_nested_int(data, "tasks_before", "completed") == 0  # type: ignore[arg-type]

    def test_invalid_int_value(self) -> None:
        """Test returns 0 when inner value is not convertible to int."""
        data = {"tasks_before": {"completed": "not_a_number"}}
        assert _get_nested_int(data, "tasks_before", "completed") == 0  # type: ignore[arg-type]


class TestFormatTokensExtended:
    """Extended tests for _format_tokens."""

    def test_million_range(self) -> None:
        """Test formatting tokens in the millions."""
        assert _format_tokens(1_000_000) == "1.0M"
        assert _format_tokens(5_500_000) == "5.5M"

    def test_thousands_range(self) -> None:
        """Test formatting tokens in the thousands."""
        assert _format_tokens(1_000) == "1.0K"
        assert _format_tokens(12_340) == "12.3K"

    def test_small_range(self) -> None:
        """Test formatting tokens below 1000."""
        assert _format_tokens(0) == "0"
        assert _format_tokens(999) == "999"


class TestFormatDurationExtended:
    """Extended tests for _format_duration."""

    def test_hours_range(self) -> None:
        """Test formatting durations in the hours range."""
        from cctmux.ralph_monitor import _format_duration

        assert _format_duration(3661) == "1h 1m"
        assert _format_duration(7200) == "2h 0m"


class TestBuildRalphStatusPanelExtended:
    """Extended tests for status panel edge cases."""

    def test_malformed_timestamp(self) -> None:
        """Test that malformed started_at timestamp does not crash."""
        state = _make_state(started_at="not-a-valid-timestamp")
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        # Should render without elapsed time but not crash
        assert "ACTIVE" in output
        assert "Elapsed" not in output

    def test_elapsed_with_ended_at(self) -> None:
        """Test elapsed time uses ended_at for completed state."""
        state = _make_state(
            status=RalphStatus.COMPLETED,
            started_at="2025-01-15T14:30:00+00:00",
            ended_at="2025-01-15T14:35:00+00:00",
        )
        panel = build_ralph_status_panel(state)
        output = _render_to_str(panel)
        assert "COMPLETED" in output
        assert "5m 0s" in output


class TestBuildIterationTimelineExtended:
    """Extended tests for timeline visualization."""

    def test_zero_duration(self) -> None:
        """Test that zero-duration iterations don't cause ZeroDivisionError."""
        state = _make_state(
            status=RalphStatus.COMPLETED,
            iterations=[
                _make_iteration(1, duration_seconds=0.0),
                _make_iteration(2, duration_seconds=0.0),
            ],
        )
        # Should not raise ZeroDivisionError
        panel = build_iteration_timeline(state)
        output = _render_to_str(panel)
        assert "0s" in output


class TestBuildIterationTableExtended:
    """Extended tests for iteration table."""

    def test_running_iteration(self) -> None:
        """Test that a running iteration shows 'running' and '-' for dur/cost."""
        running_iter = _make_iteration(1)
        # Remove ended_at to simulate running
        running_iter.pop("ended_at", None)

        state = _make_state(
            status=RalphStatus.ACTIVE,
            iterations=[running_iter],
        )
        panel = build_iteration_table(state)
        output = _render_to_str(panel)
        assert "running" in output
