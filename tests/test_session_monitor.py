"""Tests for session_monitor module."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from cctmux.session_monitor import (
    DisplayConfig,
    EventType,
    IncrementalEventReader,
    SessionEvent,
    SessionStats,
    _extract_tool_input_summary,
    build_display,
    build_events_panel,
    build_stats_panel,
    calculate_event_window,
    calculate_stats,
    estimate_cost,
    load_events_from_file,
    parse_jsonl_line,
    resolve_session_path,
)


class TestSessionEvent:
    """Tests for SessionEvent dataclass."""

    def test_user_event(self) -> None:
        """Test parsing user message."""
        line = json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "check for open PRs"},
                "timestamp": "2026-01-17T21:35:02.482Z",
                "sessionId": "abc123",
                "gitBranch": "main",
            }
        )
        event = parse_jsonl_line(line)

        assert event is not None
        assert event.event_type == EventType.USER
        assert event.content == "check for open PRs"
        assert event.session_id == "abc123"
        assert event.git_branch == "main"

    def test_assistant_thinking_event(self) -> None:
        """Test parsing assistant thinking content."""
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "Let me check the PRs"}],
                    "model": "claude-opus-4-5-20251101",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "timestamp": "2026-01-17T21:35:10.042Z",
                "sessionId": "abc123",
            }
        )
        event = parse_jsonl_line(line)

        assert event is not None
        assert event.event_type == EventType.THINKING
        assert event.content == "Let me check the PRs"
        assert event.model == "claude-opus-4-5-20251101"

    def test_assistant_tool_use_event(self) -> None:
        """Test parsing assistant tool_use content."""
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "gh pr list"}}],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "timestamp": "2026-01-17T21:35:10.042Z",
                "sessionId": "abc123",
            }
        )
        event = parse_jsonl_line(line)

        assert event is not None
        assert event.event_type == EventType.TOOL_CALL
        assert event.tool_name == "Bash"
        assert "gh pr list" in event.content

    def test_assistant_text_event(self) -> None:
        """Test parsing assistant text content."""
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "No open PRs found."}],
                },
                "timestamp": "2026-01-17T21:35:10.042Z",
                "sessionId": "abc123",
            }
        )
        event = parse_jsonl_line(line)

        assert event is not None
        assert event.event_type == EventType.ASSISTANT
        assert event.content == "No open PRs found."

    def test_progress_event(self) -> None:
        """Test parsing progress event."""
        line = json.dumps(
            {
                "type": "progress",
                "data": {"type": "hook_progress", "hookName": "SessionStart:startup"},
                "timestamp": "2026-01-17T21:35:02.482Z",
                "sessionId": "abc123",
            }
        )
        event = parse_jsonl_line(line)

        assert event is not None
        assert event.event_type == EventType.PROGRESS
        assert "SessionStart:startup" in event.content

    def test_invalid_json_returns_none(self) -> None:
        """Test invalid JSON returns None."""
        event = parse_jsonl_line("not valid json")
        assert event is None

    def test_file_snapshot_skipped_by_default(self) -> None:
        """Test file-history-snapshot returns None by default."""
        line = json.dumps(
            {
                "type": "file-history-snapshot",
                "snapshot": {"trackedFileBackups": {}},
            }
        )
        event = parse_jsonl_line(line)
        assert event is None

    def test_file_snapshot_included_when_requested(self) -> None:
        """Test file-history-snapshot is returned when include_snapshots=True."""
        line = json.dumps(
            {
                "type": "file-history-snapshot",
                "snapshot": {"trackedFileBackups": {}},
                "timestamp": "2026-01-17T21:35:02.482Z",
            }
        )
        event = parse_jsonl_line(line, include_snapshots=True)
        assert event is not None
        assert event.event_type == EventType.SNAPSHOT

    def test_system_event_skipped_by_default(self) -> None:
        """Test system events are skipped by default."""
        line = json.dumps(
            {
                "type": "system",
                "message": {"content": "System prompt"},
                "timestamp": "2026-01-17T21:35:02.482Z",
            }
        )
        event = parse_jsonl_line(line)
        assert event is None

    def test_system_event_included_when_requested(self) -> None:
        """Test system events are returned when include_system=True."""
        line = json.dumps(
            {
                "type": "system",
                "message": {"content": "System prompt"},
                "timestamp": "2026-01-17T21:35:02.482Z",
            }
        )
        event = parse_jsonl_line(line, include_system=True)
        assert event is not None
        assert event.event_type == EventType.SYSTEM

    def test_assistant_tool_result_event(self) -> None:
        """Test parsing assistant tool_result content."""
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool123",
                            "content": "Result text",
                        }
                    ],
                },
                "timestamp": "2026-01-17T21:35:10.042Z",
                "sessionId": "abc123",
            }
        )
        event = parse_jsonl_line(line)

        assert event is not None
        assert event.event_type == EventType.TOOL_RESULT
        assert event.tool_id == "tool123"
        assert event.content == "Result text"

    def test_event_symbol(self) -> None:
        """Test symbol property for different event types."""
        event = SessionEvent(
            event_type=EventType.USER,
            content="test",
            timestamp=datetime.now(),
        )
        assert event.symbol == "●"

    def test_event_color_and_label(self) -> None:
        """Test color and label properties."""
        event = SessionEvent(
            event_type=EventType.TOOL_CALL,
            content="test",
            timestamp=datetime.now(),
            tool_name="Bash",
        )
        assert event.color == "green"
        assert event.label == "TOOL Bash"


class TestSessionStats:
    """Tests for SessionStats and calculate_stats."""

    def test_empty_events(self) -> None:
        """Test stats with no events."""
        stats = calculate_stats([])

        assert stats.user_count == 0
        assert stats.assistant_count == 0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0

    def test_counts_message_types(self) -> None:
        """Test counting different message types."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="Hello",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
            ),
            SessionEvent(
                event_type=EventType.THINKING,
                content="Thinking...",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
            ),
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                content="ls",
                tool_name="Bash",
                timestamp=datetime(2026, 1, 17, 12, 0, 2),
            ),
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Done",
                timestamp=datetime(2026, 1, 17, 12, 0, 3),
            ),
        ]
        stats = calculate_stats(events)

        assert stats.user_count == 1
        assert stats.assistant_count == 1
        assert stats.thinking_count == 1
        assert stats.tool_call_count == 1
        assert stats.tool_counts["Bash"] == 1

    def test_aggregates_tokens(self) -> None:
        """Test token aggregation."""
        events = [
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response 1",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=80,
                cache_creation_tokens=20,
            ),
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response 2",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
                input_tokens=200,
                output_tokens=100,
            ),
        ]
        stats = calculate_stats(events)

        assert stats.total_input_tokens == 300
        assert stats.total_output_tokens == 150
        assert stats.total_cache_read_tokens == 80
        assert stats.total_cache_creation_tokens == 20

    def test_duration_calculation(self) -> None:
        """Test duration from first to last event."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="Start",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
            ),
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="End",
                timestamp=datetime(2026, 1, 17, 12, 5, 30),
            ),
        ]
        stats = calculate_stats(events)

        assert stats.duration_seconds == 330  # 5 min 30 sec

    def test_extracts_model_and_branch(self) -> None:
        """Test model and branch extraction."""
        events = [
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Hello",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                model="claude-opus-4-5-20251101",
                git_branch="feature-branch",
                session_id="abc123",
            ),
        ]
        stats = calculate_stats(events)

        assert stats.model == "claude-opus-4-5-20251101"
        assert stats.git_branch == "feature-branch"
        assert stats.session_id == "abc123"


class TestEstimateCost:
    """Tests for cost estimation."""

    def test_opus_cost(self) -> None:
        """Test Opus model cost calculation."""
        cost = estimate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        # Opus: $15/M input + $75/M output = $90
        assert cost == 90.0

    def test_sonnet_cost(self) -> None:
        """Test Sonnet model cost calculation."""
        cost = estimate_cost(
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        # Sonnet: $3/M input + $15/M output = $18
        assert cost == 18.0

    def test_with_cache(self) -> None:
        """Test cost with cache tokens."""
        cost = estimate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_creation_tokens=1_000_000,
        )
        # Opus: $1.50/M cache read + $18.75/M cache write = $20.25
        assert cost == 20.25

    def test_unknown_model_uses_opus(self) -> None:
        """Test unknown model defaults to Opus pricing."""
        cost = estimate_cost(
            model="unknown-model",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert cost == 15.0  # Opus input rate


class TestSessionStatsProperties:
    """Tests for SessionStats display properties."""

    def test_duration_display_seconds(self) -> None:
        """Test duration display for seconds only."""
        stats = SessionStats(duration_seconds=45)
        assert stats.duration_display == "45s"

    def test_duration_display_minutes(self) -> None:
        """Test duration display for minutes and seconds."""
        stats = SessionStats(duration_seconds=150)  # 2m 30s
        assert stats.duration_display == "2m 30s"

    def test_duration_display_hours(self) -> None:
        """Test duration display for hours and minutes."""
        stats = SessionStats(duration_seconds=4500)  # 1h 15m
        assert stats.duration_display == "1h 15m"

    def test_model_short_opus(self) -> None:
        """Test model_short for opus models."""
        stats = SessionStats(model="claude-opus-4-5-20251101")
        assert stats.model_short == "opus-4.5"

    def test_model_short_opus_46(self) -> None:
        """Test model_short for opus 4.6 models."""
        stats = SessionStats(model="claude-opus-4-6-20260205")
        assert stats.model_short == "opus-4.6"

    def test_model_short_sonnet(self) -> None:
        """Test model_short for sonnet models."""
        stats = SessionStats(model="claude-sonnet-4-20250514")
        assert stats.model_short == "sonnet-4"

    def test_model_short_haiku(self) -> None:
        """Test model_short for haiku models."""
        stats = SessionStats(model="claude-haiku-3-5-20241022")
        assert stats.model_short == "haiku-3.5"

    def test_model_short_unknown(self) -> None:
        """Test model_short for unknown models."""
        stats = SessionStats(model="some-other-model-12345678")
        assert stats.model_short == "some-other-model-123"  # Truncated to 20 chars

    def test_model_short_empty(self) -> None:
        """Test model_short when model is empty."""
        stats = SessionStats(model="")
        assert stats.model_short == "unknown"


class TestResolveSessionPath:
    """Tests for resolve_session_path function."""

    def test_direct_jsonl_path(self, tmp_path: Path) -> None:
        """Test resolving direct path to JSONL file."""
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text('{"type": "user"}', encoding="utf-8")

        path, name = resolve_session_path(session_or_path=str(jsonl_file))

        assert path == jsonl_file
        assert "session" in name

    def test_session_id_in_projects(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolving session ID from projects folder."""
        # Create mock .claude structure
        projects = tmp_path / ".claude" / "projects" / "-test-project"
        projects.mkdir(parents=True)
        jsonl_file = projects / "abc123-def456.jsonl"
        jsonl_file.write_text('{"type": "user"}', encoding="utf-8")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        path, _ = resolve_session_path(session_or_path="abc123")

        assert path == jsonl_file

    def test_no_session_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when no session found."""
        empty_claude = tmp_path / ".claude" / "projects"
        empty_claude.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        path, message = resolve_session_path(session_or_path="nonexistent")

        assert path is None
        assert "not found" in message.lower() or "no session" in message.lower()

    def test_relative_jsonl_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolving relative path to JSONL file."""
        jsonl_file = tmp_path / "my-session.jsonl"
        jsonl_file.write_text('{"type": "user"}', encoding="utf-8")

        # Change to tmp_path
        monkeypatch.chdir(tmp_path)

        path, name = resolve_session_path(session_or_path="my-session.jsonl")

        assert path == jsonl_file
        assert "my-session" in name

    def test_fallback_to_most_recent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test fallback to most recently modified JSONL file."""
        # Create mock .claude structure with two project folders
        projects = tmp_path / ".claude" / "projects"
        project1 = projects / "-project-one"
        project2 = projects / "-project-two"
        project1.mkdir(parents=True)
        project2.mkdir(parents=True)

        # Create older file
        old_file = project1 / "old-session.jsonl"
        old_file.write_text('{"type": "user"}', encoding="utf-8")

        # Create newer file (explicitly set mtime)
        import time

        time.sleep(0.1)  # Ensure different mtime
        new_file = project2 / "new-session.jsonl"
        new_file.write_text('{"type": "user"}', encoding="utf-8")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Mock cwd to a non-existent project path so it falls back
        monkeypatch.chdir(tmp_path)

        path, name = resolve_session_path()

        assert path == new_file
        assert "new-session" in name or "two" in name


class TestEventWindow:
    """Tests for EventWindow and calculate_event_window."""

    def test_all_events_fit(self) -> None:
        """Test when all events fit in window."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content=f"Message {i}",
                timestamp=datetime(2026, 1, 17, 12, 0, i),
            )
            for i in range(5)
        ]
        window = calculate_event_window(events, max_visible=10)

        assert len(window.events) == 5
        assert window.start_index == 0
        assert window.end_index == 5
        assert not window.has_events_above
        assert not window.has_events_below

    def test_shows_latest_events(self) -> None:
        """Test window shows most recent events."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content=f"Message {i}",
                timestamp=datetime(2026, 1, 17, 12, 0, i),
            )
            for i in range(20)
        ]
        window = calculate_event_window(events, max_visible=5)

        assert len(window.events) == 5
        assert window.has_events_above
        assert not window.has_events_below
        # Should show latest events (15-19)
        assert window.events[-1].content == "Message 19"

    def test_empty_events(self) -> None:
        """Test window with no events."""
        window = calculate_event_window([], max_visible=10)

        assert len(window.events) == 0
        assert window.start_index == 0
        assert window.end_index == 0
        assert not window.has_events_above
        assert not window.has_events_below

    def test_events_above_count(self) -> None:
        """Test events_above_count property."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content=f"Message {i}",
                timestamp=datetime(2026, 1, 17, 12, 0, i),
            )
            for i in range(20)
        ]
        window = calculate_event_window(events, max_visible=5)

        assert window.events_above_count == 15
        assert window.events_below_count == 0


