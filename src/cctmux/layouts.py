"""Predefined tmux layouts for cctmux."""

import subprocess

from cctmux.config import LayoutType


def apply_layout(session_name: str, layout: LayoutType, dry_run: bool = False) -> list[str]:
    """Apply a layout to a tmux session.

    Args:
        session_name: The session name.
        layout: The layout type to apply.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    if layout == LayoutType.DEFAULT:
        return apply_default_layout(session_name, dry_run)
    elif layout == LayoutType.EDITOR:
        return apply_editor_layout(session_name, dry_run)
    elif layout == LayoutType.MONITOR:
        return apply_monitor_layout(session_name, dry_run)
    elif layout == LayoutType.TRIPLE:
        return apply_triple_layout(session_name, dry_run)
    elif layout == LayoutType.CC_MON:
        return apply_cc_mon_layout(session_name, dry_run)
    elif layout == LayoutType.FULL_MONITOR:
        return apply_full_monitor_layout(session_name, dry_run)
    elif layout == LayoutType.DASHBOARD:
        return apply_dashboard_layout(session_name, dry_run)
    elif layout == LayoutType.RALPH:
        return apply_ralph_layout(session_name, dry_run)
    elif layout == LayoutType.RALPH_FULL:
        return apply_ralph_full_layout(session_name, dry_run)
    return []


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
        subprocess.run(split_cmd, check=True)

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
        subprocess.run(split_cmd, check=True)

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
        result = subprocess.run(split_h_cmd, check=True, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()

    # Split the right pane vertically (50/50) using the captured pane ID
    # Use -d to keep focus on main pane
    if dry_run:
        split_v_cmd = ["tmux", "split-window", "-d", "-t", f"{session_name}:0.1", "-v", "-p", "50"]
    else:
        split_v_cmd = ["tmux", "split-window", "-d", "-t", right_pane_id, "-v", "-p", "50"]
    commands.append(" ".join(split_v_cmd))
    if not dry_run:
        subprocess.run(split_v_cmd, check=True)

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
        result = subprocess.run(get_pane_cmd, check=True, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()

    # Split horizontally with 50% on the right, using -P to get the new pane ID
    # Use -d to keep focus on original pane during split
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "50"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = subprocess.run(split_h_cmd, check=True, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()

    # Launch cctmux-session in the right pane
    if dry_run:
        session_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-session", "Enter"]
    else:
        session_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-session", "Enter"]
    commands.append(" ".join(session_cmd))
    if not dry_run:
        subprocess.run(session_cmd, check=True)

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
        result = subprocess.run(split_v_cmd, check=True, capture_output=True, text=True)
        bottom_right_pane_id = result.stdout.strip()

    # Launch cctmux-tasks -g in the bottom-right pane
    if dry_run:
        tasks_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.2", "cctmux-tasks -g", "Enter"]
    else:
        tasks_cmd = ["tmux", "send-keys", "-t", bottom_right_pane_id, "cctmux-tasks -g", "Enter"]
    commands.append(" ".join(tasks_cmd))
    if not dry_run:
        subprocess.run(tasks_cmd, check=True)

    # Focus the left (main) pane where Claude runs using captured pane ID
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        subprocess.run(focus_cmd, check=True)

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
        result = subprocess.run(get_pane_cmd, check=True, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()

    # Split horizontally with 40% on the right, using -P to get the new pane ID
    # Use -d to keep focus on original pane during split
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = subprocess.run(split_h_cmd, check=True, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()

    # Launch cctmux-session in the top-right pane
    if dry_run:
        session_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-session", "Enter"]
    else:
        session_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-session", "Enter"]
    commands.append(" ".join(session_cmd))
    if not dry_run:
        subprocess.run(session_cmd, check=True)

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
        result = subprocess.run(split_v_cmd, check=True, capture_output=True, text=True)
        middle_pane_id = result.stdout.strip()

    # Launch cctmux-tasks -g in the middle-right pane
    if dry_run:
        tasks_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.2", "cctmux-tasks -g", "Enter"]
    else:
        tasks_cmd = ["tmux", "send-keys", "-t", middle_pane_id, "cctmux-tasks -g", "Enter"]
    commands.append(" ".join(tasks_cmd))
    if not dry_run:
        subprocess.run(tasks_cmd, check=True)

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
        result = subprocess.run(split_v2_cmd, check=True, capture_output=True, text=True)
        bottom_pane_id = result.stdout.strip()

    # Launch cctmux-activity in the bottom-right pane
    if dry_run:
        activity_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.3", "cctmux-activity", "Enter"]
    else:
        activity_cmd = ["tmux", "send-keys", "-t", bottom_pane_id, "cctmux-activity", "Enter"]
    commands.append(" ".join(activity_cmd))
    if not dry_run:
        subprocess.run(activity_cmd, check=True)

    # Focus the left (main) pane where Claude runs using captured pane ID
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        subprocess.run(focus_cmd, check=True)

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
        result = subprocess.run(get_pane_cmd, check=True, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()

    # First, move Claude to a side pane - split with 30% on right
    # Use -d to keep focus on original pane during split
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "30"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = subprocess.run(split_h_cmd, check=True, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()

    # Launch cctmux-session in the top-right pane
    if dry_run:
        session_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-session", "Enter"]
    else:
        session_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-session", "Enter"]
    commands.append(" ".join(session_cmd))
    if not dry_run:
        subprocess.run(session_cmd, check=True)

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
        result = subprocess.run(split_v_cmd, check=True, capture_output=True, text=True)
        bottom_right_pane_id = result.stdout.strip()

    # Launch cctmux-activity in the main (left) pane using captured pane ID
    if dry_run:
        activity_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.0", "cctmux-activity --show-hourly", "Enter"]
    else:
        activity_cmd = ["tmux", "send-keys", "-t", main_pane_id, "cctmux-activity --show-hourly", "Enter"]
    commands.append(" ".join(activity_cmd))
    if not dry_run:
        subprocess.run(activity_cmd, check=True)

    # Focus the bottom-right pane (mini claude area) using captured pane ID
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.2"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", bottom_right_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        subprocess.run(focus_cmd, check=True)

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
        result = subprocess.run(get_pane_cmd, check=True, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()

    # Split horizontally with 40% on the right
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = subprocess.run(split_h_cmd, check=True, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()

    # Launch cctmux-ralph (monitor) in the right pane
    if dry_run:
        ralph_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-ralph", "Enter"]
    else:
        ralph_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-ralph", "Enter"]
    commands.append(" ".join(ralph_cmd))
    if not dry_run:
        subprocess.run(ralph_cmd, check=True)

    # Focus the left (main) pane
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        subprocess.run(focus_cmd, check=True)

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
        result = subprocess.run(get_pane_cmd, check=True, capture_output=True, text=True)
        main_pane_id = result.stdout.strip()

    # Split horizontally with 40% on the right
    split_h_cmd = ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", session_name, "-h", "-p", "40"]
    commands.append(" ".join(split_h_cmd))

    right_pane_id = ""
    if not dry_run:
        result = subprocess.run(split_h_cmd, check=True, capture_output=True, text=True)
        right_pane_id = result.stdout.strip()

    # Launch cctmux-ralph (monitor) in the right pane
    if dry_run:
        ralph_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.1", "cctmux-ralph", "Enter"]
    else:
        ralph_cmd = ["tmux", "send-keys", "-t", right_pane_id, "cctmux-ralph", "Enter"]
    commands.append(" ".join(ralph_cmd))
    if not dry_run:
        subprocess.run(ralph_cmd, check=True)

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
        result = subprocess.run(split_v_cmd, check=True, capture_output=True, text=True)
        bottom_right_pane_id = result.stdout.strip()

    # Launch cctmux-tasks in the bottom-right pane
    if dry_run:
        tasks_cmd = ["tmux", "send-keys", "-t", f"{session_name}:0.2", "cctmux-tasks -g", "Enter"]
    else:
        tasks_cmd = ["tmux", "send-keys", "-t", bottom_right_pane_id, "cctmux-tasks -g", "Enter"]
    commands.append(" ".join(tasks_cmd))
    if not dry_run:
        subprocess.run(tasks_cmd, check=True)

    # Focus the left (main) pane
    if dry_run:
        focus_cmd = ["tmux", "select-pane", "-t", f"{session_name}:0.0"]
    else:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane_id]
    commands.append(" ".join(focus_cmd))
    if not dry_run:
        subprocess.run(focus_cmd, check=True)

    return commands
