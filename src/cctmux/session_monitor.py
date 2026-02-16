"""Real-time Claude Code session stream monitor."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from cctmux.task_monitor import encode_project_path, find_project_sessions
from cctmux.utils import compress_path, compress_paths_in_text


class EventType(Enum):
    """Types of events in the session stream."""

    USER = "user"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ASSISTANT = "assistant"
    PROGRESS = "progress"
    SYSTEM = "system"
    SNAPSHOT = "snapshot"


def _empty_dict() -> dict[str, Any]:
    return {}


def _empty_str_list() -> list[str]:
    return []


@dataclass
class SessionEvent:
    """Represents a single event from the session JSONL stream."""

    event_type: EventType
    content: str
    timestamp: datetime
    session_id: str = ""
    git_branch: str = ""
    model: str = ""
    tool_name: str = ""
    tool_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    raw_data: dict[str, Any] = field(default_factory=_empty_dict)

    # New enriched fields
    stop_reason: str = ""
    stop_sequence: str | None = None
    service_tier: str = ""
    cwd: str = ""
    uuid: str = ""
    parent_uuid: str = ""
    is_sidechain: bool = False
    thinking_level: str = ""
    turn_duration_ms: int = 0
    hook_errors: list[str] = field(default_factory=_empty_str_list)
    hook_infos: list[str] = field(default_factory=_empty_str_list)

    @property
    def symbol(self) -> str:
        """Get display symbol for event type."""
        symbols = {
            EventType.USER: "●",
            EventType.THINKING: "◐",
            EventType.TOOL_CALL: "▶",
            EventType.TOOL_RESULT: "◀",
            EventType.ASSISTANT: "■",
            EventType.PROGRESS: "↻",
            EventType.SYSTEM: "⚙",
            EventType.SNAPSHOT: "📁",
        }
        return symbols.get(self.event_type, "?")

    @property
    def color(self) -> str:
        """Get display color for event type."""
        colors = {
            EventType.USER: "cyan",
            EventType.THINKING: "dim yellow",
            EventType.TOOL_CALL: "green",
            EventType.TOOL_RESULT: "dim green",
            EventType.ASSISTANT: "white",
            EventType.PROGRESS: "dim magenta",
            EventType.SYSTEM: "dim",
            EventType.SNAPSHOT: "dim blue",
        }
        return colors.get(self.event_type, "white")

    @property
    def label(self) -> str:
        """Get display label for event type."""
        labels = {
            EventType.USER: "USER",
            EventType.THINKING: "THINKING",
            EventType.TOOL_CALL: f"TOOL {self.tool_name}",
            EventType.TOOL_RESULT: f"RESULT ({len(self.content)} chars)",
            EventType.ASSISTANT: "ASSISTANT",
            EventType.PROGRESS: "PROGRESS",
            EventType.SYSTEM: "SYSTEM",
            EventType.SNAPSHOT: "SNAPSHOT",
        }
        return labels.get(self.event_type, "UNKNOWN")


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    try:
        # Handle Z suffix
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError):
        return datetime.min


def _extract_text_from_content_list(content: list[dict[str, Any]]) -> str:
    """Extract text from a list of content items.

    Args:
        content: List of content items from message.

    Returns:
        Joined text from all text-type items.
    """
    parts: list[str] = []
    for item in content:
        if item.get("type") == "text":
            text = item.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return " ".join(parts)


def _extract_tool_input_summary(input_data: dict[str, Any]) -> str:
    """Extract a summary of tool input for display."""
    if not input_data:
        return ""

    # Common patterns - compress paths for display
    if "command" in input_data:
        return compress_paths_in_text(str(input_data["command"]))
    if "file_path" in input_data:
        return compress_path(str(input_data["file_path"]))
    if "pattern" in input_data:
        return compress_paths_in_text(str(input_data["pattern"]))
    if "query" in input_data:
        return compress_paths_in_text(str(input_data["query"]))
    if "url" in input_data:
        return str(input_data["url"])

    # Fallback: first string value - compress any paths
    for v in input_data.values():
        if isinstance(v, str) and v:
            return compress_paths_in_text(v[:100])

    return compress_paths_in_text(str(input_data)[:100])


def parse_jsonl_line(
    line: str,
    include_snapshots: bool = False,
    include_system: bool = False,
) -> SessionEvent | None:
    """Parse a single JSONL line into a SessionEvent.

    Args:
        line: Raw JSONL line string.
        include_snapshots: Whether to include file-history-snapshot events.
        include_system: Whether to include system events.

    Returns:
        SessionEvent or None if line should be skipped.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    msg_type = data.get("type", "")
    timestamp = _parse_timestamp(data.get("timestamp", ""))
    session_id = data.get("sessionId", "")
    git_branch = data.get("gitBranch", "")

    # Extract common enriched fields
    cwd = data.get("cwd", "")
    uuid = data.get("uuid", "")
    parent_uuid = data.get("parentUuid", "")
    is_sidechain = data.get("isSidechain", False)

    # Skip file-history-snapshot unless requested
    if msg_type == "file-history-snapshot":
        if not include_snapshots:
            return None
        return SessionEvent(
            event_type=EventType.SNAPSHOT,
            content="File history snapshot",
            timestamp=timestamp,
            session_id=session_id,
            raw_data=data,
        )

    # Handle user messages
    if msg_type == "user":
        message = data.get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            # Handle structured content
            content = _extract_text_from_content_list(cast(list[dict[str, Any]], content))
        return SessionEvent(
            event_type=EventType.USER,
            content=str(content),
            timestamp=timestamp,
            session_id=session_id,
            git_branch=git_branch,
            raw_data=data,
        )

    # Handle assistant messages
    if msg_type == "assistant":
        message = data.get("message", {})
        content_list = message.get("content", [])
        model = message.get("model", "")
        usage = message.get("usage", {})

        # Extract token counts
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)

        # Extract new enriched fields from assistant message
        stop_reason = message.get("stop_reason", "")
        stop_sequence = message.get("stop_sequence")
        service_tier = usage.get("service_tier", "")

        # Extract thinking metadata
        thinking_metadata = data.get("thinkingMetadata", {})
        thinking_level = thinking_metadata.get("level", "") if thinking_metadata else ""

        # Process first content item (each becomes separate event in real usage)
        if content_list:
            item = content_list[0]
            item_type = item.get("type", "")

            if item_type == "thinking":
                return SessionEvent(
                    event_type=EventType.THINKING,
                    content=item.get("thinking", ""),
                    timestamp=timestamp,
                    session_id=session_id,
                    git_branch=git_branch,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read,
                    cache_creation_tokens=cache_creation,
                    raw_data=data,
                    stop_reason=stop_reason,
                    stop_sequence=stop_sequence,
                    service_tier=service_tier,
                    cwd=cwd,
                    uuid=uuid,
                    parent_uuid=parent_uuid,
                    is_sidechain=is_sidechain,
                    thinking_level=thinking_level,
                )

            if item_type == "tool_use":
                tool_name = item.get("name", "")
                tool_input = item.get("input", {})
                return SessionEvent(
                    event_type=EventType.TOOL_CALL,
                    content=_extract_tool_input_summary(tool_input),
                    timestamp=timestamp,
                    session_id=session_id,
                    git_branch=git_branch,
                    model=model,
                    tool_name=tool_name,
                    tool_id=item.get("id", ""),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read,
                    cache_creation_tokens=cache_creation,
                    raw_data=data,
                    stop_reason=stop_reason,
                    stop_sequence=stop_sequence,
                    service_tier=service_tier,
                    cwd=cwd,
                    uuid=uuid,
                    parent_uuid=parent_uuid,
                    is_sidechain=is_sidechain,
                )

            if item_type == "text":
                return SessionEvent(
                    event_type=EventType.ASSISTANT,
                    content=item.get("text", ""),
                    timestamp=timestamp,
                    session_id=session_id,
                    git_branch=git_branch,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read,
                    cache_creation_tokens=cache_creation,
                    raw_data=data,
                    stop_reason=stop_reason,
                    stop_sequence=stop_sequence,
                    service_tier=service_tier,
                    cwd=cwd,
                    uuid=uuid,
                    parent_uuid=parent_uuid,
                    is_sidechain=is_sidechain,
                )

            if item_type == "tool_result":
                result_content = item.get("content", "")
                if isinstance(result_content, list):
                    result_content = _extract_text_from_content_list(cast(list[dict[str, Any]], result_content))
                return SessionEvent(
                    event_type=EventType.TOOL_RESULT,
                    content=str(result_content),
                    timestamp=timestamp,
                    session_id=session_id,
                    tool_id=item.get("tool_use_id", ""),
                    raw_data=data,
                    cwd=cwd,
                    uuid=uuid,
                    parent_uuid=parent_uuid,
                    is_sidechain=is_sidechain,
                )

        return None

    # Handle progress events
    if msg_type == "progress":
        progress_data = data.get("data", {})
        hook_name = progress_data.get("hookName", "")
        progress_type = progress_data.get("type", "")
        content = hook_name if hook_name else progress_type
        return SessionEvent(
            event_type=EventType.PROGRESS,
            content=content,
            timestamp=timestamp,
            session_id=session_id,
            git_branch=git_branch,
            raw_data=data,
        )

    # Handle system messages
    if msg_type == "system":
        message = data.get("message", {})
        content = message.get("content", "")
        subtype = data.get("subtype", "")

        # Extract turn duration from system messages
        turn_duration_ms = 0
        if subtype == "turn_duration":
            turn_duration_ms = data.get("durationMs", 0)

        # Extract hook errors and infos
        hook_errors_list: list[str] = []
        hook_infos_list: list[str] = []
        if "hookErrors" in data:
            hook_errors_list = [str(e) for e in data["hookErrors"]]
        if "hookInfos" in data:
            hook_infos_list = [str(i) for i in data["hookInfos"]]

        if not include_system and not hook_errors_list and subtype != "turn_duration":
            return None

        return SessionEvent(
            event_type=EventType.SYSTEM,
            content=str(content)[:200],
            timestamp=timestamp,
            session_id=session_id,
            raw_data=data,
            cwd=cwd,
            uuid=uuid,
            parent_uuid=parent_uuid,
            turn_duration_ms=turn_duration_ms,
            hook_errors=hook_errors_list,
            hook_infos=hook_infos_list,
        )

    return None


