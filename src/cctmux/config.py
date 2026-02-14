"""Configuration management for cctmux."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from cctmux.xdg_paths import get_config_file_path


class LayoutType(StrEnum):
    """Available tmux layout types."""

    DEFAULT = "default"  # No initial split
    EDITOR = "editor"  # 70/30 horizontal split
    MONITOR = "monitor"  # Main + bottom bar (80/20)
    TRIPLE = "triple"  # Main + 2 side panes
    CC_MON = "cc-mon"  # Claude + session monitor + task monitor
    FULL_MONITOR = "full-monitor"  # Main + session + task + activity
    DASHBOARD = "dashboard"  # Large activity dashboard with session stats
    RALPH = "ralph"  # Shell + ralph monitor side-by-side
    RALPH_FULL = "ralph-full"  # Shell + ralph monitor + task monitor
    GIT_MON = "git-mon"  # Claude + git monitor


class ConfigPreset(StrEnum):
    """Predefined configuration presets."""

    DEFAULT = "default"
    MINIMAL = "minimal"
    VERBOSE = "verbose"
    DEBUG = "debug"


class SessionMonitorConfig(BaseModel):
    """Configuration for cctmux-session monitor."""

    show_thinking: bool = True
    show_results: bool = True
    show_progress: bool = True
    show_system: bool = False
    show_snapshots: bool = False
    show_cwd: bool = False
    show_threading: bool = False
    show_stop_reasons: bool = True
    show_turn_durations: bool = True
    show_hook_errors: bool = True
    show_service_tier: bool = False
    show_sidechain: bool = True
    max_events: int = 50


class TaskMonitorConfig(BaseModel):
    """Configuration for cctmux-tasks monitor."""

    show_owner: bool = True
    show_metadata: bool = False
    show_description: bool = True
    show_graph: bool = True
    show_table: bool = True
    show_acceptance: bool = True
    show_work_log: bool = False
    max_tasks: int = 100


class ActivityMonitorConfig(BaseModel):
    """Configuration for cctmux-activity monitor."""

    default_days: int = 7
    show_heatmap: bool = True
    show_cost: bool = True
    show_tool_usage: bool = True
    show_model_usage: bool = True


class RalphMonitorConfig(BaseModel):
    """Configuration for cctmux-ralph monitor."""

    show_table: bool = True
    show_timeline: bool = True
    show_prompt: bool = False
    show_task_progress: bool = True
    max_iterations_visible: int = 20


class AgentMonitorConfig(BaseModel):
    """Configuration for cctmux-agents monitor."""

    inactive_timeout: float = 300.0  # seconds; 0 to disable


class GitMonitorConfig(BaseModel):
    """Configuration for cctmux-git monitor."""

    show_log: bool = True
    show_diff: bool = True
    show_status: bool = True
    max_commits: int = 10
    poll_interval: float = 2.0
    fetch_enabled: bool = False
    fetch_interval: float = 60.0


class SplitDirection(StrEnum):
    """Direction for a pane split."""

    HORIZONTAL = "h"  # side-by-side (left/right)
    VERTICAL = "v"  # stacked (top/bottom)


class PaneSplit(BaseModel):
    """A single split operation in a custom layout."""

    direction: SplitDirection
    size: int  # percentage for the new pane (1-90)
    command: str = ""  # command to run in the new pane (optional)
    name: str = ""  # name for referencing in later splits
    target: str = "main"  # pane to split: "main", "last", or a named pane
    focus: bool = False  # focus this pane after layout is applied


def validate_layout_name(name: str) -> str:
    """Validate that a custom layout name is valid.

    Must be lowercase, hyphens-only (like session names), and must NOT collide
    with any built-in LayoutType value.

    Args:
        name: The layout name to validate.

    Returns:
        The validated name.

    Raises:
        ValueError: If the name is invalid or collides with a built-in layout.
    """
    import re

    if not name:
        raise ValueError("Layout name cannot be empty")

    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", name):
        raise ValueError(
            f"Layout name '{name}' must be lowercase alphanumeric with hyphens, no leading/trailing hyphens"
        )

    # Check collision with built-in layouts
    builtin_values = {lt.value for lt in LayoutType}
    if name in builtin_values:
        raise ValueError(f"Layout name '{name}' conflicts with built-in layout")

    return name


class CustomLayout(BaseModel):
    """Custom layout definition."""

    name: str
    description: str = ""
    splits: list[PaneSplit] = []
    focus_main: bool = True  # focus main pane at end (unless a split has focus=True)


@dataclass
class ConfigWarning:
    """A config validation warning."""

    file: str
    field_name: str
    message: str
    value: object = field(default=None, repr=False)


class Config(BaseModel):
    """Configuration settings for cctmux."""

    default_layout: LayoutType = LayoutType.DEFAULT
    status_bar_enabled: bool = False
    max_history_entries: int = 50
    default_claude_args: str | None = None
    task_list_id: bool = False

    # When true in a project config, ignore all parent configs (user config)
    ignore_parent_configs: bool = False

    # Monitor-specific configurations
    session_monitor: SessionMonitorConfig = SessionMonitorConfig()
    task_monitor: TaskMonitorConfig = TaskMonitorConfig()
    activity_monitor: ActivityMonitorConfig = ActivityMonitorConfig()
    agent_monitor: AgentMonitorConfig = AgentMonitorConfig()
    ralph_monitor: RalphMonitorConfig = RalphMonitorConfig()
    git_monitor: GitMonitorConfig = GitMonitorConfig()

    # Custom layouts
    custom_layouts: list[CustomLayout] = []


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Recursively merge override dict into base dict.

    For nested dicts, merges recursively. For all other types, override wins.

    Args:
        base: The base dictionary.
        override: The dictionary with overriding values.

    Returns:
        A new merged dictionary.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def _load_yaml_file(path: Path) -> tuple[dict[str, object], list[ConfigWarning]]:
    """Load a YAML file and return its contents as a dict with warnings.

    Args:
        path: Path to the YAML file.

    Returns:
        Tuple of (parsed dict, list of warnings). Empty dict on missing/invalid.
    """
    if not path.exists():
        return {}, []
    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            return {}, []
        return cast(dict[str, object], raw), []
    except yaml.YAMLError as e:
        return {}, [
            ConfigWarning(
                file=str(path),
                field_name="(file)",
                message=f"YAML parse error: {e}",
                value=None,
            )
        ]
    except OSError as e:
        return {}, [
            ConfigWarning(
                file=str(path),
                field_name="(file)",
                message=f"File read error: {e}",
                value=None,
            )
        ]


def load_config(
    config_path: Path | None = None,
    project_dir: Path | None = None,
    strict: bool = False,
) -> tuple[Config, list[ConfigWarning]]:
    """Load configuration with layered merging.

    Loading order (last value wins via deep merge):
    1. User config (~/.config/cctmux/config.yaml) - base
    2. Project config (.cctmux.yaml in project_dir) - team/shared overrides
    3. Project local config (.cctmux.yaml.local in project_dir) - personal overrides

    If a project config sets ``ignore_parent_configs: true``, the user config is
    skipped and only project configs are used.

    Args:
        config_path: Optional path to user config file. Uses default if None.
        project_dir: Optional project directory containing .cctmux.yaml files.
        strict: If True, do not attempt partial recovery on validation errors.

    Returns:
        Tuple of (loaded Config, list of ConfigWarnings).
    """
    warnings: list[ConfigWarning] = []

    user_config_path = config_path or get_config_file_path()
    user_config, user_warnings = _load_yaml_file(user_config_path)
    warnings.extend(user_warnings)

    if project_dir:
        project_config, proj_warnings = _load_yaml_file(project_dir / ".cctmux.yaml")
        warnings.extend(proj_warnings)
        local_config, local_warnings = _load_yaml_file(project_dir / ".cctmux.yaml.local")
        warnings.extend(local_warnings)

        # Check if any project config wants to ignore parent configs
        ignore_parent = project_config.get("ignore_parent_configs", False) or local_config.get(
            "ignore_parent_configs", False
        )

        if ignore_parent:
            # Start from defaults, apply only project configs
            merged: dict[str, object] = _deep_merge(project_config, local_config)
        else:
            # Normal layered merge: user → project → local
            merged = _deep_merge(user_config, project_config)
            merged = _deep_merge(merged, local_config)
    else:
        merged = user_config

    try:
        return Config.model_validate(merged), warnings
    except (ValueError, ValidationError) as e:
        if isinstance(e, ValidationError):
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error["loc"])
                warnings.append(
                    ConfigWarning(
                        file="merged config",
                        field_name=field_path,
                        message=error["msg"],
                        value=error.get("input"),
                    )
                )
        else:
            warnings.append(
                ConfigWarning(
                    file="merged config",
                    field_name="(unknown)",
                    message=str(e),
                    value=None,
                )
            )

        if strict:
            return Config(), warnings

        # Attempt partial recovery: remove bad fields and retry
        if isinstance(e, ValidationError):
            for error in e.errors():
                # Remove the top-level key that caused the error
                if error["loc"]:
                    top_key = str(error["loc"][0])
                    merged.pop(top_key, None)
            try:
                return Config.model_validate(merged), warnings
            except (ValueError, ValidationError):
                pass

        return Config(), warnings


def display_config_warnings(warnings: list[ConfigWarning], console: Console) -> None:
    """Display config warnings using Rich formatting.

    Args:
        warnings: List of warnings to display.
        console: Rich console to output to.
    """
    if not warnings:
        return

    text = Text()
    for i, warning in enumerate(warnings):
        if i > 0:
            text.append("\n")
        text.append(f"  {warning.file}", style="dim")
        text.append(": ", style="dim")
        text.append(warning.field_name, style="bold")
        text.append(f" — {warning.message}", style="yellow")
        if warning.value is not None:
            text.append(f" (got: {warning.value!r})", style="dim")

    console.print(Panel(text, title="[yellow]Config Warnings[/]", border_style="yellow"))


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save configuration to YAML file.

    Args:
        config: The configuration to save.
        config_path: Optional path to config file. Uses default if None.
    """
    path = config_path or get_config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump()
    # Convert enum to string value
    data["default_layout"] = config.default_layout.value

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)


