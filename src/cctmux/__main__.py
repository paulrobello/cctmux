"""CLI entry point for cctmux."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from cctmux import __version__
from cctmux.config import (
    Config,
    ConfigPreset,
    CustomLayout,
    LayoutType,
    display_config_warnings,
    get_preset_config,
    load_config,
    save_config,
    validate_layout_name,
)
from cctmux.git_monitor import run_git_monitor
from cctmux.session_history import (
    add_or_update_entry,
    get_entry_by_name,
    get_recent_session_names,
    load_history,
    save_history,
)
from cctmux.session_monitor import (
    DisplayConfig,
    run_session_monitor,
)
from cctmux.session_monitor import (
    list_sessions as list_session_files,
)
from cctmux.subagent_monitor import (
    list_subagents,
    run_subagent_monitor,
)
from cctmux.task_monitor import list_sessions, run_monitor
from cctmux.tmux_manager import attach_session, create_session, is_inside_tmux, session_exists
from cctmux.utils import get_project_name, is_fzf_available, sanitize_session_name, select_with_fzf
from cctmux.xdg_paths import ensure_directories, get_config_file_path

app = typer.Typer(
    name="cctmux",
    help="Launch Claude Code inside tmux with session management.",
    no_args_is_help=False,
)

console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"cctmux {__version__}")
        raise typer.Exit()


def _sync_skill() -> None:
    """Auto-install the bundled cc-tmux skill if missing or outdated.

    Compares the content hash of each bundled file against the installed copy.
    Runs silently; prints a one-line notice only when an update is applied.
    Called automatically on every cctmux invocation so 'uv tool upgrade'
    keeps the skill in sync without requiring a manual 'cctmux install-skill'.
    """
    import hashlib
    import shutil

    skill_src = Path(__file__).parent / "skill" / "cc-tmux"
    skill_dest = Path.home() / ".claude" / "skills" / "cc-tmux"

    if not skill_src.exists():
        return

    def _md5(path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324

    needs_update = False
    for src_file in skill_src.iterdir():
        if not src_file.is_file():
            continue
        dest_file = skill_dest / src_file.name
        if not dest_file.exists() or _md5(src_file) != _md5(dest_file):
            needs_update = True
            break

    if needs_update:
        skill_dest.mkdir(parents=True, exist_ok=True)
        for src_file in skill_src.iterdir():
            if src_file.is_file():
                shutil.copy2(src_file, skill_dest / src_file.name)
        console.print(f"[dim]✓ cc-tmux skill updated ({skill_dest})[/]")


@app.command()
def install_skill() -> None:
    """Install the cc-tmux skill to ~/.claude/skills/."""
    import shutil

    skill_src = Path(__file__).parent / "skill" / "cc-tmux"
    skill_dest = Path.home() / ".claude" / "skills" / "cc-tmux"

    if not skill_src.exists():
        err_console.print("[red]Error:[/] Skill source not found.")
        raise typer.Exit(1)

    skill_dest.mkdir(parents=True, exist_ok=True)

    for item in skill_src.iterdir():
        if item.is_file():
            shutil.copy2(item, skill_dest / item.name)

    console.print(f"[green]✓[/] Skill installed to {skill_dest}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    layout: Annotated[
        str,
        typer.Option("--layout", "-l", help="Tmux layout to use (built-in or custom name)."),
    ] = "default",
    recent: Annotated[
        bool,
        typer.Option("--recent", "-R", help="Select from recent sessions using fzf."),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option("--resume", "-r", help="Append --resume to claude invocation to continue last conversation."),
    ] = False,
    status_bar: Annotated[
        bool,
        typer.Option("--status-bar", "-s", help="Enable status bar with git/project info."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", "-D", help="Enable debug output."),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity."),
    ] = 0,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview commands without executing."),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-C", help="Config file path."),
    ] = None,
    continue_session: Annotated[
        bool,
        typer.Option(
            "--continue", "-c", help="Append --continue to claude invocation to continue most recent conversation."
        ),
    ] = False,
    dump_config: Annotated[
        bool,
        typer.Option("--dump-config", help="Output current configuration."),
    ] = False,
    claude_args: Annotated[
        str | None,
        typer.Option("--claude-args", "-a", help="Arguments to pass to claude command (e.g., '--model sonnet')."),
    ] = None,
    yolo: Annotated[
        bool,
        typer.Option("--yolo", "-y", help="Append --dangerously-skip-permissions to claude invocation."),
    ] = False,
    task_list_id: Annotated[
        bool,
        typer.Option("--task-list-id", "-T", help="Set CLAUDE_CODE_TASK_LIST_ID to session name."),
    ] = False,
    agent_teams: Annotated[
        bool,
        typer.Option(
            "--agent-teams", "-A", help="Enable experimental agent teams (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1)."
        ),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with error on config validation warnings."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Launch Claude Code in a tmux session for the current directory."""
    # Auto-sync the bundled skill on every invocation (no-op if already current)
    _sync_skill()

    # If a subcommand was invoked, don't run main logic
    if ctx.invoked_subcommand is not None:
        return

    # Ensure directories exist
    ensure_directories()

    # Load configuration (use cwd for project-level config discovery)
    config, config_warnings = load_config(config_path, project_dir=Path.cwd(), strict=strict)

    # Handle config warnings
    if config_warnings:
        display_config_warnings(config_warnings, err_console)
        if strict:
            raise typer.Exit(1)

    # Handle dump-config
    if dump_config:
        import yaml

        data = config.model_dump()
        data["default_layout"] = config.default_layout.value
        console.print(yaml.dump(data, default_flow_style=False))
        raise typer.Exit()

    # Merge CLI args with config (CLI takes precedence)
    # layout is now a string; "default" is the CLI default meaning "use config"
    if layout != "default":
        effective_layout: LayoutType | str = layout
    else:
        effective_layout = config.default_layout
    effective_status_bar = status_bar or config.status_bar_enabled
    effective_claude_args = claude_args if claude_args else config.default_claude_args
    if yolo:
        skip_flag = "--dangerously-skip-permissions"
        if effective_claude_args:
            if skip_flag not in effective_claude_args:
                effective_claude_args = f"{effective_claude_args} {skip_flag}"
        else:
            effective_claude_args = skip_flag
    if resume:
        resume_flag = "--resume"
        if effective_claude_args:
            if resume_flag not in effective_claude_args:
                effective_claude_args = f"{effective_claude_args} {resume_flag}"
        else:
            effective_claude_args = resume_flag
    if continue_session:
        continue_flag = "--continue"
        if effective_claude_args:
            if continue_flag not in effective_claude_args:
                effective_claude_args = f"{effective_claude_args} {continue_flag}"
        else:
            effective_claude_args = continue_flag
    effective_task_list_id = task_list_id or config.task_list_id
    effective_agent_teams = agent_teams or config.agent_teams

    if debug or verbose > 1:
        console.print(f"[dim]Config file: {get_config_file_path()}[/]")
        layout_display = effective_layout.value if isinstance(effective_layout, LayoutType) else effective_layout
        console.print(f"[dim]Layout: {layout_display}[/]")
        console.print(f"[dim]Status bar: {effective_status_bar}[/]")
        if effective_claude_args:
            console.print(f"[dim]Claude args: {effective_claude_args}[/]")

    # Check if running inside tmux
    if is_inside_tmux():
        err_console.print("[red]Error:[/] Already inside a tmux session.")
        err_console.print("[dim]Use standard tmux commands to manage panes.[/]")
        raise typer.Exit(1)

    # Load history
    history = load_history()

    # Determine session
    session_name: str
    project_dir: Path

    if recent:
        # Use fzf to select from recent sessions
        if not is_fzf_available():
            err_console.print("[red]Error:[/] fzf is required for --recent but not installed.")
            raise typer.Exit(1)

        recent_names = get_recent_session_names(history)
        if not recent_names:
            err_console.print("[yellow]No recent sessions found.[/]")
            raise typer.Exit(1)

        selected = select_with_fzf(recent_names, prompt="Session: ")
        if not selected:
            raise typer.Exit(0)

        session_name = selected
        entry = get_entry_by_name(history, session_name)
        if entry:
            project_dir = Path(entry.project_dir)
            if not project_dir.exists():
                err_console.print(f"[yellow]Warning:[/] Project directory no longer exists: {entry.project_dir}")
                err_console.print("[dim]Falling back to current directory.[/]")
                project_dir = Path.cwd()
        else:
            project_dir = Path.cwd()
    else:
        # Use current directory
        project_dir = Path.cwd()
        session_name = sanitize_session_name(get_project_name(project_dir))

    if debug or verbose > 0:
        console.print(f"[dim]Session: {session_name}[/]")
        console.print(f"[dim]Project: {project_dir}[/]")

    # Create or attach to session
    if session_exists(session_name):
        if verbose > 0 or dry_run:
            console.print(f"[blue]Attaching to existing session:[/] {session_name}")

        commands = attach_session(session_name, dry_run=dry_run)

        if dry_run:
            console.print("[yellow]Commands that would be executed:[/]")
            for cmd in commands:
                console.print(f"  {cmd}")
    else:
        if verbose > 0 or dry_run:
            console.print(f"[green]Creating new session:[/] {session_name}")

        # Validate layout name against built-in and custom layouts
        try:
            LayoutType(effective_layout)
        except ValueError:
            # Not a built-in layout — check custom layouts
            custom_match = [cl for cl in config.custom_layouts if cl.name == effective_layout]
            if not custom_match:
                err_console.print(f"[red]Error:[/] Unknown layout: {effective_layout}")
                err_console.print("[dim]Use 'cctmux layout list' to see available layouts.[/]")
                raise typer.Exit(1) from None

        commands = create_session(
            session_name=session_name,
            project_dir=project_dir,
            layout=effective_layout,
            status_bar=effective_status_bar,
            claude_args=effective_claude_args,
            task_list_id=effective_task_list_id,
            agent_teams=effective_agent_teams,
            custom_layouts=config.custom_layouts,
            dry_run=dry_run,
        )

        if dry_run:
            console.print("[yellow]Commands that would be executed:[/]")
            for cmd in commands:
                console.print(f"  {cmd}")
            console.print("[dim]Note: Actual execution uses pane IDs (%%N) for reliable targeting.[/]")

    # Update history (unless dry run)
    if not dry_run:
        history = add_or_update_entry(
            history,
            session_name=session_name,
            project_dir=str(project_dir.resolve()),
            max_entries=config.max_history_entries,
        )
        save_history(history)


