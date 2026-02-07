"""Tests for ralph_runner module."""

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cctmux.ralph_runner import (
    IterationResult,
    RalphState,
    RalphStatus,
    TaskProgress,
    build_claude_command,
    build_system_prompt,
    cancel_ralph_loop,
    check_completion_promise,
    init_project_file,
    load_ralph_state,
    parse_claude_json_output,
    parse_task_progress,
    run_ralph_loop,
    save_ralph_state,
)


class TestParseTaskProgress:
    """Tests for markdown checklist parsing."""

    def test_mixed_states(self, tmp_path: Path) -> None:
        """Test parsing file with both checked and unchecked items."""
        project = tmp_path / "project.md"
        project.write_text(
            "# Project\n- [x] Done task\n- [ ] Pending task\n- [x] Another done\n- [ ] Another pending\n",
            encoding="utf-8",
        )
        progress = parse_task_progress(project)
        assert progress.total == 4
        assert progress.completed == 2
        assert progress.percentage == 50.0
        assert not progress.is_all_done

    def test_all_done(self, tmp_path: Path) -> None:
        """Test parsing file with all tasks completed."""
        project = tmp_path / "project.md"
        project.write_text(
            "- [x] Task 1\n- [x] Task 2\n- [x] Task 3\n",
            encoding="utf-8",
        )
        progress = parse_task_progress(project)
        assert progress.total == 3
        assert progress.completed == 3
        assert progress.is_all_done
        assert progress.percentage == 100.0

    def test_no_tasks(self, tmp_path: Path) -> None:
        """Test parsing file with no checklist items."""
        project = tmp_path / "project.md"
        project.write_text("# Just a heading\nSome text.\n", encoding="utf-8")
        progress = parse_task_progress(project)
        assert progress.total == 0
        assert progress.completed == 0
        assert not progress.is_all_done
        assert progress.percentage == 0.0

    def test_nested_lists(self, tmp_path: Path) -> None:
        """Test parsing with indented checklist items."""
        project = tmp_path / "project.md"
        project.write_text(
            "- [x] Top level\n  - [ ] Nested item\n    - [x] Deeply nested\n",
            encoding="utf-8",
        )
        progress = parse_task_progress(project)
        assert progress.total == 3
        assert progress.completed == 2

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Test parsing nonexistent file."""
        progress = parse_task_progress(tmp_path / "missing.md")
        assert progress.total == 0
        assert progress.completed == 0

    def test_case_insensitive_x(self, tmp_path: Path) -> None:
        """Test that both [x] and [X] are recognized."""
        project = tmp_path / "project.md"
        project.write_text(
            "- [x] lowercase\n- [X] uppercase\n- [ ] pending\n",
            encoding="utf-8",
        )
        progress = parse_task_progress(project)
        assert progress.total == 3
        assert progress.completed == 2

    def test_non_checklist_lines_ignored(self, tmp_path: Path) -> None:
        """Test that regular list items and text are not counted."""
        project = tmp_path / "project.md"
        project.write_text(
            "# Title\n- Regular bullet\n- [x] Real task\nSome paragraph text.\n- [ ] Another task\n* Star bullet\n",
            encoding="utf-8",
        )
        progress = parse_task_progress(project)
        assert progress.total == 2
        assert progress.completed == 1


class TestBuildClaudeCommand:
    """Tests for CLI command building."""

    def test_basic_command(self) -> None:
        """Test building a basic command."""
        cmd = build_claude_command(
            prompt="Hello",
            system_prompt_addition="Instructions here",
            permission_mode="acceptEdits",
            model=None,
            max_budget_usd=None,
        )
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert cmd[cmd.index("-p") + 1] == "Hello"
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--permission-mode" in cmd
        assert "acceptEdits" in cmd
        assert "--append-system-prompt" in cmd

    def test_with_model(self) -> None:
        """Test command with model specified."""
        cmd = build_claude_command(
            prompt="Hello",
            system_prompt_addition="Inst",
            permission_mode="acceptEdits",
            model="sonnet",
            max_budget_usd=None,
        )
        assert "--model" in cmd
        assert "sonnet" in cmd

    def test_with_budget(self) -> None:
        """Test command with budget specified."""
        cmd = build_claude_command(
            prompt="Hello",
            system_prompt_addition="Inst",
            permission_mode="acceptEdits",
            model=None,
            max_budget_usd=5.0,
        )
        assert "--max-budget-usd" in cmd
        assert "5.0" in cmd

    def test_with_all_options(self) -> None:
        """Test command with all options set."""
        cmd = build_claude_command(
            prompt="Project content",
            system_prompt_addition="Ralph instructions",
            permission_mode="bypassPermissions",
            model="opus",
            max_budget_usd=10.0,
        )
        assert "--model" in cmd
        assert "opus" in cmd
        assert "--max-budget-usd" in cmd
        assert "10.0" in cmd
        assert "--permission-mode" in cmd
        assert "bypassPermissions" in cmd

    def test_no_model_flag_when_none(self) -> None:
        """Test that --model is omitted when model is None."""
        cmd = build_claude_command(
            prompt="Hello",
            system_prompt_addition="Inst",
            permission_mode="acceptEdits",
            model=None,
            max_budget_usd=None,
        )
        assert "--model" not in cmd

    def test_no_budget_flag_when_none(self) -> None:
        """Test that --max-budget-usd is omitted when budget is None."""
        cmd = build_claude_command(
            prompt="Hello",
            system_prompt_addition="Inst",
            permission_mode="acceptEdits",
            model=None,
            max_budget_usd=None,
        )
        assert "--max-budget-usd" not in cmd


class TestBuildSystemPrompt:
    """Tests for system prompt generation."""

    def test_basic_prompt(self) -> None:
        """Test basic system prompt generation."""
        prompt = build_system_prompt(
            iteration=1,
            max_iterations=10,
            project_file_path="/tmp/project.md",
            completion_promise="All done",
        )
        assert "iteration 1/10" in prompt
        assert "/tmp/project.md" in prompt
        assert "All done" in prompt
        assert "<promise>All done</promise>" in prompt

    def test_unlimited_iterations(self) -> None:
        """Test prompt with unlimited iterations."""
        prompt = build_system_prompt(
            iteration=5,
            max_iterations=0,
            project_file_path="proj.md",
            completion_promise="",
        )
        assert "5/unlimited" in prompt

    def test_no_promise(self) -> None:
        """Test prompt without a completion promise."""
        prompt = build_system_prompt(
            iteration=1,
            max_iterations=10,
            project_file_path="proj.md",
            completion_promise="",
        )
        assert "<promise>" not in prompt
        assert "CRITICAL" not in prompt

    def test_file_path_substitution(self) -> None:
        """Test that the file path appears in the prompt."""
        prompt = build_system_prompt(
            iteration=1,
            max_iterations=5,
            project_file_path="/home/user/ralph-project.md",
            completion_promise="Done",
        )
        assert "/home/user/ralph-project.md" in prompt


class TestParseClaudeJsonOutput:
    """Tests for JSON output parsing."""

    def test_valid_json(self) -> None:
        """Test parsing valid Claude JSON output."""
        data = {
            "result": "I completed the task.",
            "model": "claude-sonnet-4-5-20250929",
            "cost_usd": 1.23,
            "input_tokens": 5000,
            "output_tokens": 2000,
            "cache_read_tokens": 100,
            "cache_creation_tokens": 50,
            "num_turns": 8,
        }
        parsed = parse_claude_json_output(json.dumps(data))
        assert parsed["result_text"] == "I completed the task."
        assert parsed["model"] == "claude-sonnet-4-5-20250929"
        assert parsed["cost_usd"] == 1.23
        assert parsed["input_tokens"] == 5000
        assert parsed["output_tokens"] == 2000
        assert parsed["cache_read_tokens"] == 100
        assert parsed["cache_creation_tokens"] == 50
        assert parsed["tool_calls"] == 8

    def test_invalid_json(self) -> None:
        """Test parsing invalid JSON output."""
        parsed = parse_claude_json_output("not json at all")
        assert parsed["result_text"] == "not json at all"
        assert parsed["input_tokens"] == 0
        assert parsed["cost_usd"] == 0.0

    def test_empty_output(self) -> None:
        """Test parsing empty output."""
        parsed = parse_claude_json_output("")
        assert parsed["result_text"] == ""
        assert parsed["input_tokens"] == 0

    def test_missing_fields(self) -> None:
        """Test parsing JSON with missing optional fields."""
        data = {"result": "Hello"}
        parsed = parse_claude_json_output(json.dumps(data))
        assert parsed["result_text"] == "Hello"
        assert parsed["input_tokens"] == 0
        assert parsed["output_tokens"] == 0
        assert parsed["cost_usd"] == 0.0
        assert parsed["model"] == ""

    def test_truncates_long_result(self) -> None:
        """Test that long result text is truncated."""
        data = {"result": "x" * 1000}
        parsed = parse_claude_json_output(json.dumps(data))
        assert len(parsed["result_text"]) == 500


class TestCheckCompletionPromise:
    """Tests for promise detection."""

    def test_exact_match(self) -> None:
        """Test exact promise match."""
        assert check_completion_promise(
            "Some text <promise>All tests passing</promise> more text",
            "All tests passing",
        )

    def test_no_match(self) -> None:
        """Test when promise is not found."""
        assert not check_completion_promise(
            "Some text without any promise tags",
            "All tests passing",
        )

    def test_wrong_promise_text(self) -> None:
        """Test when promise text doesn't match."""
        assert not check_completion_promise(
            "<promise>Wrong text</promise>",
            "All tests passing",
        )

    def test_empty_text(self) -> None:
        """Test with empty input text."""
        assert not check_completion_promise("", "All tests passing")

    def test_empty_promise(self) -> None:
        """Test with empty promise string."""
        assert not check_completion_promise("<promise>text</promise>", "")

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is stripped from promise text."""
        assert check_completion_promise(
            "<promise> All tests passing </promise>",
            "All tests passing",
        )

    def test_partial_tag(self) -> None:
        """Test that partial tags don't match."""
        assert not check_completion_promise(
            "<promise>All tests passing",
            "All tests passing",
        )


