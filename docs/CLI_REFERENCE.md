# CLI Reference

Complete reference for all cctmux command-line tools. Each tool includes all available options, examples, and common usage patterns.

## Table of Contents

- [Overview](#overview)
- [cctmux](#cctmux)
- [cctmux-tasks](#cctmux-tasks)
- [cctmux-session](#cctmux-session)
- [cctmux-agents](#cctmux-agents)
- [cctmux-activity](#cctmux-activity)
- [cctmux-git](#cctmux-git)
- [cctmux-ralph](#cctmux-ralph)
- [Common Patterns](#common-patterns)
- [Related Documentation](#related-documentation)

## Overview

cctmux provides seven CLI commands:

| Command | Purpose |
|---------|---------|
| `cctmux` | Launch Claude Code in a tmux session |
| `cctmux-tasks` | Monitor Claude Code tasks |
| `cctmux-session` | Monitor session events |
| `cctmux-agents` | Monitor subagent activity |
| `cctmux-activity` | Display usage statistics |
| `cctmux-git` | Monitor git repository status |
| `cctmux-ralph` | Ralph Loop automation (start, monitor, cancel, status, init) |

All commands support `--version` and `--help` flags.

## cctmux

Launch Claude Code inside tmux with session management. Supports layered configuration from user config, `.cctmux.yaml` (project), and `.cctmux.yaml.local` (personal). See [Configuration](CONFIGURATION.md#project-configuration) for details.

### Synopsis

```bash
cctmux [OPTIONS] [COMMAND]
```

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--layout` | `-l` | Tmux layout to use | `default` |
| `--recent` | `-R` | Select from recent sessions using fzf | `false` |
| `--resume` | `-r` | Append `--resume` to claude invocation to continue last conversation | `false` |
| `--status-bar` | `-s` | Enable status bar with git/project info | `false` |
| `--debug` | `-D` | Enable debug output | `false` |
| `--verbose` | `-v` | Increase verbosity (stackable) | `0` |
| `--continue` | `-c` | Append `--continue` to claude invocation to continue most recent conversation | `false` |
| `--dry-run` | `-n` | Preview commands without executing | `false` |
| `--config` | `-C` | Config file path | `~/.config/cctmux/config.yaml` |
| `--dump-config` | | Output current configuration | `false` |
| `--strict` | | Validate config strictly; exit on warnings | `false` |
| `--claude-args` | `-a` | Arguments to pass to claude command | `None` |
| `--yolo` | `-y` | Append `--dangerously-skip-permissions` to claude invocation | `false` |
| `--task-list-id` | `-T` | Set `CLAUDE_CODE_TASK_LIST_ID` to session name | `false` |
| `--agent-teams` | `-A` | Enable experimental agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) | `false` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Layout Types

| Layout | Description |
|--------|-------------|
| `default` | No initial split, create panes on demand |
| `editor` | 70/30 horizontal split (main + side pane) |
| `monitor` | 80/20 vertical split (main + bottom bar) |
| `triple` | Main + 2 side panes (50/50 horizontal, right split vertically) |
| `cc-mon` | Claude + session monitor + task monitor |
| `full-monitor` | Claude + session + tasks + activity |
| `dashboard` | Large activity dashboard with session sidebar |
| `ralph` | Shell + ralph monitor side-by-side (60/40) |
| `ralph-full` | Shell + ralph monitor + task monitor |
| `git-mon` | Claude (60%) + git status monitor (40%) |

In addition to the predefined layouts, Claude can save and recall custom pane arrangements stored in the config file. See [Saved Layouts](LAYOUTS.md#saved-layouts) for details.

Custom layouts can also be defined in the config file or via `cctmux layout add`. See [Custom Layouts](LAYOUTS.md#custom-layouts) for details.

### Subcommands

| Command | Description |
|---------|-------------|
| `install-skill` | Install the cc-tmux skill to `~/.claude/skills/` |
| `init-config` | Create default configuration file |
| `config validate` | Validate all config files and display warnings |
| `config show` | Display effective merged configuration |
| `layout list` | List all layouts (built-in and custom) |
| `layout show <name>` | Show layout details or YAML representation |
| `layout add <name>` | Create a new custom layout (opens in $EDITOR) |
| `layout remove <name>` | Delete a custom layout |
| `layout edit <name>` | Edit a custom layout (opens in $EDITOR) |

### Examples

```bash
# Start session for current project
cctmux

# Start with editor layout
cctmux -l editor

# Start with monitoring layout
cctmux -l cc-mon

# Start with git monitor layout
cctmux -l git-mon

# Start with Ralph Loop layout
cctmux -l ralph

# Pass arguments to claude
cctmux -a "--model sonnet"

# Start with dangerously-skip-permissions
cctmux -y

# Continue most recent conversation
cctmux -c

# Resume last conversation
cctmux -r

# Select from recent sessions
cctmux -R

# Preview what would happen
cctmux -n -v

# Enable task list ID environment variable
cctmux -T

# Show current config
cctmux --dump-config

# Validate config files
cctmux config validate

# Show effective config
cctmux config show

# List all layouts
cctmux layout list

# Show details of a layout
cctmux layout show cc-mon

# Create custom layout from built-in template
cctmux layout add my-layout --from cc-mon

# Use a custom layout
cctmux -l my-layout

# Strict mode (exit on config warnings)
cctmux --strict
```

### Session Control Flags

Three shortcut flags modify how Claude Code is invoked within the tmux session. Each appends a flag to the underlying `claude` command.

#### `--yolo` / `-y`

Appends `--dangerously-skip-permissions` to the Claude invocation, allowing Claude to execute tools without asking for confirmation. This is useful for unattended or automated workflows where manual approval is not practical.

```bash
# Start with permission skipping
cctmux -y

# Equivalent to
cctmux -a "--dangerously-skip-permissions"
```

#### `--resume` / `-r`

Appends `--resume` to the Claude invocation, which continues the last conversation in the session. Use this to pick up where a previous session left off.

```bash
# Resume the last conversation
cctmux -r

# Equivalent to
cctmux -a "--resume"
```

#### `--continue` / `-c`

Appends `--continue` to the Claude invocation, which continues the most recent conversation. This is similar to `--resume` but specifically targets the most recent conversation.

```bash
# Continue the most recent conversation
cctmux -c

# Equivalent to
cctmux -a "--continue"
```

#### Combining Flags

These flags compose with each other and with `--claude-args`. When multiple flags are used, they are appended in order. If the flag is already present in `--claude-args`, it is not duplicated.

```bash
# Yolo mode with resume
cctmux -y -r

# Continue with a specific model
cctmux -c -a "--model sonnet"

# All three (yolo + continue + custom args)
cctmux -y -c -a "--model opus"
```

## cctmux-tasks

Monitor Claude Code tasks in real-time with ASCII dependency visualization.

### Synopsis

```bash
cctmux-tasks [OPTIONS] [SESSION_OR_PATH]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `SESSION_OR_PATH` | Session ID, partial ID, or path to task folder |

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Project directory to find sessions for | Current directory |
| `--interval` | `-i` | Poll interval in seconds | `1.0` |
| `--max-tasks` | `-m` | Maximum tasks to display | Auto-detect |
| `--no-table` | `-g` | Show only dependency graph | `false` |
| `--table-only` | `-t` | Show only table, no graph | `false` |
| `--no-owner` | | Hide task owner column | `false` |
| `--show-metadata` | | Show custom task metadata | `false` |
| `--no-description` | | Hide task descriptions | `false` |
| `--show-acceptance` | | Show acceptance criteria completion | `false` |
| `--show-work-log` | | Show work log entries | `false` |
| `--preset` | | Use preset configuration (minimal, verbose, debug) | `None` |
| `--list` | `-l` | List available sessions and exit | `false` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Presets

| Preset | Description |
|--------|-------------|
| `minimal` | Graph only, no table/owner/description/acceptance; max 30 tasks |
| `verbose` | All columns visible, metadata and work logs shown; max 200 tasks |
| `debug` | Maximum detail, all columns and logs; max 500 tasks |

### Examples

```bash
# Auto-detect from current project
cctmux-tasks

# Monitor specific session
cctmux-tasks abc123

# Monitor task folder directly
cctmux-tasks /path/to/tasks

# List available sessions
cctmux-tasks --list

# Show only dependency graph
cctmux-tasks -g

# Show acceptance criteria
cctmux-tasks --show-acceptance

# Use verbose preset
cctmux-tasks --preset verbose

# Fast polling
cctmux-tasks -i 0.5
```

### Display Features

- **Dependency Graph**: ASCII tree showing task relationships
- **Status Indicators**: `○` pending, `◐` in progress, `●` completed
- **Progress Stats**: Total tasks, status counts, completion percentage
- **Acceptance Criteria**: `[completed/total pct%]` when present in metadata

## cctmux-session

Monitor Claude Code session stream with live statistics.

### Synopsis

```bash
cctmux-session [OPTIONS] [SESSION_OR_PATH]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `SESSION_OR_PATH` | Session ID, partial ID, or path to JSONL file |

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Project directory to find sessions for | Current directory |
| `--interval` | `-i` | Poll interval in seconds | `0.5` |
| `--max-events` | `-m` | Maximum events to display | Auto-detect |
| `--no-thinking` | | Hide thinking blocks | `false` |
| `--no-results` | | Hide tool results | `false` |
| `--no-progress` | | Hide progress/hook events | `false` |
| `--show-system` | | Show system messages | `false` |
| `--show-snapshots` | | Show file snapshots | `false` |
| `--show-cwd` | | Show working directory changes | `false` |
| `--show-threading` | | Show message parent-child relationships | `false` |
| `--no-stop-reasons` | | Hide stop reason statistics | `false` |
| `--no-turn-durations` | | Hide turn duration statistics | `false` |
| `--no-hook-errors` | | Hide hook error information | `false` |
| `--show-service-tier` | | Show API service tier | `false` |
| `--no-sidechain` | | Hide sidechain message count | `false` |
| `--preset` | | Use preset configuration (minimal, verbose, debug) | `None` |
| `--list` | `-l` | List available sessions and exit | `false` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Presets

| Preset | Description |
|--------|-------------|
| `minimal` | Hide thinking, results, progress, stop reasons, turn durations, hook errors, sidechain; max 20 events |
| `verbose` | Show system messages, cwd, service tier, all statistics; max 100 events |
| `debug` | Show everything including snapshots, threading, service tier; max 200 events |

### Examples

```bash
# Auto-detect from current project
cctmux-session

# Monitor specific session
cctmux-session abc123

# Monitor JSONL file directly
cctmux-session /path/to/session.jsonl

# List available sessions
cctmux-session --list

# Hide thinking blocks
cctmux-session --no-thinking

# Show working directory changes
cctmux-session --show-cwd

# Show message threading
cctmux-session --show-threading

# Use debug preset
cctmux-session --preset debug
```

### Display Features

- **Stats Panel**: Session ID, model, duration, tokens, cost estimate
- **Events Panel**: User prompts, thinking, tool calls, results, responses
- **Status Symbols**: `●` user, `◐` thinking, `▶` tool call, `◀` result, `■` assistant
- **Tool Histogram**: Frequency of tool usage

## cctmux-agents

Monitor Claude Code subagent activity with live updates.

### Synopsis

```bash
cctmux-agents [OPTIONS] [SESSION_OR_PATH]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `SESSION_OR_PATH` | Session ID, partial ID, or project path |

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Project directory to find sessions for | Current directory |
| `--interval` | `-i` | Poll interval in seconds | `1.0` |
| `--inactive-timeout` | `-t` | Hide agents inactive for this many seconds (0 to show all) | `300` |
| `--no-activity` | `-a` | Hide the activity panel | `false` |
| `--list` | `-l` | List available subagents and exit | `false` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Examples

```bash
# Auto-detect from current project
cctmux-agents

# Monitor specific session
cctmux-agents abc123

# List available subagents
cctmux-agents --list

# Hide activity panel
cctmux-agents --no-activity

# Show all agents (no inactive timeout)
cctmux-agents -t 0

# Hide agents inactive for 10+ minutes
cctmux-agents -t 600

# Fast polling
cctmux-agents -i 0.5
```

### Display Features

- **Stats Panel**: Total subagents, active/completed counts, aggregate tokens
- **Agent Table**: Name, model, duration, tokens, top tools, current activity
- **Activity Panel**: Recent activities across all agents with timestamps
- **Status Indicators**: `○` unknown, `◐` active, `●` completed

## cctmux-activity

Display Claude Code activity dashboard with usage statistics.

### Synopsis

```bash
cctmux-activity [OPTIONS]
```

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--days` | `-d` | Number of days to show in heatmap | `14` |
| `--no-heatmap` | | Hide activity heatmap | `false` |
| `--no-cost` | | Hide cost estimates | `false` |
| `--no-model-usage` | | Hide model usage table | `false` |
| `--show-hourly` | `-H` | Show hourly activity distribution | `false` |
| `--preset` | | Use preset configuration (minimal, verbose, debug) | `None` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Presets

| Preset | Description |
|--------|-------------|
| `minimal` | Hide heatmap and tool usage, essential stats only |
| `verbose` | 14 days, all panels visible |
| `debug` | 30 days, all panels visible |

### Examples

```bash
# Show default dashboard
cctmux-activity

# Show 7-day heatmap
cctmux-activity --days 7

# Include hourly distribution
cctmux-activity --show-hourly

# Hide cost estimates
cctmux-activity --no-cost

# Use minimal preset
cctmux-activity --preset minimal
```

### Display Features

- **Summary Panel**: Total sessions, messages, tokens, estimated cost
- **Activity Heatmap**: ASCII visualization of daily activity
- **Model Usage Table**: Token breakdown by model with cost estimates
- **Hourly Distribution**: Bar chart of activity by hour (optional)

## cctmux-git

Monitor git repository status with live updates. Shows branch info, file statuses, recent commits, and diff statistics.

### Synopsis

```bash
cctmux-git [OPTIONS]
```

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Git repository directory | Current directory |
| `--interval` | `-i` | Poll interval in seconds | `2.0` |
| `--max-commits` | `-m` | Maximum recent commits to show | `10` |
| `--no-log` | | Hide recent commits panel | `false` |
| `--no-diff` | | Hide diff stats panel | `false` |
| `--no-status` | | Hide file status panel | `false` |
| `--fetch` | `-f` | Enable periodic git fetch to check for remote commits | `false` |
| `--no-fetch` | | Disable periodic git fetch (overrides config/preset) | `false` |
| `--fetch-interval` | `-F` | How often to fetch from remote (seconds) | `60.0` |
| `--preset` | | Use preset configuration (minimal, verbose, debug) | `None` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Presets

| Preset | Description |
|--------|-------------|
| `minimal` | Hide log and diff panels, show only branch and status; max 5 commits; fetch disabled |
| `verbose` | All panels visible; max 20 commits; fetch enabled (60s interval) |
| `debug` | All panels visible; max 30 commits; fetch enabled (30s interval) |

### Examples

```bash
# Monitor current directory
cctmux-git

# Monitor a specific repository
cctmux-git -p /path/to/repo

# Hide recent commits panel
cctmux-git --no-log

# Hide diff stats panel
cctmux-git --no-diff

# Show 20 recent commits
cctmux-git -m 20

# Enable remote commit checking
cctmux-git --fetch

# Fetch every 30 seconds
cctmux-git --fetch -F 30

# Use minimal preset
cctmux-git --preset minimal

# Fast polling (every 0.5 seconds)
cctmux-git -i 0.5
```

### Display Features

- **Branch Panel**: Branch name, upstream tracking, ahead/behind counts, stash count, last commit
- **Files Panel**: Changed files with status indicators (staged, unstaged, untracked, renamed)
- **Remote Commits Panel**: Commits on the remote not yet in the local branch, with last fetch timestamp (shown when `--fetch` is enabled)
- **Recent Commits Panel**: Commit hash, message, author, and relative timestamp
- **Diff Stats Panel**: Per-file insertion/deletion counts with visual bars

## cctmux-ralph

Ralph Loop: automated iterative Claude Code execution. Reads a project markdown file, runs Claude iteratively, tracks task completion and promises, and reports progress.

### Synopsis

```bash
cctmux-ralph [OPTIONS] [COMMAND]
```

When run without a subcommand, displays a real-time dashboard monitoring an active Ralph Loop.

### Monitor Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Project directory to monitor | Current directory |
| `--interval` | `-i` | Poll interval in seconds | `1.0` |
| `--preset` | | Use preset configuration (minimal, verbose, debug) | `None` |
| `--version` | | Show version | |
| `--help` | | Show help | |

### Subcommands

#### `start` - Start a Ralph Loop

Run a Ralph Loop from a project markdown file. Runs in the foreground.

```bash
cctmux-ralph start [OPTIONS] PROJECT_FILE
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `PROJECT_FILE` | | Path to the Ralph project markdown file (required argument) | |
| `--max-iterations` | `-m` | Maximum iterations (0 = unlimited) | `0` |
| `--completion-promise` | `-c` | Text to match in `<promise>` tags | `""` |
| `--permission-mode` | | Claude permission mode | `acceptEdits` |
| `--model` | | Claude model to use | `None` |
| `--max-budget` | | Max budget per iteration in USD | `None` |
| `--project` | `-p` | Project root directory | Current directory |

#### `init` - Create a Template Project File

Generate a template Ralph project markdown file.

```bash
cctmux-ralph init [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output file path | `ralph-project.md` |
| `--name` | `-n` | Project name for the template | `""` |

#### `cancel` - Cancel an Active Ralph Loop

```bash
cctmux-ralph cancel [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Project root directory | Current directory |

#### `status` - Show Ralph Loop Status

Display the current Ralph Loop status as a one-shot output (not live).

```bash
cctmux-ralph status [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--project` | `-p` | Project root directory | Current directory |

### Presets

| Preset | Description |
|--------|-------------|
| `minimal` | Hide timeline and prompt, show table and task progress |
| `verbose` | All panels visible including prompt |
| `debug` | All panels visible, up to 50 iterations shown |

### Examples

```bash
# Create a new Ralph project template
cctmux-ralph init
cctmux-ralph init -o my-project.md -n "My Project"

# Start a Ralph Loop
cctmux-ralph start ralph-project.md
cctmux-ralph start ralph-project.md -m 5 --model sonnet
cctmux-ralph start ralph-project.md --max-budget 1.50

# Monitor a running Ralph Loop
cctmux-ralph
cctmux-ralph -p /path/to/project
cctmux-ralph --preset verbose

# Check status (one-shot)
cctmux-ralph status

# Cancel an active loop
cctmux-ralph cancel
```

### Display Features

- **Status Panel**: Current iteration, status (active/completed/cancelled/error), task counts
- **Iteration Table**: Per-iteration token usage, cost, duration, task completion
- **Timeline**: Visual progress of iterations over time
- **Task Progress**: Checklist completion tracking
- **Prompt Preview**: Current iteration prompt (optional, shown with verbose/debug presets)

## Common Patterns

### Split Terminal Workflow

Run monitor in one pane, work in another:

```bash
# In left pane
cctmux

# In right pane (new terminal tab)
cctmux-session
```

### Integrated Monitoring

Start with built-in monitoring layout:

```bash
cctmux -l cc-mon
```

### Debug Session Issues

Use debug preset to see all events:

```bash
cctmux-session --preset debug
```

### Track Parallel Agents

Monitor subagent activity during complex tasks:

```bash
cctmux-agents
```

### Monitor Git Changes

Watch git repository status while Claude works:

```bash
cctmux -l git-mon
```

### Weekly Usage Review

Check activity statistics:

```bash
cctmux-activity --days 7
```

### Ralph Loop Workflow

Start a Ralph Loop with monitoring:

```bash
# Use the ralph layout for side-by-side monitoring
cctmux -l ralph

# In the left pane, start the loop
cctmux-ralph start ralph-project.md

# The right pane automatically shows the ralph monitor
```

## Related Documentation

- [Configuration](CONFIGURATION.md) - Configuration file reference
- [Layouts](LAYOUTS.md) - Detailed layout descriptions and diagrams
- [Architecture](ARCHITECTURE.md) - System design
- [Quick Start](QUICKSTART.md) - Getting started guide