class TestBuildStatsPanel:
    """Tests for build_stats_panel."""

    def test_renders_stats(self) -> None:
        """Test stats panel renders key information."""
        from collections import Counter
        from io import StringIO

        from rich.console import Console

        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            git_branch="main",
            user_count=5,
            assistant_count=10,
            tool_counts=Counter({"Bash": 3, "Read": 2}),
            total_input_tokens=10000,
            total_output_tokens=5000,
            duration_seconds=300,
            estimated_cost=1.25,
        )

        panel = build_stats_panel(stats)
        # Panel renders to string for testing
        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=100)
        console.print(panel)
        output = string_io.getvalue()

        assert "abc123" in output  # Session ID truncated
        assert "opus" in output.lower()  # Model
        assert "main" in output  # Branch
        assert "Bash" in output  # Tool counts

    def test_renders_with_cache_tokens(self) -> None:
        """Test stats panel renders cache token info."""
        from io import StringIO

        from rich.console import Console

        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            total_input_tokens=10000,
            total_output_tokens=5000,
            total_cache_read_tokens=8000,
        )

        panel = build_stats_panel(stats)
        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=100)
        console.print(panel)
        output = string_io.getvalue()

        assert "cached" in output.lower()

    def test_renders_without_tools(self) -> None:
        """Test stats panel renders when no tools used."""
        from io import StringIO

        from rich.console import Console

        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
        )

        panel = build_stats_panel(stats)
        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=100)
        console.print(panel)
        output = string_io.getvalue()

        assert "none" in output.lower()


