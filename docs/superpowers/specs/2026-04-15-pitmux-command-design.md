# pitmux Command — Design

**Date:** 2026-04-15
**Status:** Approved (pending spec review)

## Summary

Add a new `pitmux` CLI entry point to cctmux that launches the `pi` coding
agent inside a tmux session, mirroring the core behavior of `cctmux` but
trimmed to features that make sense for pi. Sessions are prefixed (default
`pi-`) so `cctmux` and `pitmux` can coexist for the same project.

## Motivation

cctmux currently assumes Claude Code is the only agent worth launching in a
tmux session. The `pi` CLI provides a compatible experience (interactive
agent, `--continue`/`--resume` flags, system prompts) and users want the same
tmux-session ergonomics for it. Forking the project or running pi by hand
each time is wasteful; a sibling command keeps the implementation shared and
the UX consistent.

## Scope

### In scope
- New `pitmux` command that launches `pi` in a project-named tmux session
- Support the following flags (mirrored from `cctmux`):
  - `--layout/-l`, `--recent/-R`, `--resume/-r`, `--continue/-c`
  - `--status-bar/-s`, `--debug/-D`, `--verbose/-v`, `--dry-run/-n`
  - `--config/-C`, `--dump-config`, `--strict`, `--version`
  - `--pi-args/-a` (raw args passed to `pi`)
- Configurable session prefix (default `pi-`) so cctmux and pitmux sessions
  don't collide
- Two new config fields on the existing `Config` model:
  `default_pi_args`, `pi_session_prefix`
- Shared config concepts with cctmux: `default_layout`, `status_bar_enabled`,
  `custom_layouts`, `max_history_entries`
- Bundled `pi-tmux` skill auto-synced to `~/.pi/agent/skills/pi-tmux/` on
  every `pitmux` invocation (directory tree auto-created if missing)
- Session history tracking (pi sessions appear in `--recent` picker
  alongside claude sessions, distinguishable by prefix)

### Out of scope
- `--yolo` / skip-permissions flag (pi does not need this)
- `--task-list-id`, `--agent-teams` (Claude Code-specific env vars)
- Team mode (`pitmux team`) — deferred
- Companion monitors (`pitmux-tasks`, `pitmux-session`, etc.) — pi's session
  format differs from Claude's; monitors would need new parsers, deferred
- Subcommands other than the main callback (e.g., no `pitmux install-skill`
  or `pitmux init-config` for now — skill auto-syncs, config editing uses
  `cctmux init-config`)

## Architecture

### New CLI entry point

Register in `pyproject.toml`:

```toml
[project.scripts]
pitmux = "cctmux.__main__:pi_app"
```

Define `pi_app` in `src/cctmux/__main__.py` as a new `typer.Typer` instance
with an `invoke_without_command=True` callback. The callback mirrors the
structure of the existing `cctmux` `main()` callback but:
- Drops the out-of-scope flags listed above
- Uses `--pi-args` instead of `--claude-args`
- Calls `create_pi_session()` (new) instead of `create_session()`
- Calls `_sync_pi_skill()` (new) instead of `_sync_skill()`
- Reads `config.default_pi_args` and `config.pi_session_prefix`

### Session naming

```
session_name = sanitize(prefix + project_name)
```

- `prefix` comes from `config.pi_session_prefix` (default `"pi-"`)
- `project_name` comes from `get_project_name(project_dir)` as today
- `sanitize_session_name()` is reused as-is (lowercases, replaces special
  chars with hyphens, collapses runs of hyphens)

Examples:
- `~/Repos/cctmux` → `pi-cctmux`
- prefix set to `""` → `cctmux` (collides with cctmux session — user's
  choice)

### Config additions

Two new fields on the existing `Config` model in `src/cctmux/config.py`:

```python
default_pi_args: str | None = Field(default=None)
pi_session_prefix: str = Field(default="pi-")
```

Both flat (top-level), following the approved flat-config design. No nested
`pi:` section.

Project-level config files (`.cctmux.yaml`, `.cctmux.yaml.local`) pick these
fields up automatically via the existing deep-merge loader. No changes to
`load_config()`.

### Launch mechanics

New function in `src/cctmux/tmux_manager.py`:

```python
def create_pi_session(
    session_name: str,
    project_dir: Path,
    layout: LayoutType | str = LayoutType.DEFAULT,
    status_bar: bool = False,
    pi_args: str | None = None,
    custom_layouts: list[CustomLayout] | None = None,
    dry_run: bool = False,
) -> list[str]:
    ...
```

Behavior — almost identical to `create_session()`, with these differences:
- Launches `pi` instead of `claude` in the main pane
- Sets only `CCTMUX_SESSION` and `CCTMUX_PROJECT_DIR` env vars (no
  `CLAUDE_CODE_TASK_LIST_ID`, no `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`)
- Accepts `pi_args` (raw args appended to the `pi` command)

`--resume` and `--continue` are translated by the CLI callback into
`pi_args` additions (e.g., `"--resume"`, `"--continue"`), exactly as
`cctmux` already does for claude.

