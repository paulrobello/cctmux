# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cctmux is a CLI tool that launches Claude Code inside tmux with session management. It creates/attaches to tmux sessions named after project folders, sets environment variables for Claude awareness (`$CCTMUX_SESSION`, `$CCTMUX_PROJECT_DIR`), and includes a skill for Claude to manage tmux panes.

## Build & Development Commands

```bash
make checkall      # Format, lint, typecheck, and test (run before committing)
make fmt           # Format with ruff
make lint          # Lint with ruff
make typecheck     # Type check with pyright (strict mode)
make test          # Run all tests
uv run pytest tests/test_utils.py::TestSanitizeSessionName::test_lowercase  # Run single test
uv run cctmux --dry-run  # Test CLI without executing tmux commands
uv run cctmux-tasks --list  # List available task sessions
uv run cctmux-session     # Real-time session event monitor
uv run cctmux-agents      # Real-time subagent activity monitor
uv run cctmux-ralph init  # Create a Ralph project template
uv run cctmux-ralph start ralph-project.md  # Start a Ralph Loop
uv run cctmux-ralph       # Monitor a running Ralph Loop
uv run cctmux-git         # Real-time git status monitor
```

## Architecture

```
src/cctmux/
├── __main__.py         # Typer CLI: 7 apps (cctmux, cctmux-tasks, cctmux-session, cctmux-agents, cctmux-activity, cctmux-git, cctmux-ralph)
├── config.py           # Config model (Pydantic), LayoutType StrEnum, YAML load/save
├── session_history.py  # Session tracking with Pydantic models, stored in XDG data dir
├── tmux_manager.py     # Core tmux operations: create/attach sessions, status bar
├── task_monitor.py     # Real-time task monitor with ASCII dependency graphs
├── session_monitor.py  # Real-time session event monitor (thinking, tools, text)
├── subagent_monitor.py # Real-time subagent activity monitor
├── activity_monitor.py # Usage statistics dashboard
├── ralph_runner.py     # Ralph Loop engine: state, task parsing, claude invocation, loop
├── ralph_monitor.py    # Ralph Loop live dashboard: status, tasks, timeline, iterations
├── git_monitor.py      # Real-time git status monitor
├── layouts.py          # Predefined layouts (default, editor, monitor, triple, cc-mon, full-monitor, dashboard, ralph, ralph-full, git-mon)
├── xdg_paths.py        # XDG-compliant paths for config/data directories
└── utils.py            # Session name sanitization, fzf integration, path compression
```

**Seven Entry Points**:
- `cctmux` - Main CLI for tmux session management
- `cctmux-tasks` - Task monitor for Claude Code TodoWrite tasks
- `cctmux-session` - Session event monitor (shows thinking, tool calls, text output)
- `cctmux-agents` - Subagent activity monitor
- `cctmux-activity` - Usage statistics dashboard
- `cctmux-git` - Real-time git repository status monitor
- `cctmux-ralph` - Ralph Loop automation (start/monitor/cancel/status/init)

**Data Flow**: CLI (`__main__.py`) → loads config → checks/creates tmux session via `tmux_manager.py` → applies layout → updates history

**Task Monitor Flow**: `cctmux-tasks` → resolves task path via `resolve_task_path()` → loads tasks from `~/.claude/tasks/<session-id>/` → displays with Rich Live using windowed virtual scrolling

**Ralph Loop Flow**: `cctmux-ralph start <file>` → reads project markdown → for each iteration: count tasks, build prompt, run `claude -p`, parse JSON output, check promises/task completion → update `$PROJECT/.claude/ralph-state.json`

**Storage Locations**:
- Config: `~/.config/cctmux/config.yaml`
- History: `~/.local/share/cctmux/history.yaml`
- Skill: `~/.claude/skills/cc-tmux/SKILL.md`
- Claude tasks: `~/.claude/tasks/<session-id>/*.json`
- Claude sessions: `~/.claude/projects/<encoded-path>/<session-id>.jsonl`
- Claude subagents: `~/.claude/projects/<encoded-path>/agent-*.jsonl` or `<session-id>/subagents/agent-*.jsonl`
- Ralph state: `$PROJECT/.claude/ralph-state.json`

## Key Patterns

- All tmux operations support `dry_run=True` to return commands without executing
- Config and history use Pydantic models with YAML serialization
- CLI args override config defaults (e.g., `--claude-args` overrides `default_claude_args`)
- Session names are sanitized: lowercase, hyphens only, no special chars
- Task monitor uses `TaskWindow` dataclass for virtual scrolling of large task lists
- Project paths are encoded for Claude folder lookups: `/Users/foo/project` → `-Users-foo-project`
- Multi-pane layouts use `-P -F "#{pane_id}"` to capture pane IDs for reliable targeting
- Path compression utilities (`compress_path`, `compress_paths_in_text`) replace home dir with `~`
- Layout diagrams in docs use ASCII art (not mermaid) — they visualize spatial pane arrangements which mermaid handles poorly
- Ralph Loop uses atomic JSON state writes via temp files for safe concurrent reading by the monitor
- Ralph Loop detects completion via: all checklist items checked, `<promise>` tag in output, or max iterations reached
