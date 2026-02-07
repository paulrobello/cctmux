---
name: cc-tmux
description: Enables Claude to discover and manage tmux panes within a cctmux session. Use when running inside tmux to create panes for dev servers, file watchers, test runners, and other background processes.
---

# Claude Tmux Session Awareness

This skill enables Claude to work effectively within tmux sessions created by cctmux.

## Philosophy

**Terminal as Workspace**: Tmux panes provide dedicated spaces for background processes without cluttering the main conversation. Use panes for:
- Development servers
- File watchers
- Test runners in watch mode
- Build processes
- Log tailing

**Visibility Over Convenience**: Processes running in visible panes are easier to monitor and debug than hidden background processes.

**Create Then Launch**: Always create panes first, then use send-keys to launch applications. This ensures proper shell environment and allows easy process restart.

## Session Discovery

### Environment Variables

When running in a cctmux session, these environment variables are available:

```bash
$CCTMUX_SESSION    # The tmux session name (e.g., "my-project")
$CCTMUX_PROJECT_DIR # The project directory path
```

### Detecting cctmux Session

Before attempting tmux operations, verify you're in a cctmux session:

```bash
if [ -n "$CCTMUX_SESSION" ]; then
    echo "Running in cctmux session: $CCTMUX_SESSION"
fi
```

## Pane Management

### Discover Window Index AND Pane IDs First (CRITICAL)

**Both the window index AND pane indices are NOT always 0.** cctmux sessions may use window index 1 and pane indices starting at 1 or any other value. Hardcoding `:0.0` or `:0.1` will target the wrong pane or fail entirely.

**Always discover actual values** before targeting panes:

```bash
# Get the window index (use this before any pane operations)
W=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{window_index}" | head -1)

# Get all pane IDs with their commands (pane IDs like %15 are STABLE and UNIQUE)
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
```

### Prefer Pane IDs Over Positional Indices (CRITICAL)

**Pane IDs (e.g., `%15`, `%16`) are always stable and safe to target.** Positional indices (`.0`, `.1`, `.2`) shift when panes are created/destroyed and don't always start at 0.

**When creating new panes**, always capture the pane ID with `-d -P -F "#{pane_id}"`:
```bash
# -d = don't switch focus, -P -F = print the new pane's ID
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 30)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter
```

**When targeting existing panes**, look up pane IDs from `list-panes`, never assume indices:
```bash
# Find pane IDs and what's running in each
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
# Output example: %15 claude   %16 bash   %17 bash
# Then target by pane ID
tmux send-keys -t "%16" "npm run dev" Enter
```

### Identify the Main (Claude) Pane (CRITICAL)

**Never send commands to the pane where Claude Code is running.** The main pane is where YOU (Claude) are executing — sending commands there will type into your own input.

Identify the main pane before targeting others:
```bash
# The active pane is typically the Claude pane
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")

# List all panes — your pane shows as the claude/python process
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
# Target only panes that are NOT your main pane (bash/idle panes are safe targets)
```

### Examine Current State

Always check the current pane layout before making changes **and present it to the user** in a markdown table so they can make informed decisions about where to place tools.

```bash
# List all panes with window index, IDs, sizes, and running process
tmux list-panes -t "$CCTMUX_SESSION" -F "#{window_index}.#{pane_index}: #{pane_id} #{pane_width}x#{pane_height} #{pane_current_command}"
```

**After running this command, display results to the user as a table like:**

| Pane | Size | Process |
|------|------|---------|
| 1 (main) | 120x55 | claude |
| 2 | 90x27 | bash (idle) |
| 3 | 90x27 | cctmux-tasks |

This gives the user visibility into the current layout so they can instruct you where to launch processes, which panes to reuse, or how to rearrange things.

### Creating Panes

**IMPORTANT**: Always create panes without commands, then use send-keys to launch applications. This ensures:
- Proper shell environment with all exports
- Ability to restart processes with up-arrow + Enter
- Consistent behavior across different shells

