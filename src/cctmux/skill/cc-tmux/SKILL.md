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
| `ralph-full` | Claude + git monitor + ralph monitor |
| `git-mon` | Claude (60%) + git status monitor (40%) |

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

Par mode sets up a triple layout with task stats and git monitor. For the full idempotent activation script and layout diagram, read `references/par-mode.md` in this skill's directory.

## Saved Layouts

cctmux supports saving and recalling pane arrangements. For the full save/recall/delete workflow, storage format, safety rules, and example layouts, read `references/saved-layouts.md` in this skill's directory. When a user asks about layouts, check saved layouts first before creating new ones.

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

## Monitors

cctmux includes five monitor CLI tools: `cctmux-tasks` (task dependencies), `cctmux-session` (session events), `cctmux-activity` (usage dashboard), `cctmux-git` (repo status), and `cctmux-agents` (subagent tracking). For full CLI options, display features, and pane setup examples, read `references/monitors.md` in this skill's directory.

## Ralph Loop

The Ralph Loop (`cctmux-ralph`) is an automated iterative development engine. For project file format, CLI commands, completion detection, layouts, and state file details, read `references/ralph.md` in this skill's directory.

## Configuration

cctmux supports layered configuration:
1. **User config**: `~/.config/cctmux/config.yaml` — base settings
2. **Project config**: `.cctmux.yaml` in project root — shared team overrides (committed to repo)
3. **Project local config**: `.cctmux.yaml.local` in project root — personal overrides (gitignored)

Values are deep-merged (last wins). Set `ignore_parent_configs: true` in a project config to skip user config entirely.

### Configuration File Structure

```yaml
# Default Claude arguments
default_claude_args: ""

# Default layout (default, editor, monitor, triple, cc-mon, full-monitor, dashboard, ralph, ralph-full, git-mon)
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

## Team Mode

For team workflows (`cctmux team`), read `references/team.md` in this skill's directory for team-specific environment variables, agent configuration, and the skill prompt acceptance pattern. For team coordination (task delegation, messaging, progress tracking), load the **cc-team-lead** skill.

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