class TestRalphState:
    """Tests for state serialization and persistence."""

    def test_pydantic_serialization(self) -> None:
        """Test that RalphState serializes to JSON correctly."""
        state = RalphState(
            status="active",
            iteration=3,
            max_iterations=20,
            completion_promise="All done",
            started_at="2025-01-15T14:30:00Z",
            project_file="ralph-project.md",
            tasks_total=8,
            tasks_completed=3,
        )
        json_str = state.model_dump_json()
        loaded = RalphState.model_validate_json(json_str)
        assert loaded.status == "active"
        assert loaded.iteration == 3
        assert loaded.tasks_total == 8

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Test saving and loading state file."""
        state = RalphState(
            status="active",
            iteration=2,
            max_iterations=10,
            started_at="2025-01-15T14:30:00Z",
            project_file="test.md",
            tasks_total=5,
            tasks_completed=2,
            iterations=[
                {
                    "number": 1,
                    "duration_seconds": 42.3,
                    "cost_usd": 0.45,
                }
            ],
        )
        save_ralph_state(state, tmp_path)

        loaded = load_ralph_state(tmp_path)
        assert loaded is not None
        assert loaded.status == "active"
        assert loaded.iteration == 2
        assert len(loaded.iterations) == 1
        assert loaded.iterations[0]["cost_usd"] == 0.45

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Test loading when state file doesn't exist."""
        result = load_ralph_state(tmp_path)
        assert result is None

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        """Test loading corrupted state file."""
        state_dir = tmp_path / ".claude"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "ralph-state.json"
        state_file.write_text("not valid json {{{{", encoding="utf-8")

        result = load_ralph_state(tmp_path)
        assert result is None

    def test_atomic_write(self, tmp_path: Path) -> None:
        """Test that save creates .claude directory if missing."""
        state = RalphState(status="active", started_at="2025-01-15T14:30:00Z")
        save_ralph_state(state, tmp_path)

        assert (tmp_path / ".claude" / "ralph-state.json").exists()

    def test_default_values(self) -> None:
        """Test RalphState defaults."""
        state = RalphState()
        assert state.status == "active"
        assert state.iteration == 0
        assert state.max_iterations == 0
        assert state.model is None
        assert state.max_budget_usd is None
        assert state.ended_at is None
        assert state.iterations == []


