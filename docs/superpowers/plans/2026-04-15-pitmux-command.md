# pitmux Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `pitmux` CLI entry point to cctmux that launches the `pi` coding agent inside a tmux session, mirroring core cctmux flags with a configurable session prefix so both can coexist for the same project.

**Architecture:** Extends the existing `Config` model with two flat fields (`default_pi_args`, `pi_session_prefix`), adds a `create_pi_session()` function in `tmux_manager.py`, a new Typer app `pi_app` in `__main__.py`, a `_sync_pi_skill()` helper targeting `~/.pi/agent/skills/`, and a bundled `pi-tmux` skill adapted from `cc-tmux`. No team mode, no companion monitors, no yolo flag.

**Tech Stack:** Python 3.13, Typer, Pydantic, Rich, pytest, uv, ruff, pyright (strict).

**Spec:** `docs/superpowers/specs/2026-04-15-pitmux-command-design.md`

---

## Task 1: Add `default_pi_args` and `pi_session_prefix` config fields

**Files:**
- Modify: `src/cctmux/config.py:208-234` (the `Config` class)
- Test: `tests/test_config.py` (append new test cases)

- [ ] **Step 1: Write the failing tests**

Open `tests/test_config.py` and add these tests inside `class TestConfig:` (just after `test_ignore_parent_configs_default`):

```python
    def test_default_pi_args_default(self) -> None:
        """default_pi_args should default to None."""
        config = Config()
        assert config.default_pi_args is None

    def test_default_pi_args_custom(self) -> None:
        """default_pi_args should accept a string."""
        config = Config(default_pi_args="--model anthropic/claude-sonnet-4-6")
        assert config.default_pi_args == "--model anthropic/claude-sonnet-4-6"

    def test_pi_session_prefix_default(self) -> None:
        """pi_session_prefix should default to 'pi-'."""
        config = Config()
        assert config.pi_session_prefix == "pi-"

    def test_pi_session_prefix_custom(self) -> None:
        """pi_session_prefix should accept custom strings, including empty."""
        assert Config(pi_session_prefix="my-").pi_session_prefix == "my-"
        assert Config(pi_session_prefix="").pi_session_prefix == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_config.py::TestConfig -v`

Expected: 4 new tests FAIL with `AttributeError` on `default_pi_args` / `pi_session_prefix`.

- [ ] **Step 3: Add the fields to the `Config` model**

Open `src/cctmux/config.py`. Locate the `Config` class (around line 208). After the `agent_teams: bool = False` line, add the two new fields:

```python
class Config(BaseModel):
    """Configuration settings for cctmux."""

    default_layout: LayoutType = LayoutType.DEFAULT
    status_bar_enabled: bool = False
    max_history_entries: int = 50
    default_claude_args: str | None = None
    task_list_id: bool = False
    agent_teams: bool = False

    # pitmux (launches the `pi` coding agent in a tmux session)
    default_pi_args: str | None = None
    pi_session_prefix: str = "pi-"

    # When true in a project config, ignore all parent configs (user config)
    ignore_parent_configs: bool = False
    # ... (rest unchanged)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_config.py::TestConfig -v`

Expected: All tests PASS (including the 4 new ones).

- [ ] **Step 5: Run formatters and type check**