**Horizontal Split (side by side)**
```bash
# Split with 30% width on the right
tmux split-window -t "$CCTMUX_SESSION" -h -p 30

# Split with specific column width
tmux split-window -t "$CCTMUX_SESSION" -h -l 80
```

**Vertical Split (stacked)**
```bash
# Split with 20% height on the bottom
tmux split-window -t "$CCTMUX_SESSION" -v -p 20

# Split with specific line count
tmux split-window -t "$CCTMUX_SESSION" -v -l 10
```

### Launching Applications in Panes

After creating a pane, use send-keys to launch applications. **Always capture the pane ID**:

```bash
# Create pane and capture its ID, then launch application
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 30)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter
```

### Navigating Panes

```bash
# Select pane by pane ID (preferred — always stable)
tmux select-pane -t "%15"

# Select pane by direction (no index needed)
tmux select-pane -t "$CCTMUX_SESSION" -L  # Left
tmux select-pane -t "$CCTMUX_SESSION" -R  # Right
tmux select-pane -t "$CCTMUX_SESSION" -U  # Up
tmux select-pane -t "$CCTMUX_SESSION" -D  # Down
```

### Resizing Panes

```bash
# Resize by cell count
tmux resize-pane -t "$CCTMUX_SESSION" -L 10  # Shrink left
tmux resize-pane -t "$CCTMUX_SESSION" -R 10  # Expand right
tmux resize-pane -t "$CCTMUX_SESSION" -U 5   # Shrink up
tmux resize-pane -t "$CCTMUX_SESSION" -D 5   # Expand down

# Resize to percentage
tmux resize-pane -t "$CCTMUX_SESSION" -x 70%  # Set width
tmux resize-pane -t "$CCTMUX_SESSION" -y 80%  # Set height
```

### Sending Commands to Panes

```bash
# Send command to specific pane by pane ID (preferred)
tmux send-keys -t "%16" "npm run dev" Enter

# Send Ctrl+C to stop a process
tmux send-keys -t "%16" C-c

# Restart a process (Ctrl+C, then run again)
tmux send-keys -t "%16" C-c
tmux send-keys -t "%16" "npm run dev" Enter
```

### Closing Panes

```bash
# Close specific pane by pane ID (preferred)
tmux kill-pane -t "%16"

# Close all panes except the current one
tmux kill-pane -t "$CCTMUX_SESSION" -a
```

## Background Process Patterns

### Dev Server Pattern

Create a dedicated pane for a development server:

```bash
# Check if we need a dev server pane
pane_count=$(tmux list-panes -t "$CCTMUX_SESSION" | wc -l)

if [ "$pane_count" -eq 1 ]; then
    # Create pane for dev server, capture its ID
    DEV_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 30)
    # Launch dev server
    tmux send-keys -t "$DEV_PANE" "npm run dev" Enter
fi
```

### File Watcher Pattern

Run file watchers in a bottom pane:

```bash
# Create small bottom pane for watcher output, capture its ID
WATCH_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -v -l 8)
tmux send-keys -t "$WATCH_PANE" "npm run watch" Enter
```

### Test Watch Pattern

Run tests in watch mode:

```bash
# Create right pane for test output, capture its ID
TEST_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 40)
tmux send-keys -t "$TEST_PANE" "npm test -- --watch" Enter
```

### Multiple Processes Layout

For complex setups with multiple background processes:

```bash
# Create right column (50%), capture its ID
RIGHT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 50)

# Launch dev server in right pane
tmux send-keys -t "$RIGHT_PANE" "npm run dev" Enter

# Split right pane for tests (bottom half of right column), capture its ID
BOTTOM_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$RIGHT_PANE" -v -p 50)

# Launch test watcher in new bottom-right pane
tmux send-keys -t "$BOTTOM_PANE" "npm test -- --watch" Enter
```

## Predefined Layouts

cctmux supports several predefined layouts via the `--layout` / `-l` option:

