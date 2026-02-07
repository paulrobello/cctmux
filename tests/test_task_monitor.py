"""Tests for task_monitor module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from cctmux.task_monitor import (
    SessionInfo,
    Task,
    TaskWindow,
    _format_acceptance_criteria,
    _format_work_log,
    build_dependency_graph,
    build_display,
    build_stats,
    build_task_table,
    build_windowed_graph,
    calculate_task_window,
    encode_project_path,
    get_acceptance_completion,
    load_tasks_from_dir,
    resolve_task_path,
)


class TestTask:
    """Tests for Task dataclass."""

    def test_from_json_full(self) -> None:
        """Test creating task from complete JSON."""
        data = {
            "id": "1",
            "subject": "Test task",
            "description": "A test description",
            "activeForm": "Testing task",
            "status": "in_progress",
            "blocks": ["2", "3"],
            "blockedBy": ["0"],
            "owner": "agent-1",
            "metadata": {"type": "test"},
        }
        task = Task.from_json(data)

        assert task.id == "1"
        assert task.subject == "Test task"
        assert task.description == "A test description"
        assert task.active_form == "Testing task"
        assert task.status == "in_progress"
        assert task.blocks == ["2", "3"]
        assert task.blocked_by == ["0"]
        assert task.owner == "agent-1"
        assert task.metadata == {"type": "test"}

    def test_from_json_minimal(self) -> None:
        """Test creating task from minimal JSON."""
        data = {"id": "1", "subject": "Minimal"}
        task = Task.from_json(data)

        assert task.id == "1"
        assert task.subject == "Minimal"
        assert task.status == "pending"
        assert task.blocks == []
        assert task.blocked_by == []

    def test_status_symbol(self) -> None:
        """Test status symbol property."""
        pending = Task(id="1", subject="test", status="pending")
        in_progress = Task(id="2", subject="test", status="in_progress")
        completed = Task(id="3", subject="test", status="completed")

        assert pending.status_symbol == "○"
        assert in_progress.status_symbol == "◐"
        assert completed.status_symbol == "●"

    def test_status_color(self) -> None:
        """Test status color property."""
        pending = Task(id="1", subject="test", status="pending")
        in_progress = Task(id="2", subject="test", status="in_progress")
        completed = Task(id="3", subject="test", status="completed")

        assert pending.status_color == "dim white"
        assert in_progress.status_color == "yellow"
        assert completed.status_color == "green"


class TestLoadTasksFromDir:
    """Tests for load_tasks_from_dir function."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        """Test loading from empty directory."""
        tasks = load_tasks_from_dir(tmp_path)
        assert tasks == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        """Test loading from nonexistent directory."""
        tasks = load_tasks_from_dir(tmp_path / "nonexistent")
        assert tasks == []

    def test_loads_json_files(self, tmp_path: Path) -> None:
        """Test loading JSON task files."""
        (tmp_path / "1.json").write_text(json.dumps({"id": "1", "subject": "Task 1"}), encoding="utf-8")
        (tmp_path / "2.json").write_text(json.dumps({"id": "2", "subject": "Task 2"}), encoding="utf-8")

        tasks = load_tasks_from_dir(tmp_path)

        assert len(tasks) == 2
        assert tasks[0].id == "1"
        assert tasks[1].id == "2"

    def test_sorts_by_numeric_id(self, tmp_path: Path) -> None:
        """Test tasks are sorted by numeric ID."""
        (tmp_path / "10.json").write_text(json.dumps({"id": "10", "subject": "Task 10"}), encoding="utf-8")
        (tmp_path / "2.json").write_text(json.dumps({"id": "2", "subject": "Task 2"}), encoding="utf-8")
        (tmp_path / "1.json").write_text(json.dumps({"id": "1", "subject": "Task 1"}), encoding="utf-8")

        tasks = load_tasks_from_dir(tmp_path)

        assert [t.id for t in tasks] == ["1", "2", "10"]

    def test_ignores_invalid_json(self, tmp_path: Path) -> None:
        """Test invalid JSON files are skipped."""
        (tmp_path / "1.json").write_text(json.dumps({"id": "1", "subject": "Valid"}), encoding="utf-8")
        (tmp_path / "bad.json").write_text("not valid json", encoding="utf-8")

        tasks = load_tasks_from_dir(tmp_path)

        assert len(tasks) == 1
        assert tasks[0].id == "1"

    def test_ignores_lock_files(self, tmp_path: Path) -> None:
        """Test .lock files are ignored."""
        (tmp_path / "1.json").write_text(json.dumps({"id": "1", "subject": "Task"}), encoding="utf-8")
        (tmp_path / ".lock").write_text("", encoding="utf-8")

        tasks = load_tasks_from_dir(tmp_path)

        assert len(tasks) == 1


class TestBuildStats:
    """Tests for build_stats function."""

    def test_empty_tasks(self) -> None:
        """Test stats with no tasks."""
        text = build_stats([], "test-session")
        rendered = text.plain

        assert "test-session" in rendered
        assert "Total: 0" in rendered

    def test_mixed_status(self) -> None:
        """Test stats with mixed task statuses."""
        tasks = [
            Task(id="1", subject="t1", status="pending"),
            Task(id="2", subject="t2", status="in_progress"),
            Task(id="3", subject="t3", status="completed"),
            Task(id="4", subject="t4", status="completed"),
        ]
        text = build_stats(tasks, "my-session")
        rendered = text.plain

        assert "my-session" in rendered
        assert "Total: 4" in rendered
        assert "○ 1" in rendered
        assert "◐ 1" in rendered
        assert "● 2" in rendered
        assert "50% complete" in rendered


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""

    def test_empty_tasks(self) -> None:
        """Test graph with no tasks."""
        text = build_dependency_graph([])
        assert "No tasks found" in text.plain

    def test_single_task(self) -> None:
        """Test graph with single task."""
        tasks = [Task(id="1", subject="Solo task")]
        text = build_dependency_graph(tasks)

        assert "[1]" in text.plain
        assert "Solo task" in text.plain

    def test_tasks_with_dependencies(self) -> None:
        """Test graph shows task dependencies."""
        tasks = [
            Task(id="1", subject="Root task", blocks=["2"]),
            Task(id="2", subject="Dependent task", blocked_by=["1"]),
        ]
        text = build_dependency_graph(tasks)

        assert "[1]" in text.plain
        assert "[2]" in text.plain
        assert "Root task" in text.plain
        assert "Dependent task" in text.plain


class TestEncodeProjectPath:
    """Tests for encode_project_path function."""

    def test_encodes_path(self, tmp_path: Path) -> None:
        """Test path encoding replaces slashes with dashes."""
        result = encode_project_path(tmp_path)
        assert "/" not in result
        assert "-" in result
        assert result.startswith("-")


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_from_index_entry(self, tmp_path: Path) -> None:
        """Test creating SessionInfo from index entry."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()

        entry = {
            "sessionId": "abc123",
            "projectPath": "/some/project",
            "summary": "Test session",
            "modified": "2026-01-30T12:00:00Z",
        }

        info = SessionInfo.from_index_entry(entry, tasks_root)

        assert info.session_id == "abc123"
        assert info.project_path == "/some/project"
        assert info.summary == "Test session"
        assert info.task_path is None  # No task folder exists

    def test_from_index_entry_with_tasks(self, tmp_path: Path) -> None:
        """Test SessionInfo detects existing task folder."""
        tasks_root = tmp_path / "tasks"
        task_folder = tasks_root / "abc123"
        task_folder.mkdir(parents=True)
        (task_folder / "1.json").write_text('{"id": "1", "subject": "Test"}', encoding="utf-8")

        entry = {
            "sessionId": "abc123",
            "projectPath": "/some/project",
            "summary": "Test session",
            "modified": "2026-01-30T12:00:00Z",
        }

        info = SessionInfo.from_index_entry(entry, tasks_root)

        assert info.task_path == task_folder


