"""Predefined tmux layouts for cctmux."""

import subprocess
from collections.abc import Callable

from cctmux.config import CustomLayout, LayoutType, PaneSplit, SplitDirection

# Type alias for layout handler functions
LayoutHandler = Callable[[str, bool], list[str]]

# Timeout for all tmux subprocess calls (seconds)
_TMUX_TIMEOUT = 10


def _run_tmux(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a tmux subprocess command with standard timeout.

    Args:
        cmd: Command to execute.
        **kwargs: Additional arguments for subprocess.run.

    Returns:
        CompletedProcess result.
    """
    return subprocess.run(cmd, check=True, timeout=_TMUX_TIMEOUT, **kwargs)  # type: ignore[arg-type]


def _validate_pane_id(pane_id: str, context: str = "") -> None:
    """Validate that a captured pane ID looks correct.

    Args:
        pane_id: The pane ID string (should start with %).
        context: Description for error messages.

    Raises:
        ValueError: If pane ID is empty or malformed.
    """
    if not pane_id or not pane_id.startswith("%"):
        label = f" ({context})" if context else ""
        raise ValueError(f"Invalid pane ID{label}: {pane_id!r}")


def apply_default_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply default layout (no splits, panes created on demand).

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands (empty for default layout).
    """
    # Default layout has no initial splits
    _ = session_name  # unused
    _ = dry_run  # unused
    return []


def apply_editor_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply editor layout (70/30 horizontal split).

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Split horizontally with 30% on the right
    # Use -d to keep focus on the original (left) pane where Claude runs
    split_cmd = ["tmux", "split-window", "-d", "-t", session_name, "-h", "-p", "30"]
    commands.append(" ".join(split_cmd))
    if not dry_run:
        _run_tmux(split_cmd)

    return commands


def apply_monitor_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply monitor layout (main + bottom bar, 80/20).

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Split vertically with 20% on the bottom
    # Use -d to keep focus on the original (top) pane where Claude runs
    split_cmd = ["tmux", "split-window", "-d", "-t", session_name, "-v", "-p", "20"]
    commands.append(" ".join(split_cmd))
    if not dry_run:
        _run_tmux(split_cmd)

    return commands


def apply_triple_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply triple layout (main + 2 side panes).

    Layout:
    ------------------
    |        |       |
    |  MAIN  |-------|
    |  50%   | 50%   |
    ------------------

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Split horizontally with 30% on the right
    # Use -d to keep focus on the original (left) pane, -P to get new pane ID
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "50"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Split the right pane vertically (50/50) using the captured pane ID
    # Use -d to keep focus on main pane
    if dry_run:
        split_v_cmd = ["tmux", "split-window", "-d", "-t", f"{session_name}:0.1", "-v", "-p", "50"]
    else:
        split_v_cmd = ["tmux", "split-window", "-d", "-t", right_pane_id, "-v", "-p", "50"]
    commands.append(" ".join(split_v_cmd))
    if not dry_run:
        _run_tmux(split_v_cmd)

    return commands


def apply_cc_mon_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply cc-mon layout (Claude + session monitor + task monitor).

    Layout:
    -------------------------------
    | CLAUDE     | cctmux-session |
    | 50%        |    50%         |
    |            |----------------|
    |            | cctmux-tasks -g|
    |            |    50%         |
    -------------------------------

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # Split horizontally with 50% on the right, using -P to get the new pane ID
    # Use -d to keep focus on original pane during split
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "50"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Launch cctmux-session in the right pane
    if dry_run:
        session_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-session", "Enter"]
    else:
        session_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-session", "Enter"]
    commands.append(" ".join(session_cmd))
    if not dry_run:
        _run_tmux(session_cmd)

    # Split the right pane vertically (50/50), using -P to get the new pane ID
    # Use -d to keep focus on main pane
    if dry_run:
        split_v_cmd = [
            "tmux",
            "split-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:0.1",
            "-v",
            "-p",
            "50",
        ]
    else:
        split_v_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", right_pane_id, "-v", "-p", "50"]
    commands.append(" ".join(split_v_cmd))

    bottom_right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_v_cmd, capture_output=True, text=True)
        bottom_right_pane_id = result.stdout.strip()
        _validate_pane_id(bottom_right_pane_id, "bottom-right pane")

    # Launch cctmux-tasks -g in the bottom-right pane
    if dry_run:
        tasks_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.2", "cctmux-tasks -g", "Enter"]
    else:
        tasks_cmd = ["tmux", "send-keys", "-t", bottom_right_pane_id, "cctmux-tasks -g", "Enter"]
    commands.append(" ".join(tasks_cmd))
    if not dry_run:
        _run_tmux(tasks_cmd)

    # Focus the left (main) pane where Claude runs using captured pane ID
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        _run_tmux(focus_cmd)

    return commands