| Layout | Description |
|--------|-------------|
| `default` | No initial split, panes created on demand |
| `editor` | 70/30 horizontal split (main + side pane) |
| `monitor` | 80/20 vertical split (main + bottom bar) |
| `triple` | Main + 2 side panes (50/50, right split vertically) |
| `cc-mon` | Claude + session monitor + task monitor |
| `full-monitor` | Claude + session + tasks + activity dashboard |
| `dashboard` | Large activity dashboard with session sidebar |
| `ralph` | Shell + ralph monitor side-by-side (60/40) |
| `ralph-full` | Shell + ralph monitor + task monitor |

### CC-Mon Layout

The `cc-mon` layout is designed for monitoring Claude Code activity:

```
-------------------------------
| CLAUDE     | cctmux-session |
| 50%        |    50%         |
|            |----------------|
|            | cctmux-tasks -g|
|            |    50%         |
-------------------------------
```

Start with this layout:
```bash
cctmux -l cc-mon
```

This layout provides:
- **Left pane (50%)**: Main Claude Code session
- **Top-right pane**: Real-time session monitor showing tool calls, thinking blocks, and token usage
- **Bottom-right pane**: Task dependency graph showing current task progress

### Full-Monitor Layout

The `full-monitor` layout adds the activity dashboard for complete visibility:

```
-----------------------------------------
|           | cctmux-session   30%      |
| CLAUDE    |-----------------------------|
| 60%       | cctmux-tasks -g   35%      |
|           |-----------------------------|
|           | cctmux-activity   35%      |
-----------------------------------------
```

Start with this layout:
```bash
cctmux -l full-monitor
```

### Dashboard Layout

The `dashboard` layout is optimized for reviewing usage statistics:

```
-----------------------------------------
|                       | cctmux-session |
| cctmux-activity       |      30%       |
|     70%               |----------------|
|                       | mini shell     |
|                       |      30%       |
-----------------------------------------
```

Start with this layout:
```bash
cctmux -l dashboard
```

## Par Mode

Par mode sets up a triple layout with the session monitor in pane 2 and task monitor in pane 3. It checks the current layout and only reconfigures if needed.

### Activating Par Mode

Run this bash script to activate par mode. It is idempotent — safe to run multiple times.

**Key principle**: Use pane IDs (not indices) to avoid targeting the wrong pane. The main Claude pane's index is unpredictable — always identify it and avoid sending commands to it.

```bash
# Verify we're in a cctmux session
if [ -z "$CCTMUX_SESSION" ]; then
    echo "Not in a cctmux session"
    exit 1
fi

W=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{window_index}" | head -1)

# Get current pane info using pane IDs (stable identifiers)
PANE_INFO=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id}:#{pane_current_command}")
PANE_COUNT=$(echo "$PANE_INFO" | wc -l | tr -d ' ')

# Check if already in par-mode (3 panes with session monitor and task monitor)
HAS_SESSION_MON=$(echo "$PANE_INFO" | grep -c "cctmux-session" || true)
HAS_TASK_MON=$(echo "$PANE_INFO" | grep -c "cctmux-tasks" || true)

if [ "$PANE_COUNT" -eq 3 ] && [ "$HAS_SESSION_MON" -ge 1 ] && [ "$HAS_TASK_MON" -ge 1 ]; then
    echo "Par mode already active"
    exit 0
fi

# Identify the main (Claude) pane — the currently active pane
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")

# If we already have 3 panes (e.g., triple layout with idle bash panes),
# reuse the existing side panes instead of killing and recreating
if [ "$PANE_COUNT" -eq 3 ]; then
    # Get the two non-main pane IDs
    SIDE_PANES=$(echo "$PANE_INFO" | grep -v "^${MAIN_PANE}:" | cut -d: -f1)
    SIDE1=$(echo "$SIDE_PANES" | head -1)
    SIDE2=$(echo "$SIDE_PANES" | tail -1)

    # Stop any running processes in side panes, then launch monitors
    tmux send-keys -t "$SIDE1" C-c
    sleep 0.3
    tmux send-keys -t "$SIDE1" "cctmux-session" Enter

    tmux send-keys -t "$SIDE2" C-c
    sleep 0.3
    tmux send-keys -t "$SIDE2" "cctmux-tasks -g" Enter

    echo "Par mode activated (reused existing panes)"
    exit 0
fi

# Kill extra panes if not 1 or 3 (keep only main pane)
if [ "$PANE_COUNT" -gt 1 ]; then
    tmux kill-pane -t "$CCTMUX_SESSION" -a
fi

# Create triple layout: main (50%) | right column split vertically (50%)
# Split horizontally with 50% on the right, capture pane ID
RIGHT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 50)

# Launch session monitor in the right pane
tmux send-keys -t "$RIGHT_PANE" "cctmux-session" Enter

# Split right pane vertically 50/50, capture bottom pane ID
BOTTOM_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$RIGHT_PANE" -v -p 50)

# Launch task monitor in the bottom-right pane
tmux send-keys -t "$BOTTOM_PANE" "cctmux-tasks -g" Enter

echo "Par mode activated"
```

