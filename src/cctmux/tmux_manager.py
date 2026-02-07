"""Tmux session management for cctmux."""

import os
import subprocess
from pathlib import Path

from cctmux.config import LayoutType
from cctmux.layouts import apply_layout


def is_inside_tmux() -> bool:
    """Check if we're running inside a tmux session."""
    return os.environ.get("TMUX") is not None


def session_exists(session_name: str) -> bool:
    """Check if a tmux session with the given name exists.

    Args:
        session_name: The session name to check.

    Returns:
        True if the session exists, False otherwise.
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def create_session(
    session_name: str,
    project_dir: Path,
    layout: LayoutType = LayoutType.DEFAULT,
    status_bar: bool = False,
    claude_args: str | None = None,
    task_list_id: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Create a new tmux session and attach to it.

    Args:
        session_name: The session name.
        project_dir: The project directory.
        layout: The layout to apply.
        status_bar: Whether to enable status bar.
        claude_args: Additional arguments to pass to claude command.
        task_list_id: Whether to set CLAUDE_CODE_TASK_LIST_ID to session name.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []
    dir_str = str(project_dir.resolve())

    # Create new session
    cmd = ["tmux", "new-session", "-d", "-s", session_name, "-c", dir_str]
    commands.append(" ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True)

    # Set environment variables at tmux session level (for new panes)
    env_cmd1 = ["tmux", "set-environment", "-t", session_name, "CCTMUX_SESSION", session_name]
    commands.append(" ".join(env_cmd1))
    if not dry_run:
        subprocess.run(env_cmd1, check=True)

    env_cmd2 = ["tmux", "set-environment", "-t", session_name, "CCTMUX_PROJECT_DIR", dir_str]
    commands.append(" ".join(env_cmd2))
    if not dry_run:
        subprocess.run(env_cmd2, check=True)

    # Set CLAUDE_CODE_TASK_LIST_ID if requested
    if task_list_id:
        env_cmd3 = ["tmux", "set-environment", "-t", session_name, "CLAUDE_CODE_TASK_LIST_ID", session_name]
        commands.append(" ".join(env_cmd3))
        if not dry_run:
            subprocess.run(env_cmd3, check=True)

    # Export environment variables to the current shell
    export_vars = f"CCTMUX_SESSION={session_name} CCTMUX_PROJECT_DIR={dir_str}"
    if task_list_id:
        export_vars += f" CLAUDE_CODE_TASK_LIST_ID={session_name}"
    export_cmd = f"export {export_vars}"
    export_keys = ["tmux", "send-keys", "-t", session_name, export_cmd, "Enter"]
    commands.append(" ".join(export_keys))
    if not dry_run:
        subprocess.run(export_keys, check=True)

    # Launch Claude in the main pane
    claude_cmd = "claude"
    if claude_args:
        claude_cmd = f"claude {claude_args}"
    send_cmd = ["tmux", "send-keys", "-t", session_name, claude_cmd, "Enter"]
    commands.append(" ".join(send_cmd))
    if not dry_run:
        subprocess.run(send_cmd, check=True)

    # Apply layout
    layout_commands = apply_layout(session_name, layout, dry_run)
    commands.extend(layout_commands)

    # Configure status bar if enabled
    if status_bar:
        status_commands = configure_status_bar(session_name, project_dir, dry_run)
        commands.extend(status_commands)

    # Attach to session
    attach_cmd = ["tmux", "attach-session", "-t", session_name]
    commands.append(" ".join(attach_cmd))
    if not dry_run:
        subprocess.run(attach_cmd, check=True)

    return commands


def attach_session(session_name: str, dry_run: bool = False) -> list[str]:
    """Attach to an existing tmux session.

    Args:
        session_name: The session name to attach to.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    cmd = ["tmux", "attach-session", "-t", session_name]
    if not dry_run:
        subprocess.run(cmd, check=True)
    return [" ".join(cmd)]


def configure_status_bar(session_name: str, project_dir: Path, dry_run: bool = False) -> list[str]:
    """Configure the tmux status bar with project info.

    Args:
        session_name: The session name.
        project_dir: The project directory.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []

    # Get git branch if in a git repo
    git_branch = ""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            git_branch = result.stdout.strip()
    except FileNotFoundError:
        pass

    # Set status bar style
    status_style_cmd = ["tmux", "set-option", "-t", session_name, "status-style", "bg=colour235,fg=colour136"]
    commands.append(" ".join(status_style_cmd))
    if not dry_run:
        subprocess.run(status_style_cmd, check=True)

    # Set left status (project name)
    left_status = f" {project_dir.name}"
    if git_branch:
        left_status += f" [{git_branch}]"
    left_cmd = ["tmux", "set-option", "-t", session_name, "status-left", left_status]
    commands.append(" ".join(left_cmd))
    if not dry_run:
        subprocess.run(left_cmd, check=True)

    # Set right status (pane info)
    right_cmd = ["tmux", "set-option", "-t", session_name, "status-right", " #P/#{window_panes} "]
    commands.append(" ".join(right_cmd))
    if not dry_run:
        subprocess.run(right_cmd, check=True)

    return commands


def list_panes(session_name: str) -> list[dict[str, str]]:
    """List all panes in a session.

    Args:
        session_name: The session name.

    Returns:
        List of pane info dictionaries.
    """
    result = subprocess.run(
        ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_id}:#{pane_index}:#{pane_width}x#{pane_height}"],
        capture_output=True,
        text=True,
        check=False,
    )

    panes: list[dict[str, str]] = []
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split(":")
                if len(parts) >= 3:
                    panes.append(
                        {
                            "id": parts[0],
                            "index": parts[1],
                            "size": parts[2],
                        }
                    )
    return panes
