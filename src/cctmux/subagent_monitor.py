"""Real-time Claude Code subagent activity monitor."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cctmux.task_monitor import encode_project_path
from cctmux.utils import compress_path, compress_paths_in_text


class AgentStatus(Enum):
    """Status of a subagent."""

    ACTIVE = "active"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


def _empty_dict() -> dict[str, Any]:
    return {}


def _empty_counter() -> Counter[str]:
    return Counter()


def _empty_activity_list() -> list[SubagentActivity]:
    return []


@dataclass
class SubagentActivity:
    """Represents a single activity entry from a subagent."""

    activity_type: str  # thinking, tool_call, tool_result, text
    content: str
    timestamp: datetime
    tool_name: str = ""
    tool_id: str = ""

    @property
    def symbol(self) -> str:
        """Get display symbol for activity type."""
        symbols = {
            "thinking": "💭",
            "tool_call": "▶",
            "tool_result": "◀",
            "text": "💬",
            "user": "●",
        }
        return symbols.get(self.activity_type, "?")

    @property
    def color(self) -> str:
        """Get display color for activity type."""
        colors = {
            "thinking": "dim yellow",
            "tool_call": "green",
            "tool_result": "dim green",
            "text": "white",
            "user": "cyan",
        }
        return colors.get(self.activity_type, "white")


@dataclass
class Subagent:
    """Represents a Claude Code subagent."""

    agent_id: str
    slug: str
    session_id: str
    file_path: Path
    status: AgentStatus = AgentStatus.UNKNOWN
    model: str = ""
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    tool_counts: Counter[str] = field(default_factory=_empty_counter)
    activities: list[SubagentActivity] = field(default_factory=_empty_activity_list)
    last_activity: SubagentActivity | None = None
    initial_prompt: str = ""
    raw_data: dict[str, Any] = field(default_factory=_empty_dict)

    @property
    def display_name(self) -> str:
        """Get display name for the agent."""
        if self.slug:
            return self.slug
        return f"agent-{self.agent_id}"

    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        if self.first_timestamp and self.last_timestamp:
            return (self.last_timestamp - self.first_timestamp).total_seconds()
        return 0.0

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
    def status_symbol(self) -> str:
        """Get status symbol for display."""
        symbols = {
            AgentStatus.ACTIVE: "◐",
            AgentStatus.COMPLETED: "●",
            AgentStatus.UNKNOWN: "○",
        }
        return symbols.get(self.status, "?")

    @property
    def status_color(self) -> str:
        """Get color for status."""
        colors = {
            AgentStatus.ACTIVE: "yellow",
            AgentStatus.COMPLETED: "green",
            AgentStatus.UNKNOWN: "dim white",
        }
        return colors.get(self.status, "white")

    @property
    def model_short(self) -> str:
        """Get short model name for display."""
        if not self.model:
            return "unknown"
        if "opus" in self.model.lower():
            return "opus"
        if "sonnet" in self.model.lower():
            return "sonnet"
        if "haiku" in self.model.lower():
            return "haiku"
        return self.model[:15]


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError):
        return datetime.min


def _extract_tool_summary(input_data: dict[str, Any]) -> str:
    """Extract a summary of tool input for display."""
    if not input_data:
        return ""

    # Common patterns - compress paths in all text
    if "command" in input_data:
        return compress_paths_in_text(str(input_data["command"])[:80])
    if "file_path" in input_data:
        return compress_path(str(input_data["file_path"]))
    if "pattern" in input_data:
        return compress_paths_in_text(str(input_data["pattern"])[:60])
    if "query" in input_data:
        return compress_paths_in_text(str(input_data["query"])[:60])
    if "url" in input_data:
        return str(input_data["url"])[:60]
    if "prompt" in input_data:
        return compress_paths_in_text(str(input_data["prompt"])[:80])

    # Fallback - compress any paths in the value
    for v in input_data.values():
        if isinstance(v, str) and v:
            return compress_paths_in_text(v[:80])

    return compress_paths_in_text(str(input_data)[:80])


def parse_subagent_file(file_path: Path) -> Subagent | None:
    """Parse a subagent JSONL file into a Subagent object.

    Args:
        file_path: Path to the agent JSONL file.

    Returns:
        Subagent object or None if file is invalid.
    """
    if not file_path.exists():
        return None

    agent_id = ""
    slug = ""
    session_id = ""
    model = ""
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0
    tool_counts: Counter[str] = Counter()
    activities: list[SubagentActivity] = []
    initial_prompt = ""
    status = AgentStatus.UNKNOWN

    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Extract metadata from first record
                if not agent_id and data.get("agentId"):
                    agent_id = data["agentId"]
                if not slug and data.get("slug"):
                    slug = data["slug"]
                if not session_id and data.get("sessionId"):
                    session_id = data["sessionId"]

                timestamp = _parse_timestamp(data.get("timestamp", ""))
                if timestamp != datetime.min:
                    if first_ts is None or timestamp < first_ts:
                        first_ts = timestamp
                    if last_ts is None or timestamp > last_ts:
                        last_ts = timestamp

                msg_type = data.get("type", "")
                message = data.get("message", {})

                # Handle assistant messages
                if msg_type == "assistant":
                    if not model and message.get("model"):
                        model = message["model"]

                    usage = message.get("usage", {})
                    input_tokens += usage.get("input_tokens", 0)
                    output_tokens += usage.get("output_tokens", 0)
                    cache_read_tokens += usage.get("cache_read_input_tokens", 0)
                    cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)

                    content_list = message.get("content", [])
                    if content_list:
                        for item in content_list:
                            if not isinstance(item, dict):
                                continue
                            block = cast(dict[str, Any], item)

                            item_type: str = str(block.get("type", ""))

                            if item_type == "thinking":
                                thinking_text: str = str(block.get("thinking", ""))
                                if thinking_text:
                                    activity = SubagentActivity(
                                        activity_type="thinking",
                                        content=thinking_text[:200],
                                        timestamp=timestamp,
                                    )
                                    activities.append(activity)
                                    status = AgentStatus.ACTIVE

                            elif item_type == "tool_use":
                                tool_name: str = str(block.get("name", ""))
                                tool_input: dict[str, Any] = dict(block.get("input", {}))
                                tool_counts[tool_name] += 1
                                activity = SubagentActivity(
                                    activity_type="tool_call",
                                    content=_extract_tool_summary(tool_input),
                                    timestamp=timestamp,
                                    tool_name=tool_name,
                                    tool_id=str(block.get("id", "")),
                                )
                                activities.append(activity)
                                status = AgentStatus.ACTIVE

                            elif item_type == "text":
                                text_content: str = str(block.get("text", ""))
                                if text_content:
                                    # Check for completion indicators using word boundaries
                                    text_lower: str = text_content.lower()
                                    if re.search(
                                        r"\b(complete|finished|done|summary|conclusion)\b",
                                        text_lower,
                                    ):
                                        status = AgentStatus.COMPLETED
                                    activity = SubagentActivity(
                                        activity_type="text",
                                        content=text_content[:200],
                                        timestamp=timestamp,
                                    )
                                    activities.append(activity)

                # Handle user messages (initial prompt)
                elif msg_type == "user":
                    content = message.get("content", "")
                    text: str = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        # Extract text from content blocks
                        for raw_block in cast(list[Any], content):
                            if not isinstance(raw_block, dict):
                                continue
                            typed_block = cast(dict[str, Any], raw_block)
                            if typed_block.get("type") == "text":
                                text = str(typed_block.get("text", ""))
                                break
                    if text and not text.startswith("<"):
                        if not initial_prompt:
                            initial_prompt = text
                        activity = SubagentActivity(
                            activity_type="user",
                            content=text[:200],
                            timestamp=timestamp,
                        )
                        # Insert at beginning
                        activities.insert(0, activity)

    except OSError:
        return None

    if not agent_id:
        # Try to extract from filename
        if file_path.stem.startswith("agent-"):
            agent_id = file_path.stem[6:]
        else:
            return None

    # Determine final status based on activity
    if activities and status == AgentStatus.UNKNOWN:
        # If we have activities but status is unknown, assume active
        status = AgentStatus.ACTIVE

    # Check for completion: if last activity was a text response, likely completed
    # Heuristic: if there's been no activity in 30+ seconds and last was text, probably done
    if (
        activities
        and activities[-1].activity_type == "text"
        and last_ts
        and (datetime.now(last_ts.tzinfo) - last_ts).total_seconds() > 30
    ):
        status = AgentStatus.COMPLETED

    return Subagent(
        agent_id=agent_id,
        slug=slug,
        session_id=session_id,
        file_path=file_path,
        status=status,
        model=model,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        tool_counts=tool_counts,
        activities=activities,
        last_activity=activities[-1] if activities else None,
        initial_prompt=initial_prompt,
    )


def find_subagent_files(
    session_id: str | None = None,
    project_path: Path | None = None,
) -> list[Path]:
    """Find all subagent JSONL files.

    Args:
        session_id: Optional session ID to filter by.
        project_path: Optional project path to filter by.

    Returns:
        List of paths to subagent JSONL files.
    """
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return []

    agent_files: list[Path] = []

    # Determine which project folders to search
    if project_path:
        encoded = encode_project_path(project_path)
        search_folders = [claude_projects / encoded]
    else:
        search_folders = list(claude_projects.iterdir())

    for project_folder in search_folders:
        if not project_folder.is_dir():
            continue

        # Pattern 1: Direct agent-*.jsonl files in project folder
        for agent_file in project_folder.glob("agent-*.jsonl"):
            if session_id:
                # Check if this agent belongs to the session
                try:
                    with agent_file.open("r", encoding="utf-8") as f:
                        first_line = f.readline()
                        if first_line:
                            data = json.loads(first_line)
                            if data.get("sessionId") != session_id:
                                continue
                except (json.JSONDecodeError, OSError):
                    continue
            agent_files.append(agent_file)

        # Pattern 2: {session-id}/subagents/agent-*.jsonl
        for session_folder in project_folder.iterdir():
            if not session_folder.is_dir():
                continue

            # Filter by session ID if provided
            if session_id and session_id not in session_folder.name:
                continue

            subagents_folder = session_folder / "subagents"
            if subagents_folder.exists():
                for agent_file in subagents_folder.glob("agent-*.jsonl"):
                    agent_files.append(agent_file)

    return sorted(agent_files, key=lambda p: p.stat().st_mtime, reverse=True)


def filter_inactive_agents(
    agents: list[Subagent],
    inactive_timeout: float,
) -> list[Subagent]:
    """Filter out agents with no activity beyond the timeout threshold.

    Args:
        agents: List of Subagent objects.
        inactive_timeout: Seconds of inactivity before hiding an agent.
            Use 0 to disable filtering (show all agents).

    Returns:
        Filtered list of agents.
    """
    if inactive_timeout <= 0:
        return agents

    now = datetime.now(tz=UTC)
    result: list[Subagent] = []
    for agent in agents:
        if agent.last_timestamp is None:
            # No timestamp at all — skip
            continue
        last_ts = agent.last_timestamp
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        elapsed = (now - last_ts).total_seconds()
        if elapsed <= inactive_timeout:
            result.append(agent)
    return result


def load_subagents(
    session_id: str | None = None,
    project_path: Path | None = None,
    inactive_timeout: float = 0,
) -> list[Subagent]:
    """Load all subagents.

    Args:
        session_id: Optional session ID to filter by.
        project_path: Optional project path to filter by.
        inactive_timeout: Seconds of inactivity before hiding an agent.
            Use 0 to disable filtering (show all agents).

    Returns:
        List of Subagent objects sorted by first timestamp.
    """
    agent_files = find_subagent_files(session_id, project_path)
    agents: list[Subagent] = []

    for file_path in agent_files:
        agent = parse_subagent_file(file_path)
        if agent:
            agents.append(agent)

    # Filter inactive agents
    if inactive_timeout > 0:
        agents = filter_inactive_agents(agents, inactive_timeout)

    # Sort by first timestamp (most recent first)
    return sorted(
        agents,
        key=lambda a: a.first_timestamp or datetime.min,
        reverse=True,
    )


def _find_most_recent_subagent_session(
    project_folder: Path,
) -> tuple[str, float] | None:
    """Find the session with the most recently modified subagent file.

    Scans the filesystem directly instead of relying on sessions-index.json,
    which may be incomplete and miss newer sessions.

    Args:
        project_folder: Claude project folder (e.g. ~/.claude/projects/-Users-foo-bar).

    Returns:
        Tuple of (session_id, mtime) or None if no subagents found.
    """
    best: tuple[str, float] | None = None

    try:
        for session_dir in project_folder.iterdir():
            if not session_dir.is_dir():
                continue
            subagents_dir = session_dir / "subagents"
            if not subagents_dir.exists():
                continue
            for agent_file in subagents_dir.glob("agent-*.jsonl"):
                try:
                    mtime = agent_file.stat().st_mtime
                    if best is None or mtime > best[1]:
                        best = (session_dir.name, mtime)
                except OSError:
                    continue
    except OSError:
        pass

    return best


def resolve_subagent_path(
    session_or_path: str | None = None,
    project_path: Path | None = None,
) -> tuple[str | None, Path | None, str]:
    """Resolve the session/project for subagent monitoring.

    Scans the filesystem directly to find sessions with subagents, rather than
    relying on sessions-index.json which may be incomplete.

    Args:
        session_or_path: Session ID, partial session ID, or project path.
        project_path: Project directory to find sessions for.

    Returns:
        Tuple of (session_id, project_path, display_name) or (None, None, error_message).
    """
    claude_projects = Path.home() / ".claude" / "projects"

    # Case 1: Direct session ID provided
    if session_or_path:
        # Try as direct session ID in specific project
        if project_path:
            encoded = encode_project_path(project_path)
            project_folder = claude_projects / encoded
            session_folder = project_folder / session_or_path
            if session_folder.exists():
                return session_or_path, project_path, f"{session_or_path[:8]}..."

        # Search all projects for matching session (exact then partial)
        if claude_projects.exists():
            for pf in claude_projects.iterdir():
                if not pf.is_dir():
                    continue
                # Exact match
                session_folder = pf / session_or_path
                if session_folder.exists():
                    project_name = pf.name.split("-")[-1] if "-" in pf.name else pf.name
                    return session_or_path, None, f"{session_or_path[:8]}... ({project_name})"

                # Partial match
                for sf in pf.iterdir():
                    if sf.is_dir() and session_or_path in sf.name:
                        project_name = pf.name.split("-")[-1] if "-" in pf.name else pf.name
                        return sf.name, None, f"{sf.name[:8]}... ({project_name})"

        return None, None, f"No session found for: {session_or_path}"

    # Case 2: Project path provided - scan filesystem for most recent subagents
    if project_path:
        encoded = encode_project_path(project_path)
        project_folder = claude_projects / encoded

        if project_folder.exists():
            result = _find_most_recent_subagent_session(project_folder)
            if result:
                session_id, _ = result
                return session_id, project_path, f"{session_id[:8]}... ({project_path.name})"

            # Check for direct agent files in project folder
            if list(project_folder.glob("agent-*.jsonl")):
                return None, project_path, f"Project: {project_path.name}"

        return None, project_path, f"No subagents found for project: {project_path}"

    # Case 3: Use current directory - scan filesystem directly
    cwd = Path.cwd()
    encoded = encode_project_path(cwd)
    project_folder = claude_projects / encoded

    if project_folder.exists():
        result = _find_most_recent_subagent_session(project_folder)
        if result:
            session_id, _ = result
            return session_id, cwd, f"{session_id[:8]}... ({cwd.name})"

        # Check for direct agent files
        if list(project_folder.glob("agent-*.jsonl")):
            return None, cwd, f"Project: {cwd.name}"

    return None, None, "No subagents found"


def get_terminal_size() -> tuple[int, int]:
    """Get terminal width and height."""
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except (AttributeError, ValueError):
        return 80, 24


def _format_tokens(count: int) -> str:
    """Format token count for display."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def build_agent_table(agents: list[Subagent], max_agents: int = 20) -> Table:
    """Build a table of subagents.

    Args:
        agents: List of Subagent objects.
        max_agents: Maximum number of agents to display. 0 for unlimited.

    Returns:
        Rich Table with agent information.
    """
    table = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        expand=True,
    )

    table.add_column("", width=2)
    table.add_column("Agent", ratio=1)
    table.add_column("Model", width=8)
    table.add_column("Duration", width=8)
    table.add_column("Tokens", width=10)
    table.add_column("Tools", width=15)
    table.add_column("Current Activity", ratio=2)

    total_agents = len(agents)
    display_limit = max_agents if max_agents > 0 else total_agents
    display_agents = agents[:display_limit]

    # Detect duplicate slugs so we can disambiguate with agent_id suffix
    slug_counts: Counter[str] = Counter(a.display_name for a in display_agents)

    for agent in display_agents:
        # Status symbol
        status_text = Text(agent.status_symbol, style=agent.status_color)

        # Agent name — when slug is shared, show agent_id + beginning of initial prompt
        base_name = agent.display_name
        if slug_counts[base_name] > 1:
            short_id = agent.agent_id[:7]
            if agent.initial_prompt:
                prompt_preview = agent.initial_prompt.replace("\n", " ").strip()[:64]
                name = f"{short_id} · {prompt_preview}"
            else:
                name = short_id
        else:
            name = base_name

        # Token display
        tokens = f"{_format_tokens(agent.input_tokens)}→{_format_tokens(agent.output_tokens)}"

        # Top tools
        top_tools = agent.tool_counts.most_common(2)
        tools_str = ", ".join(f"{t[0]}({t[1]})" for t in top_tools) if top_tools else "-"
        if len(tools_str) > 15:
            tools_str = tools_str[:12] + "..."

        # Current activity - let ratio=2 column handle width; only strip newlines
        activity = "-"
        if agent.last_activity:
            act = agent.last_activity
            content = compress_paths_in_text(act.content).replace("\n", " ")
            if act.activity_type == "tool_call":
                activity = f"{act.symbol} {act.tool_name}: {content}"
            else:
                activity = f"{act.symbol} {content}"

        table.add_row(
            status_text,
            Text(name, style="cyan"),
            agent.model_short,
            agent.duration_display,
            tokens,
            tools_str,
            Text(activity, style=agent.status_color),
        )

    hidden = total_agents - len(display_agents)
    if hidden > 0:
        table.add_row(
            Text(""),
            Text(f"... and {hidden} more agents", style="dim italic"),
            "",
            "",
            "",
            "",
            Text(""),
        )

    return table


