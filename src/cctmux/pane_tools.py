"""Agent-facing pane inspection tools: machine-readable pane listing and idle detection.

Backs the ``cctmux panes`` and ``cctmux wait-idle`` CLI commands so orchestrating
agents can query pane state as JSON and block until a Claude pane goes idle,
instead of hand-rolling ``tmux list-panes`` parsing and ``capture-pane`` polling
loops (see the bundled skill reference ``driving-claude-panes.md``).
"""

import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass

_TMUX_TIMEOUT = 10

# Fields captured per pane, tab-separated to survive spaces in titles/paths.
_PANE_FORMAT = (
    "#{pane_id}\t#{window_index}.#{pane_index}\t#{pane_active}\t"
    "#{pane_current_command}\t#{pane_width}\t#{pane_height}\t"
    "#{pane_current_path}\t#{pane_title}"
)

# Active-spinner signatures for a working Claude Code pane. Absence across a
# sustained window is treated as idle — see driving-claude-panes.md for why
# "detect working, infer idle" is the reliable direction. The "(NNs" timer and
# "esc to interrupt" patterns are the most version-stable; the glyph set and
# "thinking with" string match the current Claude Code build.
DEFAULT_BUSY_PATTERN = r"\([0-9]+(m [0-9]+)?s |esc to interrupt|[0-9]+(\.[0-9]+)?k? tokens|thinking with|✽|✶|✻|✢"


@dataclass
class PaneInfo:
    """A single tmux pane's state, as reported by list-panes."""

    pane_id: str
    index: str
    active: bool
    command: str
    width: int
    height: int
    path: str
    title: str


@dataclass
class WaitResult:
    """Outcome of an idle-wait poll loop."""

    state: str  # "idle" or "timeout"
    elapsed: float
    tail: list[str]


def list_panes(session: str) -> list[PaneInfo]:
    """List all panes in a tmux session across all windows.

    Args:
        session: Target session name.

    Returns:
        One PaneInfo per pane.

    Raises:
        RuntimeError: If tmux fails (e.g. unknown session).
    """
    result = subprocess.run(
        ["tmux", "list-panes", "-s", "-t", session, "-F", _PANE_FORMAT],
        capture_output=True,
        text=True,
        timeout=_TMUX_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"tmux list-panes failed for session {session!r}")

    panes: list[PaneInfo] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 7)
        if len(parts) != 8:
            continue
        pane_id, index, active, command, width, height, path, title = parts
        panes.append(
            PaneInfo(
                pane_id=pane_id,
                index=index,
                active=active == "1",
                command=command,
                width=int(width),
                height=int(height),
                path=path,
                title=title,
            )
        )
    return panes


def panes_to_json(panes: list[PaneInfo]) -> str:
    """Serialize panes to a JSON array string."""
    return json.dumps([asdict(p) for p in panes], indent=2)


def capture_pane_tail(pane: str, lines: int) -> str:
    """Capture the last ``lines`` lines of a pane's visible content and scrollback.

    Args:
        pane: Pane ID (%N) or any tmux target.
        lines: Scrollback lines to include.

    Returns:
        Captured text.

    Raises:
        RuntimeError: If tmux fails (e.g. pane gone).
    """
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", pane, "-S", f"-{lines}"],
        capture_output=True,
        text=True,
        timeout=_TMUX_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"tmux capture-pane failed for pane {pane!r}")
    return result.stdout


def wait_for_idle(
    pane: str,
    timeout: float = 300.0,
    interval: float = 10.0,
    silence: float = 60.0,
    lines: int = 25,
    pattern: str = DEFAULT_BUSY_PATTERN,
) -> WaitResult:
    """Poll a pane until its agent goes idle or the heartbeat timeout expires.

    Implements the idle-or-heartbeat recipe from driving-claude-panes.md: capture
    the pane every ``interval`` seconds and match ``pattern`` (active-spinner
    signatures). A match resets the silence clock; ``silence`` seconds of
    consecutive misses means idle/waiting. ``timeout`` is the heartbeat backstop
    for panes that legitimately work longer than the silence window.

    Args:
        pane: Pane ID (%N) or any tmux target.
        timeout: Hard cap in seconds before returning state="timeout".
        interval: Seconds between capture-pane polls.
        silence: Consecutive seconds without a busy signature to declare idle.
        lines: Scrollback lines per capture (enough that a question menu which
            pushed the spinner off-screen is still in the grab).
        pattern: Busy-signature regex; override for non-Claude tools with
            different spinners.

    Returns:
        WaitResult with state "idle" or "timeout", elapsed seconds, and the
        final capture's lines.

    Raises:
        RuntimeError: If tmux fails mid-poll (e.g. pane closed).
    """
    busy_re = re.compile(pattern)
    misses_needed = max(1, int(silence / interval))
    misses = 0
    elapsed = 0.0
    out = capture_pane_tail(pane, lines)

    while True:
        if busy_re.search(out):
            misses = 0
        else:
            misses += 1
            if misses >= misses_needed:
                return WaitResult(state="idle", elapsed=elapsed, tail=out.splitlines())
        if elapsed >= timeout:
            return WaitResult(state="timeout", elapsed=elapsed, tail=out.splitlines())
        time.sleep(interval)
        elapsed += interval
        out = capture_pane_tail(pane, lines)