# Pre-compiled regex patterns for model version extraction
_MODEL_VERSION_MAJOR_MINOR_RE: dict[str, re.Pattern[str]] = {
    family: re.compile(rf"{family}-?(\d)-(\d{{1,2}})(?:-|$)") for family in ("opus", "sonnet", "haiku")
}
_MODEL_VERSION_MAJOR_RE: dict[str, re.Pattern[str]] = {
    family: re.compile(rf"{family}-?(\d)(?:-|$)") for family in ("opus", "sonnet", "haiku")
}


def _empty_counter() -> Counter[str]:
    return Counter()


def _empty_int_list() -> list[int]:
    return []


def _empty_str_dict() -> dict[str, int]:
    return {}


@dataclass
class SessionStats:
    """Aggregated statistics for a session."""

    session_id: str = ""
    model: str = ""
    git_branch: str = ""
    user_count: int = 0
    assistant_count: int = 0
    thinking_count: int = 0
    tool_call_count: int = 0
    tool_counts: Counter[str] = field(default_factory=_empty_counter)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    duration_seconds: float = 0.0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    estimated_cost: float = 0.0

    # New enriched data fields
    stop_reasons: dict[str, int] = field(default_factory=_empty_str_dict)
    turn_durations: list[int] = field(default_factory=_empty_int_list)
    hook_count: int = 0
    hook_errors: int = 0
    hook_error_messages: list[str] = field(default_factory=_empty_str_list)
    service_tier: str | None = None
    current_cwd: str = ""
    sidechain_count: int = 0
    thinking_level: str = ""

    @property
    def duration_display(self) -> str:
        """Format duration for display."""
        secs = int(self.duration_seconds)
        if secs < 60:
            return f"{secs}s"
        mins, secs = divmod(secs, 60)
        if mins < 60:
            return f"{mins}m {secs}s"
        hours, mins = divmod(mins, 60)
        return f"{hours}h {mins}m"

    @property
    def model_short(self) -> str:
        """Get short model name for display.

        Extracts model family and version from full model ID.
        e.g., 'claude-opus-4-6-20260205' -> 'opus-4.6'
             'claude-sonnet-4-20250514' -> 'sonnet-4'
        """
        model_lower = self.model.lower()
        for family in ("opus", "sonnet", "haiku"):
            if family in model_lower:
                # Try to extract version like "4-6" or "4-5" or "3-5"
                version_match = _MODEL_VERSION_MAJOR_MINOR_RE[family].search(model_lower)
                if version_match:
                    major = version_match.group(1)
                    minor = version_match.group(2)
                    return f"{family}-{major}.{minor}"
                # Try major version only
                version_match = _MODEL_VERSION_MAJOR_RE[family].search(model_lower)
                if version_match:
                    major = version_match.group(1)
                    return f"{family}-{major}"
                return family
        return self.model[:20] if self.model else "unknown"

    @property
    def avg_turn_duration_ms(self) -> int:
        """Average turn duration in milliseconds."""
        if not self.turn_durations:
            return 0
        return sum(self.turn_durations) // len(self.turn_durations)

    @property
    def total_turn_duration_ms(self) -> int:
        """Total turn duration in milliseconds."""
        return sum(self.turn_durations)

    @property
    def stop_reasons_display(self) -> str:
        """Format stop reasons for display."""
        if not self.stop_reasons:
            return ""
        parts = [f"{reason}: {count}" for reason, count in self.stop_reasons.items()]
        return ", ".join(parts)