@app.command()
def init_config() -> None:
    """Create default configuration file."""
    ensure_directories()
    config_file = get_config_file_path()

    if config_file.exists():
        err_console.print(f"[yellow]Config file already exists:[/] {config_file}")
        raise typer.Exit(1)

    config = Config()
    save_config(config)
    console.print(f"[green]✓[/] Created config file: {config_file}")


tasks_app = typer.Typer(
    name="cctmux-tasks",
    help="Monitor Claude Code tasks in real-time.",
    no_args_is_help=False,
)


@tasks_app.callback(invoke_without_command=True)
def tasks_main(
    ctx: typer.Context,
    session_or_path: Annotated[
        str | None,
        typer.Argument(help="Session ID, partial ID, or path to task folder."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project directory to find sessions for."),
    ] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds."),
    ] = 1.0,
    max_tasks: Annotated[
        int | None,
        typer.Option("--max-tasks", "-m", help="Maximum tasks to display (auto-detect if not set)."),
    ] = None,
    no_table: Annotated[
        bool,
        typer.Option("--no-table", "-g", help="Show only dependency graph, no table."),
    ] = False,
    table_only: Annotated[
        bool,
        typer.Option("--table-only", "-t", help="Show only table, no dependency graph."),
    ] = False,
    no_owner: Annotated[
        bool,
        typer.Option("--no-owner", help="Hide task owner column."),
    ] = False,
    show_metadata: Annotated[
        bool,
        typer.Option("--show-metadata", help="Show custom task metadata."),
    ] = False,
    no_description: Annotated[
        bool,
        typer.Option("--no-description", help="Hide task descriptions."),
    ] = False,
    show_acceptance: Annotated[
        bool,
        typer.Option("--show-acceptance", help="Show acceptance criteria from metadata."),
    ] = False,
    show_work_log: Annotated[
        bool,
        typer.Option("--show-work-log", help="Show work log from metadata."),
    ] = False,
    stats_only: Annotated[
        bool,
        typer.Option("--stats-only", "-s", help="Show only the stats panel (session, counts, progress)."),
    ] = False,
    preset: Annotated[
        ConfigPreset | None,
        typer.Option("--preset", help="Use preset configuration (minimal, verbose, debug)."),
    ] = None,
    do_list_sessions: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available sessions and exit."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Monitor Claude Code tasks with live ASCII dependency visualization.

    When run in a Claude Code project directory, automatically finds the most recent
    session with tasks for that project. Long task lists are windowed to fit the
    terminal, keeping the active task visible near the top.

    Examples:
        cctmux-tasks                    # Auto-detect from current project
        cctmux-tasks abc123             # Monitor session starting with abc123
        cctmux-tasks /path/to/tasks     # Monitor specific task folder
        cctmux-tasks -p /path/to/project  # Find sessions for specific project
        cctmux-tasks --list             # List all available sessions
        cctmux-tasks -m 20              # Show max 20 tasks
        cctmux-tasks --show-metadata    # Show custom metadata
        cctmux-tasks --stats-only       # Show only the stats panel
        cctmux-tasks --preset verbose   # Use verbose preset
    """
    if ctx.invoked_subcommand is not None:
        return

    if do_list_sessions:
        list_sessions(project_path=project)
        raise typer.Exit(0)

    # Load preset configuration if specified
    if preset:
        preset_config = get_preset_config(preset)
        task_config = preset_config.task_monitor
        effective_show_owner = task_config.show_owner
        effective_show_metadata = task_config.show_metadata
        effective_show_description = task_config.show_description
        effective_show_graph = task_config.show_graph
        effective_show_table = task_config.show_table
        effective_show_acceptance = task_config.show_acceptance
        effective_show_work_log = task_config.show_work_log
        effective_max_tasks = task_config.max_tasks
    else:
        effective_show_owner = not no_owner
        effective_show_metadata = show_metadata
        effective_show_description = not no_description
        effective_show_graph = not table_only
        effective_show_table = not no_table
        effective_show_acceptance = show_acceptance
        effective_show_work_log = show_work_log
        effective_max_tasks = max_tasks

    # stats_only overrides graph and table
    if stats_only:
        effective_show_graph = False
        effective_show_table = False

    # CLI overrides preset
    if max_tasks is not None:
        effective_max_tasks = max_tasks

    run_monitor(
        session_or_path=session_or_path,
        project_path=project,
        poll_interval=interval,
        show_table=effective_show_table,
        show_graph=effective_show_graph,
        show_owner=effective_show_owner,
        show_metadata=effective_show_metadata,
        show_description=effective_show_description,
        show_acceptance=effective_show_acceptance,
        show_work_log=effective_show_work_log,
        max_visible=effective_max_tasks,
    )


session_app = typer.Typer(
    name="cctmux-session",
    help="Monitor Claude Code session stream in real-time.",
    no_args_is_help=False,
)


@session_app.callback(invoke_without_command=True)
def session_main(
    ctx: typer.Context,
    session_or_path: Annotated[
        str | None,
        typer.Argument(help="Session ID, partial ID, or path to JSONL file."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project directory to find sessions for."),
    ] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds."),
    ] = 0.5,
    max_events: Annotated[
        int | None,
        typer.Option("--max-events", "-m", help="Maximum events to display (auto-detect if not set)."),
    ] = None,
    no_thinking: Annotated[
        bool,
        typer.Option("--no-thinking", help="Hide thinking blocks."),
    ] = False,
    no_results: Annotated[
        bool,
        typer.Option("--no-results", help="Hide tool results."),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Hide progress/hook events."),
    ] = False,
    show_system: Annotated[
        bool,
        typer.Option("--show-system", help="Show system messages."),
    ] = False,
    show_snapshots: Annotated[
        bool,
        typer.Option("--show-snapshots", help="Show file snapshots."),
    ] = False,
    show_cwd: Annotated[
        bool,
        typer.Option("--show-cwd", help="Show working directory changes."),
    ] = False,
    show_threading: Annotated[
        bool,
        typer.Option("--show-threading", help="Show message parent-child relationships."),
    ] = False,
    no_stop_reasons: Annotated[
        bool,
        typer.Option("--no-stop-reasons", help="Hide stop reason statistics."),
    ] = False,
    no_turn_durations: Annotated[
        bool,
        typer.Option("--no-turn-durations", help="Hide turn duration statistics."),
    ] = False,
    no_hook_errors: Annotated[
        bool,
        typer.Option("--no-hook-errors", help="Hide hook error information."),
    ] = False,
    show_service_tier: Annotated[
        bool,
        typer.Option("--show-service-tier", help="Show API service tier."),
    ] = False,
    no_sidechain: Annotated[
        bool,
        typer.Option("--no-sidechain", help="Hide sidechain message count."),
    ] = False,
    preset: Annotated[
        ConfigPreset | None,
        typer.Option("--preset", help="Use preset configuration (minimal, verbose, debug)."),
    ] = None,
    do_list_sessions: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available sessions and exit."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Monitor Claude Code session stream with live statistics.

    Shows tool calls, thinking blocks, user prompts, and assistant responses
    as they happen. Displays token usage, cost estimates, and tool histograms.

    Examples:
        cctmux-session                    # Auto-detect from current project
        cctmux-session abc123             # Monitor session starting with abc123
        cctmux-session /path/to/file.jsonl  # Monitor specific JSONL file
        cctmux-session -p /path/to/project  # Find session for specific project
        cctmux-session --list             # List all available sessions
        cctmux-session --no-thinking      # Hide thinking blocks
        cctmux-session --preset verbose   # Use verbose preset
        cctmux-session --show-cwd         # Show working directory
    """
    if ctx.invoked_subcommand is not None:
        return

    if do_list_sessions:
        list_session_files(project_path=project)
        raise typer.Exit(0)

    # Load preset configuration if specified
    if preset:
        preset_config = get_preset_config(preset)
        session_config = preset_config.session_monitor
        display_config = DisplayConfig(
            show_thinking=session_config.show_thinking,
            show_results=session_config.show_results,
            show_progress=session_config.show_progress,
            show_system=session_config.show_system,
            show_snapshots=session_config.show_snapshots,
            show_cwd=session_config.show_cwd,
            show_threading=session_config.show_threading,
            show_stop_reasons=session_config.show_stop_reasons,
            show_turn_durations=session_config.show_turn_durations,
            show_hook_errors=session_config.show_hook_errors,
            show_service_tier=session_config.show_service_tier,
            show_sidechain=session_config.show_sidechain,
            max_events=session_config.max_events,
        )
    else:
        display_config = DisplayConfig(
            show_thinking=not no_thinking,
            show_results=not no_results,
            show_progress=not no_progress,
            show_system=show_system,
            show_snapshots=show_snapshots,
            show_cwd=show_cwd,
            show_threading=show_threading,
            show_stop_reasons=not no_stop_reasons,
            show_turn_durations=not no_turn_durations,
            show_hook_errors=not no_hook_errors,
            show_service_tier=show_service_tier,
            show_sidechain=not no_sidechain,
        )

    # CLI overrides preset (explicit flags take precedence)
    if max_events is not None:
        display_config.max_events = max_events

    run_session_monitor(
        session_or_path=session_or_path,
        project_path=project,
        poll_interval=interval,
        max_visible=max_events,
        config=display_config,
    )


agents_app = typer.Typer(
    name="cctmux-agents",
    help="Monitor Claude Code subagent activity in real-time.",
    no_args_is_help=False,
)


@agents_app.callback(invoke_without_command=True)
def agents_main(
    ctx: typer.Context,
    session_or_path: Annotated[
        str | None,
        typer.Argument(help="Session ID, partial ID, or project path."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project directory to find sessions for."),
    ] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds."),
    ] = 1.0,
    inactive_timeout: Annotated[
        float | None,
        typer.Option(
            "--inactive-timeout",
            "-t",
            help="Hide agents inactive for this many seconds. 0 to show all. Default: 300 (5 min).",
        ),
    ] = None,
    max_agents: Annotated[
        int,
        typer.Option("--max-agents", "-M", help="Maximum agents to show (0 for unlimited)."),
    ] = 20,
    no_activity: Annotated[
        bool,
        typer.Option("--no-activity", "-a", help="Hide the activity panel."),
    ] = False,
    do_list: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available subagents and exit."),
    ] = False,
    summarize: Annotated[
        bool,
        typer.Option(
            "--summarize",
            "-S",
            help="Use claude haiku to generate a ≤64-char summary of each agent's initial prompt (done once per agent).",
        ),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Monitor Claude Code subagent activity with live updates.

    Shows all active and completed subagents for a session, including their
    status, token usage, tool calls, and current activity.

    By default, agents with no activity for more than 5 minutes are hidden.
    Use --inactive-timeout 0 to show all agents.

    Examples:
        cctmux-agents                     # Auto-detect from current project
        cctmux-agents abc123              # Monitor specific session
        cctmux-agents -p /path/to/project # Find subagents for specific project
        cctmux-agents --list              # List all available subagents
        cctmux-agents --no-activity       # Hide the activity panel
        cctmux-agents -t 0               # Show all agents (no timeout)
        cctmux-agents -t 600             # Hide agents inactive for 10+ minutes
        cctmux-agents --summarize         # AI-summarize each agent's task
    """
    if ctx.invoked_subcommand is not None:
        return

    # Resolve inactive timeout: CLI flag > config > default (300s)
    config, _agent_warnings = load_config(project_dir=project or Path.cwd())
    effective_timeout = inactive_timeout if inactive_timeout is not None else config.agent_monitor.inactive_timeout

    if do_list:
        list_subagents(session_id=session_or_path, project_path=project, inactive_timeout=effective_timeout)
        raise typer.Exit(0)

    run_subagent_monitor(
        session_or_path=session_or_path,
        project_path=project,
        poll_interval=interval,
        show_activity=not no_activity,
        inactive_timeout=effective_timeout,
        max_agents=max_agents,
        summarize=summarize,
    )


activity_app = typer.Typer(
    name="cctmux-activity",
    help="Display Claude Code usage activity dashboard.",
    no_args_is_help=False,
)


@activity_app.callback(invoke_without_command=True)
def activity_main(
    ctx: typer.Context,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to show in heatmap."),
    ] = 14,
    no_heatmap: Annotated[
        bool,
        typer.Option("--no-heatmap", help="Hide activity heatmap."),
    ] = False,
    no_cost: Annotated[
        bool,
        typer.Option("--no-cost", help="Hide cost estimates."),
    ] = False,
    no_model_usage: Annotated[
        bool,
        typer.Option("--no-model-usage", help="Hide model usage table."),
    ] = False,
    show_hourly: Annotated[
        bool,
        typer.Option("--show-hourly", "-H", help="Show hourly activity distribution."),
    ] = False,
    preset: Annotated[
        ConfigPreset | None,
        typer.Option("--preset", help="Use preset configuration (minimal, verbose, debug)."),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Display Claude Code activity dashboard with usage statistics.

    Shows aggregated usage data from Claude Code's stats-cache.json including
    session counts, message totals, token usage by model, and cost estimates.

    Examples:
        cctmux-activity                   # Show default dashboard
        cctmux-activity --days 7          # Show 7-day heatmap
        cctmux-activity --show-hourly     # Include hourly distribution
        cctmux-activity --no-cost         # Hide cost estimates
        cctmux-activity --preset minimal  # Minimal display
    """
    if ctx.invoked_subcommand is not None:
        return

    from cctmux.activity_monitor import run_activity_monitor

    # Load preset configuration if specified
    if preset:
        preset_config = get_preset_config(preset)
        activity_config = preset_config.activity_monitor
        effective_days = activity_config.default_days
        effective_show_heatmap = activity_config.show_heatmap
        effective_show_cost = activity_config.show_cost
        effective_show_model_usage = activity_config.show_model_usage
    else:
        effective_days = days
        effective_show_heatmap = not no_heatmap
        effective_show_cost = not no_cost
        effective_show_model_usage = not no_model_usage

    # CLI overrides preset
    if days != 14:
        effective_days = days

    run_activity_monitor(
        days=effective_days,
        show_heatmap=effective_show_heatmap,
        show_cost=effective_show_cost,
        show_model_usage=effective_show_model_usage,
        show_hour_distribution=show_hourly,
    )


git_app = typer.Typer(
    name="cctmux-git",
    help="Monitor git repository status in real-time.",
    no_args_is_help=False,
)


@git_app.callback(invoke_without_command=True)
def git_main(
    ctx: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Git repository directory."),
    ] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds."),
    ] = 2.0,
    max_commits: Annotated[
        int,
        typer.Option("--max-commits", "-m", help="Maximum recent commits to show."),
    ] = 10,
    max_files: Annotated[
        int,
        typer.Option("--max-files", "-M", help="Maximum files to show (0 for unlimited)."),
    ] = 20,
    no_log: Annotated[
        bool,
        typer.Option("--no-log", help="Hide recent commits panel."),
    ] = False,
    no_diff: Annotated[
        bool,
        typer.Option("--no-diff", help="Hide diff stats panel."),
    ] = False,
    no_status: Annotated[
        bool,
        typer.Option("--no-status", help="Hide file status panel."),
    ] = False,
    fetch: Annotated[
        bool,
        typer.Option("--fetch", "-f", help="Enable periodic git fetch to check for remote commits."),
    ] = False,
    no_fetch: Annotated[
        bool,
        typer.Option("--no-fetch", help="Disable periodic git fetch (overrides config/preset)."),
    ] = False,
    fetch_interval: Annotated[
        float | None,
        typer.Option("--fetch-interval", "-F", help="How often to fetch from remote (seconds, default: 60)."),
    ] = None,
    preset: Annotated[
        ConfigPreset | None,
        typer.Option("--preset", help="Use preset configuration (minimal, verbose, debug)."),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Monitor git repository status with live updates.

    Shows branch info, file statuses, recent commits, and diff statistics.
    Updates in real-time by polling git status. Use --fetch to periodically
    check the remote for new commits.

    Examples:
        cctmux-git                      # Monitor current directory
        cctmux-git -p /path/to/repo     # Monitor specific repo
        cctmux-git --no-log             # Hide recent commits
        cctmux-git --no-diff            # Hide diff stats
        cctmux-git -m 20               # Show 20 recent commits
        cctmux-git --fetch              # Enable remote commit checking
        cctmux-git --fetch -F 30        # Fetch every 30 seconds
        cctmux-git --preset minimal     # Minimal display
    """
    if ctx.invoked_subcommand is not None:
        return

    # Load preset configuration if specified
    if preset:
        preset_config = get_preset_config(preset)
        git_config = preset_config.git_monitor
        effective_show_log = git_config.show_log
        effective_show_diff = git_config.show_diff
        effective_show_status = git_config.show_status
        effective_max_commits = git_config.max_commits
        effective_max_files = git_config.max_files
        effective_interval = git_config.poll_interval
        effective_fetch_enabled = git_config.fetch_enabled
        effective_fetch_interval = git_config.fetch_interval
    else:
        effective_show_log = not no_log
        effective_show_diff = not no_diff
        effective_show_status = not no_status
        effective_max_commits = max_commits
        effective_max_files = max_files
        effective_interval = interval
        # Use config defaults when no preset
        config, _git_warnings = load_config(project_dir=project or Path.cwd())
        effective_fetch_enabled = config.git_monitor.fetch_enabled
        effective_fetch_interval = config.git_monitor.fetch_interval

    # CLI overrides preset
    if max_commits != 10:
        effective_max_commits = max_commits
    if max_files != 20:
        effective_max_files = max_files
    if interval != 2.0:
        effective_interval = interval

    # --fetch / --no-fetch CLI flags override preset/config
    if fetch:
        effective_fetch_enabled = True
    if no_fetch:
        effective_fetch_enabled = False
    if fetch_interval is not None:
        effective_fetch_interval = fetch_interval

    run_git_monitor(
        repo_path=project,
        poll_interval=effective_interval,
        max_commits=effective_max_commits,
        max_files=effective_max_files,
        show_log=effective_show_log,
        show_diff=effective_show_diff,
        show_status=effective_show_status,
        fetch_enabled=effective_fetch_enabled,
        fetch_interval=effective_fetch_interval,
    )


ralph_app = typer.Typer(
    name="cctmux-ralph",
    help="Ralph Loop: automated iterative Claude Code execution.",
    no_args_is_help=False,
)


@ralph_app.callback(invoke_without_command=True)
def ralph_main(
    ctx: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project directory to monitor."),
    ] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds."),
    ] = 1.0,
    preset: Annotated[
        ConfigPreset | None,
        typer.Option("--preset", help="Use preset configuration (minimal, verbose, debug)."),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Monitor a running Ralph Loop with a live dashboard.

    When run without a subcommand, displays a real-time dashboard showing
    iteration progress, task completion, token usage, and cost tracking.

    Examples:
        cctmux-ralph                      # Monitor from current directory
        cctmux-ralph -p /path/to/project  # Monitor specific project
        cctmux-ralph --preset verbose     # Use verbose display preset
    """
    if ctx.invoked_subcommand is not None:
        return

    from cctmux.ralph_monitor import RalphMonitorConfig, run_ralph_monitor

    if preset:
        preset_config = get_preset_config(preset)
        ralph_config = preset_config.ralph_monitor
        monitor_config = RalphMonitorConfig(
            show_table=ralph_config.show_table,
            show_timeline=ralph_config.show_timeline,
            show_prompt=ralph_config.show_prompt,
            show_task_progress=ralph_config.show_task_progress,
            max_iterations_visible=ralph_config.max_iterations_visible,
        )
    else:
        monitor_config = RalphMonitorConfig()

    run_ralph_monitor(
        project_path=project,
        poll_interval=interval,
        config=monitor_config,
    )


@ralph_app.command()
def start(
    project_file: Annotated[
        Path,
        typer.Argument(help="Path to the Ralph project markdown file."),
    ],
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", "-m", help="Maximum iterations (0 = unlimited)."),
    ] = 0,
    completion_promise: Annotated[
        str,
        typer.Option("--completion-promise", "-c", help="Text to match in <promise> tags."),
    ] = "",
    permission_mode: Annotated[
        str,
        typer.Option("--permission-mode", help="Claude permission mode."),
    ] = "acceptEdits",
    model: Annotated[
        str | None,
        typer.Option("--model", help="Claude model to use."),
    ] = None,
    max_budget: Annotated[
        float | None,
        typer.Option("--max-budget", help="Max budget per iteration in USD."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project root directory."),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", "-t", help="Max seconds per iteration (0 = no timeout)."),
    ] = 0,
    yolo: Annotated[
        bool,
        typer.Option("--yolo", "-y", help="Use --dangerously-skip-permissions for claude invocations."),
    ] = False,
) -> None:
    """Start a Ralph Loop from a project file. Runs in foreground."""
    from cctmux.ralph_runner import run_ralph_loop

    if not project_file.exists():
        err_console.print(f"[red]Error:[/] Project file not found: {project_file}")
        raise typer.Exit(1)

    run_ralph_loop(
        project_file=project_file,
        max_iterations=max_iterations,
        completion_promise=completion_promise,
        permission_mode=permission_mode,
        model=model,
        max_budget_usd=max_budget,
        project_path=project,
        iteration_timeout=timeout,
        yolo=yolo,
    )


@ralph_app.command()
def init(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output file path."),
    ] = Path("ralph-project.md"),
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Project name for the template."),
    ] = "",
) -> None:
    """Create a template Ralph project file."""
    from cctmux.ralph_runner import init_project_file

    if output.exists():
        err_console.print(f"[yellow]File already exists:[/] {output}")
        raise typer.Exit(1)

    init_project_file(output, name=name)
    console.print(f"[green]✓[/] Created Ralph project file: {output}")