class TestTaskWindow:
    """Tests for TaskWindow and calculate_task_window."""

    def test_all_tasks_fit(self) -> None:
        """Test when all tasks fit in the window."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(5)]
        window = calculate_task_window(tasks, max_visible=10)

        assert len(window.tasks) == 5
        assert window.start_index == 0
        assert window.end_index == 5
        assert window.total_count == 5
        assert not window.has_tasks_above
        assert not window.has_tasks_below

    def test_windowing_with_active_task(self) -> None:
        """Test windowing keeps active task near top."""
        tasks = [Task(id=str(i), subject=f"Task {i}", status="pending") for i in range(20)]
        tasks[10].status = "in_progress"  # Active task in middle

        window = calculate_task_window(tasks, max_visible=5)

        assert len(window.tasks) == 5
        assert window.total_count == 20
        # Active task should be near top (within context_above=2)
        assert window.start_index <= 10 <= window.end_index
        assert window.has_tasks_above or window.has_tasks_below

    def test_window_counts(self) -> None:
        """Test above/below counts are correct."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(10)]
        window = calculate_task_window(tasks, max_visible=4)

        assert window.tasks_above_count == window.start_index
        assert window.tasks_below_count == 10 - window.end_index

    def test_first_pending_when_no_in_progress(self) -> None:
        """Test focuses on first pending when no in_progress."""
        tasks = [
            Task(id="1", subject="Completed", status="completed"),
            Task(id="2", subject="Completed", status="completed"),
            Task(id="3", subject="Pending", status="pending"),
            Task(id="4", subject="Pending", status="pending"),
            Task(id="5", subject="Pending", status="pending"),
        ]
        window = calculate_task_window(tasks, max_visible=3)

        # Window should include first pending task (index 2)
        # With context_above=2, starts at max(0, 2-2)=0
        assert any(t.status == "pending" for t in window.tasks)