class TestCancelRalphLoop:
    """Tests for loop cancellation."""

    def test_cancel_active_loop(self, tmp_path: Path) -> None:
        """Test cancelling an active loop."""
        state = RalphState(
            status=RalphStatus.ACTIVE,
            iteration=3,
            started_at="2025-01-15T14:30:00Z",
        )
        save_ralph_state(state, tmp_path)

        result = cancel_ralph_loop(tmp_path)
        assert result is True

        loaded = load_ralph_state(tmp_path)
        assert loaded is not None
        assert loaded.status == RalphStatus.CANCELLED
        assert loaded.ended_at is not None

    def test_cancel_no_state_file(self, tmp_path: Path) -> None:
        """Test cancelling when no state file exists."""
        result = cancel_ralph_loop(tmp_path)
        assert result is False

    def test_cancel_already_completed(self, tmp_path: Path) -> None:
        """Test cancelling an already completed loop."""
        state = RalphState(
            status=RalphStatus.COMPLETED,
            iteration=5,
            started_at="2025-01-15T14:30:00Z",
        )
        save_ralph_state(state, tmp_path)

        result = cancel_ralph_loop(tmp_path)
        assert result is False


class TestInitProjectFile:
    """Tests for project file template generation."""

    def test_default_template(self, tmp_path: Path) -> None:
        """Test generating default template."""
        output = tmp_path / "ralph-project.md"
        init_project_file(output)

        content = output.read_text(encoding="utf-8")
        assert "# Ralph Project:" in content
        assert "- [ ] First task" in content
        assert "- [ ] Second task" in content
        assert "## Description" in content
        assert "## Tasks" in content
        assert "## Notes" in content

    def test_custom_name(self, tmp_path: Path) -> None:
        """Test generating template with custom name."""
        output = tmp_path / "custom.md"
        init_project_file(output, name="Todo REST API")

        content = output.read_text(encoding="utf-8")
        assert "# Ralph Project: Todo REST API" in content

    def test_default_name_when_empty(self, tmp_path: Path) -> None:
        """Test that empty name uses default."""
        output = tmp_path / "test.md"
        init_project_file(output, name="")

        content = output.read_text(encoding="utf-8")
        assert "# Ralph Project: My Project" in content