### Par Mode Layout

```
---------------------------------
|            | cctmux-session   |
|  CLAUDE    |      50%         |
|   70%      |------------------|
|            | cctmux-tasks     |
|            |      50%         |
---------------------------------
```

## Command Reference

**First, discover pane IDs**: `tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"`
**Create panes with ID capture**: `PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 30)`

| Action | Command |
|--------|---------|
| List panes (with IDs) | `tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_width}x#{pane_height} #{pane_current_command}"` |
| Get main pane ID | `MAIN=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")` |
| Split + capture ID | `PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h [-p %])` |
| Select pane | `tmux select-pane -t "$PANE_ID"` |
| Send keys | `tmux send-keys -t "$PANE_ID" "cmd" Enter` |
| Send Ctrl+C | `tmux send-keys -t "$PANE_ID" C-c` |
| Kill pane | `tmux kill-pane -t "$PANE_ID"` |
| Resize width | `tmux resize-pane -t "$CCTMUX_SESSION" -x N%` |
| Resize height | `tmux resize-pane -t "$CCTMUX_SESSION" -y N%` |

## Anti-Patterns

### Don't Use Hardcoded Pane Indices

❌ Assuming pane indices start at 0
```bash
# Bad: pane indices may start at 1 or any number — this could target your own Claude pane!
tmux send-keys -t "$CCTMUX_SESSION:$W.0" "some command" Enter
tmux send-keys -t "$CCTMUX_SESSION:$W.1" "npm run dev" Enter
```

✅ Use captured pane IDs or discover actual IDs first
```bash
# Good: capture ID when creating
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 30)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter

# Good: discover IDs for existing panes
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
tmux send-keys -t "%16" "npm run dev" Enter
```

### Don't Launch Commands Directly in split-window

❌ Running commands as split-window arguments
```bash
# Bad: command runs in subshell, no shell history, exits on completion
tmux split-window -t "$CCTMUX_SESSION" -h "npm run dev"
```

✅ Create pane with -d flag, capture ID, then send-keys
```bash
# Good: proper shell environment, can restart with up-arrow, -d keeps focus
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter
```

### Don't Create Unnecessary Panes

❌ Creating a pane for a one-off command
```bash
# Bad: pane for single command
tmux split-window -t "$CCTMUX_SESSION" -h
```

✅ Use panes for persistent processes
```bash
# Good: pane for long-running dev server
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter
```

### Always Use -d Flag (Don't Steal Focus)

❌ Creating pane without -d (steals focus to new pane)
```bash
# Bad: focus moves to new pane, then you must manually select back
tmux split-window -t "$CCTMUX_SESSION" -h
```

✅ Use -d to stay in current pane
```bash
# Good: -d keeps focus in current pane, no need to select-pane back
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter
```

### Don't Over-Split

❌ Creating too many panes
```bash
# Bad: 5+ panes become hard to manage
```

✅ Use 2-4 panes maximum
```bash
# Good: main pane + 1-2 utility panes
```