def get_preset_config(preset: ConfigPreset) -> Config:
    """Get a preset configuration.

    Args:
        preset: The preset type.

    Returns:
        Config with preset values applied.
    """
    if preset == ConfigPreset.MINIMAL:
        return Config(
            session_monitor=SessionMonitorConfig(
                show_thinking=False,
                show_results=False,
                show_progress=False,
                show_stop_reasons=False,
                show_turn_durations=False,
                show_hook_errors=False,
                show_sidechain=False,
                max_events=20,
            ),
            task_monitor=TaskMonitorConfig(
                show_owner=False,
                show_metadata=False,
                show_description=False,
                show_table=False,
                show_acceptance=False,
                max_tasks=30,
            ),
            activity_monitor=ActivityMonitorConfig(
                show_heatmap=False,
                show_tool_usage=False,
            ),
            ralph_monitor=RalphMonitorConfig(
                show_timeline=False,
                show_prompt=False,
            ),
            git_monitor=GitMonitorConfig(
                show_log=False,
                show_diff=False,
                max_commits=5,
                fetch_enabled=False,
            ),
        )
    elif preset == ConfigPreset.VERBOSE:
        return Config(
            session_monitor=SessionMonitorConfig(
                show_thinking=True,
                show_results=True,
                show_progress=True,
                show_system=True,
                show_cwd=True,
                show_stop_reasons=True,
                show_turn_durations=True,
                show_hook_errors=True,
                show_service_tier=True,
                show_sidechain=True,
                max_events=100,
            ),
            task_monitor=TaskMonitorConfig(
                show_owner=True,
                show_metadata=True,
                show_description=True,
                show_graph=True,
                show_table=True,
                show_acceptance=True,
                show_work_log=True,
                max_tasks=200,
            ),
            activity_monitor=ActivityMonitorConfig(
                default_days=14,
                show_heatmap=True,
                show_cost=True,
                show_tool_usage=True,
                show_model_usage=True,
            ),
            ralph_monitor=RalphMonitorConfig(
                show_table=True,
                show_timeline=True,
                show_prompt=True,
                show_task_progress=True,
            ),
            git_monitor=GitMonitorConfig(
                show_log=True,
                show_diff=True,
                show_status=True,
                max_commits=20,
                fetch_enabled=True,
                fetch_interval=60.0,
            ),
        )
    elif preset == ConfigPreset.DEBUG:
        return Config(
            session_monitor=SessionMonitorConfig(
                show_thinking=True,
                show_results=True,
                show_progress=True,
                show_system=True,
                show_snapshots=True,
                show_cwd=True,
                show_threading=True,
                show_stop_reasons=True,
                show_turn_durations=True,
                show_hook_errors=True,
                show_service_tier=True,
                show_sidechain=True,
                max_events=200,
            ),
            task_monitor=TaskMonitorConfig(
                show_owner=True,
                show_metadata=True,
                show_description=True,
                show_graph=True,
                show_table=True,
                show_acceptance=True,
                show_work_log=True,
                max_tasks=500,
            ),
            activity_monitor=ActivityMonitorConfig(
                default_days=30,
                show_heatmap=True,
                show_cost=True,
                show_tool_usage=True,
                show_model_usage=True,
            ),
            ralph_monitor=RalphMonitorConfig(
                show_table=True,
                show_timeline=True,
                show_prompt=True,
                show_task_progress=True,
                max_iterations_visible=50,
            ),
            git_monitor=GitMonitorConfig(
                show_log=True,
                show_diff=True,
                show_status=True,
                max_commits=30,
                fetch_enabled=True,
                fetch_interval=30.0,
            ),
        )
    # Default preset
    return Config()