def apply_full_monitor_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply full-monitor layout (Claude + session + task + activity).

    Layout:
    -----------------------------------------
    |           | cctmux-session   30%      |
    | CLAUDE    |-----------------------------|
    | 60%       | cctmux-tasks -g   35%      |
    |           |-----------------------------|
    |           | cctmux-activity   35%      |
    -----------------------------------------

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # Split horizontally with 40% on the right, using -P to get the new pane ID
    # Use -d to keep focus on original pane during split
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Launch cctmux-session in the top-right pane
    if dry_run:
        session_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-session", "Enter"]
    else:
        session_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-session", "Enter"]
    commands.append(" ".join(session_cmd))
    if not dry_run:
        _run_tmux(session_cmd)

    # Split the right pane vertically (65/35 for tasks+activity vs session)
    # Use -d to keep focus on main pane
    if dry_run:
        split_v_cmd = [
            "tmux",
            "split-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:0.1",
            "-v",
            "-p",
            "70",
        ]
    else:
        split_v_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", right_pane_id, "-v", "-p", "70"]
    commands.append(" ".join(split_v_cmd))

    middle_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_v_cmd, capture_output=True, text=True)
        middle_pane_id = result.stdout.strip()
        _validate_pane_id(middle_pane_id, "middle pane")

    # Launch cctmux-tasks -g in the middle-right pane
    if dry_run:
        tasks_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.2", "cctmux-tasks -g", "Enter"]
    else:
        tasks_cmd = ["tmux", "send-keys", "-t", middle_pane_id, "cctmux-tasks -g", "Enter"]
    commands.append(" ".join(tasks_cmd))
    if not dry_run:
        _run_tmux(tasks_cmd)

    # Split the middle pane vertically (50/50 for tasks/activity)
    # Use -d to keep focus on main pane
    if dry_run:
        split_v2_cmd = [
            "tmux",
            "split-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:0.2",
            "-v",
            "-p",
            "50",
        ]
    else:
        split_v2_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", middle_pane_id, "-v", "-p", "50"]
    commands.append(" ".join(split_v2_cmd))

    bottom_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_v2_cmd, capture_output=True, text=True)
        bottom_pane_id = result.stdout.strip()
        _validate_pane_id(bottom_pane_id, "bottom pane")

    # Launch cctmux-activity in the bottom-right pane
    if dry_run:
        activity_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.3", "cctmux-activity", "Enter"]
    else:
        activity_cmd = ["tmux", "send-keys", "-t", bottom_pane_id, "cctmux-activity", "Enter"]
    commands.append(" ".join(activity_cmd))
    if not dry_run:
        _run_tmux(activity_cmd)

    # Focus the left (main) pane where Claude runs using captured pane ID
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        _run_tmux(focus_cmd)

    return commands


