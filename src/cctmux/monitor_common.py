"""Shared helpers for the cctmux real-time monitors.

Centralizes the small utilities that were previously copy-pasted across
``session_monitor``, ``subagent_monitor``, ``ralph_monitor``,
``activity_monitor``, and ``task_monitor`` (terminal sizing, timestamp
parsing, token formatting, and model cost estimation) so fixes and
behavior land in exactly one place.
"""

from __future__ import annotations

import shutil
from datetime import datetime

# Model pricing per 1M tokens.
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


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string to datetime.

    Args:
        ts_str: ISO-8601 timestamp string, optionally with a trailing "Z".

    Returns:
        Parsed datetime, or ``datetime.min`` if parsing fails.
    """
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError):
        return datetime.min


def format_tokens(count: int) -> str:
    """Format token count for display.

    Args:
        count: Number of tokens.

    Returns:
        Formatted string like "1.2K", "1.5M", or "1.5B".
    """
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def get_model_tier(model: str) -> str:
    """Determine pricing tier from model name.

    Args:
        model: Model name/ID.

    Returns:
        Pricing tier: "opus", "sonnet", or "haiku". Defaults to "opus"
        for unrecognized models.
    """
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
    tier = get_model_tier(model)
    pricing = MODEL_PRICING.get(tier)
    if pricing is None:
        return 0.0

    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
        + (cache_read_tokens / 1_000_000) * pricing["cache_read"]
        + (cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    )
    return round(cost, 2)
