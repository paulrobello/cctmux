---
name: pi-tmux
description: Enables the pi coding agent to discover and manage tmux panes within a pitmux session. Use when running inside tmux to create panes for dev servers, file watchers, test runners, and other background processes.
---

# pi Tmux Session Awareness

This skill enables the pi coding agent to work effectively within tmux
sessions created by `pitmux` (part of the cctmux package).

## Philosophy

**Terminal as Workspace**: Tmux panes provide dedicated spaces for
background processes without cluttering the main conversation. Use panes
for development servers, file watchers, test runners in watch mode, build
processes, and log tailing.

**Visibility Over Convenience**: Processes in visible panes are easier to
monitor and debug than hidden background processes.

**Create Then Launch**: Always create panes first, then use `send-keys` to
launch applications. This ensures a clean shell environment and allows
easy process restart.

## Session Discovery

When running inside a `pitmux` session, these environment variables are
available:

```bash
$CCTMUX_SESSION      # The tmux session name (e.g., "pi-my-project")
$CCTMUX_PROJECT_DIR  # The project directory path
```

Verify you're in a pitmux session before tmux operations:

```bash
if [ -n "$CCTMUX_SESSION" ]; then
    echo "Running in tmux session: $CCTMUX_SESSION"
fi
```

## Pane Management

### Discover Window Index AND Pane IDs First (CRITICAL)

**Both the window index AND pane indices are NOT always 0.** pitmux
sessions may use window index 1 and pane indices starting at 1 or any
other value. Hardcoding `:0.0` will target the wrong pane or fail.

Always discover actual values before targeting panes:

```bash
# Get the window index
W=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{window_index}" | head -1)

# List all pane IDs with their running commands
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
```

### Prefer Pane IDs Over Positional Indices (CRITICAL)

**Pane IDs (e.g., `%15`, `%16`) are stable and unique.** Positional
indices (`.0`, `.1`) shift when panes are created or destroyed.

When creating new panes, capture the pane ID with `-d -P -F "#{pane_id}"`:

```bash
# -d = don't switch focus, -P -F = print the new pane's ID
NEW_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 30)
tmux send-keys -t "$NEW_PANE" "npm run dev" Enter
```

When targeting existing panes, look up pane IDs — never assume indices:

```bash
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
# Output: %15 pi   %16 bash   %17 bash
tmux send-keys -t "%16" "npm run dev" Enter
```

### Identify the Main (pi) Pane

The pane running `pi` is the one you're currently conversing in. Use
`list-panes` to confirm:

```bash
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
# The pane with "pi" as its current command is the main pane.
```

## Common Patterns

### Run a dev server in a side pane

```bash
DEV=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 40)
tmux send-keys -t "$DEV" "npm run dev" Enter
```

### Tail logs in a bottom pane

```bash
LOGS=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -v -p 25)
tmux send-keys -t "$LOGS" "tail -f app.log" Enter
```

### Restart a process in an existing pane

```bash
# Find the pane running the target process
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
# Send Ctrl-C, then re-run
tmux send-keys -t "%16" C-c
tmux send-keys -t "%16" "npm run dev" Enter
```

### Kill a pane when done

```bash
tmux kill-pane -t "%16"
```

## Do Not

- Hardcode pane indices (`:0.0`, `:0.1`, `.2`) — always discover IDs.
- Assume window index is `0` — discover it.
- Run destructive tmux operations (kill-session, kill-window) without
  explicit user approval.
- Create panes faster than the user can review them. Ask before spawning
  more than 2 new panes.
