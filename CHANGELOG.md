# Changelog

All notable changes to cctmux will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.8] - 2026-02-18

### Changed

- **Auto-sync skill on invocation**: `cctmux` now automatically installs or updates the bundled `cc-tmux` skill on every invocation by comparing content hashes against `~/.claude/skills/cc-tmux/`. A one-line notice is printed only when an update is applied. This means `uv tool upgrade cctmux` keeps the skill in sync without a manual `cctmux install-skill` step.
- **`make upgrade` simplified**: The `upgrade` Makefile target no longer calls `cctmux install-skill` since the skill is now synced automatically on next run.

## [0.2.7] - 2026-02-18

### Added

- **TodoWrite Task Monitor Support**: `cctmux-tasks` now detects and displays tasks from `~/.claude/todos/` (the `TodoWrite` format used by `claude -p` sessions), in addition to the cctmux `TaskCreate` directory format. Session auto-detection scans JSONL files to match todos to the current project even when sessions are not indexed.

### Changed

- **Ralph Loop One-Task-Per-Iteration**: System prompt now explicitly instructs Claude to work on exactly one task per iteration ("Work on EXACTLY ONE task — the next incomplete task only"). This ensures each task gets a fresh context window.

## [0.2.6] - 2026-02-18

### Added

- **`make upgrade` target**: New Makefile target that runs `uv tool upgrade cctmux --reinstall` followed by `cctmux install-skill` for quick in-place upgrades

## [0.2.5] - 2026-02-17

### Added

- **Ralph Loop Graceful Stop** (`cctmux-ralph stop`): Signal the loop to exit cleanly after the current iteration finishes, without killing the running subprocess
- **Ralph Loop Iteration Timeout** (`--timeout`, `-t`): Maximum seconds per iteration; subprocess is killed on timeout and the loop continues to the next iteration
- **Ralph Loop Yolo Mode** (`--yolo`, `-y`): Pass `--dangerously-skip-permissions` to claude invocations, allowing the agent to perform git operations without permission prompts
- **Ralph Subprocess Task Discovery**: `CLAUDE_CODE_TASK_LIST_ID` is now derived from `CCTMUX_SESSION` when not explicitly set, so the task monitor can find tasks created by Ralph subprocesses

### Changed

- **Ralph Loop Subprocess Monitoring**: Replaced blocking `subprocess.run` with `subprocess.Popen` for real-time process monitoring, periodic state file updates (every 5s), and mid-iteration task progress tracking
- **Ralph Monitor Dynamic Panel Sizing**: Task progress panel capped at 10 items with iterations table given priority, preventing the task list from dominating the display
- **Ralph Monitor Active Refresh**: Display now refreshes continuously when the loop is active or stopping, ensuring the elapsed timer ticks accurately
- **Ralph Subcommand Names**: Removed `ralph-` prefix from subcommands (`ralph-start` → `start`, `ralph-init` → `init`, etc.)

### Fixed

- **Ralph Token Usage Parsing**: Fixed parsing of Claude CLI JSON output which changed `cost_usd` to `total_cost_usd` and moved token counts into a nested `usage` dict
- **Ralph Stop/Cancel Signal Race Condition**: The mid-iteration polling loop was saving state (with `status: active`) before reading the state file for external signals, overwriting any `stopping` or `cancelled` status written by `cctmux-ralph stop` or `cctmux-ralph cancel`. Now reads external signals first and skips saving if a signal is detected
- **Ralph State Permission Mode with Yolo**: When `--yolo` is used, the state file now records `dangerously-skip-permissions` instead of the default `acceptEdits`, accurately reflecting the actual permission mode passed to Claude

## [0.2.3] - 2026-02-16

### Fixed

- **Subagent Monitor Timezone Bug**: Inactive agent filtering compared local-naive time against UTC-naive timestamps, causing completed agents to never be filtered out for users west of UTC

### Changed

- Removed "Press Ctrl+C to exit" messages from all monitors — redundant since Ctrl+C is standard terminal behavior

## [0.2.2] - 2026-02-16

### Added

- **Agent Teams Support** (`--agent-teams`, `-A`): New flag to enable Claude Code's experimental agent teams feature by setting `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` environment variable
- **Agent Teams Config**: Added `agent_teams` boolean field to config model for persistent agent teams setting

## [0.2.1] - 2026-02-15

### Fixed

- **Git Monitor Panel Overflow**: File status, diff stats, and remote commits panels now cap displayed items to prevent pushing other panels off screen when many files are changed
- **Subagent Monitor Panel Overflow**: Agent table now caps displayed rows to prevent overflow with many subagents