# Model pricing per 1M tokens
MODEL_PRICING: dict[str, dict[str, float]] = {
    "opus": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    "sonnet": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "haiku": {
        "input": 0.80,
        "output": 4.00,
        "cache_read": 0.08,
        "cache_write": 1.00,
    },
}


def _get_model_tier(model: str) -> str:
    """Determine pricing tier from model name."""
    model_lower = model.lower()
    if "opus" in model_lower:
        return "opus"
    if "sonnet" in model_lower:
        return "sonnet"
    if "haiku" in model_lower:
        return "haiku"
    return "opus"  # Default to opus for unknown


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> float:
    """Estimate cost based on token usage.

    Args:
        model: Model name/ID.
        input_tokens: Total input tokens.
        output_tokens: Total output tokens.
        cache_read_tokens: Cache read tokens.
        cache_creation_tokens: Cache creation tokens.

    Returns:
        Estimated cost in USD.
    """
    tier = _get_model_tier(model)
    pricing = MODEL_PRICING[tier]

    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
        + (cache_read_tokens / 1_000_000) * pricing["cache_read"]
        + (cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    )
    return round(cost, 2)


def calculate_stats(events: list[SessionEvent]) -> SessionStats:
    """Calculate aggregated statistics from events.

    Args:
        events: List of session events.

    Returns:
        SessionStats with aggregated data.
    """
    stats = SessionStats()

    if not events:
        return stats

    tool_counts: Counter[str] = Counter()
    stop_reasons: dict[str, int] = {}

    for event in events:
        # Update timestamps
        if event.timestamp != datetime.min:
            if stats.first_timestamp is None or event.timestamp < stats.first_timestamp:
                stats.first_timestamp = event.timestamp
            if stats.last_timestamp is None or event.timestamp > stats.last_timestamp:
                stats.last_timestamp = event.timestamp

        # Extract metadata from first event that has it
        if not stats.session_id and event.session_id:
            stats.session_id = event.session_id
        if not stats.model and event.model:
            stats.model = event.model
        if not stats.git_branch and event.git_branch:
            stats.git_branch = event.git_branch

        # Track service tier (use latest non-empty)
        if event.service_tier:
            stats.service_tier = event.service_tier

        # Track working directory (use latest non-empty)
        if event.cwd:
            stats.current_cwd = event.cwd

        # Track thinking level (use latest non-empty)
        if event.thinking_level:
            stats.thinking_level = event.thinking_level

        # Track stop reasons
        if event.stop_reason:
            stop_reasons[event.stop_reason] = stop_reasons.get(event.stop_reason, 0) + 1

        # Track turn durations
        if event.turn_duration_ms > 0:
            stats.turn_durations.append(event.turn_duration_ms)

        # Track hook errors
        if event.hook_errors:
            stats.hook_errors += len(event.hook_errors)
            stats.hook_error_messages.extend(event.hook_errors)
        if event.hook_infos:
            stats.hook_count += len(event.hook_infos)

        # Track sidechain messages
        if event.is_sidechain:
            stats.sidechain_count += 1

        # Count by type
        if event.event_type == EventType.USER:
            stats.user_count += 1
        elif event.event_type == EventType.ASSISTANT:
            stats.assistant_count += 1
        elif event.event_type == EventType.THINKING:
            stats.thinking_count += 1
        elif event.event_type == EventType.TOOL_CALL:
            stats.tool_call_count += 1
            if event.tool_name:
                tool_counts[event.tool_name] += 1

        # Aggregate tokens
        stats.total_input_tokens += event.input_tokens
        stats.total_output_tokens += event.output_tokens
        stats.total_cache_read_tokens += event.cache_read_tokens
        stats.total_cache_creation_tokens += event.cache_creation_tokens

    stats.tool_counts = tool_counts
    stats.stop_reasons = stop_reasons

    # Calculate duration
    if stats.first_timestamp and stats.last_timestamp:
        delta = stats.last_timestamp - stats.first_timestamp
        stats.duration_seconds = delta.total_seconds()

    # Estimate cost
    stats.estimated_cost = estimate_cost(
        model=stats.model,
        input_tokens=stats.total_input_tokens,
        output_tokens=stats.total_output_tokens,
        cache_read_tokens=stats.total_cache_read_tokens,
        cache_creation_tokens=stats.total_cache_creation_tokens,
    )

    return stats