def build_stats_panel(agents: list[Subagent], display_name: str) -> Panel:
    """Build a statistics panel.

    Args:
        agents: List of Subagent objects.
        display_name: Display name for the session/project.

    Returns:
        Rich Panel with statistics.
    """
    text = Text()

    total = len(agents)
    active = sum(1 for a in agents if a.status == AgentStatus.ACTIVE)
    completed = sum(1 for a in agents if a.status == AgentStatus.COMPLETED)

    total_input = sum(a.input_tokens for a in agents)
    total_output = sum(a.output_tokens for a in agents)

    # Aggregate tool counts
    all_tools: Counter[str] = Counter()
    for agent in agents:
        all_tools.update(agent.tool_counts)

    text.append("Session: ", style="dim")
    text.append(f"{display_name}  ", style="bold cyan")
    text.append(f"Total: {total}  ", style="bold")
    text.append(f"○ {total - active - completed}  ", style="dim white")
    text.append(f"◐ {active}  ", style="yellow")
    text.append(f"● {completed}", style="green")

    text.append("\nTokens: ", style="dim")
    text.append(f"{_format_tokens(total_input)} in / {_format_tokens(total_output)} out  ", style="bold")

    if all_tools:
        text.append("Top Tools: ", style="dim")
        top_tools = all_tools.most_common(5)
        text.append("  ".join(f"{t[0]}x{t[1]}" for t in top_tools), style="cyan")

    return Panel(text, title="Subagent Stats", border_style="blue")