@ralph_app.command()
def stop(
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project root directory."),
    ] = None,
) -> None:
    """Stop the Ralph Loop after the current iteration finishes."""
    from cctmux.ralph_runner import stop_ralph_loop

    proj_path = (project or Path.cwd()).resolve()
    if stop_ralph_loop(proj_path):
        console.print("[green]✓[/] Ralph Loop will stop after the current iteration.")
    else:
        err_console.print("[yellow]No active Ralph Loop found.[/]")
        raise typer.Exit(1)


@ralph_app.command()
def cancel(
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project root directory."),
    ] = None,
) -> None:
    """Cancel the active Ralph Loop immediately."""
    from cctmux.ralph_runner import cancel_ralph_loop

    proj_path = (project or Path.cwd()).resolve()
    if cancel_ralph_loop(proj_path):
        console.print("[green]✓[/] Ralph Loop cancelled.")
    else:
        err_console.print("[yellow]No active Ralph Loop found.[/]")
        raise typer.Exit(1)


@ralph_app.command()
def status(
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project root directory."),
    ] = None,
) -> None:
    """Show current Ralph Loop status (one-shot)."""
    from cctmux.ralph_runner import RalphStatus, load_ralph_state

    proj_path = (project or Path.cwd()).resolve()
    state = load_ralph_state(proj_path)

    if state is None:
        err_console.print("[yellow]No Ralph Loop state found.[/]")
        raise typer.Exit(1)

    status_colors = {
        RalphStatus.ACTIVE: "yellow",
        RalphStatus.STOPPING: "magenta",
        RalphStatus.COMPLETED: "green",
        RalphStatus.CANCELLED: "red",
        RalphStatus.MAX_REACHED: "cyan",
        RalphStatus.ERROR: "red",
        RalphStatus.WAITING: "dim",
    }
    color = status_colors.get(state.status, "white")  # type: ignore[arg-type]

    max_str = f"/{state.max_iterations}" if state.max_iterations > 0 else ""
    console.print(f"[{color}]Status:[/] {state.status}")
    console.print(f"Iteration: {state.iteration}{max_str}")
    console.print(f"Tasks: {state.tasks_completed}/{state.tasks_total}")

    if state.iterations:
        total_cost = sum(it.get("cost_usd", 0.0) for it in state.iterations)
        console.print(f"Total cost: ${total_cost:.2f}")

    if state.completion_promise:
        console.print(f'Promise: "{state.completion_promise}"')