### Check Before Creating

❌ Blindly creating panes
```bash
# Bad: might duplicate existing layout
tmux split-window ...
```

✅ Check existing state first
```bash
# Good: verify current layout
tmux list-panes -t "$CCTMUX_SESSION"
```

## Task Monitor

cctmux includes a real-time task monitor (`cctmux-tasks`) that visualizes Claude Code tasks with their dependencies. This is useful for monitoring complex multi-step operations.

### Running the Task Monitor

The monitor automatically finds the most recent session with tasks when run from a Claude Code project directory.

```bash
# Auto-detect from current project directory
cctmux-tasks

# List all sessions with tasks
cctmux-tasks --list

# List sessions for a specific project
cctmux-tasks --list -p /path/to/project

# Monitor specific session (partial ID match supported)
cctmux-tasks abc123

# Monitor a direct task folder path
cctmux-tasks /path/to/task/folder

# Find sessions for a specific project
cctmux-tasks -p /path/to/project

# Show only dependency graph (no table)
cctmux-tasks -g

# Custom poll interval (default 1.0 seconds)
cctmux-tasks -i 0.5

# Hide task owner column
cctmux-tasks --no-owner

# Show task metadata
cctmux-tasks --show-metadata

# Hide task descriptions
cctmux-tasks --no-description

# Show acceptance criteria completion
cctmux-tasks --show-acceptance

# Show work log entries
cctmux-tasks --show-work-log

# Use a preset configuration
cctmux-tasks --preset minimal
cctmux-tasks --preset verbose
cctmux-tasks --preset debug
```

### Session Resolution Priority

When no session is specified, the monitor resolves in this order:
1. **Current project sessions**: Finds sessions from `~/.claude/projects/` for the current directory
2. **Custom project folder**: Checks for a task folder matching the project name (e.g., `~/.claude/tasks/my-project` for `~/Repos/my-project`)
3. **Waiting mode**: If no tasks exist yet, displays "Waiting for tasks..." and polls until tasks appear

The monitor stays scoped to the current project and will not show tasks from other projects.

### Task Monitor in a Pane

Run the task monitor in a dedicated pane to watch task progress:

```bash
# Create pane for task monitor, capture its ID
TASK_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 35)
tmux send-keys -t "$TASK_PANE" "cctmux-tasks" Enter
```

### Display Features

- **Dependency Graph**: ASCII tree showing task relationships with indentation
- **Status Indicators**: `○` pending, `◐` in progress, `●` completed
- **Progress Stats**: Total tasks, status counts, completion percentage
- **Real-time Updates**: Polls task files and updates display automatically
- **Task Table**: Shows ID, subject, status, and dependency relationships
- **Owner Column**: Displays task owner/agent identifier (can be hidden)
- **Acceptance Criteria**: Shows completion percentage `[2/5 40%]` when tasks have acceptance criteria in metadata
- **Work Log**: Displays recent work log entries from task metadata (optional)
- **Custom Metadata**: Shows arbitrary key-value metadata (optional)
- **Waiting Mode**: Shows "Waiting for tasks..." when no tasks exist, automatically transitions when tasks appear
- **Auto Session Detection**: Automatically switches to new sessions when auto-compact or clear starts a new session in the same project

### Task File Location

Tasks are stored in `~/.claude/tasks/<session_id>/` as numbered JSON files (e.g., `1.json`, `2.json`).
Custom-named task folders are also supported (e.g., `~/.claude/tasks/my-project/`).

Each file contains:
- `id`: Task identifier
- `subject`: Brief task description
- `status`: pending, in_progress, or completed
- `blocks`: Array of task IDs this task blocks
- `blockedBy`: Array of task IDs blocking this task
- `activeForm`: Present continuous form shown during progress
- `owner`: Agent identifier if assigned
- `metadata`: Optional object for custom data

### Ralph Loop Conventions

For automated workflows, tasks can include structured metadata:

