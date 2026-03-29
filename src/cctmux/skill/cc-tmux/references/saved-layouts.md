# Saved Layouts Reference

> **Note:** cctmux now supports CLI-managed custom layouts via `cctmux layout add/edit/remove/list`. These are stored as proper YAML in the `custom_layouts` config field and can be used with `cctmux -l <name>`. The in-session saved layout system described below is an additional complementary mechanism for quickly saving/recalling pane arrangements during a session.

**Proactive guidance**: When a user asks about pane management, layouts, or setting up their workspace, let them know they can:
- **Save** the current layout (or describe a new one) with a name for later reuse
- **Restore** a previously saved layout by name
- **List** all saved layouts to see what's available
- **Delete** saved layouts they no longer need

## Check for Existing Saved Layouts (DO THIS FIRST)

**Before creating or modifying pane layouts**, always check the config file for existing saved layouts and present them as options to the user. This avoids recreating layouts that already exist.

```bash
# Check for saved layouts in the config file
grep -A1 '^# --- saved-layout:' ~/.config/cctmux/config.yaml 2>/dev/null
```

If saved layouts exist, present them to the user in a table like:

| Saved Layout | Description |
|--------------|-------------|
| `dev-monitor` | Task monitor + git monitor side by side |
| `dev-test` | Dev server on right, test runner below it |

Then ask: *"Would you like to activate one of these saved layouts, or set up something different?"*

If no saved layouts exist, inform the user: *"You don't have any saved layouts yet. I can set up panes for you now, and if you like the arrangement, I can save it for easy recall later."*

## Storage Format

Saved layouts are stored as YAML comment blocks at the end of `~/.config/cctmux/config.yaml`.

## Comment Block Format

Each saved layout is a comment block with a structured format. The block starts with `# --- saved-layout: <name> ---` and ends with `# --- end-saved-layout ---`. Inside, each pane is described with its split direction, size percentage, and the command to run.

```yaml
# --- saved-layout: dev-monitor ---
# description: Task monitor + git monitor side by side
# panes:
#   - split: h, size: 50, command: cctmux-tasks -g
#   - split: v, size: 50, target: prev, command: cctmux-git
# --- end-saved-layout ---
```

**Field definitions**:
- `split`: `h` (horizontal/right) or `v` (vertical/below)
- `size`: percentage of the split given to the new pane
- `target`: which pane to split from — `main` (default, splits from Claude pane) or `prev` (splits the previously created pane)
- `command`: the shell command to run in the new pane (empty string for a bare shell)

## Saving a Layout

When the user asks to save the current layout or describes a layout to save:

1. **Capture current state** (if saving the current layout):
```bash
tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id}:#{pane_width}x#{pane_height}:#{pane_current_command}"
```

2. **Read the existing config file**:
```bash
cat ~/.config/cctmux/config.yaml
```

3. **Append the layout block** to the end of the file. If a layout with the same name already exists, replace it. Example:
```bash
cat >> ~/.config/cctmux/config.yaml << 'LAYOUT'

# --- saved-layout: dev-monitor ---
# description: Task monitor + git monitor side by side
# panes:
#   - split: h, size: 50, command: cctmux-tasks -g
#   - split: v, size: 50, target: prev, command: cctmux-git
# --- end-saved-layout ---
LAYOUT
```

4. **Confirm** to the user what was saved and how to recall it.

## Recalling a Layout

When the user asks to activate a saved layout by name:

1. **Read the config file** and find the matching `# --- saved-layout: <name> ---` block.

2. **Parse the pane definitions** from the comment block.

3. **Examine the current layout** before making changes — check how many panes exist, what commands are running, and whether the desired layout is already active.

4. **Execute the layout** using the safe pane management pattern below. The script is idempotent and **never kills the main Claude pane**.