config_app = typer.Typer(
    name="config",
    help="Configuration management commands.",
)
app.add_typer(config_app, name="config")


@config_app.command("validate")
def config_validate(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-C", help="Config file path."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project directory."),
    ] = None,
) -> None:
    """Validate all config files and report warnings."""
    project_dir = project or Path.cwd()
    _config, warnings = load_config(config_path, project_dir=project_dir, strict=True)

    if warnings:
        display_config_warnings(warnings, err_console)
        raise typer.Exit(1)

    console.print("[green]✓[/] All config files are valid.")


@config_app.command("show")
def config_show(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-C", help="Config file path."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-p", help="Project directory."),
    ] = None,
) -> None:
    """Show effective merged configuration."""
    import yaml

    project_dir = project or Path.cwd()
    config, warnings = load_config(config_path, project_dir=project_dir)

    if warnings:
        display_config_warnings(warnings, err_console)

    data = config.model_dump()
    data["default_layout"] = config.default_layout.value
    console.print(yaml.dump(data, default_flow_style=False))


layout_app = typer.Typer(
    name="layout",
    help="Layout management commands.",
)
app.add_typer(layout_app, name="layout")


@layout_app.command("list")
def layout_list() -> None:
    """List all available layouts (built-in and custom)."""
    from rich.table import Table

    from cctmux.layouts import LAYOUT_DESCRIPTIONS

    config, _warnings = load_config(project_dir=Path.cwd())

    table = Table(title="Available Layouts")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    # Built-in layouts
    for lt in LayoutType:
        desc = LAYOUT_DESCRIPTIONS.get(lt, "")
        table.add_row(lt.value, "built-in", desc)

    # Custom layouts
    for cl in config.custom_layouts:
        table.add_row(cl.name, "custom", cl.description)

    console.print(table)