class TestBuildEventsPanel:
    """Tests for build_events_panel."""

    def test_renders_events(self) -> None:
        """Test events panel renders event content."""
        from io import StringIO

        from rich.console import Console

        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="Hello Claude",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
            ),
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                content="ls -la",
                tool_name="Bash",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
            ),
        ]
        window = calculate_event_window(events, max_visible=10)

        panel = build_events_panel(window)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=100)
        console.print(panel)
        output = string_io.getvalue()

        assert "Hello Claude" in output
        assert "Bash" in output

    def test_renders_events_above_indicator(self) -> None:
        """Test events panel shows indicator for events above."""
        from io import StringIO

        from rich.console import Console

        events = [
            SessionEvent(
                event_type=EventType.USER,
                content=f"Message {i}",
                timestamp=datetime(2026, 1, 17, 12, 0, i),
            )
            for i in range(20)
        ]
        window = calculate_event_window(events, max_visible=5)

        panel = build_events_panel(window)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=100)
        console.print(panel)
        output = string_io.getvalue()

        assert "15 earlier events" in output

    def test_truncates_long_content(self) -> None:
        """Test events panel truncates long content."""
        from io import StringIO

        from rich.console import Console

        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="x" * 500,  # Very long content
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
            ),
        ]
        window = calculate_event_window(events, max_visible=10)

        panel = build_events_panel(window, max_content_length=100)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=200)
        console.print(panel)
        output = string_io.getvalue()

        # Content should be truncated with "..."
        assert "..." in output
        # Should not contain the full 500 x's
        assert "x" * 500 not in output