def build_activity_panel(agents: list[Subagent], max_activities: int = 15) -> Panel:
    """Build a panel showing recent activities across all agents.

    Args:
        agents: List of Subagent objects.
        max_activities: Maximum number of activities to show.

    Returns:
        Rich Panel with recent activities.
    """
    # Collect all activities with agent info
    all_activities: list[tuple[Subagent, SubagentActivity]] = []
    for agent in agents:
        for activity in agent.activities[-10:]:  # Last 10 from each agent
            all_activities.append((agent, activity))

    # Sort by timestamp (most recent first)
    all_activities.sort(key=lambda x: x[1].timestamp, reverse=True)

    text = Text()
    for agent, activity in all_activities[:max_activities]:
        ts_str = activity.timestamp.strftime("%H:%M:%S")
        text.append(f"{ts_str} ", style="dim")
        text.append(f"[{agent.agent_id[:7]}] ", style="cyan")
        text.append(f"{activity.symbol} ", style=activity.color)

        content = compress_paths_in_text(activity.content.replace("\n", " "))
        if activity.activity_type == "tool_call":
            content = f"{activity.tool_name}: {content}"

        if len(content) > 60:
            content = content[:57] + "..."

        text.append(f"{content}\n", style=activity.color)

    if not all_activities:
        text.append("No activity yet", style="dim")

    return Panel(text, title="Recent Activity", border_style="cyan")