Run: `uv run ruff format . && uv run ruff check --fix . && uv run pyright src/cctmux/config.py tests/test_config.py`

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add src/cctmux/config.py tests/test_config.py
git commit -m "feat(config): add default_pi_args and pi_session_prefix fields"
```

---

## Task 2: Add `create_pi_session()` to `tmux_manager.py`

**Files:**
- Modify: `src/cctmux/tmux_manager.py` (append new function after `create_session`)
- Test: `tests/test_tmux_manager.py` (append a new `class TestCreatePiSession`)

- [ ] **Step 1: Write the failing tests**

Open `tests/test_tmux_manager.py`. At the top, update the import from `cctmux.tmux_manager` to include `create_pi_session` (add it to the existing import list). For example:

```python
from cctmux.tmux_manager import (
    attach_session,
    configure_status_bar,
    create_pi_session,
    create_session,
    is_inside_tmux,
    list_panes,
    session_exists,
)
```

(Only add the names that aren't already imported. If the file uses individual `from ... import` lines, add `create_pi_session` in its own line.)

Then append this test class after `TestCreateSession`:

```python
class TestCreatePiSession:
    """Tests for create_pi_session function."""

    def test_dry_run_default_layout(self, tmp_path: Path) -> None:
        """Should return commands without executing in dry run."""
        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            dry_run=True,
        )
        assert len(commands) >= 5
        assert "new-session" in commands[0]
        assert "pi-test" in commands[0]
        assert str(tmp_path.resolve()) in commands[0]
        assert "CCTMUX_SESSION" in commands[1]
        assert "CCTMUX_PROJECT_DIR" in commands[2]
        # The launched command must be `pi`, not `claude`
        pi_cmds = [c for c in commands if " pi" in c or c.endswith(" pi Enter")]
        assert any(" pi " in c or c.rstrip().endswith(" pi") or c.endswith(" pi Enter") for c in commands)
        assert not any("claude" in c for c in commands)
        assert "attach-session" in commands[-1]

    def test_dry_run_with_pi_args(self, tmp_path: Path) -> None:
        """Should include pi args in the launch command."""
        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            pi_args="--model anthropic/claude-sonnet-4-6",
            dry_run=True,
        )
        pi_launch = [c for c in commands if "pi --model anthropic/claude-sonnet-4-6" in c]
        assert len(pi_launch) >= 1

    def test_dry_run_with_continue_and_resume(self, tmp_path: Path) -> None:
        """pi_args may carry --continue or --resume flags verbatim."""
        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            pi_args="--continue",
            dry_run=True,
        )
        assert any("pi --continue" in c for c in commands)

        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            pi_args="--resume",
            dry_run=True,
        )
        assert any("pi --resume" in c for c in commands)

    def test_dry_run_no_claude_env_vars(self, tmp_path: Path) -> None:
        """Must not set CLAUDE_CODE_TASK_LIST_ID or CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS."""
        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            dry_run=True,
        )
        assert not any("CLAUDE_CODE_TASK_LIST_ID" in c for c in commands)
        assert not any("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in c for c in commands)

    def test_dry_run_with_status_bar(self, tmp_path: Path) -> None:
        """Should include status bar commands when enabled."""
        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            status_bar=True,
            dry_run=True,
        )
        status_cmds = [c for c in commands if "status-style" in c or "status-left" in c or "status-right" in c]
        assert len(status_cmds) >= 3

    def test_dry_run_with_editor_layout(self, tmp_path: Path) -> None:
        """Should include layout split commands."""
        commands = create_pi_session(
            session_name="pi-test",
            project_dir=tmp_path,
            layout=LayoutType.EDITOR,
            dry_run=True,
        )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_tmux_manager.py::TestCreatePiSession -v`

Expected: All tests FAIL with `ImportError` on `create_pi_session`.

- [ ] **Step 3: Implement `create_pi_session()`**

Open `src/cctmux/tmux_manager.py`. Locate the end of `create_session()` (around line 132). Insert the following function immediately after `create_session()` and before `_build_claude_cmd()`:

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
    """Create a new tmux session and launch the pi coding agent.

    Mirrors create_session but runs `pi` instead of `claude` and does not
    set Claude Code-specific env vars (CLAUDE_CODE_TASK_LIST_ID,
    CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS).

    Args:
        session_name: The session name.
        project_dir: The project directory.
        layout: The layout to apply (built-in or custom name).
        status_bar: Whether to enable status bar.
        pi_args: Additional arguments to pass to the pi command.
        custom_layouts: Optional list of custom layouts for name resolution.
        dry_run: If True, return commands without executing.

    Returns:
        List of commands that were (or would be) executed.
    """
    commands: list[str] = []
    dir_str = str(project_dir.resolve())

    # Create new session
    cmd = ["tmux", "new-session", "-d", "-s", session_name, "-c", dir_str]
    commands.append(" ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True)

    # Set environment variables at tmux session level (for new panes)
    env_cmd1 = ["tmux", "set-environment", "-t", session_name, "CCTMUX_SESSION", session_name]
    commands.append(" ".join(env_cmd1))
    if not dry_run:
        subprocess.run(env_cmd1, check=True)

    env_cmd2 = ["tmux", "set-environment", "-t", session_name, "CCTMUX_PROJECT_DIR", dir_str]
    commands.append(" ".join(env_cmd2))
    if not dry_run:
        subprocess.run(env_cmd2, check=True)

    # Export environment variables to the current shell in the main pane
    export_cmd = f"export CCTMUX_SESSION={session_name} CCTMUX_PROJECT_DIR={dir_str}"
    export_keys = ["tmux", "send-keys", "-t", session_name, export_cmd, "Enter"]
    commands.append(" ".join(export_keys))
    if not dry_run:
        subprocess.run(export_keys, check=True)

    # Launch pi in the main pane
    pi_cmd = "pi"
    if pi_args:
        pi_cmd = f"pi {pi_args}"
    send_cmd = ["tmux", "send-keys", "-t", session_name, pi_cmd, "Enter"]
    commands.append(" ".join(send_cmd))
    if not dry_run:
        subprocess.run(send_cmd, check=True)

    # Apply layout
    layout_commands = apply_layout(session_name, layout, dry_run, custom_layouts=custom_layouts)
    commands.extend(layout_commands)

    # Configure status bar if enabled
    if status_bar:
        status_commands = configure_status_bar(session_name, project_dir, dry_run)
        commands.extend(status_commands)

    # Attach to session
    attach_cmd = ["tmux", "attach-session", "-t", session_name]
    commands.append(" ".join(attach_cmd))
    if not dry_run:
        subprocess.run(attach_cmd, check=True)

    return commands
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_tmux_manager.py::TestCreatePiSession -v`

