"""Tests for cctmux.config module."""

import tempfile
from pathlib import Path

import yaml

from cctmux.config import Config, GitMonitorConfig, LayoutType, load_config, save_config


class TestConfig:
    """Tests for Config model."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        config = Config()
        assert config.default_layout == LayoutType.DEFAULT
        assert config.status_bar_enabled is False
        assert config.max_history_entries == 50

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = Config(
            default_layout=LayoutType.EDITOR,
            status_bar_enabled=True,
            max_history_entries=100,
        )
        assert config.default_layout == LayoutType.EDITOR
        assert config.status_bar_enabled is True
        assert config.max_history_entries == 100


class TestLayoutType:
    """Tests for LayoutType enum."""

    def test_values(self) -> None:
        """Should have expected enum values."""
        assert LayoutType.DEFAULT.value == "default"
        assert LayoutType.EDITOR.value == "editor"
        assert LayoutType.MONITOR.value == "monitor"
        assert LayoutType.TRIPLE.value == "triple"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_missing_file_returns_defaults(self) -> None:
        """Should return defaults when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yaml"
            config = load_config(config_path)
            assert config == Config()

    def test_loads_valid_config(self) -> None:
        """Should load valid config from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                yaml.dump(
                    {
                        "default_layout": "editor",
                        "status_bar_enabled": True,
                        "max_history_entries": 25,
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            assert config.default_layout == LayoutType.EDITOR
            assert config.status_bar_enabled is True
            assert config.max_history_entries == 25

    def test_invalid_yaml_returns_defaults(self) -> None:
        """Should return defaults for invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("invalid: yaml: content:", encoding="utf-8")
            config = load_config(config_path)
            assert config == Config()

    def test_empty_file_returns_defaults(self) -> None:
        """Should return defaults for empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("", encoding="utf-8")
            config = load_config(config_path)
            assert config == Config()


class TestSaveConfig:
    """Tests for save_config function."""

    def test_saves_config(self) -> None:
        """Should save config to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config = Config(
                default_layout=LayoutType.MONITOR,
                status_bar_enabled=True,
                max_history_entries=75,
            )
            save_config(config, config_path)

            assert config_path.exists()
            with config_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data["default_layout"] == "monitor"
            assert data["status_bar_enabled"] is True
            assert data["max_history_entries"] == 75

    def test_creates_parent_directories(self) -> None:
        """Should create parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nested" / "dir" / "config.yaml"
            config = Config()
            save_config(config, config_path)
            assert config_path.exists()


class TestGitMonitorConfig:
    """Tests for GitMonitorConfig model."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        config = GitMonitorConfig()
        assert config.show_log is True
        assert config.show_diff is True
        assert config.show_status is True
        assert config.max_commits == 10
        assert config.poll_interval == 2.0

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = GitMonitorConfig(show_log=False, max_commits=5)
        assert config.show_log is False
        assert config.max_commits == 5


class TestLayoutTypeGitMon:
    """Tests for git-mon layout type."""

    def test_git_mon_value(self) -> None:
        """Should have git-mon enum value."""
        assert LayoutType.GIT_MON.value == "git-mon"

    def test_config_includes_git_monitor(self) -> None:
        """Config should include git_monitor field."""
        config = Config()
        assert hasattr(config, "git_monitor")
        assert isinstance(config.git_monitor, GitMonitorConfig)