def build_display(
    agents: list[Subagent],
    display_name: str,
    show_activity: bool = True,
    max_agents: int = 20,
    max_activities: int = 15,
    terminal_height: int = 0,
) -> Group:
    """Build the complete display.

    Args:
        agents: List of Subagent objects.
        display_name: Display name for the session/project.
        show_activity: Whether to show the activity panel.
        max_agents: Maximum number of agents to display. 0 for unlimited.
        max_activities: Maximum number of recent activities to show.
        terminal_height: Terminal height for dynamic sizing. 0 to disable.

    Returns:
        Rich Group with all panels.
    """
    effective_agents = max_agents
    effective_activities = max_activities

    if terminal_height > 0:
        # Stats panel: 2 content lines + 2 borders = 4 rows
        stats_height = 4
        available = terminal_height - stats_height

        # Agent table overhead: 2 panel borders + 1 table header = 3
        agent_overhead = 3
        # Activity panel overhead: 2 panel borders
        activity_overhead = 2

        natural_agents = min(len(agents), max_agents) if max_agents > 0 else len(agents)
        natural_agents = max(natural_agents, 1)

        if show_activity:
            total_activities = sum(min(10, len(a.activities)) for a in agents)
            natural_activities = max(min(total_activities, max_activities), 1)
            total_natural = natural_agents + natural_activities
            content_budget = max(2, available - agent_overhead - activity_overhead)

            if content_budget >= total_natural:
                effective_agents = natural_agents
                effective_activities = natural_activities
            else:
                effective_agents = max(1, round(content_budget * natural_agents / total_natural))
                effective_activities = max(1, content_budget - effective_agents)
                effective_agents = min(effective_agents, natural_agents)
                effective_activities = min(effective_activities, natural_activities)
        else:
            content_budget = max(1, available - agent_overhead)
            effective_agents = min(natural_agents, content_budget)

    components = [
        build_stats_panel(agents, display_name),
        Panel(build_agent_table(agents, max_agents=effective_agents), title="Subagents", border_style="green"),
    ]

    if show_activity:
        components.append(build_activity_panel(agents, max_activities=effective_activities))

    return Group(*components)


