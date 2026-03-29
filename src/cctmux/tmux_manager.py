"""Tmux session management for cctmux."""

import os
import subprocess
import uuid
from pathlib import Path

from cctmux.config import CustomLayout, LayoutType, TeamAgent, TeamConfig
from cctmux.layouts import apply_custom_layout, apply_layout, compute_team_layout


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
    layout: LayoutType | str = LayoutType.DEFAULT,
    status_bar: bool = False,
    claude_args: str | None = None,
    task_list_id: bool = False,
    agent_teams: bool = False,
    custom_layouts: list[CustomLayout] | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Create a new tmux session and attach to it.

    Args:
        session_name: The session name.
        project_dir: The project directory.
        layout: The layout to apply (built-in or custom name).
        status_bar: Whether to enable status bar.
        claude_args: Additional arguments to pass to claude command.
        task_list_id: Whether to set CLAUDE_CODE_TASK_LIST_ID to session name.
        agent_teams: Whether to enable experimental agent teams.
        custom_layouts: Optional list of custom layouts for name resolution.
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

    # Set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS if requested
    if agent_teams:
        env_cmd4 = ["tmux", "set-environment", "-t", session_name, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1"]
        commands.append(" ".join(env_cmd4))
        if not dry_run:
            subprocess.run(env_cmd4, check=True)

    # Export environment variables to the current shell
    export_vars = f"CCTMUX_SESSION={session_name} CCTMUX_PROJECT_DIR={dir_str}"
    if task_list_id:
        export_vars += f" CLAUDE_CODE_TASK_LIST_ID={session_name}"
    if agent_teams:
        export_vars += " CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
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
    layout_commands = apply_layout(session_name, layout, dry_run, custom_layouts=custom_layouts)
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


def _build_claude_cmd(
    agent: TeamAgent,
    n_agents: int,
    project: str,
    default_args: str | None,
    prompt_dir: Path,
) -> str:
    """Build the claude CLI command for a team agent.

    Args:
        agent: The team agent configuration.
        n_agents: Total number of agents in the team.
        project: The project name for the cc2cc topic.
        default_args: Default claude CLI arguments (used if agent has none).
        prompt_dir: Directory where prompt files are written (must exist).

    Returns:
        The fully-formed claude command string.
    """
    parts = ["claude"]

    # Role-specific system prompt
    skills_to_load = "/cc2cc"
    if "lead" in agent.role.lower():
        skills_to_load = "/cc-team-lead, /cc-tmux, and /cc2cc"
    team_prompt = (
        f"You are the {agent.role} on a team of {n_agents} Claude Code instances "
        f"collaborating via cc2cc on the '{project}' topic.\n\n"
        f"{agent.prompt.strip()}\n\n"
        f"Load the {skills_to_load} skill(s) immediately when your session starts, "
        f"then call set_role('{agent.role}')."
    )
    # Write prompt to a file to avoid shell quoting issues with tmux send-keys
    prompt_file = prompt_dir / f"{agent.role}.md"
    prompt_file.write_text(team_prompt, encoding="utf-8")
    parts.append(f"--append-system-prompt-file '{prompt_file}'")

    parts.append(f"--name '{agent.role}'")

    # Team agents run autonomously — skip all permission prompts
    parts.append("--dangerously-skip-permissions")

    # Load cc2cc development channel for team communication
    parts.append("--dangerously-load-development-channels plugin:cc2cc@probello-local")

    # Per-agent model flag
    if agent.model:
        parts.append(f"--model {agent.model}")

    # Per-agent args override default
    extra_args = agent.claude_args or default_args
    if extra_args:
        parts.append(extra_args)

    return " ".join(parts)


def _build_export_cmd(
    session_name: str,
    dir_str: str,
    shared_task_list: bool,
    agent_teams: bool,
) -> str:
    """Build the export command for environment variables in a team pane.

    Args:
        session_name: The session name.
        dir_str: The resolved project directory path.
        shared_task_list: Whether to set CLAUDE_CODE_TASK_LIST_ID.
        agent_teams: Whether to enable experimental agent teams.

    Returns:
        The export command string.
    """
    export_vars = f"CCTMUX_SESSION={session_name} CCTMUX_PROJECT_DIR={dir_str}"
    export_vars += f" CC2CC_SESSION_ID={uuid.uuid4()}"
    if shared_task_list:
        export_vars += f" CLAUDE_CODE_TASK_LIST_ID={session_name}"
    if agent_teams:
        export_vars += " CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
    return f"export {export_vars}"


def _ensure_gitignore_entry(project_dir: Path, entry: str) -> None:
    """Add *entry* to the project's .gitignore if it isn't already present.

    Creates the .gitignore file if it doesn't exist.

    Args:
        project_dir: Root of the project (where .gitignore lives).
        entry: The gitignore pattern to ensure (e.g. ".cctmux/").
    """
    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        # Check for the entry as a standalone line (ignoring trailing whitespace)
        for line in content.splitlines():
            if line.strip() == entry:
                return
        # Ensure we start on a new line
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{entry}\n"
        gitignore.write_text(content, encoding="utf-8")
    else:
        gitignore.write_text(f"{entry}\n", encoding="utf-8")


def create_team_session(
    session_name: str,
    project_dir: Path,
    team: TeamConfig,
    default_claude_args: str | None = None,
    status_bar: bool = False,
    agent_teams: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Create a tmux session with multiple Claude Code instances for team mode.

    Each agent gets its own pane running Claude Code with role-specific
    system prompts. All agents share the same project directory and
    optionally a task list.

    Args:
        session_name: The session name.
        project_dir: The project directory.
        team: Team configuration with agent definitions.
        default_claude_args: Default arguments for claude command.
        status_bar: Whether to enable status bar.
        agent_teams: Whether to enable experimental agent teams.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []
    dir_str = str(project_dir.resolve())
    project = project_dir.name

    # Create a directory for agent system prompt files to avoid shell quoting
    # issues when passing long prompts through tmux send-keys.
    prompt_dir = project_dir.resolve() / ".cctmux" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    # Ensure .cctmux is in .gitignore so prompt files aren't committed
    _ensure_gitignore_entry(project_dir.resolve(), ".cctmux/")

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
    if team.shared_task_list:
        env_cmd3 = ["tmux", "set-environment", "-t", session_name, "CLAUDE_CODE_TASK_LIST_ID", session_name]
        commands.append(" ".join(env_cmd3))
        if not dry_run:
            subprocess.run(env_cmd3, check=True)

    # Set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS if requested
    if agent_teams:
        env_cmd4 = ["tmux", "set-environment", "-t", session_name, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1"]
        commands.append(" ".join(env_cmd4))
        if not dry_run:
            subprocess.run(env_cmd4, check=True)

    # --- Agent 0: main pane (already exists from new-session) ---
    export_cmd = _build_export_cmd(session_name, dir_str, team.shared_task_list, agent_teams)
    export_keys = ["tmux", "send-keys", "-t", session_name, export_cmd, "Enter"]
    commands.append(" ".join(export_keys))
    if not dry_run:
        subprocess.run(export_keys, check=True)

    claude_cmd = _build_claude_cmd(team.agents[0], len(team.agents), project, default_claude_args, prompt_dir)
    send_cmd = ["tmux", "send-keys", "-t", session_name, claude_cmd, "Enter"]
    commands.append(" ".join(send_cmd))
    if not dry_run:
        subprocess.run(send_cmd, check=True)

    # --- Apply team layout to create split panes for agents 1..N-1 + optional monitor ---
    team_layout = compute_team_layout(len(team.agents), team.layout.value, team.monitor)
    layout_commands, pane_registry = apply_custom_layout(session_name, team_layout, dry_run)
    commands.extend(layout_commands)

    # --- Agents 1..N-1: export env and launch claude in each split pane ---
    # Use pane_registry from apply_custom_layout to target agent panes by name,
    # since tmux pane indices don't reliably match agent order when a monitor
    # pane is inserted (it splits from main, shifting positional indices).
    for i in range(1, len(team.agents)):
        agent = team.agents[i]
        agent_export = _build_export_cmd(session_name, dir_str, team.shared_task_list, agent_teams)
        agent_claude = _build_claude_cmd(agent, len(team.agents), project, default_claude_args, prompt_dir)

        pane_name = f"agent-{i}"
        if not dry_run and pane_name in pane_registry:
            pane_id = pane_registry[pane_name]

            export_keys_i = ["tmux", "send-keys", "-t", pane_id, agent_export, "Enter"]
            commands.append(" ".join(export_keys_i))
            subprocess.run(export_keys_i, check=True)

            send_cmd_i = ["tmux", "send-keys", "-t", pane_id, agent_claude, "Enter"]
            commands.append(" ".join(send_cmd_i))
            subprocess.run(send_cmd_i, check=True)
        else:
            # dry_run: record commands with placeholder pane target
            placeholder = f"{{pane-{i}}}"
            commands.append(f"tmux send-keys -t {placeholder} {agent_export} Enter")
            commands.append(f"tmux send-keys -t {placeholder} {agent_claude} Enter")

    # Configure status bar if enabled
    if status_bar:
        status_commands = configure_status_bar(session_name, project_dir, dry_run)
        commands.extend(status_commands)

    # Focus the first (agent-0) pane
    main_pane = pane_registry.get("main", "")
    if not dry_run and main_pane:
        focus_cmd = ["tmux", "select-pane", "-t", main_pane]
        commands.append(" ".join(focus_cmd))
        subprocess.run(focus_cmd, check=True)
    else:
        commands.append(f"tmux select-pane -t {session_name}:0.0")

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
