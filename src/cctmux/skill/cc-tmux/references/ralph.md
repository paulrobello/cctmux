# Ralph Loop Reference

The Ralph Loop (`cctmux-ralph`) is an automated iterative development engine where Claude Code runs in a loop until a project is complete. Each iteration gets fresh context. The input is a structured markdown project file with task checklists.

## Creating a Project File

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

## Starting a Ralph Loop

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

## Monitoring a Running Loop

```bash
# Live dashboard (default when no subcommand given)
cctmux-ralph

# Monitor a specific project
cctmux-ralph -p /path/to/project

# Use verbose preset
cctmux-ralph --preset verbose
```

## Managing Loop Lifecycle

```bash
# Graceful stop — finish current iteration then exit
cctmux-ralph stop

# Cancel immediately (between iterations)
cctmux-ralph cancel

# Show one-shot status
cctmux-ralph status

# Target a specific project's loop
cctmux-ralph stop -p /path/to/project
cctmux-ralph cancel -p /path/to/project
```

## Completion Detection

The loop stops when any of these conditions are met:
1. **All checklist items checked**: All `- [ ]` items become `- [x]` in the project file
2. **Promise tag**: Claude outputs `<promise>completion text</promise>` matching the configured promise
3. **Max iterations**: Safety limit reached (if set with `--max-iterations`)
4. **Graceful stop**: User runs `cctmux-ralph stop` — finishes current iteration then exits with `completed` status
5. **Cancellation**: User runs `cctmux-ralph cancel` or presses Ctrl+C

## Ralph Layouts

```
ralph layout:                  ralph-full layout:
+----------+----------+       +----------+----------+
|          | cctmux-  |       |  CLAUDE   | cctmux-  |
|  shell   | ralph    |       |   50%     | ralph    |
|  60%     |   40%    |       |  ~12%h    |  ~77%h   |
|          |          |       +----------+|          |
|          |          |       | cctmux-  ||          |
|          |          |       | git      ||          |
+----------+----------+       |  ~88%h   ||          |
                              +----------+----------+
```

Start with a Ralph layout:
```bash
cctmux -l ralph
# In the left shell pane:
cctmux-ralph start ralph-project.md -m 20 -c "All tests passing"
```

Start with the ralph-full layout:
```bash
cctmux -l ralph-full
```

To manually set up the ralph-full layout:
```bash
# Identify main pane
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")

# Split main pane horizontally 50/50 — right column for ralph
RIGHT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$MAIN_PANE" -h -p 50)
tmux send-keys -t "$RIGHT_PANE" "cctmux-ralph" Enter

# Split main pane vertically — bottom-left ~88% for git monitor
BOTTOM_LEFT=$(tmux split-window -d -P -F "#{pane_id}" -t "$MAIN_PANE" -v -p 88)
tmux send-keys -t "$BOTTOM_LEFT" "cctmux-git" Enter
```

## State File

State is stored at `$PROJECT/.claude/ralph-state.json` and tracks:
- Current status (active, stopping, completed, cancelled, max_reached, error)
- Iteration count and results (tokens, cost, duration, tools)
- Task progress (completed/total)
- Permission mode (reflects actual mode, e.g. `dangerously-skip-permissions` when `--yolo` is used)
- Per-iteration details for the monitor dashboard