def resolve_session_path(
    session_or_path: str | None = None,
    project_path: Path | None = None,
) -> tuple[Path | None, str]:
    """Resolve the session JSONL file to monitor.

    Args:
        session_or_path: Session ID, partial session ID, or direct path to JSONL file.
        project_path: Project directory to find sessions for.

    Returns:
        Tuple of (jsonl_path, display_name) or (None, error_message).
    """
    claude_projects = Path.home() / ".claude" / "projects"

    # Case 1: Direct path to JSONL file
    if session_or_path:
        path = Path(session_or_path)

        # Check if absolute path exists
        if path.is_absolute() and path.exists() and path.suffix == ".jsonl":
            return path, path.stem

        # Check relative path from cwd
        if not path.is_absolute():
            cwd_path = Path.cwd() / path
            if cwd_path.exists() and cwd_path.suffix == ".jsonl":
                return cwd_path, cwd_path.stem

        # Search in all project folders for matching session ID
        if claude_projects.exists():
            for project_folder in claude_projects.iterdir():
                if not project_folder.is_dir():
                    continue
                for jsonl_file in project_folder.glob("*.jsonl"):
                    if session_or_path in jsonl_file.stem:
                        # Extract project name from folder
                        folder_name = project_folder.name
                        # Decode: -Users-foo-project -> project (last segment)
                        project_name = folder_name.split("-")[-1] if "-" in folder_name else folder_name
                        display = f"{jsonl_file.stem[:8]}... ({project_name})"
                        return jsonl_file, display

        return None, f"No session found for: {session_or_path}"

    # Case 2: Project path provided - find most recent JSONL file
    if project_path:
        encoded = encode_project_path(project_path)
        project_folder = claude_projects / encoded

        if project_folder.exists():
            # Find most recently modified JSONL in project folder
            best_file: tuple[Path, float] | None = None
            for jsonl_file in project_folder.glob("*.jsonl"):
                try:
                    mtime = jsonl_file.stat().st_mtime
                    if best_file is None or mtime > best_file[1]:
                        best_file = (jsonl_file, mtime)
                except OSError:
                    continue

            if best_file:
                jsonl_path = best_file[0]
                # Try to get summary from sessions index
                sessions = find_project_sessions(project_path)
                for session in sessions:
                    if session.session_id in jsonl_path.stem:
                        display = f"{session.session_id[:8]}... ({session.summary[:30]})"
                        return jsonl_path, display
                # Fallback display if not in index yet
                project_name = project_path.name
                return jsonl_path, f"{jsonl_path.stem[:8]}... ({project_name})"

        return None, f"No sessions found for project: {project_path}"

    # Case 3: Try current directory as project - use most recent JSONL file
    cwd = Path.cwd()
    encoded = encode_project_path(cwd)
    project_folder = claude_projects / encoded

    if project_folder.exists():
        # Find most recently modified JSONL in project folder (catches current session)
        best_file: tuple[Path, float] | None = None
        for jsonl_file in project_folder.glob("*.jsonl"):
            try:
                mtime = jsonl_file.stat().st_mtime
                if best_file is None or mtime > best_file[1]:
                    best_file = (jsonl_file, mtime)
            except OSError:
                continue

        if best_file:
            jsonl_path = best_file[0]
            # Try to get summary from sessions index
            sessions = find_project_sessions(cwd)
            for session in sessions:
                if session.session_id in jsonl_path.stem:
                    display = f"{session.session_id[:8]}... ({session.summary[:30]})"
                    return jsonl_path, display
            # Fallback display if not in index yet (current running session)
            project_name = cwd.name
            return jsonl_path, f"{jsonl_path.stem[:8]}... ({project_name})"

    # Case 4: Fall back to most recently modified JSONL globally
    if claude_projects.exists():
        best_file: tuple[Path, float] | None = None
        for project_folder in claude_projects.iterdir():
            if not project_folder.is_dir():
                continue
            for jsonl_file in project_folder.glob("*.jsonl"):
                try:
                    mtime = jsonl_file.stat().st_mtime
                    if best_file is None or mtime > best_file[1]:
                        best_file = (jsonl_file, mtime)
                except OSError:
                    continue

        if best_file:
            jsonl_path = best_file[0]
            folder_name = jsonl_path.parent.name
            project_name = folder_name.split("-")[-1] if "-" in folder_name else folder_name
            return jsonl_path, f"{jsonl_path.stem[:8]}... ({project_name})"

    return None, "No session files found"