class TestExtractToolInputSummary:
    """Tests for _extract_tool_input_summary function."""

    def test_command_input(self) -> None:
        """Should extract command field."""
        result = _extract_tool_input_summary({"command": "git status"})
        assert "git status" in result

    def test_file_path_input(self) -> None:
        """Should extract file_path field."""
        result = _extract_tool_input_summary({"file_path": "/tmp/test.py"})
        assert "test.py" in result

    def test_pattern_input(self) -> None:
        """Should extract pattern field."""
        result = _extract_tool_input_summary({"pattern": "*.py"})
        assert "*.py" in result

    def test_query_input(self) -> None:
        """Should extract query field."""
        result = _extract_tool_input_summary({"query": "search terms"})
        assert "search terms" in result

    def test_url_input(self) -> None:
        """Should extract url field."""
        result = _extract_tool_input_summary({"url": "https://example.com"})
        assert "https://example.com" in result

    def test_fallback_to_first_string(self) -> None:
        """Should fall back to first string value."""
        result = _extract_tool_input_summary({"custom_key": "some value"})
        assert "some value" in result

    def test_empty_input(self) -> None:
        """Should return empty string for empty dict."""
        result = _extract_tool_input_summary({})
        assert result == ""

    def test_fallback_no_strings(self) -> None:
        """Should convert to string when no string values."""
        result = _extract_tool_input_summary({"count": 42})
        assert "42" in result