@layout_app.command("show")
def layout_show(
    name: Annotated[
        str,
        typer.Argument(help="Layout name to show."),
    ],
) -> None:
    """Show layout details."""
    import yaml

    from cctmux.layouts import BUILTIN_TEMPLATES, LAYOUT_DESCRIPTIONS

    # Check built-in
    try:
        lt = LayoutType(name)
        console.print(f"[cyan]{name}[/] [dim](built-in)[/]")
        desc = LAYOUT_DESCRIPTIONS.get(lt, "")
        if desc:
            console.print(f"  {desc}")
        template = BUILTIN_TEMPLATES.get(lt)
        if template:
            console.print("\n[dim]Template representation:[/]")
            splits_data = [s.model_dump() for s in template]
            console.print(yaml.dump({"splits": splits_data}, default_flow_style=False))
        return
    except ValueError:
        pass

    # Check custom
    config, _warnings = load_config(project_dir=Path.cwd())
    for cl in config.custom_layouts:
        if cl.name == name:
            console.print(f"[cyan]{name}[/] [dim](custom)[/]")
            if cl.description:
                console.print(f"  {cl.description}")
            data = cl.model_dump()
            console.print(yaml.dump(data, default_flow_style=False))
            return

    err_console.print(f"[red]Error:[/] Layout '{name}' not found.")
    raise typer.Exit(1)


