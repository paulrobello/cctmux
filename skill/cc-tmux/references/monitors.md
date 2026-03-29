# Monitor Tools Reference

cctmux includes five monitor CLI tools for real-time visibility into Claude Code sessions.

## Task Monitor

`cctmux-tasks` visualizes Claude Code tasks with their dependencies. Useful for monitoring complex multi-step operations.

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

# Show only stats panel (no graph or table)
cctmux-tasks -s

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

`cctmux-session` displays Claude Code session activity including tool calls, thinking blocks, and token usage.

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

`cctmux-activity` displays usage statistics from Claude Code's stats cache, including token usage, cost estimates, and activity patterns.

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

## Git Monitor

`cctmux-git` displays repository status including branch info, file changes, recent commits, and diff statistics.

### Running the Git Monitor

```bash
# Monitor current project directory
cctmux-git

# Monitor a specific repository
cctmux-git -p /path/to/repo

# Hide recent commits panel
cctmux-git --no-log

# Hide diff stats panel
cctmux-git --no-diff

# Show 20 recent commits
cctmux-git -m 20

# Enable periodic remote fetch to check for new remote commits
cctmux-git --fetch

# Fetch every 30 seconds (default: 60s)
cctmux-git --fetch -F 30

# Use a preset configuration
cctmux-git --preset minimal
cctmux-git --preset verbose
```

### Git Monitor in a Pane

Run the git monitor alongside your work:

```bash
# Create pane for git monitor, capture its ID
GIT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 40)
tmux send-keys -t "$GIT_PANE" "cctmux-git" Enter

# With remote tracking enabled
GIT_PANE=$(tmux split-window -d -P -F "#{pane_id}" -t "$CCTMUX_SESSION" -h -p 40)
tmux send-keys -t "$GIT_PANE" "cctmux-git --fetch" Enter
```

### Display Features

- **Branch Panel**: Branch name, upstream tracking, ahead/behind counts, stash count, last commit
- **Files Panel**: Changed files with status indicators (staged in green, unstaged in yellow, untracked in dim)
- **Remote Commits Panel**: Commits on the remote not yet in the local branch, with fetch timestamp (shown when `--fetch` is enabled)
- **Recent Commits Panel**: Commit hash, message, author, and relative timestamp
- **Diff Stats Panel**: Per-file insertion/deletion counts with visual bars

## Subagent Monitor

`cctmux-agents` tracks activity across all Claude Code subagents spawned during a session. Useful for monitoring parallel task execution and understanding subagent workload.

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

# AI-summarize each agent's initial prompt via claude haiku (done once per agent)
cctmux-agents --summarize
cctmux-agents -S

# Hide agents inactive for more than 10 minutes (default 300s); 0 = show all
cctmux-agents -t 600
cctmux-agents -t 0

# Limit table to 5 agents (0 = unlimited)
cctmux-agents -M 5
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
- **Agent Table**: Agent ID + task description, model, duration, tokens (in->out), top tools, current activity
- **Activity Panel**: Recent activities across all agents with timestamps and agent IDs
- **Status Indicators**: `○` unknown, `◐` active, `●` completed
- **Real-time Updates**: Polls agent files and updates display automatically
- **Auto Detection**: Automatically discovers new subagents as they spawn

### Subagent Information

Each subagent displays:
- **Agent Name**: When multiple agents share the same session slug, shows `<agent-id> · <task>` where task is either the first 64 chars of the initial prompt or an AI-generated summary (with `--summarize`)
- **Model**: The Claude model being used (haiku, sonnet, opus)
- **Duration**: How long the agent has been running
- **Tokens**: Input and output token counts
- **Tools**: Most frequently used tools with counts
- **Current Activity**: Latest tool call, thinking, or text output

### Task Summarization (`--summarize`)

When `--summarize` / `-S` is passed, each newly discovered agent's initial prompt is sent once to `claude-haiku` to generate a concise <=64-character summary of what the agent was asked to do. This runs in a background thread pool (up to 4 concurrent summarizations) and the display updates automatically when summaries arrive. Without this flag, the first 64 characters of the raw initial prompt are shown as a fallback.

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

## Configuration Presets

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