class TestTaskProgress:
    """Tests for TaskProgress dataclass."""

    def test_percentage_calculation(self) -> None:
        """Test percentage calculation."""
        p = TaskProgress(total=10, completed=3)
        assert p.percentage == 30.0

    def test_percentage_zero_total(self) -> None:
        """Test percentage with zero total."""
        p = TaskProgress(total=0, completed=0)
        assert p.percentage == 0.0

    def test_is_all_done_true(self) -> None:
        """Test is_all_done when complete."""
        p = TaskProgress(total=5, completed=5)
        assert p.is_all_done is True

    def test_is_all_done_false(self) -> None:
        """Test is_all_done when incomplete."""
        p = TaskProgress(total=5, completed=3)
        assert p.is_all_done is False

    def test_is_all_done_zero(self) -> None:
        """Test is_all_done with no tasks."""
        p = TaskProgress(total=0, completed=0)
        assert p.is_all_done is False


class TestIterationResult:
    """Tests for IterationResult.to_dict()."""

    def _make_result(self, **kwargs: Any) -> IterationResult:
        """Helper to create an IterationResult with defaults."""
        defaults: dict[str, Any] = {
            "number": 1,
            "started_at": "2025-01-15T14:30:00+00:00",
            "ended_at": "2025-01-15T14:30:42+00:00",
            "duration_seconds": 42.3,
            "exit_code": 0,
            "input_tokens": 5000,
            "output_tokens": 2000,
            "cache_read_tokens": 100,
            "cache_creation_tokens": 50,
            "cost_usd": 0.45,
            "tool_calls": 12,
            "model": "claude-sonnet-4-5-20250929",
            "result_text": "I completed the task.",
            "promise_found": False,
            "tasks_before": TaskProgress(total=8, completed=0),
            "tasks_after": TaskProgress(total=8, completed=2),
        }
        defaults.update(kwargs)
        return IterationResult(**defaults)

    def test_to_dict_all_fields(self) -> None:
        """Test that to_dict includes all 16 fields with correct types."""
        result = self._make_result()
        d = result.to_dict()

        assert len(d) == 16
        assert d["number"] == 1
        assert d["started_at"] == "2025-01-15T14:30:00+00:00"
        assert d["ended_at"] == "2025-01-15T14:30:42+00:00"
        assert d["duration_seconds"] == 42.3
        assert d["exit_code"] == 0
        assert d["input_tokens"] == 5000
        assert d["output_tokens"] == 2000
        assert d["cache_read_tokens"] == 100
        assert d["cache_creation_tokens"] == 50
        assert d["cost_usd"] == 0.45
        assert d["tool_calls"] == 12
        assert d["model"] == "claude-sonnet-4-5-20250929"
        assert d["result_text"] == "I completed the task."
        assert d["promise_found"] is False
        assert isinstance(d["tasks_before"], dict)
        assert isinstance(d["tasks_after"], dict)

    def test_to_dict_task_progress_nested(self) -> None:
        """Test that tasks_before/tasks_after are dicts with total/completed."""
        result = self._make_result(
            tasks_before=TaskProgress(total=10, completed=3),
            tasks_after=TaskProgress(total=10, completed=7),
        )
        d = result.to_dict()

        assert d["tasks_before"] == {"total": 10, "completed": 3}
        assert d["tasks_after"] == {"total": 10, "completed": 7}