@layout_app.command("add")
def layout_add(
    name: Annotated[
        str,
        typer.Argument(help="Name for the new custom layout."),
    ],
    from_layout: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Copy from an existing layout as starting point."),
    ] = None,
) -> None:
    """Create a new custom layout."""
    import os
    import tempfile

    import yaml

    from cctmux.layouts import BUILTIN_TEMPLATES

    # Validate name
    try:
        validate_layout_name(name)
    except ValueError as e:
        err_console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1) from None

    config, _warnings = load_config(project_dir=Path.cwd())

    # Check if name already exists in custom layouts
    if any(cl.name == name for cl in config.custom_layouts):
        err_console.print(f"[red]Error:[/] Custom layout '{name}' already exists. Use 'layout edit' to modify.")
        raise typer.Exit(1)

    # Build template YAML
    if from_layout:
        # Try built-in
        try:
            lt = LayoutType(from_layout)
            template = BUILTIN_TEMPLATES.get(lt)
            splits_data = [s.model_dump(exclude_defaults=True) for s in template] if template else []
            layout_data = {
                "name": name,
                "description": f"Custom layout based on {from_layout}",
                "splits": splits_data,
                "focus_main": True,
            }
        except ValueError:
            # Try custom
            source = next((cl for cl in config.custom_layouts if cl.name == from_layout), None)
            if source is None:
                err_console.print(f"[red]Error:[/] Source layout '{from_layout}' not found.")
                raise typer.Exit(1) from None
            layout_data = source.model_dump()
            layout_data["name"] = name
            layout_data["description"] = f"Custom layout based on {from_layout}"
    else:
        layout_data = {
            "name": name,
            "description": "My custom layout",
            "splits": [
                {"direction": "h", "size": 40, "command": "", "name": "right", "target": "main"},
            ],
            "focus_main": True,
        }

    yaml_content = yaml.dump(layout_data, default_flow_style=False, sort_keys=False)

    # Open in editor
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(f"# Custom layout: {name}\n")
        f.write("# Edit this file, save and close to create the layout.\n")
        f.write("# Delete all content to cancel.\n\n")
        f.write(yaml_content)
        tmp_path = f.name

    try:
        os.system(f'{editor} "{tmp_path}"')  # noqa: S605

        # Read back
        content = Path(tmp_path).read_text(encoding="utf-8")
        # Strip comment lines for emptiness check
        stripped = "\n".join(line for line in content.splitlines() if not line.strip().startswith("#"))
        if not stripped.strip():
            console.print("[yellow]Cancelled.[/]")
            return

        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            err_console.print("[red]Error:[/] Invalid YAML — expected a mapping.")
            raise typer.Exit(1)

        # Validate
        try:
            new_layout = CustomLayout.model_validate(parsed)
            validate_layout_name(new_layout.name)
        except (ValueError, Exception) as e:
            err_console.print(f"[red]Error:[/] Invalid layout: {e}")
            raise typer.Exit(1) from None

        # Add to config and save
        config.custom_layouts.append(new_layout)
        save_config(config)
        console.print(f"[green]✓[/] Custom layout '{new_layout.name}' added.")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@layout_app.command("remove")