### Added

- **Git Monitor `--max-files` / `-M`**: Limit files shown in status and diff panels (default: 20, 0 for unlimited)
- **Subagent Monitor `--max-agents` / `-M`**: Limit agents shown in the table (default: 20, 0 for unlimited)
- **`max_files` config field**: `git_monitor.max_files` in config and presets (minimal: 15, default: 20, verbose: 30, debug: 50)
- Truncated panels show "... and N more" indicator with accurate total counts in subtitles

## [0.2.0] - 2026-02-14

### Added

- **Project-Level Configuration**: Layered config loading from `.cctmux.yaml` (shared/committed) and `.cctmux.yaml.local` (personal/gitignored) in the project directory. Deep merge preserves sibling fields from parent configs. Set `ignore_parent_configs: true` to skip user config entirely.
- **Git Monitor** (`cctmux-git`): Real-time git repository status monitor with branch info, file status, recent commits, and diff statistics
- **Git-Mon Layout**: New `git-mon` layout providing Claude (60%) + git status monitor (40%) side-by-side
- **Git Monitor Configuration**: `git_monitor` section in config with `show_log`, `show_diff`, `show_status`, `max_commits`, and `poll_interval` settings
- **Git Monitor Presets**: Minimal, verbose, and debug presets for `cctmux-git`
- **Git Monitor Remote Fetch**: Opt-in periodic remote fetch with `--fetch` flag to check for new remote commits, configurable interval via `--fetch-interval` (default 60s), and new Remote Commits panel
- **Saved Layouts in Skill**: Claude can now save, recall, list, and delete custom pane layouts stored as YAML comment blocks in the config file
- **Yolo Mode** (`--yolo`, `-y`): Shortcut flag to append `--dangerously-skip-permissions` to the Claude invocation
- **Resume Mode** (`--resume`, `-r`): Shortcut flag to append `--resume` to the Claude invocation to continue the last conversation
- **Continue Mode** (`--continue`, `-c`): Shortcut flag to append `--continue` to the Claude invocation to continue the most recent conversation

### Changed

- **Recent Sessions**: Short flag changed from `-r` to `-R` to free `-r` for `--resume`
- **Config Path**: Short flag changed from `-c` to `-C` to free `-c` for `--continue`
- **Saved Layout Discovery in Skill**: Claude proactively checks the config file for saved layouts and presents them as options when users ask about pane management
- **Par Mode**: Updated to use task monitor + git monitor (previously used session monitor + task monitor), Claude pane width adjusted to 50%

### Fixed

- Resolved pyright strict mode issues in git_monitor dataclass fields
- **Install Skill**: Bundled skill files inside the package for wheel installs — previously the skill source path resolved relative to the repo root, which doesn't exist when installed via pip/uv

## [0.1.0] - 2026-02-06

### Added

- **Session Management**: Create and attach to tmux sessions named after project folders
- **Predefined Layouts**: 9 layouts (default, editor, monitor, triple, cc-mon, full-monitor, dashboard, ralph, ralph-full)
- **Task Monitor** (`cctmux-tasks`): Real-time task monitoring with ASCII dependency graphs and virtual scrolling
- **Session Monitor** (`cctmux-session`): Live session event monitoring with tool calls, thinking blocks, token usage, and cost estimates
- **Subagent Monitor** (`cctmux-agents`): Track subagent activity across parallel tasks
- **Activity Dashboard** (`cctmux-activity`): Usage statistics with heatmaps, model usage tables, and hourly distribution
- **Ralph Loop** (`cctmux-ralph`): Automated iterative Claude Code execution with task tracking and completion detection
- **Ralph Monitor**: Live dashboard for Ralph Loop progress, iterations, and cost tracking
- **Claude Skill**: cc-tmux skill for Claude to manage tmux panes with pane ID targeting
- **Configuration System**: YAML-based config with presets (default, minimal, verbose, debug)
- **Session History**: Track recent sessions with fzf integration for quick switching
- **Status Bar**: Optional tmux status bar showing git branch and project info
- **Dry Run Mode**: Preview tmux commands without executing
- **Environment Variables**: `CCTMUX_SESSION`, `CCTMUX_PROJECT_DIR`, optional `CLAUDE_CODE_TASK_LIST_ID`
- **Path Compression**: Replace home directory with `~` in display output
- **XDG Compliance**: Config and data stored in XDG-compliant locations

### Fixed

- Downgraded Python requirement from 3.14 to 3.13 for broader compatibility