class TestSaveRalphStateErrorPath:
    """Tests for save_ralph_state error handling."""

    def test_save_cleanup_on_write_error(self, tmp_path: Path) -> None:
        """Test that temp file is cleaned up when replace raises OSError."""
        state = RalphState(status="active", started_at="2025-01-15T14:30:00Z")
        state_dir = tmp_path / ".claude"
        state_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("cctmux.ralph_runner.Path.replace", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            save_ralph_state(state, tmp_path)

        # Verify no .tmp files remain
        tmp_files = list(state_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


def _mock_claude_output(
    result: str = "I completed the task.",
    cost_usd: float = 0.50,
    input_tokens: int = 5000,
    output_tokens: int = 2000,
    num_turns: int = 8,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """Generate valid JSON stdout matching Claude's --output-format json."""
    return json.dumps(
        {
            "result": result,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "num_turns": num_turns,
            "model": model,
        }
    )


class TestRunRalphLoop:
    """Tests for the main run_ralph_loop function."""

    def test_missing_project_file(self, tmp_path: Path) -> None:
        """Test that missing project file returns immediately."""
        missing = tmp_path / "nonexistent.md"
        run_ralph_loop(project_file=missing, project_path=tmp_path)

        # No state file should be created
        state = load_ralph_state(tmp_path)
        assert state is None

    def test_all_tasks_already_done(self, tmp_path: Path) -> None:
        """Test that loop exits immediately when all tasks are already done."""
        project = tmp_path / "project.md"
        project.write_text("- [x] Task 1\n- [x] Task 2\n- [x] Task 3\n", encoding="utf-8")

        with patch("cctmux.ralph_runner.subprocess.run") as mock_run:
            run_ralph_loop(project_file=project, project_path=tmp_path)
            mock_run.assert_not_called()

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.COMPLETED
        assert state.ended_at is not None

    def test_max_iterations_reached(self, tmp_path: Path) -> None:
        """Test that loop stops when max_iterations is reached."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n- [ ] Task 2\n", encoding="utf-8")

        mock_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_mock_claude_output(),
            stderr="",
        )

        with (
            patch("cctmux.ralph_runner.subprocess.run", return_value=mock_result),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(
                project_file=project,
                max_iterations=1,
                project_path=tmp_path,
            )

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.MAX_REACHED
        assert len(state.iterations) == 1

    def test_promise_found_in_output(self, tmp_path: Path) -> None:
        """Test that loop exits when promise is found in output."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n", encoding="utf-8")

        mock_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_mock_claude_output(result="Done! <promise>All tests passing</promise>"),
            stderr="",
        )

        with (
            patch("cctmux.ralph_runner.subprocess.run", return_value=mock_result),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(
                project_file=project,
                completion_promise="All tests passing",
                project_path=tmp_path,
            )

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.COMPLETED
        assert state.iterations[0]["promise_found"] is True

    def test_nonzero_exit_code_stops_loop(self, tmp_path: Path) -> None:
        """Test that nonzero exit code results in ERROR status."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n", encoding="utf-8")

        mock_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=1,
            stdout=_mock_claude_output(),
            stderr="some error",
        )

        with (
            patch("cctmux.ralph_runner.subprocess.run", return_value=mock_result),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(project_file=project, project_path=tmp_path)

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.ERROR
        assert len(state.iterations) == 1

    def test_subprocess_exception(self, tmp_path: Path) -> None:
        """Test that subprocess.run raising an exception results in ERROR."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n", encoding="utf-8")

        with (
            patch("cctmux.ralph_runner.subprocess.run", side_effect=OSError("command not found")),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(project_file=project, project_path=tmp_path)

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.ERROR

    def test_external_cancellation(self, tmp_path: Path) -> None:
        """Test that external cancellation via state file stops the loop."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n- [ ] Task 2\n", encoding="utf-8")

        mock_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_mock_claude_output(),
            stderr="",
        )

        def mock_sleep(_seconds: float) -> None:
            # Between iteration 1 and 2, simulate external cancel
            st = load_ralph_state(tmp_path)
            if st and st.iterations:
                st.status = RalphStatus.CANCELLED
                save_ralph_state(st, tmp_path)

        with (
            patch("cctmux.ralph_runner.subprocess.run", return_value=mock_result),
            patch("cctmux.ralph_runner.time.sleep", side_effect=mock_sleep),
        ):
            run_ralph_loop(project_file=project, project_path=tmp_path)

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.CANCELLED
        assert len(state.iterations) == 1

    def test_ctrl_c_cancellation(self, tmp_path: Path) -> None:
        """Test that Ctrl+C signal handler sets CANCELLED status."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n- [ ] Task 2\n", encoding="utf-8")

        captured_handler: Any = None

        original_signal = __import__("signal").signal

        def capture_signal(signum: int, handler: Any) -> Any:
            nonlocal captured_handler
            if signum == __import__("signal").SIGINT:
                captured_handler = handler
            return original_signal(signum, handler)

        def mock_subprocess_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            # Simulate Ctrl+C during first iteration
            if captured_handler is not None:
                captured_handler(2, None)
            return subprocess.CompletedProcess(
                args=["claude"],
                returncode=0,
                stdout=_mock_claude_output(),
                stderr="",
            )

        with (
            patch("cctmux.ralph_runner.signal.signal", side_effect=capture_signal),
            patch("cctmux.ralph_runner.subprocess.run", side_effect=mock_subprocess_run),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(project_file=project, project_path=tmp_path)

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.CANCELLED

    def test_task_completion_after_iteration(self, tmp_path: Path) -> None:
        """Test that loop detects all tasks completed after an iteration."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n- [ ] Task 2\n", encoding="utf-8")

        def mock_subprocess_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            # Simulate Claude completing all tasks by rewriting the file
            project.write_text("- [x] Task 1\n- [x] Task 2\n", encoding="utf-8")
            return subprocess.CompletedProcess(
                args=["claude"],
                returncode=0,
                stdout=_mock_claude_output(),
                stderr="",
            )

        with (
            patch("cctmux.ralph_runner.subprocess.run", side_effect=mock_subprocess_run),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(project_file=project, project_path=tmp_path)

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert state.status == RalphStatus.COMPLETED
        assert state.tasks_completed == 2
        assert state.tasks_total == 2

    def test_iteration_state_tracking(self, tmp_path: Path) -> None:
        """Test that iterations list grows and tasks_before/tasks_after are correct."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n- [ ] Task 2\n- [ ] Task 3\n", encoding="utf-8")

        mock_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_mock_claude_output(),
            stderr="",
        )

        with (
            patch("cctmux.ralph_runner.subprocess.run", return_value=mock_result),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(
                project_file=project,
                max_iterations=2,
                project_path=tmp_path,
            )

        state = load_ralph_state(tmp_path)
        assert state is not None
        assert len(state.iterations) == 2
        assert state.iterations[0]["number"] == 1
        assert state.iterations[1]["number"] == 2
        # tasks_before should have total/completed structure
        assert "total" in state.iterations[0]["tasks_before"]
        assert "completed" in state.iterations[0]["tasks_before"]

    def test_final_summary_output(self, tmp_path: Path) -> None:
        """Test that final summary includes cost/token aggregation."""
        project = tmp_path / "project.md"
        project.write_text("- [ ] Task 1\n", encoding="utf-8")

        mock_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_mock_claude_output(cost_usd=1.50, input_tokens=10000, output_tokens=3000),
            stderr="",
        )

        with (
            patch("cctmux.ralph_runner.subprocess.run", return_value=mock_result),
            patch("cctmux.ralph_runner.time.sleep"),
        ):
            run_ralph_loop(
                project_file=project,
                max_iterations=1,
                project_path=tmp_path,
            )

        state = load_ralph_state(tmp_path)
        assert state is not None
        total_cost = sum(it.get("cost_usd", 0.0) for it in state.iterations)
        assert total_cost == 1.50
        total_in = sum(it.get("input_tokens", 0) for it in state.iterations)
        assert total_in == 10000
