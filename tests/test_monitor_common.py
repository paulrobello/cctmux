"""Tests for monitor_common module."""

from __future__ import annotations

import logging
from concurrent.futures import Future
from datetime import datetime

import pytest

from cctmux.monitor_common import (
    MODEL_PRICING,
    estimate_cost,
    format_tokens,
    get_model_tier,
    get_terminal_size,
    parse_timestamp,
)
from cctmux.subagent_monitor import _handle_summary_result


class TestFormatTokens:
    """Tests for format_tokens tier boundaries."""

    def test_below_thousand(self) -> None:
        """Counts under 1,000 are shown as-is."""
        assert format_tokens(0) == "0"
        assert format_tokens(999) == "999"

    def test_thousands_tier(self) -> None:
        """Counts in the thousands are formatted with a K suffix."""
        assert format_tokens(1_000) == "1.0K"
        assert format_tokens(12_340) == "12.3K"

    def test_millions_tier(self) -> None:
        """Counts in the millions are formatted with an M suffix."""
        assert format_tokens(1_000_000) == "1.0M"
        assert format_tokens(5_500_000) == "5.5M"

    def test_billions_tier(self) -> None:
        """Counts in the billions are formatted with a B suffix (the drifted tier)."""
        assert format_tokens(1_500_000_000) == "1.5B"
        assert format_tokens(1_000_000_000) == "1.0B"


class TestParseTimestamp:
    """Tests for parse_timestamp."""

    def test_valid_iso_timestamp(self) -> None:
        """A standard ISO timestamp with a Z suffix parses correctly."""
        result = parse_timestamp("2026-01-17T21:35:02.482Z")
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 17

    def test_valid_iso_timestamp_with_offset(self) -> None:
        """A timestamp with an explicit UTC offset parses correctly."""
        result = parse_timestamp("2026-01-17T21:35:02+00:00")
        assert result.year == 2026

    def test_invalid_timestamp_returns_min(self) -> None:
        """An unparseable string falls back to datetime.min."""
        assert parse_timestamp("not-a-timestamp") == datetime.min

    def test_empty_string_returns_min(self) -> None:
        """An empty string falls back to datetime.min."""
        assert parse_timestamp("") == datetime.min


class TestGetModelTier:
    """Tests for get_model_tier."""

    def test_opus(self) -> None:
        """Model names containing 'opus' resolve to the opus tier."""
        assert get_model_tier("claude-opus-4-5-20251101") == "opus"

    def test_sonnet(self) -> None:
        """Model names containing 'sonnet' resolve to the sonnet tier."""
        assert get_model_tier("claude-sonnet-4-20250514") == "sonnet"

    def test_haiku(self) -> None:
        """Model names containing 'haiku' resolve to the haiku tier."""
        assert get_model_tier("claude-haiku-4-5-20251001") == "haiku"

    def test_unknown_model_defaults_to_opus(self) -> None:
        """An unrecognized model name defaults to the opus tier."""
        assert get_model_tier("unknown-model") == "opus"


class TestEstimateCost:
    """Tests for estimate_cost."""

    def test_opus_cost(self) -> None:
        """Opus pricing is applied for input and output tokens."""
        cost = estimate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert cost == MODEL_PRICING["opus"]["input"] + MODEL_PRICING["opus"]["output"]

    def test_sonnet_cost_with_cache(self) -> None:
        """Sonnet pricing accounts for cache read and cache write tokens."""
        cost = estimate_cost(
            model="claude-sonnet-4-20250514",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_creation_tokens=1_000_000,
        )
        expected = MODEL_PRICING["sonnet"]["cache_read"] + MODEL_PRICING["sonnet"]["cache_write"]
        assert cost == round(expected, 2)

    def test_zero_tokens_is_free(self) -> None:
        """No tokens used means no cost."""
        assert estimate_cost("claude-opus-4-5-20251101", 0, 0, 0, 0) == 0.0


class TestGetTerminalSize:
    """Tests for get_terminal_size."""

    def test_returns_positive_dimensions(self) -> None:
        """The terminal size always returns positive width and height."""
        columns, lines = get_terminal_size()
        assert columns > 0
        assert lines > 0


class TestSubagentSummaryFailureNotSwallowed:
    """Regression test for QA-001: summary future failures must not be silently dropped."""

    def test_raising_future_is_logged_not_swallowed(self, caplog: pytest.LogCaptureFixture) -> None:
        """A future that raises records a debug log and does not crash the callback."""
        fut: Future[str] = Future()
        fut.set_exception(OSError("summary subprocess failed"))

        summaries: dict[str, str] = {}
        with caplog.at_level(logging.DEBUG, logger="cctmux.subagent_monitor"):
            redraw_needed = _handle_summary_result("agent-123", fut, summaries)

        assert redraw_needed is False
        assert "agent-123" not in summaries
        assert any("agent-123" in record.getMessage() for record in caplog.records)