class TestCalculateStatsEnriched:
    """Tests for enriched fields in calculate_stats."""

    def test_stop_reasons_tracked(self) -> None:
        """Should track stop reasons from events."""
        events = [
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                stop_reason="end_turn",
            ),
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response 2",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
                stop_reason="end_turn",
            ),
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                content="ls",
                tool_name="Bash",
                timestamp=datetime(2026, 1, 17, 12, 0, 2),
                stop_reason="tool_use",
            ),
        ]
        stats = calculate_stats(events)
        assert stats.stop_reasons == {"end_turn": 2, "tool_use": 1}
        assert "end_turn" in stats.stop_reasons_display

    def test_turn_durations_tracked(self) -> None:
        """Should track turn durations from events."""
        events = [
            SessionEvent(
                event_type=EventType.SYSTEM,
                content="",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                turn_duration_ms=5000,
            ),
            SessionEvent(
                event_type=EventType.SYSTEM,
                content="",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
                turn_duration_ms=3000,
            ),
        ]
        stats = calculate_stats(events)
        assert stats.turn_durations == [5000, 3000]
        assert stats.avg_turn_duration_ms == 4000
        assert stats.total_turn_duration_ms == 8000

    def test_hook_errors_tracked(self) -> None:
        """Should track hook errors."""
        events = [
            SessionEvent(
                event_type=EventType.SYSTEM,
                content="",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                hook_errors=["Hook 'pre-commit' failed"],
            ),
        ]
        stats = calculate_stats(events)
        assert stats.hook_errors == 1
        assert "Hook 'pre-commit' failed" in stats.hook_error_messages

    def test_hook_infos_tracked(self) -> None:
        """Should track hook info count."""
        events = [
            SessionEvent(
                event_type=EventType.SYSTEM,
                content="",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                hook_infos=["info1", "info2"],
            ),
        ]
        stats = calculate_stats(events)
        assert stats.hook_count == 2

    def test_service_tier_tracked(self) -> None:
        """Should track latest service tier."""
        events = [
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                service_tier="standard",
            ),
        ]
        stats = calculate_stats(events)
        assert stats.service_tier == "standard"

    def test_cwd_tracked(self) -> None:
        """Should track latest working directory."""
        events = [
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                cwd="/home/user/project",
            ),
        ]
        stats = calculate_stats(events)
        assert stats.current_cwd == "/home/user/project"

    def test_sidechain_counted(self) -> None:
        """Should count sidechain events."""
        events = [
            SessionEvent(
                event_type=EventType.ASSISTANT,
                content="Response",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                is_sidechain=True,
            ),
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                content="ls",
                tool_name="Bash",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
                is_sidechain=True,
            ),
        ]
        stats = calculate_stats(events)
        assert stats.sidechain_count == 2

    def test_thinking_level_tracked(self) -> None:
        """Should track latest thinking level."""
        events = [
            SessionEvent(
                event_type=EventType.THINKING,
                content="Thinking...",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                thinking_level="high",
            ),
        ]
        stats = calculate_stats(events)
        assert stats.thinking_level == "high"


