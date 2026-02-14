# Configuration Reference

Complete reference for cctmux configuration options, presets, and customization.

## Table of Contents

- [Overview](#overview)
- [Configuration File](#configuration-file)
- [Project Configuration](#project-configuration)
- [Configuration Options](#configuration-options)
- [Custom Layouts](#custom-layouts)
- [Monitor Configurations](#monitor-configurations)
- [Presets](#presets)
- [CLI Overrides](#cli-overrides)
- [Environment Variables](#environment-variables)
- [Related Documentation](#related-documentation)

## Overview

cctmux uses layered YAML configuration files with deep merging for persistent settings. Configuration values can be overridden at the project level and via CLI flags, with presets providing quick access to common configurations.

```mermaid
graph LR
    Defaults[Default Values]
    UserConfig[User Config]
    ProjectConfig[Project Config]
    LocalConfig[Local Config]
    Presets[Presets]
    CLI[CLI Flags]
    Effective[Effective Config]

    Defaults --> UserConfig
    UserConfig --> ProjectConfig
    ProjectConfig --> LocalConfig
    LocalConfig --> Presets
    Presets --> CLI
    CLI --> Effective

    style Defaults fill:#37474f,stroke:#78909c,stroke-width:2px,color:#ffffff
    style UserConfig fill:#0d47a1,stroke:#2196f3,stroke-width:2px,color:#ffffff
    style ProjectConfig fill:#006064,stroke:#00acc1,stroke-width:2px,color:#ffffff
    style LocalConfig fill:#004d40,stroke:#00897b,stroke-width:2px,color:#ffffff
    style Presets fill:#1b5e20,stroke:#4caf50,stroke-width:2px,color:#ffffff
    style CLI fill:#e65100,stroke:#ff9800,stroke-width:3px,color:#ffffff
    style Effective fill:#4a148c,stroke:#9c27b0,stroke-width:2px,color:#ffffff
```

**Priority Order** (highest to lowest):
1. CLI flags
2. Preset configuration (if `--preset` specified)
3. Project local config (`.cctmux.yaml.local`)
4. Project config (`.cctmux.yaml`)
5. User configuration file
6. Default values

## Configuration File

### Location

The user configuration file is located at:

```
~/.config/cctmux/config.yaml
```

### Creating the Config File

Create a default configuration file:

```bash
cctmux init-config
```

### Viewing Current Configuration

Display the effective configuration:

```bash
cctmux --dump-config
```

### Validating Configuration

Validate all config files (user, project, local) and display any warnings:

```bash
cctmux config validate
```

Use strict mode to exit with an error on config warnings:

```bash
cctmux --strict
```

In non-strict mode (default), invalid config values produce warnings and fall back to defaults.

### Example Configuration

```yaml
# Default layout for new sessions
default_layout: default

# Enable tmux status bar
status_bar_enabled: false

# Maximum history entries to keep
max_history_entries: 50

# Default arguments for claude command
default_claude_args: null

# Set CLAUDE_CODE_TASK_LIST_ID environment variable
task_list_id: false

# Skip user config when set in project config
ignore_parent_configs: false

# Session monitor settings
session_monitor:
  show_thinking: true
  show_results: true
  show_progress: true
  show_system: false
  show_snapshots: false
  show_cwd: false
  show_threading: false
  show_stop_reasons: true
  show_turn_durations: true
  show_hook_errors: true
  show_service_tier: false
  show_sidechain: true
  max_events: 50

# Task monitor settings
task_monitor:
  show_owner: true
  show_metadata: false
  show_description: true
  show_graph: true
  show_table: true
  show_acceptance: true
  show_work_log: false
  max_tasks: 100

# Activity monitor settings
activity_monitor:
  default_days: 7
  show_heatmap: true
  show_cost: true
  show_tool_usage: true
  show_model_usage: true

# Agent monitor settings
agent_monitor:
  inactive_timeout: 300.0  # seconds; 0 to disable

# Git monitor settings
git_monitor:
  show_log: true
  show_diff: true
  show_status: true
  max_commits: 10
  poll_interval: 2.0
  fetch_enabled: false    # Periodically fetch from remote to check for new commits
  fetch_interval: 60.0    # How often to fetch (seconds)

# Ralph monitor settings
ralph_monitor:
  show_table: true
  show_timeline: true
  show_prompt: false
  show_task_progress: true
  max_iterations_visible: 20

# Custom layouts
custom_layouts:
  - name: dev-monitor
    description: "Task monitor + git monitor side by side"
    splits:
      - direction: h
        size: 50
        command: "cctmux-tasks -g"
      - direction: v
        size: 50
        target: last
        command: "cctmux-git"
```

## Project Configuration

In addition to the user config, cctmux supports per-project configuration files that are deep-merged on top of the user config.

### Project Config Files

| File | Location | Purpose |
|------|----------|---------|
| `.cctmux.yaml` | Project root | Shared team settings (commit to repo) |
| `.cctmux.yaml.local` | Project root | Personal overrides (gitignored) |

### Loading Order

1. **User config** (`~/.config/cctmux/config.yaml`) — base settings
2. **Project config** (`.cctmux.yaml`) — team/shared overrides
3. **Project local config** (`.cctmux.yaml.local`) — personal overrides

Last value wins via deep merge. Partial nested objects only override the fields they specify — sibling fields are preserved from parent configs.

### Deep Merge Behavior

When a project config overrides a nested section, only the specified fields change:

```yaml
# User config (~/.config/cctmux/config.yaml)
git_monitor:
  show_log: true
  show_diff: true
  max_commits: 10
  fetch_enabled: false

# Project config (.cctmux.yaml)
git_monitor:
  fetch_enabled: true    # Only this field changes

# Effective config
git_monitor:
  show_log: true         # Preserved from user config
  show_diff: true        # Preserved from user config
  max_commits: 10        # Preserved from user config
  fetch_enabled: true    # Overridden by project config
```

### Ignoring Parent Configs

Set `ignore_parent_configs: true` in a project config to skip the user config entirely. Only project configs and defaults are used:

```yaml
# .cctmux.yaml
ignore_parent_configs: true
default_layout: cc-mon
git_monitor:
  fetch_enabled: true
```

This is useful when a project requires a specific, self-contained configuration that should not be affected by individual user settings. The flag can be set in either `.cctmux.yaml` or `.cctmux.yaml.local`.

### Example Project Config

```yaml
# .cctmux.yaml (committed to repo)
default_layout: cc-mon
default_claude_args: "--model sonnet"
task_list_id: true

git_monitor:
  fetch_enabled: true
  fetch_interval: 30.0
```

```yaml
# .cctmux.yaml.local (personal, gitignored)
default_claude_args: "--model opus"
git_monitor:
  max_commits: 20
```

## Configuration Options

### Main Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_layout` | string | `default` | Layout for new sessions |
| `status_bar_enabled` | boolean | `false` | Enable tmux status bar |
| `max_history_entries` | integer | `50` | Max session history entries |
| `default_claude_args` | string | `null` | Default claude CLI arguments |
| `task_list_id` | boolean | `false` | Set task list ID env var |
| `ignore_parent_configs` | boolean | `false` | Skip user config (project configs only) |
| `custom_layouts` | list | `[]` | Custom layout definitions |

### Layout Options

| Value | Description |
|-------|-------------|
| `default` | No initial split |
| `editor` | 70/30 horizontal split |
| `monitor` | 80/20 vertical split |
| `triple` | Main + 2 side panes |
| `cc-mon` | Claude + session + tasks monitors |
| `full-monitor` | Claude + session + tasks + activity monitors |
| `dashboard` | Large activity dashboard with session sidebar |
| `ralph` | Shell + ralph monitor side-by-side |
| `ralph-full` | Shell + ralph monitor + task monitor |
| `git-mon` | Claude + git status monitor |

### Custom Layouts

Custom layouts extend the built-in layout options with user-defined pane arrangements. They are stored in the `custom_layouts` list in the config file.

#### Custom Layout Schema

Each custom layout consists of a name, optional description, and a list of split operations:

```yaml
custom_layouts:
  - name: my-monitor
    description: "Session monitor and git side by side"
    focus_main: true
    splits:
      - direction: h
        size: 50
        command: "cctmux-session"
        name: session
      - direction: v
        size: 50
        command: "cctmux-git"
        target: session
        name: git
```

#### Split Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `direction` | string | (required) | Split direction: `h` (horizontal/side-by-side) or `v` (vertical/stacked) |
| `size` | integer | (required) | Percentage for the new pane (1-90) |
| `command` | string | `""` | Command to run in the new pane |
| `name` | string | `""` | Name for referencing in later splits |
| `target` | string | `"main"` | Pane to split: `"main"`, `"last"`, or a named pane |
| `focus` | boolean | `false` | Focus this pane after layout is applied |

#### Layout-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | (required) | Lowercase alphanumeric with hyphens; must not conflict with built-in layout names |
| `description` | string | `""` | Human-readable description |
| `splits` | list | `[]` | List of split operations |
| `focus_main` | boolean | `true` | Focus main pane at end (unless a split has `focus: true`) |

#### Managing Custom Layouts via CLI

```bash
# List all layouts (built-in + custom)
cctmux layout list

# Show layout details
cctmux layout show my-monitor

# Create from built-in template
cctmux layout add my-layout --from cc-mon

# Create from scratch (opens $EDITOR)
cctmux layout add my-layout

# Edit existing custom layout
cctmux layout edit my-layout

# Remove custom layout
cctmux layout remove my-layout

# Use a custom layout
cctmux -l my-layout
```

## Monitor Configurations

### Session Monitor (`session_monitor`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_thinking` | boolean | `true` | Show thinking blocks |
| `show_results` | boolean | `true` | Show tool results |
| `show_progress` | boolean | `true` | Show progress events |
| `show_system` | boolean | `false` | Show system messages |
| `show_snapshots` | boolean | `false` | Show file snapshots |
| `show_cwd` | boolean | `false` | Show working directory |
| `show_threading` | boolean | `false` | Show message threading |
| `show_stop_reasons` | boolean | `true` | Show stop reason stats |
| `show_turn_durations` | boolean | `true` | Show turn duration stats |
| `show_hook_errors` | boolean | `true` | Show hook error info |
| `show_service_tier` | boolean | `false` | Show API service tier |
| `show_sidechain` | boolean | `true` | Show sidechain count |
| `max_events` | integer | `50` | Max events to display |

### Task Monitor (`task_monitor`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_owner` | boolean | `true` | Show owner column |
| `show_metadata` | boolean | `false` | Show custom metadata |
| `show_description` | boolean | `true` | Show task descriptions |
| `show_graph` | boolean | `true` | Show dependency graph |
| `show_table` | boolean | `true` | Show task table |
| `show_acceptance` | boolean | `true` | Show acceptance criteria |
| `show_work_log` | boolean | `false` | Show work log entries |
| `max_tasks` | integer | `100` | Max tasks to display |

### Activity Monitor (`activity_monitor`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_days` | integer | `7` | Days to show in heatmap |
| `show_heatmap` | boolean | `true` | Show activity heatmap |
| `show_cost` | boolean | `true` | Show cost estimates |
| `show_tool_usage` | boolean | `true` | Show tool usage stats |
| `show_model_usage` | boolean | `true` | Show model usage table |

### Agent Monitor (`agent_monitor`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `inactive_timeout` | float | `300.0` | Seconds before hiding inactive agents (0 to disable) |

### Git Monitor (`git_monitor`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_log` | boolean | `true` | Show recent commits panel |
| `show_diff` | boolean | `true` | Show diff stats panel |
| `show_status` | boolean | `true` | Show file status panel |
| `max_commits` | integer | `10` | Maximum recent commits to display |
| `poll_interval` | float | `2.0` | Polling interval in seconds |
| `fetch_enabled` | boolean | `false` | Periodically fetch from remote |
| `fetch_interval` | float | `60.0` | How often to fetch from remote (seconds) |

### Ralph Monitor (`ralph_monitor`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_table` | boolean | `true` | Show iteration data table |
| `show_timeline` | boolean | `true` | Show iteration timeline |
| `show_prompt` | boolean | `false` | Show iteration prompts |
| `show_task_progress` | boolean | `true` | Show task completion progress |
| `max_iterations_visible` | integer | `20` | Max iterations to display |

## Presets

Presets provide quick access to common configurations for all monitors.

### Available Presets

| Preset | Description |
|--------|-------------|
| `default` | Standard configuration |
| `minimal` | Essential information only |
| `verbose` | All information displayed |
| `debug` | Maximum detail for troubleshooting |

### Using Presets

```bash
# Task monitor with verbose preset
cctmux-tasks --preset verbose

# Session monitor with minimal preset
cctmux-session --preset minimal

# Activity with debug preset
cctmux-activity --preset debug

# Git monitor with verbose preset
cctmux-git --preset verbose

# Ralph monitor with verbose preset
cctmux-ralph --preset verbose
```

### Preset Details

#### Minimal Preset

Reduces visual noise for focused work:

**Session Monitor:**
- Hide thinking, results, progress, sidechain
- Hide stop reasons, turn durations, hook errors
- Max 20 events

**Task Monitor:**
- Hide owner, description, metadata, acceptance criteria
- Show graph only (no table)
- Max 30 tasks

**Activity Monitor:**
- Hide heatmap
- Hide tool usage

**Git Monitor:**
- Hide log and diff panels
- Max 5 commits
- Fetch disabled

**Ralph Monitor:**
- Hide timeline
- Hide prompt

**Agent Monitor:**
- Uses default settings

#### Verbose Preset

Shows comprehensive information:

**Session Monitor:**
- Show all event types including system
- Show cwd, stop reasons, turn durations, hook errors
- Show service tier, sidechain
- Max 100 events

**Task Monitor:**
- Show all columns including metadata, acceptance criteria, work logs
- Max 200 tasks

**Activity Monitor:**
- 14-day heatmap
- Show all usage tables

**Git Monitor:**
- All panels visible
- Max 20 commits
- Fetch enabled (60s interval)

**Ralph Monitor:**
- Show table, timeline, prompt, task progress

**Agent Monitor:**
- Uses default settings

#### Debug Preset

Maximum detail for troubleshooting:

**Session Monitor:**
- Show everything including snapshots and threading
- Show service tier, sidechain, all statistics
- Max 200 events

**Task Monitor:**
- Show all data including metadata, acceptance criteria, work logs
- Max 500 tasks

**Activity Monitor:**
- 30-day heatmap
- All statistics visible

**Git Monitor:**
- All panels visible
- Max 30 commits
- Fetch enabled (30s interval)

**Ralph Monitor:**
- Show table, timeline, prompt, task progress
- Max 50 iterations visible

**Agent Monitor:**
- Uses default settings

## CLI Overrides

CLI flags always take precedence over configuration file and presets.

### Override Examples

```bash
# Override max events from config
cctmux-session -m 100

# Override preset value
cctmux-tasks --preset minimal --show-metadata

# Override config default layout
cctmux -l cc-mon

# Override poll interval
cctmux-session -i 0.25
```

### Combining Presets and Overrides

When using a preset with CLI flags, the preset is applied first, then CLI flags override specific values:

```bash
# Start with minimal preset, but show thinking
cctmux-session --preset minimal --show-thinking
# Result: minimal config but with thinking blocks visible
```

## Environment Variables

cctmux sets environment variables in tmux sessions:

| Variable | Description |
|----------|-------------|
| `CCTMUX_SESSION` | Current tmux session name |
| `CCTMUX_PROJECT_DIR` | Project directory path |
| `CLAUDE_CODE_TASK_LIST_ID` | Session name (if `--task-list-id` enabled) |

### Checking Environment Variables

Inside a cctmux session:

```bash
echo $CCTMUX_SESSION
echo $CCTMUX_PROJECT_DIR
```

### Task List ID

Enable automatic task list ID assignment:

```yaml
# In config.yaml
task_list_id: true
```

Or via CLI:

```bash
cctmux -T
```

This sets `CLAUDE_CODE_TASK_LIST_ID` to the session name, allowing tasks to be scoped to the session.

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Command documentation
- [Architecture](ARCHITECTURE.md) - System design
- [Quick Start](QUICKSTART.md) - Getting started guide
- [Layouts](LAYOUTS.md) - Layout descriptions and diagrams