class TestResolveTaskPath:
    """Tests for resolve_task_path function."""

    def test_direct_path(self, tmp_path: Path) -> None:
        """Test resolving a direct path to task folder."""
        task_folder = tmp_path / "my-tasks"
        task_folder.mkdir()
        (task_folder / "1.json").write_text('{"id": "1", "subject": "Test"}', encoding="utf-8")

        path, name = resolve_task_path(session_or_path=str(task_folder))

        assert path == task_folder
        assert name == "my-tasks"

    def test_no_sessions_returns_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error message when no sessions found."""
        # Point to empty tasks directory
        empty_tasks = tmp_path / ".claude" / "tasks"
        empty_tasks.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        path, message = resolve_task_path()

        assert path is None
        assert "No task sessions found" in message

    def test_env_var_task_list_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test CLAUDE_CODE_TASK_LIST_ID environment variable is used."""

        # Create task folder matching env var
        tasks_root = tmp_path / ".claude" / "tasks"
        task_folder = tasks_root / "my-session"
        task_folder.mkdir(parents=True)
        (task_folder / "1.json").write_text('{"id": "1", "subject": "Test"}', encoding="utf-8")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("CLAUDE_CODE_TASK_LIST_ID", "my-session")

        path, name = resolve_task_path()

        assert path == task_folder
        assert "my-session" in name
        assert "from env" in name

    def test_env_var_ignored_when_session_provided(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test CLAUDE_CODE_TASK_LIST_ID is ignored when session_or_path provided."""
        # Create two task folders
        tasks_root = tmp_path / ".claude" / "tasks"
        env_folder = tasks_root / "env-session"
        env_folder.mkdir(parents=True)
        (env_folder / "1.json").write_text('{"id": "1", "subject": "Env"}', encoding="utf-8")

        explicit_folder = tmp_path / "explicit-tasks"
        explicit_folder.mkdir()
        (explicit_folder / "1.json").write_text('{"id": "1", "subject": "Explicit"}', encoding="utf-8")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("CLAUDE_CODE_TASK_LIST_ID", "env-session")

        # Explicit path should be used, not env var
        path, name = resolve_task_path(session_or_path=str(explicit_folder))

        assert path == explicit_folder
        assert name == "explicit-tasks"


class TestFormatAcceptanceCriteria:
    """Tests for _format_acceptance_criteria function."""

    def test_with_dict_items(self) -> None:
        """Should format dict items with checkboxes."""
        metadata = {
            "acceptance_criteria": [
                {"text": "Tests pass", "done": True},
                {"text": "Lint passes", "done": False},
            ]
        }
        result = _format_acceptance_criteria(metadata)
        assert len(result) == 2
        assert "☑" in result[0]
        assert "Tests pass" in result[0]
        assert "☐" in result[1]
        assert "Lint passes" in result[1]

    def test_with_string_items(self) -> None:
        """Should format string items without checkboxes."""
        metadata = {"acceptance_criteria": ["item 1", "item 2"]}
        result = _format_acceptance_criteria(metadata)
        assert len(result) == 2
        assert "☐" in result[0]
        assert "item 1" in result[0]

    def test_empty_criteria(self) -> None:
        """Should return empty list when no criteria."""
        assert _format_acceptance_criteria({}) == []
        assert _format_acceptance_criteria({"acceptance_criteria": None}) == []
        assert _format_acceptance_criteria({"acceptance_criteria": []}) == []

    def test_non_iterable_criteria(self) -> None:
        """Should handle non-iterable criteria gracefully."""
        assert _format_acceptance_criteria({"acceptance_criteria": 42}) == []

    def test_max_items(self) -> None:
        """Should limit to max_items."""
        metadata = {"acceptance_criteria": ["a", "b", "c", "d", "e"]}
        result = _format_acceptance_criteria(metadata, max_items=2)
        assert len(result) == 2


class TestFormatWorkLog:
    """Tests for _format_work_log function."""

    def test_with_dict_entries(self) -> None:
        """Should format dict entries with timestamps."""
        metadata = {
            "work_log": [
                {"timestamp": "2026-01-17T12:00", "action": "Started task"},
                {"action": "Made progress"},
            ]
        }
        result = _format_work_log(metadata)
        assert len(result) == 2
        # Most recent first (reversed)
        assert "Made progress" in result[0]
        assert "Started task" in result[1]

    def test_with_string_entries(self) -> None:
        """Should format string entries with bullets."""
        metadata = {"work_log": ["step 1", "step 2"]}
        result = _format_work_log(metadata)
        assert len(result) == 2
        assert "•" in result[0]

    def test_empty_log(self) -> None:
        """Should return empty list when no work log."""
        assert _format_work_log({}) == []
        assert _format_work_log({"work_log": None}) == []
        assert _format_work_log({"work_log": []}) == []

    def test_non_iterable_log(self) -> None:
        """Should handle non-iterable log gracefully."""
        assert _format_work_log({"work_log": 42}) == []

    def test_max_entries(self) -> None:
        """Should limit to max_entries."""
        metadata = {"work_log": ["a", "b", "c", "d", "e"]}
        result = _format_work_log(metadata, max_entries=2)
        assert len(result) == 2


class TestGetAcceptanceCompletion:
    """Tests for get_acceptance_completion function."""

    def test_with_mixed_completion(self) -> None:
        """Should count completed and total."""
        metadata = {
            "acceptance_criteria": [
                {"text": "Done", "done": True},
                {"text": "Not done", "done": False},
                {"text": "Also done", "done": True},
            ]
        }
        completed, total = get_acceptance_completion(metadata)
        assert completed == 2
        assert total == 3

    def test_empty_criteria(self) -> None:
        """Should return (0, 0) when no criteria."""
        assert get_acceptance_completion({}) == (0, 0)
        assert get_acceptance_completion({"acceptance_criteria": None}) == (0, 0)

    def test_non_iterable(self) -> None:
        """Should return (0, 0) for non-iterable."""
        assert get_acceptance_completion({"acceptance_criteria": 42}) == (0, 0)

    def test_string_items_not_completed(self) -> None:
        """String items should count as not completed."""
        metadata = {"acceptance_criteria": ["item1", "item2"]}
        completed, total = get_acceptance_completion(metadata)
        assert completed == 0
        assert total == 2


class TestBuildTaskTable:
    """Tests for build_task_table function."""

    def _render_table(self, table: Table) -> str:  # noqa: F821
        """Helper to render table to string."""
        from io import StringIO

        from rich.console import Console

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(table)
        return string_io.getvalue()

    def test_basic_rendering(self) -> None:
        """Should render tasks in table."""
        tasks = [
            Task(id="1", subject="Task 1", status="completed"),
            Task(id="2", subject="Task 2", status="in_progress", blocked_by=["1"]),
        ]
        table = build_task_table(tasks)
        output = self._render_table(table)
        assert "Task 1" in output
        assert "Task 2" in output
        assert "completed" in output
        assert "in_progress" in output

    def test_with_owner(self) -> None:
        """Should show owner column."""
        tasks = [Task(id="1", subject="Task", owner="agent-1")]
        table = build_task_table(tasks, show_owner=True)
        output = self._render_table(table)
        assert "agent-1" in output

    def test_without_owner(self) -> None:
        """Should hide owner column when disabled."""
        tasks = [Task(id="1", subject="Task", owner="agent-1")]
        table = build_task_table(tasks, show_owner=False)
        output = self._render_table(table)
        # Owner header should not appear
        assert "Owner" not in output

    def test_with_description(self) -> None:
        """Should show description preview."""
        tasks = [Task(id="1", subject="Task", description="A detailed description here")]
        table = build_task_table(tasks, show_description=True)
        output = self._render_table(table)
        assert "detailed description" in output

    def test_with_metadata(self) -> None:
        """Should show metadata when enabled."""
        tasks = [Task(id="1", subject="Task", metadata={"priority": "high"})]
        table = build_task_table(tasks, show_metadata=True)
        output = self._render_table(table)
        assert "priority=high" in output

    def test_with_acceptance_criteria(self) -> None:
        """Should show acceptance criteria and completion percentage."""
        tasks = [
            Task(
                id="1",
                subject="Task",
                metadata={
                    "acceptance_criteria": [
                        {"text": "Done", "done": True},
                        {"text": "Not done", "done": False},
                    ]
                },
            )
        ]
        table = build_task_table(tasks, show_acceptance=True)
        output = self._render_table(table)
        assert "1/2" in output
        assert "50%" in output

    def test_with_work_log(self) -> None:
        """Should show work log when enabled."""
        tasks = [
            Task(
                id="1",
                subject="Task",
                metadata={"work_log": ["Started work", "Made progress"]},
            )
        ]
        table = build_task_table(tasks, show_work_log=True)
        output = self._render_table(table)
        assert "Started work" in output or "Made progress" in output

    def test_long_subject_truncated(self) -> None:
        """Should truncate long subjects."""
        tasks = [Task(id="1", subject="A" * 100)]
        table = build_task_table(tasks)
        output = self._render_table(table)
        assert "..." in output


class TestBuildStatsWithWindow:
    """Tests for build_stats with window info."""

    def test_stats_with_window_info(self) -> None:
        """Should show window info when windowed."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(20)]
        window = TaskWindow(
            tasks=tasks[:5],
            start_index=5,
            end_index=10,
            total_count=20,
            active_index=0,
        )
        text = build_stats(tasks, "test-session", window=window)
        rendered = text.plain
        assert "showing 5 of 20" in rendered

    def test_stats_without_window(self) -> None:
        """Should not show window info when all tasks fit."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(3)]
        window = TaskWindow(
            tasks=tasks,
            start_index=0,
            end_index=3,
            total_count=3,
            active_index=None,
        )
        text = build_stats(tasks, "test-session", window=window)
        rendered = text.plain
        assert "showing" not in rendered


class TestBuildWindowedGraph:
    """Tests for build_windowed_graph function."""

    def test_with_tasks_above(self) -> None:
        """Should show above indicator."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(5)]
        window = TaskWindow(
            tasks=tasks,
            start_index=5,
            end_index=10,
            total_count=15,
            active_index=0,
        )
        text = build_windowed_graph(window, max_width=80)
        rendered = text.plain
        assert "5 more task(s) above" in rendered

    def test_with_tasks_below(self) -> None:
        """Should show below indicator."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(5)]
        window = TaskWindow(
            tasks=tasks,
            start_index=0,
            end_index=5,
            total_count=15,
            active_index=0,
        )
        text = build_windowed_graph(window, max_width=80)
        rendered = text.plain
        assert "10 more task(s) below" in rendered

    def test_no_indicators_when_all_visible(self) -> None:
        """Should not show indicators when all tasks visible."""
        tasks = [Task(id=str(i), subject=f"Task {i}") for i in range(3)]
        window = TaskWindow(
            tasks=tasks,
            start_index=0,
            end_index=3,
            total_count=3,
            active_index=None,
        )
        text = build_windowed_graph(window, max_width=80)
        rendered = text.plain
        assert "more task" not in rendered


class TestBuildDisplayIntegration:
    """Tests for build_display integration function."""

    def test_renders_full_display(self) -> None:
        """Should render complete display with graph and table."""
        from io import StringIO

        from rich.console import Console

        tasks = [
            Task(id="1", subject="Root task", status="completed", blocks=["2"]),
            Task(id="2", subject="Child task", status="in_progress", blocked_by=["1"]),
        ]
        display = build_display(tasks, "test-session", max_visible=10)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(display)
        output = string_io.getvalue()

        assert "test-session" in output
        assert "Dependency Graph" in output
        assert "Task List" in output
        assert "Root task" in output
        assert "Child task" in output

    def test_graph_only_display(self) -> None:
        """Should render display without table."""
        from io import StringIO

        from rich.console import Console

        tasks = [Task(id="1", subject="Task 1")]
        display = build_display(tasks, "test-session", show_table=False, max_visible=10)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(display)
        output = string_io.getvalue()

        assert "Dependency Graph" in output
        assert "Task List" not in output

    def test_table_only_display(self) -> None:
        """Should render display without graph."""
        from io import StringIO

        from rich.console import Console

        tasks = [Task(id="1", subject="Task 1")]
        display = build_display(tasks, "test-session", show_graph=False, max_visible=10)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(display)
        output = string_io.getvalue()

        assert "Dependency Graph" not in output
        assert "Task List" in output


class TestBuildDependencyGraphExtended:
    """Extended tests for build_dependency_graph function."""

    def test_active_form_display(self) -> None:
        """Should show active form for in-progress tasks."""
        tasks = [Task(id="1", subject="Task", status="in_progress", active_form="Working on it")]
        text = build_dependency_graph(tasks, max_width=120)
        rendered = text.plain
        assert "Working on it" in rendered

    def test_owner_display(self) -> None:
        """Should show owner for tasks with owner."""
        tasks = [Task(id="1", subject="Task", owner="agent-1")]
        text = build_dependency_graph(tasks, max_width=80)
        rendered = text.plain
        assert "@agent-1" in rendered

    def test_deep_nesting_overflow(self) -> None:
        """Should handle deep nesting with overflow markers."""
        # Create a chain of tasks 8 levels deep (beyond max_indent_depth=6)
        tasks = []
        for i in range(8):
            blocks = [str(i + 2)] if i < 7 else []
            blocked_by = [str(i)] if i > 0 else []
            tasks.append(Task(id=str(i + 1), subject=f"Level {i}", blocks=blocks, blocked_by=blocked_by))
        text = build_dependency_graph(tasks, max_width=120, max_indent_depth=3)
        rendered = text.plain
        # Should contain overflow marker for deep levels
        assert "»" in rendered