def layout_remove(
    name: Annotated[
        str,
        typer.Argument(help="Name of the custom layout to remove."),
    ],
) -> None:
    """Remove a custom layout."""
    # Prevent removing built-in
    try:
        LayoutType(name)
        err_console.print(f"[red]Error:[/] '{name}' is a built-in layout and cannot be removed.")
        raise typer.Exit(1)
    except ValueError:
        pass

    config, _warnings = load_config(project_dir=Path.cwd())
    original_count = len(config.custom_layouts)
    config.custom_layouts = [cl for cl in config.custom_layouts if cl.name != name]

    if len(config.custom_layouts) == original_count:
        err_console.print(f"[red]Error:[/] Custom layout '{name}' not found.")
        raise typer.Exit(1)

    save_config(config)
    console.print(f"[green]✓[/] Custom layout '{name}' removed.")


@layout_app.command("edit")
def layout_edit(
    name: Annotated[
        str,
        typer.Argument(help="Name of the custom layout to edit."),
    ],
) -> None:
    """Edit an existing custom layout."""
    import os
    import tempfile

    import yaml

    # Prevent editing built-in
    try:
        LayoutType(name)
        err_console.print(f"[red]Error:[/] '{name}' is a built-in layout and cannot be edited.")
        raise typer.Exit(1)
    except ValueError:
        pass

    config, _warnings = load_config(project_dir=Path.cwd())
    layout_idx = next((i for i, cl in enumerate(config.custom_layouts) if cl.name == name), None)

    if layout_idx is None:
        err_console.print(f"[red]Error:[/] Custom layout '{name}' not found.")
        raise typer.Exit(1)

    current = config.custom_layouts[layout_idx]
    yaml_content = yaml.dump(current.model_dump(), default_flow_style=False, sort_keys=False)

    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(f"# Editing custom layout: {name}\n")
        f.write("# Save and close to apply changes. Delete all content to cancel.\n\n")
        f.write(yaml_content)
        tmp_path = f.name

    try:
        os.system(f'{editor} "{tmp_path}"')  # noqa: S605

        content = Path(tmp_path).read_text(encoding="utf-8")
        stripped = "\n".join(line for line in content.splitlines() if not line.strip().startswith("#"))
        if not stripped.strip():
            console.print("[yellow]Cancelled.[/]")
            return

        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            err_console.print("[red]Error:[/] Invalid YAML — expected a mapping.")
            raise typer.Exit(1)

        try:
            updated_layout = CustomLayout.model_validate(parsed)
            validate_layout_name(updated_layout.name)
        except (ValueError, Exception) as e:
            err_console.print(f"[red]Error:[/] Invalid layout: {e}")
            raise typer.Exit(1) from None

        config.custom_layouts[layout_idx] = updated_layout
        save_config(config)
        console.print(f"[green]✓[/] Custom layout '{updated_layout.name}' updated.")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    app()