Expected: All 6 new tests PASS.

- [ ] **Step 5: Run the full tmux_manager test module to confirm no regressions**

Run: `uv run pytest tests/test_tmux_manager.py -v`

Expected: All tests (existing + new) PASS.

- [ ] **Step 6: Run formatters and type check**

Run: `uv run ruff format . && uv run ruff check --fix . && uv run pyright src/cctmux/tmux_manager.py tests/test_tmux_manager.py`

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add src/cctmux/tmux_manager.py tests/test_tmux_manager.py
git commit -m "feat(tmux): add create_pi_session for launching pi agent"
```

---

## Task 3: Create the bundled `pi-tmux` skill

**Files:**
- Create: `src/cctmux/skill-pi/pi-tmux/SKILL.md`

No tests — this is a data file. It is verified indirectly in Task 4 (skill sync) and Task 5 (CLI wiring).

- [ ] **Step 1: Create the skill directory**

Run: `mkdir -p src/cctmux/skill-pi/pi-tmux`

- [ ] **Step 2: Write `SKILL.md`**

Create `src/cctmux/skill-pi/pi-tmux/SKILL.md` with this content:

```markdown
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
```

- [ ] **Step 3: Verify the file was created**

Run: `ls src/cctmux/skill-pi/pi-tmux/SKILL.md && head -5 src/cctmux/skill-pi/pi-tmux/SKILL.md`

Expected: File lists, shows the frontmatter.

- [ ] **Step 4: Commit**

```bash
git add src/cctmux/skill-pi/pi-tmux/SKILL.md
git commit -m "feat(skill): bundle pi-tmux skill for pitmux sessions"
```

---

## Task 4: Add `_sync_pi_skill()` helper

**Files:**
- Modify: `src/cctmux/__main__.py` (add new function; do not touch `_sync_skill`)
- Create: `tests/test_pitmux.py` (new file, starting with sync tests)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pitmux.py` with this content:

```python
"""Tests for pitmux functionality."""

from pathlib import Path
from unittest.mock import patch

from cctmux.__main__ import _sync_pi_skill


class TestSyncPiSkill:
    """Tests for _sync_pi_skill function."""

    def test_creates_destination_tree_and_copies_skill(self, tmp_path: Path) -> None:
        """Should create ~/.pi/agent/skills/ if missing and copy bundled skills."""
        fake_home = tmp_path / "home"
        # Destination tree does NOT pre-exist.
        with patch("cctmux.__main__.Path.home", return_value=fake_home):
            _sync_pi_skill()
        dest = fake_home / ".pi" / "agent" / "skills" / "pi-tmux" / "SKILL.md"
        assert dest.exists(), f"Expected {dest} to exist after sync"
        content = dest.read_text(encoding="utf-8")
        assert "name: pi-tmux" in content

    def test_noop_when_already_in_sync(self, tmp_path: Path) -> None:
        """Second call should not rewrite files when content matches."""
        fake_home = tmp_path / "home"
        with patch("cctmux.__main__.Path.home", return_value=fake_home):
            _sync_pi_skill()
            dest = fake_home / ".pi" / "agent" / "skills" / "pi-tmux" / "SKILL.md"
            mtime_first = dest.stat().st_mtime_ns
            # Call again — should be a no-op.
            _sync_pi_skill()
            mtime_second = dest.stat().st_mtime_ns
        assert mtime_first == mtime_second, "Sync should not touch file when hashes match"

    def test_rewrites_on_content_change(self, tmp_path: Path) -> None:
        """Should rewrite the destination when source hash differs."""
        fake_home = tmp_path / "home"
        with patch("cctmux.__main__.Path.home", return_value=fake_home):
            _sync_pi_skill()
            dest = fake_home / ".pi" / "agent" / "skills" / "pi-tmux" / "SKILL.md"
            # Simulate drift: corrupt the installed copy.
            dest.write_text("stale content\n", encoding="utf-8")
            _sync_pi_skill()
        content = dest.read_text(encoding="utf-8")
        assert "name: pi-tmux" in content
        assert "stale content" not in content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pitmux.py::TestSyncPiSkill -v`

Expected: All tests FAIL with `ImportError` on `_sync_pi_skill`.

- [ ] **Step 3: Implement `_sync_pi_skill()`**

Open `src/cctmux/__main__.py`. Locate `_sync_skill()` (around line 64). Add the following function immediately after `_sync_skill()` and before `install_skill()`:

```python
def _sync_pi_skill() -> None:
    """Auto-install bundled pi skills to ~/.pi/agent/skills/ if missing or outdated.

    Compares the content hash of each bundled file against the installed copy.
    Creates the destination tree (~/.pi/agent/skills/) if it does not exist.
    Runs silently; prints a one-line notice only when an update is applied.
    Called automatically on every pitmux invocation.
    """
    import hashlib
    import shutil

    skill_base = Path(__file__).parent / "skill-pi"
    dest_base = Path.home() / ".pi" / "agent" / "skills"

    if not skill_base.exists():
        return

    def _md5(path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324

    for skill_src in skill_base.iterdir():
        if not skill_src.is_dir():
            continue
        skill_dest = dest_base / skill_src.name

        needs_update = False
        for src_file in skill_src.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(skill_src)
            dest_file = skill_dest / rel
            if not dest_file.exists() or _md5(src_file) != _md5(dest_file):
                needs_update = True
                break

        if needs_update:
            skill_dest.mkdir(parents=True, exist_ok=True)
            for src_file in skill_src.rglob("*"):
                if src_file.is_file():
                    rel = src_file.relative_to(skill_src)
                    dest_file = skill_dest / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dest_file)
            console.print(f"[dim]✓ {skill_src.name} skill updated ({skill_dest})[/]")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_pitmux.py::TestSyncPiSkill -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Run formatters and type check**

Run: `uv run ruff format . && uv run ruff check --fix . && uv run pyright src/cctmux/__main__.py tests/test_pitmux.py`

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add src/cctmux/__main__.py tests/test_pitmux.py
git commit -m "feat(skill): add _sync_pi_skill to install pi-tmux to ~/.pi/agent/skills"
```

---

## Task 5: Add the `pi_app` Typer callback and register the entry point

**Files:**
- Modify: `src/cctmux/__main__.py` (add `pi_app` app + callback; new imports)
- Modify: `src/cctmux/tmux_manager.py` (nothing — already done in Task 2; confirm import list)
- Modify: `pyproject.toml:55-63` (scripts section — add `pitmux`)
- Test: `tests/test_pitmux.py` (append `TestPitmuxCLI` class)

- [ ] **Step 1: Write the failing CLI integration tests**

Open `tests/test_pitmux.py`. At the top of the file (with existing imports) add:

```python
import pytest
from typer.testing import CliRunner

from cctmux.__main__ import pi_app
```

Then append this class to the bottom of the file:

