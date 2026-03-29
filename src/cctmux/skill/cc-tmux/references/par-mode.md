# Par Mode Reference

Par mode sets up a triple layout with a compact task stats panel (pane 2) and git monitor (pane 3). It checks the current layout and only reconfigures if needed.

## Activating Par Mode

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

# Check if already in par-mode (3 panes with task monitor and git monitor)
HAS_TASK_MON=$(echo "$PANE_INFO" | grep -c "cctmux-tasks" || true)
HAS_GIT_MON=$(echo "$PANE_INFO" | grep -c "cctmux-git" || true)

if [ "$PANE_COUNT" -eq 3 ] && [ "$HAS_TASK_MON" -ge 1 ] && [ "$HAS_GIT_MON" -ge 1 ]; then
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
    tmux send-keys -t "$SIDE1" "cctmux-tasks -s" Enter

    tmux send-keys -t "$SIDE2" C-c
    sleep 0.3
    tmux send-keys -t "$SIDE2" "cctmux-git" Enter

    echo "Par mode activated (reused existing panes)"
    exit 0
fi

# Kill extra panes, keeping ONLY the main Claude pane
# NEVER use kill-pane -a — it can kill the main pane if it's not active
if [ "$PANE_COUNT" -gt 1 ]; then
    for PANE_ID in $(echo "$PANE_INFO" | grep -v "^${MAIN_PANE}:" | cut -d: -f1); do
        tmux kill-pane -t "$PANE_ID"
    done
fi

# Create triple layout: main (50%) | right column split vertically (50%)
# Split horizontally with 50% on the right, capture pane ID
RIGHT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 50)

# Launch stats-only task monitor in the right pane (compact single-line display)
tmux send-keys -t "$RIGHT_PANE" "cctmux-tasks -s" Enter

# Split right pane vertically — tasks stays on top (3 rows), git gets the rest
BOTTOM_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$RIGHT_PANE" -v -p 93)

# Launch git monitor in the bottom-right pane
tmux send-keys -t "$BOTTOM_PANE" "cctmux-git" Enter

echo "Par mode activated"
```

## Par Mode Layout

```
---------------------------------
|            | cctmux-tasks -s  |
|  CLAUDE    |------------------|
|   50%      |                  |
|            | cctmux-git  93%  |
|            |                  |
---------------------------------
```
