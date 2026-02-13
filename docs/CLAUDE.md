Layout diagrams are exempt from being converted to mermaid diagrams in this folder.

When updating documentation in this folder, use the DOCUMENTATION_STYLE_GUIDE.md as the authoritative style reference. Key rules:

- Always use Mermaid for architecture/flow diagrams (except layout pane diagrams which use ASCII art)
- Use dark backgrounds with white text in Mermaid diagrams
- Do not include line numbers in file references
- Do not include package version numbers (reference pyproject.toml instead)
- Specify language in all code blocks
- Include Table of Contents for documents over 500 words
- Include a Related Documentation section at the end of each document

This project has seven CLI entry points defined in pyproject.toml:

| Entry Point | Typer App | Purpose |
|-------------|-----------|---------|
| `cctmux` | `app` | Main session launcher |
| `cctmux-tasks` | `tasks_app` | Task monitor |
| `cctmux-session` | `session_app` | Session event monitor |
| `cctmux-agents` | `agents_app` | Subagent monitor |
| `cctmux-activity` | `activity_app` | Usage dashboard |
| `cctmux-git` | `git_app` | Git repository status monitor |
| `cctmux-ralph` | `ralph_app` | Ralph Loop automation |

Source modules in `src/cctmux/`:

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package version |
| `__main__.py` | All seven Typer CLI apps |
| `config.py` | Pydantic config models, LayoutType enum, presets, YAML I/O |
| `session_history.py` | Session tracking with Pydantic, YAML persistence |
| `tmux_manager.py` | Session creation, attachment, environment setup, status bar |
| `layouts.py` | Ten predefined layout implementations |
| `task_monitor.py` | Parse task JSON, dependency graphs, Rich Live display |
| `session_monitor.py` | Parse JSONL events, statistics, Rich Live display |
| `subagent_monitor.py` | Discover and monitor subagent JSONL files |
| `activity_monitor.py` | Parse stats-cache.json, heatmaps, model usage |
| `ralph_runner.py` | Ralph Loop engine: state management, task parsing, claude invocation |
| `ralph_monitor.py` | Ralph Loop live dashboard: status, tasks, timeline, iterations |
| `git_monitor.py` | Real-time git status monitor |
| `xdg_paths.py` | XDG-compliant config/data paths |
| `utils.py` | Name sanitization, fzf integration, path compression |

Ten layout types: default, editor, monitor, triple, cc-mon, full-monitor, dashboard, ralph, ralph-full, git-mon.

Four config presets: default, minimal, verbose, debug.