def list_subagents(
    session_id: str | None = None,
    project_path: Path | None = None,
    inactive_timeout: float = 0,
) -> None:
    """List available subagents.

    Args:
        session_id: Optional session ID to filter by.
        project_path: Optional project path to filter by.
        inactive_timeout: Seconds of inactivity before hiding an agent.
            Use 0 to disable filtering.
    """
    console = Console()

    agents = load_subagents(session_id, project_path, inactive_timeout)

    if not agents:
        console.print("[yellow]No subagents found.[/]")
        return

    console.print(f"[bold]Found {len(agents)} subagent(s):[/]\n")

    for agent in agents:
        status_text = f"[{agent.status_color}]{agent.status_symbol}[/]"
        console.print(f"  {status_text} [cyan]{agent.display_name}[/] ({agent.agent_id})")
        console.print(f"      Model: {agent.model_short}  Duration: {agent.duration_display}")
        console.print(
            f"      Tokens: {_format_tokens(agent.input_tokens)} in / {_format_tokens(agent.output_tokens)} out"
        )
        if agent.tool_counts:
            top = agent.tool_counts.most_common(3)
            console.print(f"      Tools: {', '.join(f'{t[0]}({t[1]})' for t in top)}")
        console.print()


def run_subagent_monitor(
    session_or_path: str | None = None,
    project_path: Path | None = None,
    poll_interval: float = 1.0,
    show_activity: bool = True,
    inactive_timeout: float = 300.0,
    max_agents: int = 20,
) -> None:
    """Run the subagent monitor with Rich Live.

    Args:
        session_or_path: Session ID, partial ID, or project path.
        project_path: Project directory to find sessions for.
        poll_interval: How often to poll for changes (seconds).
        show_activity: Whether to show the activity panel.
        inactive_timeout: Seconds of inactivity before hiding an agent.
            Use 0 to disable filtering. Default is 300 (5 minutes).
        max_agents: Maximum number of agents to display. 0 for unlimited.
    """
    console = Console()

    # Resolve what to monitor - may return project without session if no subagents yet
    session_id, resolved_project, display_name = resolve_subagent_path(session_or_path, project_path)

    # If we have neither session nor project, try to at least use current directory
    if not session_id and not resolved_project:
        # Fall back to current directory even if no subagents exist yet
        cwd = Path.cwd()
        claude_projects = Path.home() / ".claude" / "projects"
        encoded = encode_project_path(cwd)
        if (claude_projects / encoded).exists():
            resolved_project = cwd
            display_name = f"Project: {cwd.name} (waiting for subagents)"
        else:
            console.print(f"[red]{display_name}[/]")
            console.print("[dim]No Claude project found for current directory.[/]")
            console.print("[dim]Run Claude Code in this directory first.[/]")
            return

    console.clear()
    console.print(f"[bold cyan]Subagent Monitor[/] - {display_name}")
    console.print("[dim]Auto-refreshes every poll interval[/]\n")

    # Track last data hash to avoid unnecessary display updates
    last_data_hash = ""

    def compute_data_hash(agents: list[Subagent]) -> str:
        """Compute a simple hash of agent state for change detection."""
        parts: list[str] = []
        for agent in agents:
            parts.append(f"{agent.agent_id}:{agent.last_timestamp}:{len(agent.activities)}")
        return "|".join(parts)

    try:
        with Live(
            Text("Loading subagents...", style="dim"),
            console=console,
            refresh_per_second=1,
        ) as live:
            while True:
                # Always reload data on each poll
                agents = load_subagents(session_id, resolved_project, inactive_timeout)
                data_hash = compute_data_hash(agents)

                # Only update display if data actually changed
                if data_hash != last_data_hash:
                    last_data_hash = data_hash
                    if agents:
                        live.update(
                            build_display(
                                agents,
                                display_name,
                                show_activity,
                                max_agents=max_agents,
                                terminal_height=console.height - 2,
                            )
                        )
                    else:
                        live.update(
                            Panel(
                                Text("Waiting for subagents to spawn...", style="dim"),
                                title="Subagent Monitor",
                                border_style="yellow",
                            )
                        )

                time.sleep(poll_interval)

    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")