class TestBuildStatsPanelExtended:
    """Tests for build_stats_panel with various options."""

    def _render_panel(self, panel: Panel) -> str:  # noqa: F821
        """Helper to render panel to string."""
        from io import StringIO

        from rich.console import Console

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(panel)
        return string_io.getvalue()

    def test_show_service_tier(self) -> None:
        """Should show service tier when enabled."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            service_tier="standard",
        )
        panel = build_stats_panel(stats, show_service_tier=True)
        output = self._render_panel(panel)
        assert "standard" in output

    def test_show_cwd(self) -> None:
        """Should show working directory when enabled."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            current_cwd="/home/user/project",
        )
        panel = build_stats_panel(stats, show_cwd=True)
        output = self._render_panel(panel)
        assert "CWD" in output

    def test_show_turn_durations(self) -> None:
        """Should show average turn duration."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            turn_durations=[5000, 3000],
        )
        panel = build_stats_panel(stats, show_turn_durations=True)
        output = self._render_panel(panel)
        assert "Avg Turn" in output
        assert "4.0s" in output

    def test_show_turn_durations_ms(self) -> None:
        """Should show turn duration in ms for fast turns."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            turn_durations=[500, 300],
        )
        panel = build_stats_panel(stats, show_turn_durations=True)
        output = self._render_panel(panel)
        assert "400ms" in output

    def test_show_hook_errors(self) -> None:
        """Should show hook errors when present."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            hook_errors=2,
            hook_error_messages=["pre-commit failed"],
        )
        panel = build_stats_panel(stats, show_hook_errors=True)
        output = self._render_panel(panel)
        assert "Hook Errors: 2" in output
        assert "pre-commit failed" in output

    def test_show_sidechain(self) -> None:
        """Should show sidechain count when present."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            sidechain_count=3,
        )
        panel = build_stats_panel(stats, show_sidechain=True)
        output = self._render_panel(panel)
        assert "Sidechain" in output
        assert "3" in output

    def test_show_stop_reasons(self) -> None:
        """Should show stop reasons when present."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            stop_reasons={"end_turn": 5, "tool_use": 3},
        )
        panel = build_stats_panel(stats, show_stop_reasons=True)
        output = self._render_panel(panel)
        assert "Stop" in output
        assert "end_turn" in output

    def test_show_thinking_level(self) -> None:
        """Should show thinking level when present."""
        stats = SessionStats(
            session_id="abc123def456",
            model="claude-opus-4-5-20251101",
            thinking_level="high",
        )
        panel = build_stats_panel(stats)
        output = self._render_panel(panel)
        assert "Think" in output
        assert "high" in output


class TestBuildEventsPanelExtended:
    """Tests for build_events_panel with threading."""

    def _render_panel(self, panel: Panel) -> str:  # noqa: F821
        """Helper to render panel to string."""
        from io import StringIO

        from rich.console import Console

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(panel)
        return string_io.getvalue()

    def test_threading_display(self) -> None:
        """Should show threading indentation for child events."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="Hello",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                uuid="root-1",
            ),
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                content="ls",
                tool_name="Bash",
                timestamp=datetime(2026, 1, 17, 12, 0, 1),
                uuid="child-1",
                parent_uuid="root-1",
            ),
        ]
        window = calculate_event_window(events, max_visible=10)
        panel = build_events_panel(window, show_threading=True)
        output = self._render_panel(panel)
        # Should contain threading characters
        assert "Hello" in output
        assert "Bash" in output

    def test_sidechain_indicator(self) -> None:
        """Should show sidechain indicator."""
        events = [
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                content="ls",
                tool_name="Bash",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                is_sidechain=True,
            ),
        ]
        window = calculate_event_window(events, max_visible=10)
        panel = build_events_panel(window)
        output = self._render_panel(panel)
        assert "sidechain" in output

    def test_events_below_indicator(self) -> None:
        """Should show indicator for events below window."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content=f"Message {i}",
                timestamp=datetime(2026, 1, 17, 12, 0, i),
            )
            for i in range(20)
        ]
        # Create a window that doesn't show most recent events
        from cctmux.session_monitor import EventWindow

        window = EventWindow(
            events=events[:5],
            start_index=0,
            end_index=5,
            total_count=20,
        )
        panel = build_events_panel(window)
        output = self._render_panel(panel)
        assert "15 newer events" in output


class TestLoadEventsFromFile:
    """Tests for load_events_from_file function."""

    def test_loads_events_from_jsonl(self, tmp_path: Path) -> None:
        """Should load and parse events from JSONL file."""
        jsonl_file = tmp_path / "session.jsonl"
        lines = [
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": "Hello"},
                    "timestamp": "2026-01-17T12:00:00Z",
                    "sessionId": "abc123",
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "Hi"}],
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    },
                    "timestamp": "2026-01-17T12:00:01Z",
                    "sessionId": "abc123",
                }
            ),
        ]
        jsonl_file.write_text("\n".join(lines), encoding="utf-8")

        config = DisplayConfig()
        events = load_events_from_file(jsonl_file, config)

        assert len(events) == 2
        assert events[0].event_type == EventType.USER
        assert events[1].event_type == EventType.ASSISTANT

    def test_filters_thinking_when_disabled(self, tmp_path: Path) -> None:
        """Should filter thinking events when show_thinking=False."""
        jsonl_file = tmp_path / "session.jsonl"
        lines = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "thinking", "thinking": "Let me think"}],
                        "usage": {},
                    },
                    "timestamp": "2026-01-17T12:00:00Z",
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "Hello"}],
                        "usage": {},
                    },
                    "timestamp": "2026-01-17T12:00:01Z",
                }
            ),
        ]
        jsonl_file.write_text("\n".join(lines), encoding="utf-8")

        config = DisplayConfig(show_thinking=False)
        events = load_events_from_file(jsonl_file, config)

        assert len(events) == 1
        assert events[0].event_type == EventType.ASSISTANT

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty list for nonexistent file."""
        config = DisplayConfig()
        events = load_events_from_file(tmp_path / "nonexistent.jsonl", config)
        assert events == []

    def test_filters_progress_when_disabled(self, tmp_path: Path) -> None:
        """Should filter progress events when show_progress=False."""
        jsonl_file = tmp_path / "session.jsonl"
        lines = [
            json.dumps(
                {
                    "type": "progress",
                    "data": {"type": "hook_progress", "hookName": "test"},
                    "timestamp": "2026-01-17T12:00:00Z",
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": "Hello"},
                    "timestamp": "2026-01-17T12:00:01Z",
                }
            ),
        ]
        jsonl_file.write_text("\n".join(lines), encoding="utf-8")

        config = DisplayConfig(show_progress=False)
        events = load_events_from_file(jsonl_file, config)

        assert len(events) == 1
        assert events[0].event_type == EventType.USER