```python
class TestPitmuxCLI:
    """End-to-end tests for the pitmux CLI callback."""

    def test_dry_run_uses_default_prefix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Session name should start with default 'pi-' prefix."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "-v"])
        assert result.exit_code == 0, result.output
        # Session name is derived from project dir name, prefixed with "pi-"
        expected_prefix = f"pi-{tmp_path.name}"
        assert expected_prefix in result.output

    def test_dry_run_includes_pi_launch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dry-run output should show a `pi` launch command, not claude."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run"])
        assert result.exit_code == 0, result.output
        assert "send-keys" in result.output
        assert " pi " in result.output or result.output.count(" pi\n") > 0 or " pi Enter" in result.output
        assert "claude" not in result.output

    def test_dry_run_continue_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-c/--continue should append --continue to pi command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "-c"])
        assert result.exit_code == 0, result.output
        assert "pi --continue" in result.output

    def test_dry_run_resume_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-r/--resume should append --resume to pi command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "-r"])
        assert result.exit_code == 0, result.output
        assert "pi --resume" in result.output

    def test_dry_run_pi_args(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--pi-args should be passed through to the pi command."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TMUX", raising=False)

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run", "--pi-args", "--model x"])
        assert result.exit_code == 0, result.output
        assert "pi --model x" in result.output

    def test_refuses_when_inside_tmux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should exit non-zero if $TMUX is set."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("TMUX", "/tmp/tmux-fake,1234,0")

        runner = CliRunner()
        result = runner.invoke(pi_app, ["--dry-run"])
        assert result.exit_code != 0
        assert "Already inside a tmux session" in result.output

    def test_version(self) -> None:
        """--version should print the version and exit 0."""
        runner = CliRunner()
        result = runner.invoke(pi_app, ["--version"])
        assert result.exit_code == 0
        assert "cctmux" in result.output  # version string includes the package name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pitmux.py::TestPitmuxCLI -v`

Expected: All tests FAIL with `ImportError` on `pi_app`.

- [ ] **Step 3: Update the existing import in `__main__.py` to include `create_pi_session`**

Open `src/cctmux/__main__.py`. Find the line (around line 43):

```python
from cctmux.tmux_manager import attach_session, create_session, create_team_session, is_inside_tmux, session_exists
```

Change to:

```python
from cctmux.tmux_manager import (
    attach_session,
    create_pi_session,
    create_session,
    create_team_session,
    is_inside_tmux,
    session_exists,
)
```

- [ ] **Step 4: Add the `pi_app` Typer instance and its callback**

Open `src/cctmux/__main__.py`. Go to the END of the file (after all existing apps such as `ralph_app`, `git_app`, etc.). Append:

```python
pi_app = typer.Typer(
    name="pitmux",
    help="Launch the pi coding agent inside tmux with session management.",
    no_args_is_help=False,
)


@pi_app.callback(invoke_without_command=True)
def pi_main(
    ctx: typer.Context,
    layout: Annotated[
        str,
        typer.Option("--layout", "-l", help="Tmux layout to use (built-in or custom name)."),
    ] = "default",
    recent: Annotated[
        bool,
        typer.Option("--recent", "-R", help="Select from recent sessions using fzf."),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option("--resume", "-r", help="Append --resume to pi invocation to select a session to resume."),
    ] = False,
    status_bar: Annotated[
        bool,
        typer.Option("--status-bar", "-s", help="Enable status bar with git/project info."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", "-D", help="Enable debug output."),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity."),
    ] = 0,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview commands without executing."),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-C", help="Config file path."),
    ] = None,
    continue_session: Annotated[
        bool,
        typer.Option(
            "--continue", "-c", help="Append --continue to pi invocation to continue the previous session."
        ),
    ] = False,
    dump_config: Annotated[
        bool,
        typer.Option("--dump-config", help="Output current configuration."),
    ] = False,
    pi_args: Annotated[
        str | None,
        typer.Option("--pi-args", "-a", help="Arguments to pass to the pi command (e.g., '--model anthropic/claude-sonnet-4-6')."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with error on config validation warnings."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Launch the pi coding agent in a tmux session for the current directory."""
    # Auto-sync the bundled pi-tmux skill on every invocation.
    _sync_pi_skill()

    if ctx.invoked_subcommand is not None:
        return

    ensure_directories()

    config, config_warnings = load_config(config_path, project_dir=Path.cwd(), strict=strict)

    if config_warnings:
        display_config_warnings(config_warnings, err_console)
        if strict:
            raise typer.Exit(1)

    if dump_config:
        import yaml

        data = config.model_dump()
        data["default_layout"] = config.default_layout.value
        console.print(yaml.dump(data, default_flow_style=False))
        raise typer.Exit()

    # Merge CLI args with config (CLI takes precedence)
    if layout != "default":
        effective_layout: LayoutType | str = layout
    else:
        effective_layout = config.default_layout
    effective_status_bar = status_bar or config.status_bar_enabled
    effective_pi_args = pi_args if pi_args else config.default_pi_args
    if resume:
        resume_flag = "--resume"
        if effective_pi_args:
            if resume_flag not in effective_pi_args:
                effective_pi_args = f"{effective_pi_args} {resume_flag}"
        else:
            effective_pi_args = resume_flag
    if continue_session:
        continue_flag = "--continue"
        if effective_pi_args:
            if continue_flag not in effective_pi_args:
                effective_pi_args = f"{effective_pi_args} {continue_flag}"
        else:
            effective_pi_args = continue_flag

    if debug or verbose > 1:
        console.print(f"[dim]Config file: {get_config_file_path()}[/]")
        layout_display = effective_layout.value if isinstance(effective_layout, LayoutType) else effective_layout
        console.print(f"[dim]Layout: {layout_display}[/]")
        console.print(f"[dim]Status bar: {effective_status_bar}[/]")
        if effective_pi_args:
            console.print(f"[dim]pi args: {effective_pi_args}[/]")

    if is_inside_tmux():
        err_console.print("[red]Error:[/] Already inside a tmux session.")
        err_console.print("[dim]Use standard tmux commands to manage panes.[/]")
        raise typer.Exit(1)

    history = load_history()

    session_name: str
    project_dir: Path

    if recent:
        if not is_fzf_available():
            err_console.print("[red]Error:[/] fzf is required for --recent but not installed.")
            raise typer.Exit(1)

        recent_names = get_recent_session_names(history)
        if not recent_names:
            err_console.print("[yellow]No recent sessions found.[/]")
            raise typer.Exit(1)

        selected = select_with_fzf(recent_names, prompt="Session: ")
        if not selected:
            raise typer.Exit(0)

        session_name = selected
        entry = get_entry_by_name(history, session_name)
        if entry:
            project_dir = Path(entry.project_dir)
            if not project_dir.exists():
                err_console.print(f"[yellow]Warning:[/] Project directory no longer exists: {entry.project_dir}")
                err_console.print("[dim]Falling back to current directory.[/]")
                project_dir = Path.cwd()
        else:
            project_dir = Path.cwd()
    else:
        project_dir = Path.cwd()
        base_name = get_project_name(project_dir)
        session_name = sanitize_session_name(f"{config.pi_session_prefix}{base_name}")

    if debug or verbose > 0:
        console.print(f"[dim]Session: {session_name}[/]")
        console.print(f"[dim]Project: {project_dir}[/]")

    if session_exists(session_name):
        if verbose > 0 or dry_run:
            console.print(f"[blue]Attaching to existing session:[/] {session_name}")

        commands = attach_session(session_name, dry_run=dry_run)

        if dry_run:
            console.print("[yellow]Commands that would be executed:[/]")
            for cmd in commands:
                console.print(f"  {cmd}")
    else:
        if verbose > 0 or dry_run:
            console.print(f"[green]Creating new session:[/] {session_name}")

        # Validate layout name against built-in and custom layouts
        try:
            LayoutType(effective_layout)
        except ValueError:
            custom_match = [cl for cl in config.custom_layouts if cl.name == effective_layout]
            if not custom_match:
                err_console.print(f"[red]Error:[/] Unknown layout: {effective_layout}")
                err_console.print("[dim]Use 'cctmux layout list' to see available layouts.[/]")
                raise typer.Exit(1) from None

        commands = create_pi_session(
            session_name=session_name,
            project_dir=project_dir,
            layout=effective_layout,
            status_bar=effective_status_bar,
            pi_args=effective_pi_args,
            custom_layouts=config.custom_layouts,
            dry_run=dry_run,
        )

        if dry_run:
            console.print("[yellow]Commands that would be executed:[/]")
            for cmd in commands:
                console.print(f"  {cmd}")
            console.print("[dim]Note: Actual execution uses pane IDs (%%N) for reliable targeting.[/]")

    if not dry_run:
        history = add_or_update_entry(
            history,
            session_name=session_name,
            project_dir=str(project_dir.resolve()),
            max_entries=config.max_history_entries,
        )
        save_history(history)
```