**Acceptance Criteria** - Checklist for task completion:
```json
{
  "metadata": {
    "acceptance_criteria": [
      {"description": "Tests pass", "done": true},
      {"description": "Linting passes", "done": false},
      {"description": "Documentation updated", "done": false}
    ]
  }
}
```

**Work Log** - Record of iterations and handoffs:
```json
{
  "metadata": {
    "work_log": [
      {"timestamp": "2024-01-15T10:30:00Z", "action": "Started implementation"},
      {"timestamp": "2024-01-15T11:00:00Z", "action": "Fixed test failures"},
      "Plain string entries also supported"
    ]
  }
}
```

The task monitor displays acceptance completion as `[completed/total pct%]` in the subject column.

## Session Monitor

cctmux includes a real-time session monitor (`cctmux-session`) that displays Claude Code session activity including tool calls, thinking blocks, and token usage.

### Running the Session Monitor

```bash
# Auto-detect from current project directory
cctmux-session

# List all available sessions
cctmux-session --list

# List sessions for a specific project
cctmux-session --list -p /path/to/project

# Monitor specific session (partial ID match supported)
cctmux-session abc123

# Monitor a direct JSONL file
cctmux-session /path/to/session.jsonl

# Find sessions for a specific project
cctmux-session -p /path/to/project

# Custom poll interval (default 0.5 seconds)
cctmux-session -i 0.25
```

### Display Options

Control what's shown in the event stream:

```bash
# Hide thinking blocks (reduce noise)
cctmux-session --no-thinking

# Hide tool results (show only tool calls)
cctmux-session --no-results

# Hide progress/hook events
cctmux-session --no-progress

# Show system messages (hidden by default)
cctmux-session --show-system

# Show file snapshots (hidden by default)
cctmux-session --show-snapshots

# Show current working directory in stats
cctmux-session --show-cwd

# Show message threading (parent-child relationships)
cctmux-session --show-threading

# Hide stop reason tracking
cctmux-session --no-stop-reasons

# Hide turn duration stats
cctmux-session --no-turn-durations

# Hide hook error tracking
cctmux-session --no-hook-errors

# Show service tier information
cctmux-session --show-service-tier

# Hide sidechain messages
cctmux-session --no-sidechain

# Limit visible events
cctmux-session -m 20

# Use a preset configuration
cctmux-session --preset minimal
cctmux-session --preset verbose
cctmux-session --preset debug
```

### Session Monitor in a Pane

Run the session monitor alongside your work:

```bash
# Create pane for session monitor, capture its ID
SESSION_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 40)
tmux send-keys -t "$SESSION_PANE" "cctmux-session" Enter
```

### Display Features

- **Stats Panel**: Session ID, model, git branch, duration, message counts, token usage, estimated cost, tool histogram
- **Stop Reason Tracking**: Counts of tool_use, end_turn, max_tokens stop reasons
- **Turn Duration Stats**: Average, min, max turn times when available
- **Hook Error Tracking**: Hook execution counts and error indicators
- **Service Tier**: API service tier information (optional)
- **Working Directory**: Current working directory (optional, with path compression)
- **Events Panel**: Chronological view of user prompts, thinking blocks, tool calls, tool results, and assistant responses
- **Threading View**: Tree-style indentation showing message parent-child relationships (optional)
- **Sidechain Indicators**: Visual differentiation for sidechain messages
- **Status Symbols**: `●` user, `◐` thinking, `▶` tool call, `◀` result, `■` assistant, `↻` progress
- **Real-time Updates**: Polls JSONL file and updates display automatically
- **Windowed View**: Shows most recent events, indicates count of earlier events
- **Auto Session Detection**: Automatically switches to new sessions when auto-compact or clear starts a new session in the same project

### Session File Location

Session JSONL files are stored at:
```
~/.claude/projects/<encoded-project-path>/<session-id>.jsonl
```

Where `<encoded-project-path>` is the project path with `/` replaced by `-`.

## Activity Dashboard

cctmux includes an activity dashboard (`cctmux-activity`) that displays usage statistics from Claude Code's stats cache, including token usage, cost estimates, and activity patterns.

