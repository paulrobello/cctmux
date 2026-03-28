# Quick Start Guide

Get started with cctmux in minutes. This guide covers installation, basic usage, and common workflows.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Monitoring Tools](#monitoring-tools)
- [Ralph Loop](#ralph-loop)
- [Layouts](#layouts)
- [Team Mode Quick Start](#team-mode-quick-start)
- [Next Steps](#next-steps)

## Prerequisites

**Required:**
- Python 3.14+
- tmux
- Claude Code CLI (`claude`)

**Optional:**
- fzf (for session selection with `--recent`)

Verify your environment:

```bash
# Check Python version
python --version

# Check tmux
tmux -V

# Check Claude Code
claude --version
```

## Installation

Install cctmux using uv (recommended), pip, or from source:

```bash
# Using uv (recommended)
uv tool install cctmux

# From GitHub
uv tool install git+https://github.com/paulrobello/cctmux.git

# Using pip
pip install cctmux

# From source
git clone https://github.com/paulrobello/cctmux.git
cd cctmux
uv sync
uv run cctmux --help
```

Verify installation:

```bash
cctmux --version
```

### Install the Skill (Optional)

Install the cc-tmux skill to enable Claude to manage tmux panes:

```bash
cctmux install-skill
```

This copies the skill to `~/.claude/skills/cc-tmux/`.

## Basic Usage

### Start a Session

Navigate to your project directory and run:

```bash
cd ~/my-project
cctmux
```

This creates a tmux session named after your project folder (e.g., `my-project`) and launches Claude Code inside it.

### Attach to Existing Session

If a session already exists for the project, cctmux attaches to it:

```bash
cctmux
# Output: Attaching to existing session: my-project
```

### Select from Recent Sessions

Use fzf to select from recent sessions:

```bash
cctmux --recent
```

### Preview Commands (Dry Run)

See what commands would be executed without running them:

```bash
cctmux --dry-run
```

## Monitoring Tools

cctmux provides six real-time monitoring tools to track Claude Code activity.

### Task Monitor

Watch task progress with dependency visualization:

```bash
cctmux-tasks
```

Features:
- ASCII dependency graph
- Status indicators (pending, in-progress, completed)
- Windowed virtual scrolling for large task lists
- Progress statistics
- Acceptance criteria and work log display
- Configurable presets (minimal, verbose, debug)

### Session Monitor

Track session events in real-time:

```bash
cctmux-session
```

Features:
- Tool calls and results
- Thinking blocks
- Token usage and cost estimates
- Tool usage histograms
- Stop reason and turn duration statistics
- Hook error tracking
- Sidechain message counts

### Subagent Monitor

Monitor subagent activity:

```bash
cctmux-agents
```

Features:
- Active and completed subagents
- Token usage per agent
- Current activity tracking
- Configurable inactive timeout (default 5 minutes)

### Git Monitor

Monitor git repository status in real-time:

```bash
cctmux-git
```

Features:
- Branch info with upstream tracking and ahead/behind counts
- File status display (staged, unstaged, untracked)
- Recent commits log with author and timestamps
- Diff statistics with visual bars

### Activity Dashboard

View usage statistics:

```bash
cctmux-activity
```

Features:
- Session and message totals
- Model usage breakdown
- Cost estimates
- Activity heatmap
- Hourly activity distribution (with `--show-hourly`)

## Ralph Loop

Ralph Loop provides automated iterative Claude Code execution with task tracking.

### Create a Project File

```bash
cctmux-ralph init
```

This creates a `ralph-project.md` template in the current directory.

### Start a Ralph Loop

```bash
cctmux-ralph start ralph-project.md
```

### Monitor a Running Loop

```bash
cctmux-ralph
```

### Check Status, Stop, or Cancel

```bash
cctmux-ralph status
cctmux-ralph stop    # Finish current iteration then exit
cctmux-ralph cancel  # Cancel immediately
```

## Layouts

Predefined layouts arrange panes for common workflows. Ten layouts are available:

| Layout | Description |
|--------|-------------|
| `default` | No initial splits (panes created on demand) |
| `editor` | 70/30 horizontal split (main + side pane) |
| `monitor` | 80/20 vertical split (main + bottom bar) |
| `triple` | Main pane with two side panes (50/50 right, split vertically) |
| `cc-mon` | Claude + session monitor + task monitor |
| `full-monitor` | Claude + session + tasks + activity monitors |
| `dashboard` | Large activity dashboard with session sidebar |
| `ralph` | Shell + ralph monitor side-by-side (60/40) |
| `ralph-full` | Claude + git monitor + ralph monitor + task monitor (2x2 grid) |
| `git-mon` | Claude (60%) + git status monitor (40%) |

### CC-Mon Layout

Claude + session monitor + task monitor (recommended for monitoring):

```bash
cctmux -l cc-mon
```

```
┌──────────────────┬──────────────────┐
│                  │ cctmux-session   │
│                  │      50%         │
│   Claude Code    ├──────────────────┤
│      50%         │ cctmux-tasks -g  │
│                  │      50%         │
│                  │                  │
└──────────────────┴──────────────────┘
```

### Full Monitor Layout

All monitoring tools visible:

```bash
cctmux -l full-monitor
```

```
┌──────────────────────┬──────────────┐
│                      │cctmux-session│
│                      │     30%      │
│                      ├──────────────┤
│     Claude Code      │cctmux-tasks  │
│        60%           │  -g  35%     │
│                      ├──────────────┤
│                      │cctmux-       │
│                      │activity 35%  │
└──────────────────────┴──────────────┘
```

### Dashboard Layout

Large activity dashboard with session sidebar:

```bash
cctmux -l dashboard
```

```
┌─────────────────────────┬───────────┐
│                         │ cctmux-   │
│                         │ session   │
│  cctmux-activity        │   50%     │
│  --show-hourly          ├───────────┤
│       70%               │  Shell    │
│                         │  50% *    │
│                         │           │
└─────────────────────────┴───────────┘
              * = focused pane
```

### Ralph Layout

Shell + ralph monitor for running and monitoring Ralph Loops:

```bash
cctmux -l ralph
```

```
┌──────────────┬─────────────┐
│              │             │
│    Shell     │ cctmux-     │
│    60%       │ ralph       │
│              │   40%       │
│              │             │
└──────────────┴─────────────┘
```

### Ralph Full Layout

Claude + git monitor + ralph monitor + task monitor (2x2 grid):

```bash
cctmux -l ralph-full
```

```
┌──────────────┬─────────────┐
│  CLAUDE      │ cctmux-     │
│   50%        │ ralph       │
│  ~12%h       │  ~77%h      │
├──────────────┤─────────────┤
│ cctmux-      │ cctmux-     │
│ git          │ tasks -g    │
│  ~88%h       │  ~23%h      │
└──────────────┴─────────────┘
```

### Git-Mon Layout

Claude Code + git status monitor:

```bash
cctmux -l git-mon
```

```
┌──────────────┬─────────────┐
│              │             │
│   Claude     │ cctmux-     │
│   60%        │ git         │
│              │   40%       │
│              │             │
└──────────────┴─────────────┘
```

## Team Mode Quick Start

Launch multiple Claude Code instances as a coordinated team.

**Prerequisites:** cc2cc hub running, cc2cc plugin installed in Claude Code.

### 1. Create a Team Config

```yaml
# team.yaml
team:
  name: my-team
  shared_task_list: true
  layout: grid
  agents:
    - role: architect
      prompt: |
        You lead the team. Create tasks, review work, coordinate via cc2cc.
    - role: implementer
      prompt: |
        Pick up tasks and implement them.
```

### 2. Launch the Team

```bash
cctmux team team.yaml
```

This creates a tmux session with one pane per agent. Each agent runs Claude Code with its role-specific prompt and communicates with other agents via cc2cc.

## Next Steps

- Read the [CLI Reference](CLI_REFERENCE.md) for all options
- Learn about [Configuration](CONFIGURATION.md) for customization
- Explore [Layouts](LAYOUTS.md) for all predefined layouts with diagrams
- See the [Skill Guide](SKILL_GUIDE.md) for using the cc-tmux skill with Claude

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Complete command reference
- [Configuration](CONFIGURATION.md) - Configuration options and presets
- [Layouts](LAYOUTS.md) - All predefined layouts with diagrams
- [Skill Guide](SKILL_GUIDE.md) - Using the cc-tmux skill with Claude
- [Architecture](ARCHITECTURE.md) - System design and data flow
