# Architecture

System design and data flow for cctmux. This document describes how the components interact and where data is stored.

## Table of Contents

- [Overview](#overview)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [File Locations](#file-locations)
- [Module Structure](#module-structure)
- [Configuration System](#configuration-system)
- [Layout System](#layout-system)
- [Team Mode](#team-mode)
- [Related Documentation](#related-documentation)

## Overview

cctmux is a CLI toolset that integrates Claude Code with tmux for enhanced session management and monitoring. The system consists of eight CLI entry points (seven for Claude Code, one for the pi coding agent) that share common modules for configuration, session tracking, and display rendering.

```mermaid
graph TB
    subgraph "User Interface"
        CLI[CLI Commands]
        Term[Terminal Display]
    end

    subgraph "Core Components"
        Config[Configuration]
        TmuxMgr[Tmux Manager]
        History[Session History]
    end

    subgraph "Monitors"
        TaskMon[Task Monitor]
        SessionMon[Session Monitor]
        AgentMon[Subagent Monitor]
        ActivityMon[Activity Monitor]
        GitMon[Git Monitor]
        RalphMon[Ralph Monitor]
    end

    subgraph "Ralph Loop"
        RalphRunner[Ralph Runner]
        RalphState[Ralph State]
    end

    subgraph "External Systems"
        Tmux[tmux]
        ClaudeCode[Claude Code]
        ClaudeData[Claude Data Files]
        GitRepo[Git Repository]
    end

    CLI --> Config
    CLI --> TmuxMgr
    CLI --> History
    CLI --> TaskMon
    CLI --> SessionMon
    CLI --> AgentMon
    CLI --> ActivityMon
    CLI --> GitMon
    CLI --> RalphRunner
    CLI --> RalphMon

    TmuxMgr --> Tmux
    Tmux --> ClaudeCode

    TaskMon --> ClaudeData
    SessionMon --> ClaudeData
    AgentMon --> ClaudeData
    ActivityMon --> ClaudeData
    GitMon --> GitRepo

    TaskMon --> Term
    SessionMon --> Term
    AgentMon --> Term
    ActivityMon --> Term
    GitMon --> Term
    RalphMon --> Term
    RalphRunner --> ClaudeCode
    RalphRunner --> RalphState

    style CLI fill:#e65100,stroke:#ff9800,stroke-width:3px,color:#ffffff
    style Term fill:#e65100,stroke:#ff9800,stroke-width:2px,color:#ffffff
    style Config fill:#0d47a1,stroke:#2196f3,stroke-width:2px,color:#ffffff
    style TmuxMgr fill:#0d47a1,stroke:#2196f3,stroke-width:2px,color:#ffffff
    style History fill:#0d47a1,stroke:#2196f3,stroke-width:2px,color:#ffffff
    style TaskMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style SessionMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style AgentMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style ActivityMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style GitMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style RalphMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style RalphRunner fill:#ff6f00,stroke:#ffa726,stroke-width:2px,color:#ffffff
    style RalphState fill:#1a237e,stroke:#3f51b5,stroke-width:2px,color:#ffffff
    style Tmux fill:#37474f,stroke:#78909c,stroke-width:2px,color:#ffffff
    style ClaudeCode fill:#4a148c,stroke:#9c27b0,stroke-width:2px,color:#ffffff
    style ClaudeData fill:#1a237e,stroke:#3f51b5,stroke-width:2px,color:#ffffff
    style GitRepo fill:#004d40,stroke:#00897b,stroke-width:2px,color:#ffffff
```

## Component Architecture

### CLI Entry Points

| Entry Point | Module | Purpose |
|-------------|--------|---------|
| `cctmux` | `__main__.py:app` | Main session launcher with `install-skill`, `init-config`, `config`, `layout`, and `team` subcommands |
| `cctmux-tasks` | `__main__.py:tasks_app` | Task monitor with dependency graphs |
| `cctmux-session` | `__main__.py:session_app` | Session event monitor with statistics |
| `cctmux-agents` | `__main__.py:agents_app` | Subagent activity monitor |
| `cctmux-activity` | `__main__.py:activity_app` | Usage statistics dashboard |
| `cctmux-git` | `__main__.py:git_app` | Real-time git repository status monitor |
| `cctmux-ralph` | `__main__.py:ralph_app` | Ralph Loop automation with `start`, `init`, `stop`, `cancel`, and `status` subcommands |
| `pitmux` | `__main__.py:pi_app` | Launch the pi coding agent in a tmux session |

### Core Modules

```mermaid
graph LR
    subgraph "CLI Layer"
        Main[__main__.py]
    end

    subgraph "Business Logic"
        TmuxMgr[tmux_manager.py]
        Layouts[layouts.py]
        TaskMon[task_monitor.py]
        SessionMon[session_monitor.py]
        AgentMon[subagent_monitor.py]
        ActivityMon[activity_monitor.py]
        GitMon[git_monitor.py]
        RalphRunner[ralph_runner.py]
        RalphMon[ralph_monitor.py]
    end

    subgraph "Data Layer"
        Config[config.py]
        History[session_history.py]
        XDG[xdg_paths.py]
        Utils[utils.py]
    end

    Main --> TmuxMgr
    Main --> Layouts
    Main --> TaskMon
    Main --> SessionMon
    Main --> AgentMon
    Main --> ActivityMon
    Main --> GitMon
    Main --> RalphRunner
    Main --> RalphMon
    Main --> Config
    Main --> History
    Main --> Utils
    Main --> XDG

    TmuxMgr --> Layouts
    TmuxMgr --> Config
    Layouts --> Config

    SessionMon --> TaskMon
    SessionMon --> Utils
    AgentMon --> TaskMon
    AgentMon --> Utils
    RalphMon --> RalphRunner
    RalphMon --> Utils

    Config --> XDG
    History --> XDG

    style Main fill:#e65100,stroke:#ff9800,stroke-width:3px,color:#ffffff
    style TmuxMgr fill:#0d47a1,stroke:#2196f3,stroke-width:2px,color:#ffffff
    style Layouts fill:#0d47a1,stroke:#2196f3,stroke-width:2px,color:#ffffff
    style TaskMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style SessionMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style AgentMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style ActivityMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style GitMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style RalphRunner fill:#ff6f00,stroke:#ffa726,stroke-width:2px,color:#ffffff
    style RalphMon fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style Config fill:#4a148c,stroke:#9c27b0,stroke-width:2px,color:#ffffff
    style History fill:#4a148c,stroke:#9c27b0,stroke-width:2px,color:#ffffff
    style XDG fill:#4a148c,stroke:#9c27b0,stroke-width:2px,color:#ffffff
    style Utils fill:#4a148c,stroke:#9c27b0,stroke-width:2px,color:#ffffff
```

## Data Flow

### Session Creation Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as cctmux
    participant Config
    participant TmuxMgr as Tmux Manager
    participant History
    participant Tmux
    participant Claude as Claude Code

    User->>CLI: cctmux
    CLI->>Config: load_config()
    Config-->>CLI: Config object
    CLI->>TmuxMgr: session_exists(name)
    TmuxMgr->>Tmux: tmux has-session
    Tmux-->>TmuxMgr: exists/not exists

    alt Session exists
        CLI->>TmuxMgr: attach_session(name)
        TmuxMgr->>Tmux: tmux attach-session
    else Session does not exist
        CLI->>TmuxMgr: session_exists(cross_tool_name)
        opt Cross-tool variant exists (and TTY)
            CLI->>User: Prompt: resume cctmux/pitmux session?
            User-->>CLI: y/n
            CLI->>TmuxMgr: attach_session(cross_tool_name)
        end
        CLI->>TmuxMgr: create_session(name, layout, ...)
        TmuxMgr->>Tmux: tmux new-session
        TmuxMgr->>Tmux: Set environment vars
        TmuxMgr->>Tmux: Apply layout splits
        TmuxMgr->>Tmux: send-keys claude
        Tmux->>Claude: Launch Claude Code
    end

    CLI->>History: add_or_update_entry()
    CLI->>History: save_history()
```

Session creation sets environment variables at the tmux session level: `CCTMUX_SESSION`, `CCTMUX_PROJECT_DIR`, and optionally `CLAUDE_CODE_TASK_LIST_ID` (when `--task-list-id` is used) and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` (when `--agent-teams` is used). These are also exported into the shell so that Claude Code and layout pane commands can reference them.

### Monitor Data Flow

```mermaid
sequenceDiagram
    participant Monitor
    participant FileSystem as Claude Data Files
    participant Parser
    participant Display as Rich Display

    loop Poll Interval
        Monitor->>FileSystem: Read data files
        FileSystem-->>Monitor: Raw data (JSON/JSONL)
        Monitor->>Parser: Parse events/tasks
        Parser-->>Monitor: Structured data
        Monitor->>Display: Build display
        Display-->>Monitor: Rendered output
        Monitor->>Monitor: Update terminal
    end
```

All monitors auto-detect new sessions. When no explicit session or path is provided, the monitor searches for the most recent session associated with the current project directory using the encoded project path.

### Ralph Loop Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as cctmux-ralph start
    participant Runner as Ralph Runner
    participant State as ralph-state.json
    participant Claude as claude -p
    participant Project as Project File

    User->>CLI: cctmux-ralph start project.md
    CLI->>Runner: run_ralph_loop()
    Runner->>Project: parse_task_progress()
    Runner->>State: save_ralph_state(active)

    loop Each Iteration
        Runner->>State: Check for stop/cancel signal
        Runner->>Project: Read project content
        Runner->>Runner: Build system prompt
        Runner->>Claude: Run claude -p with JSON output

        loop Every 5s during subprocess
            Runner->>State: Check for stop/cancel signal
            Runner->>Project: Re-read task progress
            Runner->>State: Save progress (skip if signal detected)
        end

        Claude-->>Runner: JSON result
        Runner->>Runner: Parse output and check promise
        Runner->>Project: Re-read task progress
        Runner->>State: Save iteration result

        alt Promise found
            Runner->>State: status = completed
        else All tasks done
            Runner->>State: status = completed
        else Max iterations reached
            Runner->>State: status = max_reached
        else Stop requested
            Runner->>State: status = completed
        else Error
            Runner->>State: status = error
        end
    end
```

Ralph Loop completion is detected via three mechanisms: all checklist items in the project file are checked (`- [x]`), the `<promise>` tag containing the expected text appears in the output, or the maximum iteration count is reached. State is written atomically via temp files so the Ralph monitor can safely read concurrently.

## File Locations

### cctmux Data

| Purpose | Location |
|---------|----------|
| Configuration | `~/.config/cctmux/config.yaml` |
| Session History | `~/.local/share/cctmux/history.yaml` |
| Skill Files | `~/.claude/skills/cc-tmux/` and `~/.claude/skills/cc-team-lead/` |
| Pi Skill Files | `~/.pi/agent/skills/pi-tmux/` |

### Claude Code Data

| Purpose | Location |
|---------|----------|
| Task Files | `~/.claude/tasks/<session-id>/*.json` |
| Session Transcripts | `~/.claude/projects/<encoded-path>/<session-id>.jsonl` |
| Subagent Transcripts | `~/.claude/projects/<encoded-path>/agent-*.jsonl` or `<session-id>/subagents/agent-*.jsonl` |
| Stats Cache | `~/.claude/stats-cache.json` |
| Ralph State | `$PROJECT/.claude/ralph-state.json` |
| Team Prompt Files | `$PROJECT/.cctmux/prompts/<role>.md` |

### Path Encoding

Project paths are encoded for Claude folder lookups by replacing `/` with `-`:

```
/Users/alice/repos/my-project → -Users-alice-repos-my-project
```

## Module Structure

```
src/cctmux/
├── __init__.py           # Package version
├── __main__.py           # CLI entry points (8 Typer apps + config, layout, team subcommand groups)
├── config.py             # Configuration models and presets
├── session_history.py    # Session tracking with Pydantic
├── tmux_manager.py       # Core tmux operations
├── layouts.py            # Predefined layout implementations
├── task_monitor.py       # Task monitor with dependency graphs
├── session_monitor.py    # Session event monitor
├── subagent_monitor.py   # Subagent activity monitor
├── activity_monitor.py   # Usage dashboard
├── git_monitor.py        # Real-time git status monitor
├── ralph_runner.py       # Ralph Loop engine
├── ralph_monitor.py      # Ralph Loop live dashboard
├── xdg_paths.py          # XDG-compliant path management
├── utils.py              # Shared utilities
├── skill/                # Bundled skill files (cc-tmux, cc-team-lead)
└── skill-pi/             # Bundled pi agent skill files (pi-tmux)
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `config.py` | Pydantic models for config, monitor-specific configs, custom layouts, team config, pitmux config, presets (`default`, `minimal`, `verbose`, `debug`), YAML I/O |
| `session_history.py` | Track recent sessions, LRU management, Pydantic models with YAML serialization |
| `tmux_manager.py` | Session creation (`create_session`, `create_pi_session`, `create_team_session`), attachment, environment variable setup, status bar configuration |
| `layouts.py` | Pane splitting with captured pane IDs, custom layout support, command execution per layout |
| `task_monitor.py` | Parse task JSON, build ASCII dependency graphs, windowed virtual scrolling |
| `session_monitor.py` | Parse JSONL events, compute statistics, cost estimation, path compression |
| `subagent_monitor.py` | Discover and monitor subagent JSONL files, parse activity and token usage |
| `activity_monitor.py` | Parse `stats-cache.json`, render heatmaps, model usage tables, hourly distribution |
| `git_monitor.py` | Parse git status, diff stats, and log output; collect data via subprocess; build Rich display panels |
| `ralph_runner.py` | Ralph Loop state management, project file parsing, claude CLI invocation, iteration tracking |
| `ralph_monitor.py` | Real-time Ralph Loop dashboard with status, timeline, task progress, iteration table |
| `xdg_paths.py` | Platform-appropriate config/data paths using `xdg-base-dirs` |
| `utils.py` | Name sanitization, fzf integration, path compression (`compress_path`, `compress_paths_in_text`) |

## Configuration System

### Config Model Hierarchy

The configuration uses a hierarchy of Pydantic models. The top-level `Config` model contains nested monitor-specific configuration models:

```mermaid
graph TD
    Config[Config]
    SMC[SessionMonitorConfig]
    TMC[TaskMonitorConfig]
    AMC[ActivityMonitorConfig]
    AgMC[AgentMonitorConfig]
    GMC[GitMonitorConfig]
    RMC[RalphMonitorConfig]
    CL[CustomLayout]
    TC[TeamConfig]

    Config --> SMC
    Config --> TMC
    Config --> AMC
    Config --> AgMC
    Config --> GMC
    Config --> RMC
    Config --> CL
    Config --> TC

    style Config fill:#e65100,stroke:#ff9800,stroke-width:3px,color:#ffffff
    style SMC fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style TMC fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style AMC fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style AgMC fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style GMC fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style RMC fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style CL fill:#37474f,stroke:#78909c,stroke-width:2px,color:#ffffff
    style TC fill:#ff6f00,stroke:#ffa726,stroke-width:2px,color:#ffffff
```

### Top-Level Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_layout` | `LayoutType` | `default` | Layout to use when none specified |
| `status_bar_enabled` | `bool` | `false` | Enable tmux status bar with git/project info |
| `max_history_entries` | `int` | `50` | Maximum session history entries to keep |
| `default_claude_args` | `str` or `null` | `null` | Default arguments passed to the `claude` command |
| `default_pi_args` | `str` or `null` | `null` | Default arguments passed to the `pi` command |
| `pi_session_prefix` | `str` | `"pi-"` | Prefix prepended to session names for pitmux |
| `task_list_id` | `bool` | `false` | Set `CLAUDE_CODE_TASK_LIST_ID` to session name |
| `agent_teams` | `bool` | `false` | Enable experimental agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) |
| `ignore_parent_configs` | `bool` | `false` | When set in a project config, skip user-level config |

### Configuration Presets

The `ConfigPreset` enum defines four presets that configure all monitors simultaneously:

| Preset | Description |
|--------|-------------|
| `default` | Standard settings with sensible defaults |
| `minimal` | Reduced display elements, smaller windows, fewer columns |
| `verbose` | All display elements enabled, larger windows, all metadata shown |
| `debug` | Maximum detail, largest windows, all metadata and system events shown |

CLI arguments always override preset values when explicitly provided.

## Layout System

### Layout Types

Ten predefined layouts are available, selected via the `--layout` / `-l` flag or the `default_layout` config option:

```
default          editor             monitor
┌──────────┐    ┌────────┬───┐    ┌──────────┐
│          │    │        │   │    │          │
│  Claude  │    │ Claude │Si-│    │  Claude  │
│  100%    │    │  70%   │de │    │   80%    │
│          │    │        │30%│    ├──────────┤
└──────────┘    └────────┴───┘    │Bottom 20%│
                                  └──────────┘

triple               cc-mon               full-monitor
┌──────┬──────┐    ┌──────┬──────┐    ┌────────┬─────┐
│      │ Top  │    │      │Ses-  │    │        │Sess-│
│      │Right │    │      │sion  │    │        │ion  │
│Claude├──────┤    │Claude├──────┤    │ Claude ├─────┤
│ 50%  │Bottom│    │ 50%  │Tasks │    │  60%   │Tasks│
│      │Right │    │      │      │    │        ├─────┤
│      │      │    │      │      │    │        │Activ│
└──────┴──────┘    └──────┴──────┘    └────────┴─────┘

dashboard               ralph                ralph-full
┌───────────────┬──────┐ ┌──────────┬────────┐ ┌────────┬────────┐
│               │Sess- │ │          │cctmux- │ │ Claude │cctmux- │
│ cctmux-       │ion   │ │          │ralph   │ │  50% * │ralph   │
│ activity      ├──────┤ │  Shell   │  40%   │ ├────────┤  ~77%h │
│   70%         │Shell │ │  60% *   │        │ │cctmux- ├────────┤
│               │  *   │ │          │        │ │git     │cctmux- │
└───────────────┴──────┘ └──────────┴────────┘ │  ~88%h │tasks   │
                                               └────────┴────────┘

git-mon
┌──────────┬────────┐
│          │cctmux- │
│ Claude   │git     │
│  60%     │  40%   │
│          │        │
└──────────┴────────┘
         * = focused pane
```

### Layout Implementation

Each layout function follows a consistent pattern for reliable pane targeting:

1. Captures the main pane ID before any splits using `tmux display-message -p "#{pane_id}"`
2. Splits panes using `tmux split-window` with `-d` (keep focus on original pane) and `-P -F "#{pane_id}"` (capture new pane ID)
3. Sends commands to new panes using captured pane IDs (e.g., `%15`) rather than positional indices
4. Returns focus to the main pane using the captured main pane ID

Pane IDs (`%N` format) are used instead of positional indices (`session:window.N`) because tmux pane indices do not always start at zero and can shift after splits. In `dry_run=True` mode, positional indices are used as fallback placeholders since no actual panes exist.

## Team Mode

Team mode launches N Claude Code instances in a single tmux session, each with its own role and system prompt.

### Session Creation

`create_team_session()` in `tmux_manager.py`:
1. Creates a new tmux session named after the team (or project)
2. Writes per-agent system prompt files to `$PROJECT/.cctmux/prompts/` (ensures `.cctmux/` is gitignored)
3. Calls `compute_team_layout()` to determine pane split dimensions based on the chosen strategy (`grid`, `columns`, or `rows`)
4. Splits the session window into N panes using the computed dimensions
5. For each pane, sets environment variables and sends the `claude` command with role-specific flags

### Layout Computation

`compute_team_layout()` in `layouts.py` accepts the agent count and layout strategy:
- **grid** — arranges panes in a balanced grid (e.g., 2x2 for 4 agents)
- **columns** — all panes side-by-side in equal-width columns
- **rows** — all panes stacked vertically

### Per-Pane Environment

Each agent pane receives:
- `CC2CC_SESSION_ID` — unique per pane (prevents session file races between agents)
- `CLAUDE_CODE_TASK_LIST_ID` — shared across all panes when `shared_task_list` is enabled
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` — set to `1` when `agent_teams` is enabled
- `CCTMUX_SESSION` and `CCTMUX_PROJECT_DIR` — standard cctmux env vars

### cc2cc Integration

Each agent is launched with `--append-system-prompt-file` pointing to a generated prompt file containing the role instructions, and `--name` set to the role name. Team agents also receive `--dangerously-skip-permissions` for autonomous operation and `--dangerously-load-development-channels` for cc2cc communication. All agents auto-subscribe to the project's cc2cc topic on connect, enabling inter-agent communication through the cc2cc hub.

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Command documentation
- [Configuration](CONFIGURATION.md) - Configuration options
- [Layouts](LAYOUTS.md) - Layout types and customization
- [Skill Guide](SKILL_GUIDE.md) - Using the cc-tmux skill with Claude
- [Quick Start](QUICKSTART.md) - Getting started guide