def apply_dashboard_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply dashboard layout (large activity dashboard with session stats sidebar).

    Layout:
    -----------------------------------------
    |                       | cctmux-session |
    | cctmux-activity       |      30%       |
    |     70%               |----------------|
    |                       | mini claude    |
    |                       |      30%       |
    -----------------------------------------

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits (this will become the activity pane)
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # First, move Claude to a side pane - split with 30% on right
    # Use -d to keep focus on original pane during split
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "30"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Launch cctmux-session in the top-right pane
    if dry_run:
        session_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-session", "Enter"]
    else:
        session_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-session", "Enter"]
    commands.append(" ".join(session_cmd))
    if not dry_run:
        _run_tmux(session_cmd)

    # Split the right pane vertically (50/50 for session/mini-claude)
    # Use -d to keep focus on main pane during split
    if dry_run:
        split_v_cmd = [
            "tmux",
            "split-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:0.1",
            "-v",
            "-p",
            "50",
        ]
    else:
        split_v_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", right_pane_id, "-v", "-p", "50"]
    commands.append(" ".join(split_v_cmd))

    bottom_right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_v_cmd, capture_output=True, text=True)
        bottom_right_pane_id = result.stdout.strip()
        _validate_pane_id(bottom_right_pane_id, "bottom-right pane")

    # Launch cctmux-activity in the main (left) pane using captured pane ID
    if dry_run:
        activity_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.0", "cctmux-activity --show-hourly", "Enter"]
    else:
        activity_cmd = ["tmux", "send-keys", "-t", main_pane_id, "cctmux-activity --show-hourly", "Enter"]
    commands.append(" ".join(activity_cmd))
    if not dry_run:
        _run_tmux(activity_cmd)

    # Focus the bottom-right pane (mini claude area) using captured pane ID
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.2"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", bottom_right_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        _run_tmux(focus_cmd)

    return commands


def apply_ralph_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply ralph layout (shell + ralph monitor side-by-side).

    Layout:
    ┌──────────┬──────────┐
    │          │ cctmux-  │
    │  shell   │ ralph    │
    │  60%     │   40%    │
    │          │          │
    └──────────┴──────────┘

    Main pane: shell where user runs cctmux-ralph start.
    Right pane: ralph monitor dashboard.

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # Split horizontally with 40% on the right
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Launch cctmux-ralph (monitor) in the right pane
    if dry_run:
        ralph_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-ralph", "Enter"]
    else:
        ralph_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-ralph", "Enter"]
    commands.append(" ".join(ralph_cmd))
    if not dry_run:
        _run_tmux(ralph_cmd)

    # Focus the left (main) pane
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        _run_tmux(focus_cmd)

    return commands


def apply_ralph_full_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply ralph-full layout (shell + ralph monitor + task monitor).

    Layout:
    ┌──────────┬──────────┐
    │          │ cctmux-  │
    │  shell   │ ralph    │
    │  60%     ├──────────┤
    │          │ cctmux-  │
    │          │ tasks    │
    └──────────┴──────────┘

    Main pane: shell where user runs cctmux-ralph start.
    Top-right: ralph monitor dashboard.
    Bottom-right: task monitor.

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # Split horizontally with 40% on the right
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Launch cctmux-ralph (monitor) in the right pane
    if dry_run:
        ralph_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-ralph", "Enter"]
    else:
        ralph_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-ralph", "Enter"]
    commands.append(" ".join(ralph_cmd))
    if not dry_run:
        _run_tmux(ralph_cmd)

    # Split the right pane vertically (50/50)
    if dry_run:
        split_v_cmd = [
            "tmux",
            "split-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:0.1",
            "-v",
            "-p",
            "50",
        ]
    else:
        split_v_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", right_pane_id, "-v", "-p", "50"]
    commands.append(" ".join(split_v_cmd))

    bottom_right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_v_cmd, capture_output=True, text=True)
        bottom_right_pane_id = result.stdout.strip()
        _validate_pane_id(bottom_right_pane_id, "bottom-right pane")

    # Launch cctmux-tasks in the bottom-right pane
    if dry_run:
        tasks_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.2", "cctmux-tasks -g", "Enter"]
    else:
        tasks_cmd = ["tmux", "send-keys", "-t", bottom_right_pane_id, "cctmux-tasks -g", "Enter"]
    commands.append(" ".join(tasks_cmd))
    if not dry_run:
        _run_tmux(tasks_cmd)

    # Focus the left (main) pane
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        _run_tmux(focus_cmd)

    return commands


