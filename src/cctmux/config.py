"""Configuration management for cctmux."""

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

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


class CustomLayout(BaseModel):
    """Custom layout definition."""

    name: str
    description: str = ""
    splits: list[dict[str, str | int]] = []


class Config(BaseModel):
    """Configuration settings for cctmux."""

    default_layout: LayoutType = LayoutType.DEFAULT
    status_bar_enabled: bool = False
    max_history_entries: int = 50
    default_claude_args: str | None = None
    task_list_id: bool = False

    # Monitor-specific configurations
    session_monitor: SessionMonitorConfig = SessionMonitorConfig()
    task_monitor: TaskMonitorConfig = TaskMonitorConfig()
    activity_monitor: ActivityMonitorConfig = ActivityMonitorConfig()
    agent_monitor: AgentMonitorConfig = AgentMonitorConfig()
    ralph_monitor: RalphMonitorConfig = RalphMonitorConfig()
    git_monitor: GitMonitorConfig = GitMonitorConfig()

    # Custom layouts
    custom_layouts: list[CustomLayout] = []


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Optional path to config file. Uses default if None.

    Returns:
        The loaded configuration, or defaults if file doesn't exist.
    """
    path = config_path or get_config_file_path()

    if not path.exists():
        return Config()

    try:
        with path.open(encoding="utf-8") as f:
            data: dict[str, object] = yaml.safe_load(f) or {}
        return Config.model_validate(data)
    except (yaml.YAMLError, ValueError):
        return Config()


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
            ),
        )
    # Default preset
    return Config()
