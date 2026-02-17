"""Real-time Claude Code activity dashboard monitor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _empty_dict() -> dict[str, int]:
    return {}


def _empty_list() -> list[DailyActivity]:
    return []


def _empty_str_dict() -> dict[str, Any]:
    return {}


@dataclass
class DailyActivity:
    """Activity data for a single day."""

    date: str
    message_count: int = 0
    session_count: int = 0
    tool_call_count: int = 0
    tokens_by_model: dict[str, int] = field(default_factory=_empty_dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DailyActivity:
        """Create DailyActivity from JSON data."""
        return cls(
            date=str(data.get("date", "")),
            message_count=int(data.get("messageCount", 0)),
            session_count=int(data.get("sessionCount", 0)),
            tool_call_count=int(data.get("toolCallCount", 0)),
        )


@dataclass
class ModelUsage:
    """Token usage data for a model."""

    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    web_search_requests: int = 0

    @classmethod
    def from_json(cls, model_name: str, data: dict[str, Any]) -> ModelUsage:
        """Create ModelUsage from JSON data."""
        return cls(
            model_name=model_name,
            input_tokens=int(data.get("inputTokens", 0)),
            output_tokens=int(data.get("outputTokens", 0)),
            cache_read_tokens=int(data.get("cacheReadInputTokens", 0)),
            cache_creation_tokens=int(data.get("cacheCreationInputTokens", 0)),
            web_search_requests=int(data.get("webSearchRequests", 0)),
        )

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens

    @property
    def model_short(self) -> str:
        """Get short model name for display.

        Extracts model family and version from full model ID.
        e.g., 'claude-opus-4-6-20260205' -> 'opus-4.6'
             'claude-sonnet-4-20250514' -> 'sonnet-4'
        """
        import re

        model_lower = self.model_name.lower()
        # Match model family and version numbers (e.g., opus-4-6 or sonnet-4-5)
        # Only match 1-2 digit versions to avoid matching dates (8 digits)
        for family in ("opus", "sonnet", "haiku"):
            if family in model_lower:
                # Try to extract version like "4-6" or "4-5" or "3-5"
                # Minor version must be 1-2 digits followed by dash or end
                version_match = re.search(rf"{family}-?(\d)-(\d{{1,2}})(?:-|$)", model_lower)
                if version_match:
                    major = version_match.group(1)
                    minor = version_match.group(2)
                    return f"{family}-{major}.{minor}"
                # Try major version only
                version_match = re.search(rf"{family}-?(\d)(?:-|$)", model_lower)
                if version_match:
                    major = version_match.group(1)
                    return f"{family}-{major}"
                return family
        if "glm" in model_lower:
            return "glm"
        return self.model_name[:15]


@dataclass
class ActivityStats:
    """Aggregated activity statistics."""

    total_sessions: int = 0
    total_messages: int = 0
    first_session_date: str = ""
    last_computed_date: str = ""
    daily_activity: list[DailyActivity] = field(default_factory=_empty_list)
    model_usage: dict[str, ModelUsage] = field(default_factory=_empty_str_dict)
    hour_counts: dict[str, int] = field(default_factory=_empty_dict)
    longest_session: dict[str, Any] = field(default_factory=_empty_str_dict)

    @property
    def total_tokens(self) -> int:
        """Total tokens across all models."""
        return sum(m.total_tokens for m in self.model_usage.values())

    @property
    def days_tracked(self) -> int:
        """Number of days with activity data."""
        return len(self.daily_activity)

    def get_recent_activity(self, days: int = 7) -> list[DailyActivity]:
        """Get activity for the last N days."""
        if not self.daily_activity:
            return []
        # Sort by date descending
        sorted_activity = sorted(self.daily_activity, key=lambda x: x.date, reverse=True)
        return sorted_activity[:days]

    def get_weekly_summary(self) -> dict[str, int]:
        """Get activity summary for the last 7 days."""
        recent = self.get_recent_activity(7)
        return {
            "messages": sum(a.message_count for a in recent),
            "sessions": sum(a.session_count for a in recent),
            "tool_calls": sum(a.tool_call_count for a in recent),
        }


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


def estimate_cost(model_usage: ModelUsage) -> float:
    """Estimate cost based on token usage.

    Args:
        model_usage: Model usage data.

    Returns:
        Estimated cost in USD.
    """
    tier = _get_model_tier(model_usage.model_name)
    if tier not in MODEL_PRICING:
        return 0.0

    pricing = MODEL_PRICING[tier]
    cost = (
        (model_usage.input_tokens / 1_000_000) * pricing["input"]
        + (model_usage.output_tokens / 1_000_000) * pricing["output"]
        + (model_usage.cache_read_tokens / 1_000_000) * pricing["cache_read"]
        + (model_usage.cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    )
    return round(cost, 2)


def load_stats_cache() -> ActivityStats | None:
    """Load activity stats from Claude Code's stats-cache.json.

    Returns:
        ActivityStats object or None if file doesn't exist.
    """
    stats_file = Path.home() / ".claude" / "stats-cache.json"
    if not stats_file.exists():
        return None

    try:
        with stats_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Parse daily activity
    daily_activity: list[DailyActivity] = []
    for item in data.get("dailyActivity", []):
        daily_activity.append(DailyActivity.from_json(item))

    # Merge daily token data
    daily_tokens = {d.get("date"): d.get("tokensByModel", {}) for d in data.get("dailyModelTokens", [])}
    for activity in daily_activity:
        if activity.date in daily_tokens:
            activity.tokens_by_model = daily_tokens[activity.date]

    # Parse model usage
    model_usage: dict[str, ModelUsage] = {}
    for model_name, model_data in data.get("modelUsage", {}).items():
        model_usage[model_name] = ModelUsage.from_json(model_name, model_data)

    # Parse hour counts
    hour_counts: dict[str, int] = {}
    for hour_str, count in data.get("hourCounts", {}).items():
        hour_counts[hour_str] = int(count)

    return ActivityStats(
        total_sessions=int(data.get("totalSessions", 0)),
        total_messages=int(data.get("totalMessages", 0)),
        first_session_date=str(data.get("firstSessionDate", "")),
        last_computed_date=str(data.get("lastComputedDate", "")),
        daily_activity=daily_activity,
        model_usage=model_usage,
        hour_counts=hour_counts,
        longest_session=dict(data.get("longestSession", {})),
    )


def _format_tokens(count: int) -> str:
    """Format token count for display."""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def build_ascii_heatmap(stats: ActivityStats, days: int = 14) -> Text:
    """Build an ASCII heatmap of activity.

    Args:
        stats: Activity statistics.
        days: Number of days to show.

    Returns:
        Rich Text with heatmap.
    """
    text = Text()
    recent = stats.get_recent_activity(days)

    if not recent:
        text.append("No activity data available", style="dim")
        return text

    # Find max for scaling
    max_messages = max(a.message_count for a in recent) if recent else 1
    if max_messages == 0:
        max_messages = 1

    # Blocks for intensity
    blocks = " ░▒▓█"

    # Reverse to show oldest first
    recent_sorted = list(reversed(recent))

    for activity in recent_sorted:
        # Calculate intensity (0-4)
        intensity = min(4, int((activity.message_count / max_messages) * 4))
        block = blocks[intensity]

        # Parse date for display
        try:
            date_obj = datetime.fromisoformat(activity.date)
            day_str = date_obj.strftime("%a %d")
        except ValueError:
            day_str = activity.date[-5:]

        color = ["dim", "green", "yellow", "orange1", "red"][intensity]
        text.append(f"{day_str} ", style="dim")
        text.append(f"{block * 10} ", style=color)
        text.append(f"{activity.message_count:>5} msgs", style="dim")
        text.append(f"  {activity.session_count:>2} sessions", style="dim")
        text.append(f"  {activity.tool_call_count:>4} tools\n", style="dim")

    return text


def build_model_usage_table(
    stats: ActivityStats,
    show_cost: bool = True,
    max_models: int = 0,
) -> Table:
    """Build a table of model usage.

    Args:
        stats: Activity statistics.
        show_cost: Whether to show cost estimates.
        max_models: Maximum number of models to display. 0 for unlimited.

    Returns:
        Rich Table with model usage.
    """
    table = Table(show_header=True, header_style="bold magenta", border_style="dim", expand=True)

    table.add_column("Model", ratio=1)
    table.add_column("Input", width=10)
    table.add_column("Output", width=10)
    table.add_column("Cache Read", width=12)
    table.add_column("Cache Write", width=12)
    if show_cost:
        table.add_column("Est. Cost", width=10)

    sorted_models = sorted(stats.model_usage.items())
    display_models = sorted_models[:max_models] if max_models > 0 else sorted_models

    for _model_name, usage in display_models:
        row: list[str | Text] = [
            Text(usage.model_short, style="cyan"),
            _format_tokens(usage.input_tokens),
            _format_tokens(usage.output_tokens),
            _format_tokens(usage.cache_read_tokens),
            _format_tokens(usage.cache_creation_tokens),
        ]
        if show_cost:
            cost = estimate_cost(usage)
            row.append(Text(f"${cost:.2f}", style="yellow"))
        table.add_row(*row)

    hidden = len(sorted_models) - len(display_models)
    if hidden > 0:
        truncation_row: list[str | Text] = [
            Text(f"... and {hidden} more models", style="dim italic"),
            "",
            "",
            "",
            "",
        ]
        if show_cost:
            truncation_row.append("")
        table.add_row(*truncation_row)

    return table


def build_hour_distribution(stats: ActivityStats) -> Text:
    """Build ASCII visualization of hourly activity distribution.

    Args:
        stats: Activity statistics.

    Returns:
        Rich Text with hour distribution.
    """
    text = Text()

    if not stats.hour_counts:
        text.append("No hourly data available", style="dim")
        return text

    max_count = max(stats.hour_counts.values()) if stats.hour_counts else 1
    if max_count == 0:
        max_count = 1

    # Show distribution as bar chart
    for hour in range(24):
        hour_str = str(hour)
        count = stats.hour_counts.get(hour_str, 0)
        bar_len = int((count / max_count) * 20) if max_count > 0 else 0

        hour_display = f"{hour:02d}:00"
        bar = "█" * bar_len
        text.append(f"{hour_display} ", style="dim")
        text.append(f"{bar:<20} ", style="cyan")
        text.append(f"{count}\n", style="dim")

    return text


def build_summary_panel(stats: ActivityStats, show_cost: bool = True) -> Panel:
    """Build summary statistics panel.

    Args:
        stats: Activity statistics.
        show_cost: Whether to show cost estimates.

    Returns:
        Rich Panel with summary.
    """
    text = Text()

    # Overall stats
    text.append("Total Sessions: ", style="dim")
    text.append(f"{stats.total_sessions}  ", style="bold cyan")
    text.append("Total Messages: ", style="dim")
    text.append(f"{stats.total_messages:,}  ", style="bold cyan")
    text.append("Days Tracked: ", style="dim")
    text.append(f"{stats.days_tracked}\n", style="bold")

    # Weekly summary
    weekly = stats.get_weekly_summary()
    text.append("Last 7 Days: ", style="dim")
    text.append(f"{weekly['messages']:,} msgs  ", style="green")
    text.append(f"{weekly['sessions']} sessions  ", style="green")
    text.append(f"{weekly['tool_calls']:,} tool calls\n", style="green")

    # Token totals
    text.append("Total Tokens: ", style="dim")
    text.append(f"{_format_tokens(stats.total_tokens)}", style="bold")

    # Cost estimates
    if show_cost:
        total_cost = sum(estimate_cost(m) for m in stats.model_usage.values())
        text.append("  Est. Total Cost: ", style="dim")
        text.append(f"${total_cost:,.2f}", style="bold yellow")

    # First session
    if stats.first_session_date:
        try:
            first_date = datetime.fromisoformat(stats.first_session_date.replace("Z", "+00:00"))
            text.append("\nFirst Session: ", style="dim")
            text.append(first_date.strftime("%Y-%m-%d"), style="dim cyan")
        except ValueError:
            pass

    return Panel(text, title="Activity Summary", border_style="blue")


def build_display(
    stats: ActivityStats,
    days: int = 14,
    show_heatmap: bool = True,
    show_cost: bool = True,
    show_tool_usage: bool = True,
    show_model_usage: bool = True,
    show_hour_distribution: bool = False,
    terminal_height: int = 0,
) -> Group:
    """Build the complete activity dashboard display.

    Args:
        stats: Activity statistics.
        days: Number of days to show in heatmap.
        show_heatmap: Whether to show activity heatmap.
        show_cost: Whether to show cost estimates.
        show_tool_usage: Whether to show tool usage (in heatmap).
        show_model_usage: Whether to show model usage table.
        show_hour_distribution: Whether to show hourly distribution.
        terminal_height: Terminal height for dynamic sizing. 0 to disable.

    Returns:
        Rich Group with all panels.
    """
    effective_days = days
    effective_max_models = 0  # 0 = unlimited

    if terminal_height > 0:
        # Summary panel: ~6 content lines + 2 borders = 8
        summary_height = 8
        # Hourly distribution: 24 content lines + 2 borders = 26 (if shown)
        hourly_height = 26 if show_hour_distribution else 0
        available = terminal_height - summary_height - hourly_height

        # Variable panels: heatmap and model usage
        heatmap_overhead = 2  # panel borders
        model_overhead = 3  # panel borders + table header

        show_heat = show_heatmap
        show_models = show_model_usage

        natural_heatmap = min(days, len(stats.daily_activity)) if show_heat else 0
        natural_heatmap = max(natural_heatmap, 1) if show_heat else 0
        natural_models = len(stats.model_usage) if show_models else 0
        natural_models = max(natural_models, 1) if show_models else 0

        if show_heat and show_models:
            total_natural = natural_heatmap + natural_models
            content_budget = max(2, available - heatmap_overhead - model_overhead)
            if content_budget >= total_natural:
                effective_days = natural_heatmap
                effective_max_models = natural_models
            else:
                heat_share = max(1, round(content_budget * natural_heatmap / total_natural))
                model_share = max(1, content_budget - heat_share)
                effective_days = min(heat_share, natural_heatmap)
                effective_max_models = min(model_share, natural_models)
        elif show_heat:
            content_budget = max(1, available - heatmap_overhead)
            effective_days = min(natural_heatmap, content_budget)
        elif show_models:
            content_budget = max(1, available - model_overhead)
            effective_max_models = min(natural_models, content_budget)

    components: list[Panel | Table] = [
        build_summary_panel(stats, show_cost),
    ]

    if show_heatmap:
        components.append(
            Panel(
                build_ascii_heatmap(stats, effective_days),
                title=f"Activity Heatmap (Last {effective_days} Days)",
                border_style="cyan",
            )
        )

    if show_model_usage:
        components.append(
            Panel(
                build_model_usage_table(stats, show_cost, max_models=effective_max_models),
                title="Model Usage",
                border_style="green",
            )
        )

    if show_hour_distribution:
        components.append(
            Panel(
                build_hour_distribution(stats),
                title="Hourly Activity Distribution",
                border_style="magenta",
            )
        )

    return Group(*components)


def run_activity_monitor(
    days: int = 14,
    show_heatmap: bool = True,
    show_cost: bool = True,
    show_model_usage: bool = True,
    show_hour_distribution: bool = False,
    once: bool = True,
) -> None:
    """Run the activity dashboard monitor.

    Args:
        days: Number of days to show.
        show_heatmap: Whether to show activity heatmap.
        show_cost: Whether to show cost estimates.
        show_model_usage: Whether to show model usage table.
        show_hour_distribution: Whether to show hourly distribution.
        once: Whether to display once and exit (vs live refresh).
    """
    console = Console()

    console.clear()

    stats = load_stats_cache()
    if not stats:
        console.print("[red]No activity data found.[/]")
        console.print("[dim]Claude Code stats-cache.json not found at ~/.claude/stats-cache.json[/]")
        return

    console.print("[bold cyan]Claude Code Activity Dashboard[/]\n")

    display = build_display(
        stats,
        days=days,
        show_heatmap=show_heatmap,
        show_cost=show_cost,
        show_model_usage=show_model_usage,
        show_hour_distribution=show_hour_distribution,
        terminal_height=console.height - 2,
    )

    console.print(display)