def apply_git_mon_layout(session_name: str, dry_run: bool = False) -> list[str]:
    """Apply git-mon layout (Claude + git monitor).

    Layout:
    +-----------+----------+
    |           | cctmux-  |
    |  CLAUDE   | git      |
    |  60%      |   40%    |
    |           |          |
    +-----------+----------+

    Args:
        session_name: The session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # Split horizontally with 40% on the right
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = _run_tmux(split_h_cmd, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()
        _validate_pane_id(right_pane_id, "right pane")

    # Launch cctmux-git in the right pane
    if dry_run:
        git_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-git", "Enter"]
    else:
        git_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-git", "Enter"]
    commands.append(" ".join(git_cmd))
    if not dry_run:
        _run_tmux(git_cmd)

    # Focus the left (main) pane
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        _run_tmux(focus_cmd)

    return commands


def apply_custom_layout(session_name: str, layout: CustomLayout, dry_run: bool = False) -> list[str]:
    """Apply a custom layout to a tmux session.

    Args:
        session_name: The session name.
        layout: The custom layout definition.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Capture the main pane ID before any splits
    main_pane_id = ""
    if not dry_run:
        get_pane_cmd = ["tmux", "display-message", "-p", "-t", session_name, "#{pane_id}"]
        result = _run_tmux(get_pane_cmd, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()
        _validate_pane_id(main_pane_id, "main pane")

    # Track pane IDs by name
    pane_registry: dict[str, str] = {
        "main": main_pane_id,
    }
    last_pane_id = main_pane_id
    focus_pane_id = ""

    for split_idx, split in enumerate(layout.splits):
        # dry_run_index is 1-based (pane 0 is main, splits start at 1)
        dry_run_index = split_idx + 1
        # Resolve target pane ID
        target_name = split.target
        if dry_run:
            if target_name == "main":
                target_ref = f"{session_name}:0.0"
            elif target_name == "last":
                target_ref = f"{session_name}:0.{split_idx}" if split_idx > 0 else f"{session_name}:0.0"
            else:
                # Named pane — use positional index in dry-run
                target_ref = f"{session_name}:0.0"
        else:
            if target_name in pane_registry:
                target_ref = pane_registry[target_name]
            elif target_name == "last":
                target_ref = last_pane_id
            else:
                # Unknown target, fall back to main
                target_ref = pane_registry.get("main", main_pane_id)

        direction_flag = f"-{split.direction.value}"

        # Build split command
        split_cmd = [
            "tmux",
            "split-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            target_ref,
            direction_flag,
            "-p",
            str(split.size),
        ]
        commands.append(" ".join(split_cmd))

        new_pane_id = ""
        if not dry_run:
            result = _run_tmux(split_cmd, capture_output=True, text=True)
            new_pane_id = result.stdout.strip()
            _validate_pane_id(new_pane_id, split.name or "split pane")

        # Register the new pane
        last_pane_id = new_pane_id
        pane_registry["last"] = new_pane_id
        if split.name:
            pane_registry[split.name] = new_pane_id

        # Send command if specified
        if split.command:
            if dry_run:
                send_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.{dry_run_index}", split.command, "Enter"]
            else:
                send_cmd = ["tmux", "send-keys", "-t", new_pane_id, split.command, "Enter"]
            commands.append(" ".join(send_cmd))
            if not dry_run:
                _run_tmux(send_cmd)

        # Track which pane to focus
        if split.focus:
            focus_pane_id = f"{session_name}:0.{dry_run_index}" if dry_run else new_pane_id

    # Focus the appropriate pane
    if focus_pane_id:
        target = focus_pane_id
    elif layout.focus_main:
        target = f"{session_name}:0.0" if dry_run else main_pane_id
    else:
        target = ""

    if target:
        focus_cmd = ["tmux", "select-pane", "-t", target]
        commands.append(" ".join(focus_cmd))
        if not dry_run:
            _run_tmux(focus_cmd)

    return commands


# Built-in layout templates for --from support in layout add
BUILTIN_TEMPLATES: dict[LayoutType, list[PaneSplit]] = {
    LayoutType.EDITOR: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=30),
    ],
    LayoutType.MONITOR: [
        PaneSplit(direction=SplitDirection.VERTICAL, size=20),
    ],
    LayoutType.TRIPLE: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=50, name="right"),
        PaneSplit(direction=SplitDirection.VERTICAL, size=50, target="right"),
    ],
    LayoutType.CC_MON: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=50, command="cctmux-session", name="session"),
        PaneSplit(
            direction=SplitDirection.VERTICAL, size=50, command="cctmux-tasks -g", target="session", name="tasks"
        ),
    ],
    LayoutType.FULL_MONITOR: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=40, command="cctmux-session", name="session"),
        PaneSplit(
            direction=SplitDirection.VERTICAL, size=70, command="cctmux-tasks -g", target="session", name="tasks"
        ),
        PaneSplit(
            direction=SplitDirection.VERTICAL, size=50, command="cctmux-activity", target="tasks", name="activity"
        ),
    ],
    LayoutType.DASHBOARD: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=30, command="cctmux-session", name="session"),
        PaneSplit(direction=SplitDirection.VERTICAL, size=50, target="session"),
        PaneSplit(
            direction=SplitDirection.HORIZONTAL,
            size=0,
            command="cctmux-activity --show-hourly",
            target="main",
            name="activity",
        ),
    ],
    LayoutType.RALPH: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=40, command="cctmux-ralph", name="ralph"),
    ],
    LayoutType.RALPH_FULL: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=40, command="cctmux-ralph", name="ralph"),
        PaneSplit(direction=SplitDirection.VERTICAL, size=50, command="cctmux-tasks -g", target="ralph", name="tasks"),
    ],
    LayoutType.GIT_MON: [
        PaneSplit(direction=SplitDirection.HORIZONTAL, size=40, command="cctmux-git", name="git"),
    ],
}