- [ ] **Step 5: Register the `pitmux` entry point**

Open `pyproject.toml`. Locate the `[project.scripts]` section (around line 55-63). Add a line for `pitmux`. Final block should look like:

```toml
[project.scripts]
cctmux = "cctmux.__main__:app"
cctmux-tasks = "cctmux.__main__:tasks_app"
cctmux-session = "cctmux.__main__:session_app"
cctmux-agents = "cctmux.__main__:agents_app"
cctmux-activity = "cctmux.__main__:activity_app"
cctmux-git = "cctmux.__main__:git_app"
cctmux-ralph = "cctmux.__main__:ralph_app"
pitmux = "cctmux.__main__:pi_app"
```

- [ ] **Step 6: Install the updated entry points in the local venv**

Run: `uv sync`

Expected: The `pitmux` command is available via `uv run pitmux` and as a console script.

- [ ] **Step 7: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_pitmux.py -v`

Expected: All tests (TestSyncPiSkill + TestPitmuxCLI) PASS.

- [ ] **Step 8: Sanity-check the CLI in dry-run mode from outside a tmux session**

Run: `TMUX= uv run pitmux --dry-run -v`

Expected: Output lists tmux commands that include `pi` (not `claude`) and a session name prefixed with `pi-<project>`. Exit code 0.

- [ ] **Step 9: Run formatters and type check**

Run: `uv run ruff format . && uv run ruff check --fix . && uv run pyright`

Expected: No errors.

- [ ] **Step 10: Commit**

```bash
git add src/cctmux/__main__.py pyproject.toml tests/test_pitmux.py
git commit -m "feat(cli): add pitmux command for launching pi in tmux sessions"
```

---

## Task 6: Documentation updates

**Files:**
- Modify: `docs/CLI_REFERENCE.md` (new section)
- Modify: `docs/CONFIGURATION.md` (new fields)
- Modify: `docs/ARCHITECTURE.md` (new entry point + function)
- Modify: `README.md` (mention pitmux)

No tests — docs only. The goal is to satisfy the CLAUDE.md Change Checklist (skill file, CLI reference, configuration reference, architecture doc).

- [ ] **Step 1: Read the target doc files to understand existing structure**

Run: `wc -l docs/CLI_REFERENCE.md docs/CONFIGURATION.md docs/ARCHITECTURE.md README.md`

Then read each, using `offset`/`limit` as needed for files over 500 LOC. Locate natural insertion points (end of "Commands" section in CLI_REFERENCE, the config field table in CONFIGURATION, entry-points list in ARCHITECTURE, the "Usage" section in README).

- [ ] **Step 2: Add `pitmux` section to `docs/CLI_REFERENCE.md`**

Locate the section that documents `cctmux` (the main command). Directly after it — before the first companion command (likely `cctmux-tasks`) — insert a new `### pitmux` subsection.

Content to insert:

````markdown
### pitmux

Launch the `pi` coding agent inside a tmux session, mirroring the core
`cctmux` UX. Sessions are prefixed (default `pi-`) so `cctmux` and
`pitmux` can coexist for the same project.

```bash
pitmux [OPTIONS]
```

| Flag | Short | Description |
|------|-------|-------------|
| `--layout <name>` | `-l` | Tmux layout to use (built-in or custom name). |
| `--recent` | `-R` | Select from recent sessions using fzf. |
| `--resume` | `-r` | Append `--resume` to the pi invocation. |
| `--continue` | `-c` | Append `--continue` to the pi invocation. |
| `--status-bar` | `-s` | Enable status bar with git/project info. |
| `--debug` | `-D` | Enable debug output. |
| `--verbose` | `-v` | Increase verbosity (stackable). |
| `--dry-run` | `-n` | Preview commands without executing. |
| `--config <path>` | `-C` | Config file path. |
| `--dump-config` | | Output current configuration. |
| `--pi-args "..."` | `-a` | Arguments to pass through to `pi`. |
| `--strict` | | Exit with error on config validation warnings. |
| `--version` | | Show version. |

**Examples:**

```bash
# Launch pi in the current project's tmux session
pitmux

# Resume the previous pi session
pitmux -c

# Pick a pi session to resume from a list
pitmux -r

# Use a specific model
pitmux --pi-args "--model anthropic/claude-sonnet-4-6"

# Preview what would run
pitmux --dry-run
```