```bash
if [ -z "$CCTMUX_SESSION" ]; then
    echo "Not in a cctmux session"
    exit 1
fi

# Identify the main Claude pane — NEVER send commands to or kill this pane
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")

# Get current pane info using pane IDs (stable identifiers)
PANE_INFO=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id}:#{pane_current_command}")
PANE_COUNT=$(echo "$PANE_INFO" | wc -l | tr -d ' ')

# --- Step 1: Check if desired layout is already active ---
# For each command in the saved layout, check if it's already running.
# Example for "dev-monitor" (cctmux-tasks + cctmux-git):
HAS_CMD1=$(echo "$PANE_INFO" | grep -c "cctmux-tasks" || true)
HAS_CMD2=$(echo "$PANE_INFO" | grep -c "cctmux-git" || true)
EXPECTED_PANES=3  # main + number of panes in saved layout

if [ "$PANE_COUNT" -eq "$EXPECTED_PANES" ] && [ "$HAS_CMD1" -ge 1 ] && [ "$HAS_CMD2" -ge 1 ]; then
    echo "Layout 'dev-monitor' already active"
    exit 0
fi

# --- Step 2: Reuse existing side panes if pane count matches ---
if [ "$PANE_COUNT" -eq "$EXPECTED_PANES" ]; then
    # Get all non-main pane IDs (preserve order)
    SIDE_PANES=$(echo "$PANE_INFO" | grep -v "^${MAIN_PANE}:" | cut -d: -f1)
    SIDE1=$(echo "$SIDE_PANES" | sed -n '1p')
    SIDE2=$(echo "$SIDE_PANES" | sed -n '2p')

    # Stop running processes and launch the desired commands
    tmux send-keys -t "$SIDE1" C-c
    sleep 0.3
    tmux send-keys -t "$SIDE1" "cctmux-tasks -g" Enter

    tmux send-keys -t "$SIDE2" C-c
    sleep 0.3
    tmux send-keys -t "$SIDE2" "cctmux-git" Enter

    echo "Layout 'dev-monitor' activated (reused existing panes)"
    exit 0
fi

# --- Step 3: Kill extra panes, keeping ONLY the main Claude pane ---
if [ "$PANE_COUNT" -gt 1 ]; then
    for PANE_ID in $(echo "$PANE_INFO" | grep -v "^${MAIN_PANE}:" | cut -d: -f1); do
        tmux kill-pane -t "$PANE_ID"
    done
fi

# --- Step 4: Create panes per the saved layout definition ---
# For each pane entry, determine the target and split:
#   target=main  -> split from MAIN_PANE
#   target=prev  -> split from the last created pane
# Example for "dev-monitor":
PANE1=$(tmux split-window -d -P -F "#{pane_id}" -t "$MAIN_PANE" -h -p 50)
tmux send-keys -t "$PANE1" "cctmux-tasks -g" Enter

PANE2=$(tmux split-window -d -P -F "#{pane_id}" -t "$PANE1" -v -p 50)
tmux send-keys -t "$PANE2" "cctmux-git" Enter

echo "Layout 'dev-monitor' activated"
```

**Critical safety rules**:
- **NEVER** use `tmux kill-pane -a` — it kills all panes including the main Claude pane if it's not the active one. Instead, enumerate non-main panes and kill them individually.
- **ALWAYS** identify the main pane first via `tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}"` and exclude it from all kill/send-keys operations.
- **ALWAYS** use `-d` flag on `split-window` to avoid stealing focus from the Claude pane.
- **Check before acting** — if the layout is already active, do nothing. If the pane count matches, reuse existing panes instead of destroying and recreating.

## Listing Saved Layouts

When the user asks what layouts are saved:

```bash
grep -E '^# --- saved-layout:' ~/.config/cctmux/config.yaml 2>/dev/null | sed 's/# --- saved-layout: //;s/ ---//'
```

## Deleting a Saved Layout

When the user asks to delete a saved layout, remove the entire block from `# --- saved-layout: <name> ---` through `# --- end-saved-layout ---` (inclusive) from the config file.

## Example Layouts

**Three-column with monitors**:
```yaml
# --- saved-layout: full-monitor ---
# description: Session monitor, task monitor, and git monitor
# panes:
#   - split: h, size: 50, command: cctmux-session
#   - split: v, size: 50, target: prev, command: cctmux-tasks -g
#   - split: v, size: 50, target: prev, command: cctmux-git
# --- end-saved-layout ---
```

**Dev server + tests**:
```yaml
# --- saved-layout: dev-test ---
# description: Dev server on right, test runner below it
# panes:
#   - split: h, size: 40, command: uv run dev
#   - split: v, size: 50, target: prev, command: uv run pytest --watch
# --- end-saved-layout ---
```

**Bare shells for ad-hoc work**:
```yaml
# --- saved-layout: workspace ---
# description: Two empty shells on the right
# panes:
#   - split: h, size: 40, command:
#   - split: v, size: 50, target: prev, command:
# --- end-saved-layout ---
```