# Layout descriptions for list command
LAYOUT_DESCRIPTIONS: dict[LayoutType, str] = {
    LayoutType.DEFAULT: "No initial split, panes created on demand",
    LayoutType.EDITOR: "70/30 horizontal split",
    LayoutType.MONITOR: "Main + bottom bar (80/20)",
    LayoutType.TRIPLE: "Main + 2 side panes (50/50)",
    LayoutType.CC_MON: "Claude + session monitor + task monitor",
    LayoutType.FULL_MONITOR: "Main + session + task + activity monitors",
    LayoutType.DASHBOARD: "Large activity dashboard with session stats",
    LayoutType.RALPH: "Shell + ralph monitor side-by-side",
    LayoutType.RALPH_FULL: "Shell + ralph monitor + task monitor",
    LayoutType.GIT_MON: "Claude + git monitor",
}


# Dictionary dispatch for layout handlers
_LAYOUT_HANDLERS: dict[LayoutType, LayoutHandler] = {
    LayoutType.DEFAULT: apply_default_layout,
    LayoutType.EDITOR: apply_editor_layout,
    LayoutType.MONITOR: apply_monitor_layout,
    LayoutType.TRIPLE: apply_triple_layout,
    LayoutType.CC_MON: apply_cc_mon_layout,
    LayoutType.FULL_MONITOR: apply_full_monitor_layout,
    LayoutType.DASHBOARD: apply_dashboard_layout,
    LayoutType.RALPH: apply_ralph_layout,
    LayoutType.RALPH_FULL: apply_ralph_full_layout,
    LayoutType.GIT_MON: apply_git_mon_layout,
}


def apply_layout(
    session_name: str,
    layout: LayoutType | str,
    dry_run: bool = False,
    custom_layouts: list[CustomLayout] | None = None,
) -> list[str]:
    """Apply a layout to a tmux session.

    Args:
        session_name: The session name.
        layout: The layout type (built-in) or custom layout name (string).
        dry_run: If True, return commands without executing.
        custom_layouts: Optional list of custom layouts to search.

    Returns:
        List of commands that were (or would be) executed.
    """
    # Try as built-in layout
    if isinstance(layout, LayoutType):
        handler = _LAYOUT_HANDLERS.get(layout)
        if handler is None:
            return []
        return handler(session_name, dry_run)

    # Try built-in by string value
    try:
        builtin = LayoutType(layout)
        handler = _LAYOUT_HANDLERS.get(builtin)
        if handler is None:
            return []
        return handler(session_name, dry_run)
    except ValueError:
        pass

    # Look up custom layout by name
    if custom_layouts:
        for custom in custom_layouts:
            if custom.name == layout:
                return apply_custom_layout(session_name, custom, dry_run)

    return []