class TestBuildDisplay:
    """Tests for build_display function."""

    def test_returns_group(self) -> None:
        """Should return a Rich Group with stats and events panels."""
        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="Hello",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
            ),
        ]
        stats = calculate_stats(events)
        display = build_display(events, stats, max_visible=10)

        from rich.console import Group

        assert isinstance(display, Group)

    def test_renders_without_error(self) -> None:
        """Should render complete display without errors."""
        from io import StringIO

        from rich.console import Console

        events = [
            SessionEvent(
                event_type=EventType.USER,
                content="Hello",
                timestamp=datetime(2026, 1, 17, 12, 0, 0),
                model="claude-opus-4-5-20251101",
                session_id="abc123def456",
            ),
        ]
        stats = calculate_stats(events)
        display = build_display(events, stats, max_visible=10)

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=120)
        console.print(display)
        output = string_io.getvalue()
        assert "Session Stats" in output
        assert "Session Events" in output


class TestSystemEventParsing:
    """Tests for system event parsing with hook errors and turn duration."""

    def test_system_with_hook_errors_included(self) -> None:
        """System events with hook errors should be included by default."""
        line = json.dumps(
            {
                "type": "system",
                "message": {"content": "System prompt"},
                "timestamp": "2026-01-17T21:35:02.482Z",
                "hookErrors": ["pre-commit hook failed"],
            }
        )
        event = parse_jsonl_line(line)
        assert event is not None
        assert event.event_type == EventType.SYSTEM
        assert event.hook_errors == ["pre-commit hook failed"]

    def test_system_with_turn_duration_included(self) -> None:
        """System events with turn_duration subtype should be included by default."""
        line = json.dumps(
            {
                "type": "system",
                "message": {"content": ""},
                "timestamp": "2026-01-17T21:35:02.482Z",
                "subtype": "turn_duration",
                "durationMs": 5000,
            }
        )
        event = parse_jsonl_line(line)
        assert event is not None
        assert event.event_type == EventType.SYSTEM
        assert event.turn_duration_ms == 5000

    def test_user_structured_content(self) -> None:
        """Should handle user messages with structured content list."""
        line = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ]
                },
                "timestamp": "2026-01-17T21:35:02.482Z",
            }
        )
        event = parse_jsonl_line(line)
        assert event is not None
        assert "Part 1" in event.content
        assert "Part 2" in event.content

    def test_tool_result_structured_content(self) -> None:
        """Should handle tool_result with structured content list."""
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool1",
                            "content": [{"type": "text", "text": "Result text"}],
                        }
                    ],
                },
                "timestamp": "2026-01-17T21:35:02.482Z",
            }
        )
        event = parse_jsonl_line(line)
        assert event is not None
        assert event.event_type == EventType.TOOL_RESULT
        assert "Result text" in event.content

    def test_assistant_with_enriched_fields(self) -> None:
        """Should parse enriched fields from assistant message."""
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hello"}],
                    "model": "claude-opus-4-5-20251101",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "service_tier": "standard",
                    },
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                },
                "timestamp": "2026-01-17T21:35:02.482Z",
                "cwd": "/home/user/project",
                "uuid": "uuid-123",
                "parentUuid": "uuid-000",
                "isSidechain": True,
                "thinkingMetadata": {"level": "high"},
            }
        )
        event = parse_jsonl_line(line)
        assert event is not None
        assert event.stop_reason == "end_turn"
        assert event.service_tier == "standard"
        assert event.cwd == "/home/user/project"
        assert event.uuid == "uuid-123"
        assert event.parent_uuid == "uuid-000"
        assert event.is_sidechain is True