`attach_session()` is reused as-is — it takes only a session name and
doesn't care what's running inside.

### Skill sync

Bundled skill lives at:

```
src/cctmux/skill-pi/pi-tmux/
├── SKILL.md
└── references/          # (only if needed; optional)
```

Content adapted from `cc-tmux` (pi-specific language, drops Claude
slash-command references that don't apply). This is option (b) from the
approved skill-content sub-question.

New function in `__main__.py`:

```python
def _sync_pi_skill() -> None:
    """Auto-install bundled pi skills to ~/.pi/agent/skills/."""
    ...
```

Implementation mirrors `_sync_skill()`:
- Source: `Path(__file__).parent / "skill-pi"`
- Destination: `Path.home() / ".pi" / "agent" / "skills"`
- Creates the destination tree (`~/.pi/agent/skills/`) if missing
- Content-hash comparison to decide whether to rewrite
- Silent no-op when already in sync; one-line notice on update

Called from `pi_app` callback (analogous to `_sync_skill()` in `main()`).

The existing `_sync_skill()` is untouched — Claude skills continue to go to
`~/.claude/skills/`.

### Session history

Reuses existing `session_history.py` as-is. Pi sessions are added via
`add_or_update_entry()` with the prefixed session name, so `--recent`
picker shows them alongside claude sessions. Users can visually distinguish
by the `pi-` prefix.

No schema changes to `history.yaml`.

### Dry-run

Full dry-run parity with `cctmux`: `--dry-run/-n` prints the tmux commands
that would execute and skips `subprocess.run()` calls, just like
`create_session()`. History is not updated on dry runs.

## Data Flow

```
pitmux [flags]
  → _sync_pi_skill()           # mirror bundled skill into ~/.pi/agent/skills/
  → load_config()              # picks up default_pi_args, pi_session_prefix
  → compute session name       # prefix + sanitized project name
  → session_exists()?
      yes → attach_session()
      no  → create_pi_session(): new-session, set env, launch pi, apply layout
  → add_or_update_entry() in history (if not dry-run)
```

## Error Handling

Reuses cctmux's existing patterns:
- Refuse to run if already inside tmux (`is_inside_tmux()` check)
- Validate layout name against built-in and custom layouts; exit 1 with a
  helpful message if unknown
- Strict mode (`--strict`) exits 1 on config warnings
- Missing `pi` binary: left to the shell — tmux will show the failure in
  the pane, same as `cctmux` behaves today when `claude` is missing (no
  pre-flight check in current code, keep parity)

## Testing

New `tests/test_pitmux.py` covering:
- Session name prefixing (default `pi-`, empty prefix, custom prefix)
- pi command construction (base, with `--pi-args`, with `--continue`, with
  `--resume`, combinations)
- Config field defaults and loading (`default_pi_args`, `pi_session_prefix`)
- `create_pi_session()` dry-run output includes `pi` not `claude`
- `create_pi_session()` dry-run output does NOT include
  `CLAUDE_CODE_TASK_LIST_ID` or `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
- `_sync_pi_skill()` creates destination tree when missing
- `_sync_pi_skill()` writes files when source/dest content hashes differ
- `_sync_pi_skill()` is a no-op when already in sync

Existing cctmux tests remain untouched and must still pass.

## Documentation Updates

Per CLAUDE.md Change Checklist:
- `docs/CLI_REFERENCE.md` — new `pitmux` section with flags table and
  examples
- `docs/CONFIGURATION.md` — document `default_pi_args` and
  `pi_session_prefix` fields; add example YAML
- `README.md` — mention pitmux in the overview and quickstart (short
  paragraph, link to CLI_REFERENCE)
- `docs/ARCHITECTURE.md` — add `pi_app` to the entry-points list and
  `create_pi_session()` to tmux_manager description
- Skill file at `src/cctmux/skill-pi/pi-tmux/SKILL.md` is itself
  documentation and ships with the package

## Risks and Tradeoffs

- **Shared history file** — pi and claude sessions land in the same
  `history.yaml`. Benefit: one `--recent` picker. Risk: growing list if
  both are used heavily. Mitigation: existing `max_history_entries` caps
  total. No per-agent filtering needed for MVP.
- **Shared `CCTMUX_*` env var names** — pi panes will see
  `CCTMUX_SESSION` / `CCTMUX_PROJECT_DIR`. Semantically these refer to the
  tmux session (agent-agnostic), so this is fine. Future work could
  introduce `PITMUX_*` aliases if confusion arises.
- **Skill fork vs. share** — we copy cc-tmux content into a new pi-tmux
  skill. Future cc-tmux updates won't flow automatically. Acceptable: the
  core tmux patterns are stable, and the pi-tmux skill needs pi-specific
  guidance anyway.
- **Session prefix collision** — if a user sets `pi_session_prefix: ""`,
  pitmux and cctmux will fight over the same session name. This is the
  user's explicit choice; document the caveat in CONFIGURATION.md.