### Running the Activity Dashboard

```bash
# Display activity for last 14 days (default)
cctmux-activity

# Show last 7 days
cctmux-activity --days 7

# Show hourly activity distribution
cctmux-activity --show-hourly

# Hide cost estimates
cctmux-activity --no-cost

# Hide model usage table
cctmux-activity --no-model-usage

# Hide activity heatmap
cctmux-activity --no-heatmap

# Use a preset configuration
cctmux-activity --preset verbose
```

### Display Features

- **Summary Panel**: Total sessions, messages, days tracked, weekly stats, total tokens, estimated cost
- **Activity Heatmap**: ASCII visualization of daily activity (messages, sessions, tool calls)
- **Model Usage Table**: Token breakdown by model (input, output, cache read/write), cost estimates
- **Hourly Distribution**: Bar chart showing activity by hour of day (optional)

### Data Source

Activity data is read from `~/.claude/stats-cache.json`, which Claude Code updates automatically.

## Subagent Monitor

cctmux includes a real-time subagent monitor (`cctmux-agents`) that tracks activity across all Claude Code subagents spawned during a session. This is useful for monitoring parallel task execution and understanding subagent workload.

### Running the Subagent Monitor

```bash
# Auto-detect from current project directory
cctmux-agents

# List all available subagents
cctmux-agents --list

# Monitor specific session (partial ID match supported)
cctmux-agents abc123

# Find subagents for a specific project
cctmux-agents -p /path/to/project

# Hide the activity panel (show only stats and table)
cctmux-agents --no-activity

# Custom poll interval (default 1.0 seconds)
cctmux-agents -i 0.5
```

### Subagent Monitor in a Pane

Run the subagent monitor alongside your work:

```bash
# Create pane for subagent monitor, capture its ID
AGENT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 45)
tmux send-keys -t "$AGENT_PANE" "cctmux-agents" Enter
```

### Display Features

- **Stats Panel**: Total subagents, active/completed counts, aggregate token usage, top tools across all agents
- **Agent Table**: Name/slug, model, duration, tokens (in→out), top tools, current activity
- **Activity Panel**: Recent activities across all agents with timestamps and agent IDs
- **Status Indicators**: `○` unknown, `◐` active, `●` completed
- **Real-time Updates**: Polls agent files and updates display automatically
- **Auto Detection**: Automatically discovers new subagents as they spawn

### Subagent Information

Each subagent displays:
- **Display Name**: Human-readable slug (e.g., "dreamy-mapping-naur") or agent ID
- **Model**: The Claude model being used (haiku, sonnet, opus)
- **Duration**: How long the agent has been running
- **Tokens**: Input and output token counts
- **Tools**: Most frequently used tools with counts
- **Current Activity**: Latest tool call, thinking, or text output

### Subagent File Location

Subagent transcript files are stored in two locations:
```
~/.claude/projects/<encoded-project-path>/agent-<id>.jsonl
~/.claude/projects/<encoded-project-path>/<session-id>/subagents/agent-<id>.jsonl
```

Each JSONL file contains the subagent's full conversation history including:
- Initial task prompt
- Tool calls and results
- Thinking blocks
- Text responses
- Token usage per message

## Ralph Loop

cctmux includes the Ralph Loop (`cctmux-ralph`), an automated iterative development engine where Claude Code runs in a loop until a project is complete. Each iteration gets fresh context. The input is a structured markdown project file with task checklists.

### Creating a Project File

```bash
# Generate a template project file
cctmux-ralph init -o ralph-project.md -n "Todo REST API"
```

The project file is markdown with checklist items:

```markdown
# Ralph Project: Todo REST API

## Description
Build a REST API for managing todos with full CRUD operations using FastAPI.

## Tasks
- [ ] Set up project structure with FastAPI
- [ ] Implement GET /todos endpoint
- [ ] Implement POST /todos endpoint
- [ ] Write unit tests (>80% coverage)

## Notes
Use SQLite for storage. Follow REST best practices.
```

