"""XDG-compliant path management for cctmux."""

from pathlib import Path

from xdg_base_dirs import xdg_config_home, xdg_data_home

APP_NAME = "cctmux"


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    return xdg_config_home() / APP_NAME


def get_data_dir() -> Path:
    """Get the data directory path."""
    return xdg_data_home() / APP_NAME


def get_config_file_path() -> Path:
    """Get the config.yaml file path."""
    return get_config_dir() / "config.yaml"


def get_history_file_path() -> Path:
    """Get the history.yaml file path."""
    return get_data_dir() / "history.yaml"


def ensure_directories() -> None:
    """Create config and data directories if they don't exist."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_data_dir().mkdir(parents=True, exist_ok=True)