**Not supported (by design):** `--yolo`, `--task-list-id`, `--agent-teams`,
team mode, companion monitors. These are Claude Code-specific.

**Skill bundling:** Each `pitmux` run auto-installs the `pi-tmux` skill
to `~/.pi/agent/skills/pi-tmux/` (created if missing). The skill teaches
pi how to manage tmux panes using the same patterns as `cc-tmux`.
````

- [ ] **Step 3: Add config fields to `docs/CONFIGURATION.md`**

Locate the table of top-level Config fields. Add two new rows:

```markdown
| `default_pi_args` | `string \| null` | `null` | Default CLI args passed to the `pi` command by `pitmux` (e.g. `"--model anthropic/claude-sonnet-4-6"`). |
| `pi_session_prefix` | `string` | `"pi-"` | Prefix applied to the `pitmux` tmux session name. Set to `""` to drop the prefix (collides with `cctmux` sessions — not recommended). |
```

Then at the end of the file (or in the example YAML section), add an
`Example YAML` snippet:

```yaml
# Optional pitmux settings
default_pi_args: "--model anthropic/claude-sonnet-4-6"
pi_session_prefix: "pi-"
```

- [ ] **Step 4: Update `docs/ARCHITECTURE.md`**

Find the "Entry Points" list (or equivalent). Add `pitmux` to the list:

```markdown
- `pitmux` — Launch the `pi` coding agent in a tmux session
```

Find the `tmux_manager.py` description. Update it to mention
`create_pi_session` alongside `create_session` and `create_team_session`.

Find any diagram or section listing `__main__.py` apps. Append `pi_app`.

- [ ] **Step 5: Update `README.md`**

Add a short mention in the feature or usage section:

```markdown
### pitmux (launch the `pi` coding agent)

`pitmux` is a sibling command that launches the [pi coding agent](https://github.com/paulrobello/pi)
in a tmux session instead of Claude Code. It mirrors `cctmux`'s core flags
(layout, status-bar, dry-run, `-c`/`-r`, config) and uses a configurable
session prefix (`pi-` by default) so you can run both `cctmux` and
`pitmux` for the same project simultaneously. See
[`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md#pitmux) for details.
```

- [ ] **Step 6: Verify all four docs render cleanly**

Run: `grep -n "pitmux" docs/CLI_REFERENCE.md docs/CONFIGURATION.md docs/ARCHITECTURE.md README.md`

Expected: At least one match in each file.

- [ ] **Step 7: Commit**

```bash
git add docs/CLI_REFERENCE.md docs/CONFIGURATION.md docs/ARCHITECTURE.md README.md
git commit -m "docs: document pitmux command, config fields, and skill sync"
```

---

## Task 7: Final verification

**Files:** none modified — this is the project-wide check.

- [ ] **Step 1: Run the full checkall sweep**

Run: `make checkall`

Expected: Format, lint, typecheck, and all tests PASS.

If any check fails:
- **Format:** Run `uv run ruff format .` and recommit.
- **Lint:** Fix the reported issues, then recommit.
- **Typecheck:** Fix the reported issues (strict mode). Recommit.
- **Tests:** Understand the failure first. If a test is wrong, fix the test; if the code is wrong, fix the code. Never make tests pass by weakening assertions.

- [ ] **Step 2: End-to-end smoke test from outside a tmux session**

Run: `TMUX= uv run pitmux --dry-run -v`

Expected: Output includes:
- `Session: pi-<project-name>`
- A `tmux send-keys ... pi Enter` line (or similar pi launch)
- No `claude` command references
- Exit code 0

Run: `TMUX= uv run pitmux --dry-run -c`

Expected: Output contains `pi --continue`.

Run: `TMUX= uv run pitmux --dry-run -r`

Expected: Output contains `pi --resume`.

- [ ] **Step 3: Verify the skill was installed on first run**

Run: `ls ~/.pi/agent/skills/pi-tmux/SKILL.md`

Expected: File exists (may already have existed from a prior run — still must exist now).

- [ ] **Step 4: Verify the main `cctmux` command still works**

Run: `TMUX= uv run cctmux --dry-run`

Expected: Exits 0 with the normal cctmux output (no regressions).

- [ ] **Step 5: (no commit)** — verification-only step.
