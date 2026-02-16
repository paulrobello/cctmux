# Changelog

All notable changes to cctmux will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