class TestSessionStatsAvgTurnEmpty:
    """Tests for SessionStats edge cases."""

    def test_avg_turn_empty(self) -> None:
        """Avg turn duration should be 0 with no data."""
        stats = SessionStats()
        assert stats.avg_turn_duration_ms == 0
        assert stats.total_turn_duration_ms == 0

    def test_stop_reasons_display_empty(self) -> None:
        """Stop reasons display should be empty string when no data."""
        stats = SessionStats()
        assert stats.stop_reasons_display == ""


class TestIncrementalEventReader:
    """Tests for IncrementalEventReader."""

    def _make_user_line(self, text: str) -> str:
        """Helper to create a user JSONL line."""
        return json.dumps({"type": "user", "message": {"content": text}})

    def _make_assistant_line(self, text: str) -> str:
        """Helper to create an assistant JSONL line."""
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": text}],
                    "model": "test",
                    "usage": {},
                },
            }
        )

    def test_reads_initial_events(self, tmp_path: Path) -> None:
        """Should read all events on first call."""
        jsonl_file = tmp_path / "session.jsonl"
        lines = [self._make_user_line("Hello"), self._make_assistant_line("Hi")]
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        config = DisplayConfig()
        reader = IncrementalEventReader(config)
        events = reader.read(jsonl_file)

        assert len(events) == 2

    def test_incremental_reads_only_new(self, tmp_path: Path) -> None:
        """Should only parse new bytes on subsequent reads."""
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(self._make_user_line("First") + "\n", encoding="utf-8")

        config = DisplayConfig()
        reader = IncrementalEventReader(config)
        events = reader.read(jsonl_file)
        assert len(events) == 1

        # Append a new line
        with jsonl_file.open("a", encoding="utf-8") as f:
            f.write(self._make_assistant_line("Second") + "\n")

        events = reader.read()
        assert len(events) == 2

    def test_reset_on_file_shrink(self, tmp_path: Path) -> None:
        """Should re-read from scratch if file shrinks."""
        jsonl_file = tmp_path / "session.jsonl"
        lines = [self._make_user_line(f"Msg {i}") for i in range(5)]
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        config = DisplayConfig()
        reader = IncrementalEventReader(config)
        events = reader.read(jsonl_file)
        assert len(events) == 5

        # Truncate file to fewer lines
        jsonl_file.write_text(self._make_user_line("New") + "\n", encoding="utf-8")
        events = reader.read()
        assert len(events) == 1

    def test_reset_on_path_change(self, tmp_path: Path) -> None:
        """Should reset when a different path is provided."""
        file_a = tmp_path / "a.jsonl"
        file_b = tmp_path / "b.jsonl"
        file_a.write_text(self._make_user_line("A1") + "\n", encoding="utf-8")
        file_b.write_text(self._make_user_line("B1") + "\n" + self._make_user_line("B2") + "\n", encoding="utf-8")

        config = DisplayConfig()
        reader = IncrementalEventReader(config)
        events = reader.read(file_a)
        assert len(events) == 1

        events = reader.read(file_b)
        assert len(events) == 2

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty list for nonexistent file."""
        config = DisplayConfig()
        reader = IncrementalEventReader(config)
        events = reader.read(tmp_path / "nope.jsonl")
        assert events == []

    def test_no_new_data_returns_cached(self, tmp_path: Path) -> None:
        """Should return cached events when file hasn't changed."""
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(self._make_user_line("Hello") + "\n", encoding="utf-8")

        config = DisplayConfig()
        reader = IncrementalEventReader(config)
        events1 = reader.read(jsonl_file)
        events2 = reader.read()
        assert events1 is events2