def get_terminal_size() -> tuple[int, int]:
    """Get terminal width and height.

    Returns:
        Tuple of (columns, lines).
    """
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except (AttributeError, ValueError):
        return 80, 24


def get_visible_event_count() -> int:
    """Calculate how many events can fit in terminal.

    Returns:
        Number of events that can be displayed.
    """
    _, terminal_height = get_terminal_size()
    # Reserve space for stats panel (5 lines) + panel borders (4) + footer (2)
    reserved = 11
    available = terminal_height - reserved
    # Each event takes ~3 lines (timestamp line + content + blank)
    return max(5, available // 3)


@dataclass
class EventWindow:
    """Windowed view of events for display."""

    events: list[SessionEvent]
    start_index: int
    end_index: int
    total_count: int

    @property
    def has_events_above(self) -> bool:
        """Check if there are events above visible window."""
        return self.start_index > 0

    @property
    def has_events_below(self) -> bool:
        """Check if there are events below visible window."""
        return self.end_index < self.total_count

    @property
    def events_above_count(self) -> int:
        """Number of events above the window."""
        return self.start_index

    @property
    def events_below_count(self) -> int:
        """Number of events below the window."""
        return self.total_count - self.end_index


def calculate_event_window(
    events: list[SessionEvent],
    max_visible: int | None = None,
) -> EventWindow:
    """Calculate window of events to display (most recent).

    Args:
        events: All events (should be sorted by timestamp).
        max_visible: Maximum events to show.

    Returns:
        EventWindow with visible events.
    """
    if max_visible is None:
        max_visible = get_visible_event_count()

    total = len(events)

    if total <= max_visible:
        return EventWindow(
            events=events,
            start_index=0,
            end_index=total,
            total_count=total,
        )

    # Show most recent events
    start = total - max_visible
    return EventWindow(
        events=events[start:],
        start_index=start,
        end_index=total,
        total_count=total,
    )


def _format_tokens(count: int) -> str:
    """Format token count for display.

    Args:
        count: Number of tokens.

    Returns:
        Formatted string like "1.2K" or "1.5M".
    """
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def build_stats_panel(
    stats: SessionStats,
    show_stop_reasons: bool = True,
    show_turn_durations: bool = True,
    show_hook_errors: bool = True,
    show_service_tier: bool = False,
    show_cwd: bool = False,
    show_sidechain: bool = True,
) -> Panel:
    """Build the stats panel.

    Args:
        stats: Session statistics.
        show_stop_reasons: Whether to display stop reasons.
        show_turn_durations: Whether to display turn duration stats.
        show_hook_errors: Whether to display hook error info.
        show_service_tier: Whether to display service tier.
        show_cwd: Whether to display current working directory.
        show_sidechain: Whether to display sidechain count.

    Returns:
        Rich Panel with stats display.
    """
    text = Text()

    # Line 1: Session, Model, Branch
    text.append("Session: ", style="dim")
    text.append(f"{stats.session_id[:8]}...  ", style="bold cyan")
    text.append("Model: ", style="dim")
    text.append(f"{stats.model_short}  ", style="bold")
    text.append("Branch: ", style="dim")
    text.append(f"{stats.git_branch or 'unknown'}", style="green")

    # Show service tier if enabled
    if show_service_tier and stats.service_tier:
        text.append("  Tier: ", style="dim")
        text.append(stats.service_tier, style="magenta")

    text.append("\n")

    # Line 2: Duration, Messages, Status
    text.append("Duration: ", style="dim")
    text.append(f"{stats.duration_display}  ", style="bold")
    text.append("Messages: ", style="dim")
    text.append(f"{stats.user_count} user / {stats.assistant_count} assistant  ", style="bold")

    # Show thinking level if available
    if stats.thinking_level:
        text.append("Think: ", style="dim")
        text.append(f"{stats.thinking_level}  ", style="yellow")

    # Show sidechain count if enabled and non-zero
    if show_sidechain and stats.sidechain_count > 0:
        text.append("Sidechain: ", style="dim")
        text.append(f"{stats.sidechain_count}", style="magenta")

    # Line 3: Tokens and Cost
    text.append("\nTokens: ", style="dim")
    input_display = _format_tokens(stats.total_input_tokens)
    if stats.total_cache_read_tokens > 0:
        cache_display = _format_tokens(stats.total_cache_read_tokens)
        text.append(f"{input_display} in ({cache_display} cached) / ", style="bold")
    else:
        text.append(f"{input_display} in / ", style="bold")
    text.append(f"{_format_tokens(stats.total_output_tokens)} out  ", style="bold")
    text.append("Est. Cost: ", style="dim")
    text.append(f"${stats.estimated_cost:.2f}", style="bold yellow")

    # Show turn duration if enabled and available
    if show_turn_durations and stats.turn_durations:
        avg_ms = stats.avg_turn_duration_ms
        if avg_ms >= 1000:
            text.append(f"  Avg Turn: {avg_ms / 1000:.1f}s", style="dim")
        else:
            text.append(f"  Avg Turn: {avg_ms}ms", style="dim")

    text.append("\n")

    # Line 4: Tool counts
    text.append("Tools: ", style="dim")
    if stats.tool_counts:
        tool_parts = [f"{name} x{count}" for name, count in stats.tool_counts.most_common(6)]
        text.append("  ".join(tool_parts), style="cyan")
    else:
        text.append("none", style="dim")

    # Line 5: Stop reasons (if enabled and available)
    if show_stop_reasons and stats.stop_reasons:
        text.append("\nStop: ", style="dim")
        text.append(stats.stop_reasons_display, style="dim cyan")

    # Line 6: Hook errors (if enabled and available)
    if show_hook_errors and stats.hook_errors > 0:
        text.append("\n")
        text.append(f"Hook Errors: {stats.hook_errors}", style="bold red")
        if stats.hook_error_messages:
            text.append(f" ({stats.hook_error_messages[0][:50]})", style="dim red")

    # Line 7: Working directory (if enabled and available)
    if show_cwd and stats.current_cwd:
        text.append("\nCWD: ", style="dim")
        text.append(compress_path(stats.current_cwd), style="dim blue")

    return Panel(text, title="Session Stats", border_style="blue")


def _build_threading_map(events: list[SessionEvent]) -> dict[str, int]:
    """Build a map of uuid to depth level for threading visualization.

    Args:
        events: List of events to analyze.

    Returns:
        Dict mapping uuid to indent depth (0 = root, 1+ = child level).
    """
    depth_map: dict[str, int] = {}
    parent_to_children: dict[str, list[str]] = {}

    # First pass: collect parent-child relationships
    for event in events:
        if event.uuid:
            if event.parent_uuid:
                if event.parent_uuid not in parent_to_children:
                    parent_to_children[event.parent_uuid] = []
                parent_to_children[event.parent_uuid].append(event.uuid)
            else:
                # Root level event
                depth_map[event.uuid] = 0

    # Second pass: assign depths based on parent chain
    def get_depth(uuid: str, visited: set[str] | None = None) -> int:
        if visited is None:
            visited = set()
        if uuid in visited:
            return 0  # Prevent cycles
        visited.add(uuid)

        if uuid in depth_map:
            return depth_map[uuid]

        # Find parent depth
        for event in events:
            if event.uuid == uuid and event.parent_uuid:
                parent_depth = get_depth(event.parent_uuid, visited)
                depth_map[uuid] = parent_depth + 1
                return depth_map[uuid]

        # No parent found, treat as root
        depth_map[uuid] = 0
        return 0

    for event in events:
        if event.uuid and event.uuid not in depth_map:
            get_depth(event.uuid)

    return depth_map


def build_events_panel(
    window: EventWindow,
    max_content_length: int = 200,
    show_threading: bool = False,
) -> Panel:
    """Build the events panel.

    Args:
        window: EventWindow with events to display.
        max_content_length: Max chars per event content.
        show_threading: Whether to show threading indentation.

    Returns:
        Rich Panel with events display.
    """
    text = Text()

    # Build threading map if needed
    threading_map: dict[str, int] = {}
    if show_threading:
        threading_map = _build_threading_map(window.events)

    # Show "N earlier events" indicator
    if window.has_events_above:
        text.append(f"  \u25b2 {window.events_above_count} earlier events\n\n", style="dim yellow")

    for event in window.events:
        # Calculate threading indent
        indent = ""
        if show_threading and event.uuid:
            depth = threading_map.get(event.uuid, 0)
            if depth > 0:
                # Use tree characters for visual hierarchy
                indent = "│ " * (depth - 1) + "├─"

        # Timestamp and label
        ts_str = event.timestamp.strftime("%H:%M:%S")
        text.append(f"{ts_str} ", style="dim")
        if indent:
            text.append(f"{indent}", style="dim blue")
        text.append(f"{event.symbol} ", style=event.color)
        text.append(f"{event.label}", style=f"bold {event.color}")

        # Show sidechain indicator
        if event.is_sidechain:
            text.append(" [sidechain]", style="dim magenta")

        text.append("\n")

        # Content (truncated) - compress paths for display
        content = compress_paths_in_text(event.content)
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."

        # Calculate content indent based on threading
        content_indent = "  "
        if show_threading and event.uuid:
            depth = threading_map.get(event.uuid, 0)
            content_indent = "  " + "│ " * depth

        # Indent content
        for line in content.split("\n")[:3]:  # Max 3 lines
            text.append(f"{content_indent}{line}\n", style=event.color)

        text.append("\n")

    # Show "N newer events" indicator
    if window.has_events_below:
        text.append(f"  \u25bc {window.events_below_count} newer events", style="dim yellow")

    return Panel(
        text,
        title="Session Events",
        border_style="cyan",
    )


def build_display(
    events: list[SessionEvent],
    stats: SessionStats,
    max_visible: int | None = None,
    show_stop_reasons: bool = True,
    show_turn_durations: bool = True,
    show_hook_errors: bool = True,
    show_service_tier: bool = False,
    show_cwd: bool = False,
    show_sidechain: bool = True,
    show_threading: bool = False,
) -> Group:
    """Build complete display with stats and events panels.

    Args:
        events: All session events.
        stats: Session statistics.
        max_visible: Maximum events to show.
        show_stop_reasons: Whether to display stop reasons.
        show_turn_durations: Whether to display turn duration stats.
        show_hook_errors: Whether to display hook error info.
        show_service_tier: Whether to display service tier.
        show_cwd: Whether to display current working directory.
        show_sidechain: Whether to display sidechain count.
        show_threading: Whether to display message threading.

    Returns:
        Rich Group with all panels.
    """
    window = calculate_event_window(events, max_visible)

    return Group(
        build_stats_panel(
            stats,
            show_stop_reasons=show_stop_reasons,
            show_turn_durations=show_turn_durations,
            show_hook_errors=show_hook_errors,
            show_service_tier=show_service_tier,
            show_cwd=show_cwd,
            show_sidechain=show_sidechain,
        ),
        build_events_panel(window, show_threading=show_threading),
    )


@dataclass
class DisplayConfig:
    """Configuration for what to display."""

    show_thinking: bool = True
    show_results: bool = True
    show_progress: bool = True
    show_system: bool = False
    show_snapshots: bool = False

    # New enriched display options
    show_cwd: bool = False
    show_threading: bool = False
    show_stop_reasons: bool = True
    show_turn_durations: bool = True
    show_hook_errors: bool = True
    show_service_tier: bool = False
    show_sidechain: bool = True
    max_events: int = 50


def load_events_from_file(
    jsonl_path: Path,
    config: DisplayConfig,
) -> list[SessionEvent]:
    """Load and parse all events from JSONL file.

    Args:
        jsonl_path: Path to JSONL file.
        config: Display configuration.

    Returns:
        List of SessionEvent objects.
    """
    events: list[SessionEvent] = []

    if not jsonl_path.exists():
        return events

    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                event = parse_jsonl_line(
                    line,
                    include_snapshots=config.show_snapshots,
                    include_system=config.show_system,
                )

                if event is None:
                    continue

                # Apply display filters
                if event.event_type == EventType.THINKING and not config.show_thinking:
                    continue
                if event.event_type == EventType.TOOL_RESULT and not config.show_results:
                    continue
                if event.event_type == EventType.PROGRESS and not config.show_progress:
                    continue

                events.append(event)
    except OSError:
        pass

    return events


class IncrementalEventReader:
    """Reads JSONL events incrementally, tracking file byte offset.

    On each call to read(), only new bytes appended since the last read
    are parsed.  If the file shrinks (truncation / rotation) or the path
    changes, the reader resets and re-reads from the beginning.
    """

    def __init__(self, config: DisplayConfig) -> None:
        self._config = config
        self._events: list[SessionEvent] = []
        self._byte_offset: int = 0
        self._path: Path | None = None

    def reset(self, path: Path | None = None) -> None:
        """Reset reader state, optionally setting a new path."""
        self._events = []
        self._byte_offset = 0
        if path is not None:
            self._path = path

    def read(self, path: Path | None = None) -> list[SessionEvent]:
        """Read new events incrementally.

        Args:
            path: File to read. If different from the current path, resets
                  and reads from scratch.

        Returns:
            The full accumulated list of events.
        """
        if path is not None and path != self._path:
            self.reset(path)

        if self._path is None or not self._path.exists():
            return self._events

        try:
            file_size = self._path.stat().st_size
        except OSError:
            return self._events

        # File shrank — full re-read
        if file_size < self._byte_offset:
            self._events = []
            self._byte_offset = 0

        # No new data
        if file_size == self._byte_offset:
            return self._events

        try:
            with self._path.open("r", encoding="utf-8") as f:
                f.seek(self._byte_offset)
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue

                    event = parse_jsonl_line(
                        stripped,
                        include_snapshots=self._config.show_snapshots,
                        include_system=self._config.show_system,
                    )
                    if event is None:
                        continue

                    # Apply display filters
                    if event.event_type == EventType.THINKING and not self._config.show_thinking:
                        continue
                    if event.event_type == EventType.TOOL_RESULT and not self._config.show_results:
                        continue
                    if event.event_type == EventType.PROGRESS and not self._config.show_progress:
                        continue

                    self._events.append(event)

                self._byte_offset = f.tell()
        except OSError:
            pass

        return self._events

    @property
    def events(self) -> list[SessionEvent]:
        """Return the accumulated events without reading new data."""
        return self._events


def list_sessions(project_path: Path | None = None) -> None:
    """List available session JSONL files.

    Args:
        project_path: Optional project path to filter sessions.
    """
    console = Console()
    claude_projects = Path.home() / ".claude" / "projects"

    if not claude_projects.exists():
        console.print("[yellow]No Claude projects found.[/]")
        return

    if project_path:
        # Show sessions for specific project
        sessions = find_project_sessions(project_path)
        if not sessions:
            console.print(f"[yellow]No sessions found for project: {project_path}[/]")
            return

        console.print(f"[bold]Sessions for: {project_path}[/]\n")
        encoded = encode_project_path(project_path)
        project_folder = claude_projects / encoded

        for session in sessions[:10]:  # Limit to 10
            # Find matching JSONL
            for jsonl_file in project_folder.glob("*.jsonl"):
                if session.session_id in jsonl_file.stem:
                    size_kb = jsonl_file.stat().st_size / 1024
                    console.print(f"  [cyan]{jsonl_file.stem[:12]}...[/]")
                    console.print(f"    Summary: {session.summary[:50]}")
                    console.print(f"    Modified: {session.modified.strftime('%Y-%m-%d %H:%M')}")
                    console.print(f"    Size: {size_kb:.1f} KB")
                    console.print()
                    break
    else:
        # Show all recent sessions
        console.print("[bold]Recent Claude Code sessions:[/]\n")

        all_sessions: list[tuple[Path, float, str]] = []
        for project_folder in claude_projects.iterdir():
            if not project_folder.is_dir():
                continue
            project_name = project_folder.name.split("-")[-1] if "-" in project_folder.name else project_folder.name
            for jsonl_file in project_folder.glob("*.jsonl"):
                try:
                    mtime = jsonl_file.stat().st_mtime
                    all_sessions.append((jsonl_file, mtime, project_name))
                except OSError:
                    continue

        # Sort by mtime, most recent first
        all_sessions.sort(key=lambda x: x[1], reverse=True)

        for jsonl_file, mtime, project_name in all_sessions[:15]:
            size_kb = jsonl_file.stat().st_size / 1024
            from datetime import datetime as dt

            mod_time = dt.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            console.print(f"  [cyan]{jsonl_file.stem[:12]}...[/] ({project_name})")
            console.print(f"    Modified: {mod_time}  Size: {size_kb:.1f} KB")


def _find_most_recent_jsonl(project_folder: Path) -> tuple[Path, float] | None:
    """Find the most recently modified JSONL file in a folder.

    Args:
        project_folder: Path to the project folder.

    Returns:
        Tuple of (path, mtime) or None if no JSONL files found.
    """
    if not project_folder.exists():
        return None

    best: tuple[Path, float] | None = None
    for jsonl_file in project_folder.glob("*.jsonl"):
        try:
            mtime = jsonl_file.stat().st_mtime
            if best is None or mtime > best[1]:
                best = (jsonl_file, mtime)
        except OSError:
            continue
    return best


def run_session_monitor(
    session_or_path: str | None = None,
    project_path: Path | None = None,
    poll_interval: float = 0.5,
    max_visible: int | None = None,
    config: DisplayConfig | None = None,
) -> None:
    """Run the session monitor with Rich Live.

    Args:
        session_or_path: Session ID, partial ID, or path to JSONL file.
        project_path: Project directory to find sessions for.
        poll_interval: How often to poll for changes (seconds).
        max_visible: Maximum events to display.
        config: Display configuration.
    """
    console = Console()

    if config is None:
        config = DisplayConfig()

    # Use max_events from config if max_visible not specified
    if max_visible is None:
        max_visible = config.max_events if config.max_events > 0 else None

    # Resolve session path
    jsonl_path, display_name = resolve_session_path(session_or_path, project_path)

    if not jsonl_path:
        console.print(f"[red]{display_name}[/]")
        console.print("[dim]Use --list to see available sessions[/]")
        return

    # Track project folder for auto-detecting new sessions
    project_folder = jsonl_path.parent
    current_session_file = jsonl_path

    console.clear()
    console.print(f"[bold cyan]Session Monitor[/] - Watching: {jsonl_path.name}")
    console.print(f"[dim]Display: {display_name}[/]")
    console.print("[dim]Auto-detects new sessions[/]\n")

    last_size = 0
    last_check_time = 0.0
    session_check_interval = 2.0  # Check for new sessions every 2 seconds

    def check_for_changes() -> bool:
        """Check if current file has grown."""
        nonlocal last_size
        try:
            current_size = current_session_file.stat().st_size
            if current_size != last_size:
                last_size = current_size
                return True
        except OSError:
            pass
        return False

    def check_for_new_session() -> Path | None:
        """Check if a new session file appeared in the project folder."""
        nonlocal last_check_time
        current_time = time.time()

        # Only check periodically
        if current_time - last_check_time < session_check_interval:
            return None
        last_check_time = current_time

        result = _find_most_recent_jsonl(project_folder)
        if result is None:
            return None

        newest_file, _ = result
        if newest_file != current_session_file:
            return newest_file
        return None

    def make_display(events: list[SessionEvent], stats: SessionStats) -> Group:
        """Build display with current config settings."""
        return build_display(
            events,
            stats,
            max_visible=max_visible,
            show_stop_reasons=config.show_stop_reasons,
            show_turn_durations=config.show_turn_durations,
            show_hook_errors=config.show_hook_errors,
            show_service_tier=config.show_service_tier,
            show_cwd=config.show_cwd,
            show_sidechain=config.show_sidechain,
            show_threading=config.show_threading,
        )

    reader = IncrementalEventReader(config)

    try:
        # Initial load
        events = reader.read(current_session_file)
        stats = calculate_stats(events)

        with Live(
            make_display(events, stats),
            console=console,
            refresh_per_second=1,
        ) as live:
            while True:
                time.sleep(poll_interval)

                # Check for new session file (auto-compact, clear, etc.)
                new_session = check_for_new_session()
                if new_session:
                    current_session_file = new_session
                    last_size = 0  # Reset size tracking
                    reader.reset(new_session)
                    events = reader.read()
                    stats = calculate_stats(events)
                    live.update(make_display(events, stats))
                    continue

                if check_for_changes():
                    events = reader.read()
                    stats = calculate_stats(events)
                    live.update(make_display(events, stats))

    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")