### Starting a Ralph Loop

```bash
# Start with default settings
cctmux-ralph start ralph-project.md

# Set max iterations and completion promise
cctmux-ralph start ralph-project.md -m 20 -c "All tests passing"

# Use a specific model and budget per iteration
cctmux-ralph start ralph-project.md --model sonnet --max-budget 5.0

# Use bypassPermissions mode for fully unattended execution
cctmux-ralph start ralph-project.md --permission-mode bypassPermissions

# Specify project root (if different from project file location)
cctmux-ralph start ralph-project.md -p /path/to/project
```

### Monitoring a Running Loop

```bash
# Live dashboard (default when no subcommand given)
cctmux-ralph

# Monitor a specific project
cctmux-ralph -p /path/to/project

# Use verbose preset
cctmux-ralph --preset verbose
```

### Managing Loop Lifecycle

```bash
# Cancel a running loop (between iterations)
cctmux-ralph cancel

# Show one-shot status
cctmux-ralph status

# Cancel a specific project's loop
cctmux-ralph cancel -p /path/to/project
```

### Completion Detection

The loop stops when any of these conditions are met:
1. **All checklist items checked**: All `- [ ]` items become `- [x]` in the project file
2. **Promise tag**: Claude outputs `<promise>completion text</promise>` matching the configured promise
3. **Max iterations**: Safety limit reached (if set with `--max-iterations`)
4. **Cancellation**: User runs `cctmux-ralph cancel` or presses Ctrl+C

### Ralph Layouts

```
ralph layout:                  ralph-full layout:
┌──────────┬──────────┐       ┌──────────┬──────────┐
│          │ cctmux-  │       │          │ cctmux-  │
│  shell   │ ralph    │       │  shell   │ ralph    │
│  60%     │   40%    │       │  60%     ├──────────┤
│          │          │       │          │ cctmux-  │
│          │          │       │          │ tasks    │
└──────────┴──────────┘       └──────────┴──────────┘
```

Start with a Ralph layout:
```bash
cctmux -l ralph
# In the left shell pane:
cctmux-ralph start ralph-project.md -m 20 -c "All tests passing"
```

### State File

State is stored at `$PROJECT/.claude/ralph-state.json` and tracks:
- Current status (active, completed, cancelled, max_reached, error)
- Iteration count and results (tokens, cost, duration, tools)
- Task progress (completed/total)
- Per-iteration details for the monitor dashboard

## Configuration

cctmux supports configuration via YAML file at `~/.config/cctmux/config.yaml`.

### Configuration File Structure

```yaml
# Default Claude arguments
default_claude_args: ""

# Default layout (default, editor, monitor, triple, cc-mon, full-monitor, dashboard)
default_layout: default

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
  show_acceptance: true
  show_work_log: false
  max_tasks: 100

# Activity monitor settings
activity_monitor:
  default_days: 14
  show_heatmap: true
  show_cost: true
  show_model_usage: true
  show_hour_distribution: false
```

### Configuration Presets

All monitors support `--preset` for quick configuration:

| Preset | Description |
|--------|-------------|
| `minimal` | Essential info only, reduced visual noise |
| `verbose` | All information displayed, including optional fields |
| `debug` | Maximum detail for troubleshooting |

```bash
cctmux-session --preset minimal
cctmux-tasks --preset verbose
cctmux-activity --preset debug
```

CLI flags override both config file and preset values.

## Troubleshooting

### "Not in cctmux session"

If `$CCTMUX_SESSION` is not set, you're not in a cctmux-managed session. Either:
1. Start a new session with `cctmux`
2. Use standard tmux commands without the session variable

### "Can't split window: pane too small"

The terminal is too small for more splits. Either:
1. Resize the terminal window
2. Close existing panes before creating new ones
3. Use smaller split percentages

### Process Not Starting

If a command doesn't start in the new pane:
1. Check the command syntax
2. Verify the working directory
3. Use `tmux capture-pane -p -t "$CCTMUX_SESSION:$W.N"` to see pane output
