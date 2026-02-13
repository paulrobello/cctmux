# Layouts Reference

Complete reference for all cctmux predefined layouts. Each layout provides a different pane arrangement optimized for specific workflows.

## Table of Contents

- [Overview](#overview)
- [Default Layout](#default-layout)
- [Editor Layout](#editor-layout)
- [Monitor Layout](#monitor-layout)
- [Triple Layout](#triple-layout)
- [CC-Mon Layout](#cc-mon-layout)
- [Full-Monitor Layout](#full-monitor-layout)
- [Dashboard Layout](#dashboard-layout)
- [Ralph Layout](#ralph-layout)
- [Ralph-Full Layout](#ralph-full-layout)
- [Git-Mon Layout](#git-mon-layout)
- [Choosing a Layout](#choosing-a-layout)
- [Related Documentation](#related-documentation)

## Overview

cctmux provides ten predefined layouts that can be selected with the `--layout` or `-l` flag:

```bash
cctmux -l <layout-name>
```

| Layout | Panes | Best For |
|--------|-------|----------|
| `default` | 1 | Simple tasks, manual pane creation |
| `editor` | 2 | Code editing with side panel |
| `monitor` | 2 | Main work with status bar |
| `triple` | 3 | Multiple auxiliary processes |
| `cc-mon` | 3 | Monitoring Claude Code activity |
| `full-monitor` | 4 | Complete monitoring visibility |
| `dashboard` | 3 | Usage review and statistics |
| `ralph` | 2 | Ralph Loop with monitor dashboard |
| `ralph-full` | 3 | Ralph Loop with monitor and task tracker |
| `git-mon` | 2 | Claude Code with git status monitor |

All layouts keep focus on the main Claude pane after creation, except `dashboard` which focuses the shell pane, and `ralph`/`ralph-full` which focus the shell pane for running `cctmux-ralph start`.

## Default Layout

No initial splits. Panes are created on demand.

```bash
cctmux
# or
cctmux -l default
```

```
┌─────────────────────────────────────┐
│                                     │
│                                     │
│            Claude Code              │
│              100%                   │
│                                     │
│                                     │
└─────────────────────────────────────┘
```

**Use Cases:**
- Simple tasks that don't need auxiliary panes
- When you prefer to create panes manually
- Maximizing screen space for Claude

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 100% |

## Editor Layout

70/30 horizontal split with a side pane for auxiliary tasks.

```bash
cctmux -l editor
```

```
┌─────────────────────────┬───────────┐
│                         │           │
│                         │   Side    │
│       Claude Code       │   Pane    │
│          70%            │   30%     │
│                         │           │
│                         │           │
└─────────────────────────┴───────────┘
```

**Use Cases:**
- Running a dev server while coding
- Tailing logs alongside development
- Manual testing in a side terminal

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 70% width |
| 0.1 | Empty shell | 30% width |

**Example Usage:**
```bash
# Start with editor layout
cctmux -l editor

# In the side pane (0.1), run a dev server
tmux send-keys -t "$CCTMUX_SESSION:0.1" "npm run dev" Enter
```

## Monitor Layout

80/20 vertical split with a bottom status bar.

```bash
cctmux -l monitor
```

```
┌─────────────────────────────────────┐
│                                     │
│            Claude Code              │
│              80%                    │
│                                     │
├─────────────────────────────────────┤
│          Bottom Bar  20%            │
└─────────────────────────────────────┘
```

**Use Cases:**
- Running test watchers
- Monitoring build output
- Watching file changes

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 80% height |
| 0.1 | Empty shell | 20% height |

**Example Usage:**
```bash
# Start with monitor layout
cctmux -l monitor

# In the bottom pane (0.1), run tests in watch mode
tmux send-keys -t "$CCTMUX_SESSION:0.1" "npm test -- --watch" Enter
```

## Triple Layout

Main pane with two stacked side panes for multiple auxiliary processes.

```bash
cctmux -l triple
```

```
┌──────────────────┬──────────────────┐
│                  │    Top Right     │
│                  │      50%         │
│   Claude Code    ├──────────────────┤
│      50%         │   Bottom Right   │
│                  │      50%         │
│                  │                  │
└──────────────────┴──────────────────┘
```

**Use Cases:**
- Dev server + test watcher
- Multiple log streams
- Frontend + backend processes

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 50% width |
| 0.1 | Top right shell | 50% width, 50% height |
| 0.2 | Bottom right shell | 50% width, 50% height |

**Example Usage:**
```bash
# Start with triple layout
cctmux -l triple

# Top right: dev server
tmux send-keys -t "$CCTMUX_SESSION:0.1" "npm run dev" Enter

# Bottom right: test watcher
tmux send-keys -t "$CCTMUX_SESSION:0.2" "npm test -- --watch" Enter
```

## CC-Mon Layout

Claude Code with session monitor and task monitor. Recommended for monitoring Claude activity.

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

**Use Cases:**
- Monitoring tool calls and token usage
- Tracking task progress during complex work
- Understanding Claude's activity in real-time

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 50% width |
| 0.1 | `cctmux-session` | 50% width, 50% height |
| 0.2 | `cctmux-tasks -g` | 50% width, 50% height |

**Monitors Launched:**
- **Session Monitor**: Shows tool calls, thinking blocks, token usage, cost estimates
- **Task Monitor**: Shows dependency graph only (`-g` flag)

## Full-Monitor Layout

Complete monitoring setup with all monitors visible.

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

**Use Cases:**
- Maximum visibility into Claude activity
- Long-running complex tasks
- Cost monitoring during intensive sessions

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 60% width |
| 0.1 | `cctmux-session` | 40% width, 30% height |
| 0.2 | `cctmux-tasks -g` | 40% width, 35% height |
| 0.3 | `cctmux-activity` | 40% width, 35% height |

**Monitors Launched:**
- **Session Monitor**: Tool calls, thinking, tokens, costs
- **Task Monitor**: Dependency graph only
- **Activity Dashboard**: Usage statistics and heatmap

## Dashboard Layout

Large activity dashboard with session stats sidebar. Optimized for usage review.

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

**Use Cases:**
- Reviewing usage patterns and costs
- End-of-day activity summary
- Planning based on usage trends

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | `cctmux-activity --show-hourly` | 70% width |
| 0.1 | `cctmux-session` | 30% width, 50% height |
| 0.2 | Empty shell (focused) | 30% width, 50% height |

**Monitors Launched:**
- **Activity Dashboard**: Full dashboard with hourly distribution
- **Session Monitor**: Current session statistics

> **Note:** Focus is placed on the shell pane (0.2) in this layout, allowing you to optionally run Claude or other commands.

## Ralph Layout

Shell pane with a Ralph Loop monitor dashboard side-by-side. Designed for running and monitoring Ralph Loop automation.

```bash
cctmux -l ralph
```

```
┌──────────────────┬──────────────────┐
│                  │                  │
│                  │  cctmux-ralph    │
│     Shell        │     40%          │
│      60%         │                  │
│                  │                  │
│                  │                  │
└──────────────────┴──────────────────┘
```

**Use Cases:**
- Running a Ralph Loop with live monitoring
- Iterative automated Claude Code execution
- Watching Ralph progress while issuing commands

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Shell (focused) | 60% width |
| 0.1 | `cctmux-ralph` | 40% width |

**Monitors Launched:**
- **Ralph Monitor**: Live dashboard showing iteration progress, task completion, token usage, and cost tracking

**Example Usage:**
```bash
# Start with ralph layout
cctmux -l ralph

# In the shell pane (focused), start a Ralph Loop
cctmux-ralph start ralph-project.md
```

## Ralph-Full Layout

Shell pane with Ralph Loop monitor and task monitor. Provides full visibility into both Ralph Loop progress and individual task status.

```bash
cctmux -l ralph-full
```

```
┌──────────────────┬──────────────────┐
│                  │  cctmux-ralph    │
│                  │      50%         │
│     Shell        ├──────────────────┤
│      60%         │ cctmux-tasks -g  │
│                  │      50%         │
│                  │                  │
└──────────────────┴──────────────────┘
```

**Use Cases:**
- Full Ralph Loop monitoring with task dependency visibility
- Tracking both iteration progress and individual task completion
- Complex multi-task Ralph projects

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Shell (focused) | 60% width |
| 0.1 | `cctmux-ralph` | 40% width, 50% height |
| 0.2 | `cctmux-tasks -g` | 40% width, 50% height |

**Monitors Launched:**
- **Ralph Monitor**: Iteration progress, task completion, token usage, cost tracking
- **Task Monitor**: Dependency graph only (`-g` flag)

**Example Usage:**
```bash
# Start with ralph-full layout
cctmux -l ralph-full

# In the shell pane (focused), start a Ralph Loop
cctmux-ralph start ralph-project.md --max-iterations 10
```

## Git-Mon Layout

Claude Code with a real-time git status monitor. Ideal for watching repository changes as Claude works.

```bash
cctmux -l git-mon
```

```
┌──────────────────┬──────────────────┐
│                  │                  │
│                  │   cctmux-git     │
│   Claude Code    │      40%         │
│      60%         │                  │
│                  │                  │
│                  │                  │
└──────────────────┴──────────────────┘
```

**Use Cases:**
- Watching file changes as Claude edits code
- Monitoring branch status and commit history
- Tracking staged vs unstaged changes during development

**Pane Structure:**
| Pane | Content | Size |
|------|---------|------|
| 0.0 | Claude Code | 60% width |
| 0.1 | `cctmux-git` | 40% width |

**Monitors Launched:**
- **Git Monitor**: Branch info, file status, recent commits, diff statistics

## Choosing a Layout

```
What do you need?
│
├─ Simple task? ──────── Yes ──→ default
│
├─ Need monitoring?
│  ├─ Yes ────────────────────→ cc-mon
│  └─ All monitors ──────────→ full-monitor
│
├─ Need auxiliary processes?
│  ├─ 1 side process ────────→ editor
│  ├─ 1 bottom bar ─────────→ monitor
│  └─ 2 processes ──────────→ triple
│
├─ Want git status visible?
│  └─ Yes ─────────────────→ git-mon
│
├─ Running Ralph Loop?
│  ├─ Basic monitoring ──────→ ralph
│  └─ With task tracking ────→ ralph-full
│
└─ Reviewing usage? ─────────→ dashboard
```

### Quick Reference

| Scenario | Recommended Layout |
|----------|-------------------|
| Quick task, no monitoring | `default` |
| Dev server while coding | `editor` |
| Test watcher while coding | `monitor` |
| Dev server + test watcher | `triple` |
| Track Claude activity | `cc-mon` |
| Full visibility during long tasks | `full-monitor` |
| Review daily/weekly usage | `dashboard` |
| Ralph Loop with live dashboard | `ralph` |
| Ralph Loop with task tracking | `ralph-full` |
| Watch git changes while coding | `git-mon` |

### Setting a Default Layout

Set your preferred layout in the configuration file:

```yaml
# ~/.config/cctmux/config.yaml
default_layout: cc-mon
```

Then simply run:

```bash
cctmux  # Uses cc-mon layout
```

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Complete command reference
- [Configuration](CONFIGURATION.md) - Configuration options
- [Architecture](ARCHITECTURE.md) - System design
- [Quick Start](QUICKSTART.md) - Getting started guide
