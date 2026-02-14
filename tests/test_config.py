"""Tests for cctmux.config module."""

import tempfile
from pathlib import Path

import yaml

from cctmux.config import (
    Config,
    GitMonitorConfig,
    LayoutType,
    _deep_merge,
    _load_yaml_file,
    load_config,
    save_config,
)


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

    def test_ignore_parent_configs_default(self) -> None:
        """Should default ignore_parent_configs to False."""
        config = Config()
        assert config.ignore_parent_configs is False


class TestLayoutType:
    """Tests for LayoutType enum."""

    def test_values(self) -> None:
        """Should have expected enum values."""
        assert LayoutType.DEFAULT.value == "default"
        assert LayoutType.EDITOR.value == "editor"
        assert LayoutType.MONITOR.value == "monitor"
        assert LayoutType.TRIPLE.value == "triple"


class TestDeepMerge:
    """Tests for _deep_merge function."""

    def test_flat_merge(self) -> None:
        """Should merge flat dicts with override winning."""
        base: dict[str, object] = {"a": 1, "b": 2}
        override: dict[str, object] = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        """Should recursively merge nested dicts."""
        base: dict[str, object] = {"git_monitor": {"show_log": True, "max_commits": 10}}
        override: dict[str, object] = {"git_monitor": {"max_commits": 20}}
        result = _deep_merge(base, override)
        assert result == {"git_monitor": {"show_log": True, "max_commits": 20}}

    def test_override_replaces_non_dict(self) -> None:
        """Should replace non-dict values entirely."""
        base: dict[str, object] = {"a": [1, 2, 3]}
        override: dict[str, object] = {"a": [4, 5]}
        result = _deep_merge(base, override)
        assert result == {"a": [4, 5]}

    def test_empty_override(self) -> None:
        """Should return base when override is empty."""
        base: dict[str, object] = {"a": 1, "b": 2}
        result = _deep_merge(base, {})
        assert result == {"a": 1, "b": 2}

    def test_empty_base(self) -> None:
        """Should return override when base is empty."""
        override: dict[str, object] = {"a": 1, "b": 2}
        result = _deep_merge({}, override)
        assert result == {"a": 1, "b": 2}

    def test_does_not_mutate_inputs(self) -> None:
        """Should not modify the input dicts."""
        base: dict[str, object] = {"a": 1, "nested": {"x": 1}}
        override: dict[str, object] = {"nested": {"y": 2}}
        _deep_merge(base, override)
        assert base == {"a": 1, "nested": {"x": 1}}
        assert override == {"nested": {"y": 2}}

    def test_deeply_nested_merge(self) -> None:
        """Should handle multiple levels of nesting."""
        base: dict[str, object] = {"l1": {"l2": {"l3": {"a": 1, "b": 2}}}}
        override: dict[str, object] = {"l1": {"l2": {"l3": {"b": 3, "c": 4}}}}
        result = _deep_merge(base, override)
        assert result == {"l1": {"l2": {"l3": {"a": 1, "b": 3, "c": 4}}}}


class TestLoadYamlFile:
    """Tests for _load_yaml_file function."""

    def test_missing_file(self) -> None:
        """Should return empty dict for missing file."""
        result = _load_yaml_file(Path("/nonexistent/path/config.yaml"))
        assert result == {}

    def test_valid_yaml(self) -> None:
        """Should parse valid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text(yaml.dump({"key": "value"}), encoding="utf-8")
            result = _load_yaml_file(path)
            assert result == {"key": "value"}

    def test_empty_file(self) -> None:
        """Should return empty dict for empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text("", encoding="utf-8")
            result = _load_yaml_file(path)
            assert result == {}

    def test_invalid_yaml(self) -> None:
        """Should return empty dict for invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text("invalid: yaml: content:", encoding="utf-8")
            result = _load_yaml_file(path)
            assert result == {}

    def test_non_dict_yaml(self) -> None:
        """Should return empty dict when YAML is not a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text("- item1\n- item2\n", encoding="utf-8")
            result = _load_yaml_file(path)
            assert result == {}


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


class TestLayeredConfig:
    """Tests for layered project configuration loading."""

    def test_project_config_overrides_user(self) -> None:
        """Project config should override user config values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump({"default_layout": "editor", "status_bar_enabled": True}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml").write_text(
                yaml.dump({"default_layout": "cc-mon"}),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            assert config.default_layout == LayoutType.CC_MON
            # User value preserved when project doesn't override
            assert config.status_bar_enabled is True

    def test_local_config_overrides_project(self) -> None:
        """Local config should override both user and project config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump({"default_layout": "editor", "max_history_entries": 100}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml").write_text(
                yaml.dump({"default_layout": "cc-mon"}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml.local").write_text(
                yaml.dump({"default_layout": "triple"}),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            assert config.default_layout == LayoutType.TRIPLE
            # User value preserved
            assert config.max_history_entries == 100

    def test_partial_nested_override(self) -> None:
        """Partial nested override should not wipe sibling fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump(
                    {
                        "git_monitor": {
                            "show_log": True,
                            "show_diff": True,
                            "max_commits": 10,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml").write_text(
                yaml.dump({"git_monitor": {"fetch_enabled": True}}),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            assert config.git_monitor.fetch_enabled is True
            # Sibling fields preserved from user config
            assert config.git_monitor.show_log is True
            assert config.git_monitor.show_diff is True
            assert config.git_monitor.max_commits == 10

    def test_no_project_configs(self) -> None:
        """Should work when project dir has no config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump({"default_layout": "editor"}),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            assert config.default_layout == LayoutType.EDITOR

    def test_no_project_dir(self) -> None:
        """Should use only user config when no project_dir provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config = Path(tmpdir) / "user.yaml"
            user_config.write_text(
                yaml.dump({"default_layout": "monitor"}),
                encoding="utf-8",
            )

            config = load_config(user_config)
            assert config.default_layout == LayoutType.MONITOR

    def test_ignore_parent_configs_in_project(self) -> None:
        """Project config with ignore_parent_configs should skip user config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump({"default_layout": "editor", "status_bar_enabled": True}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml").write_text(
                yaml.dump(
                    {
                        "ignore_parent_configs": True,
                        "default_layout": "cc-mon",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            assert config.default_layout == LayoutType.CC_MON
            # User config was ignored, so status_bar_enabled should be default
            assert config.status_bar_enabled is False

    def test_ignore_parent_configs_in_local(self) -> None:
        """Local config with ignore_parent_configs should skip user config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump({"default_layout": "editor", "max_history_entries": 200}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml").write_text(
                yaml.dump({"default_layout": "cc-mon"}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml.local").write_text(
                yaml.dump({"ignore_parent_configs": True}),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            # Project config value applied
            assert config.default_layout == LayoutType.CC_MON
            # User config was ignored
            assert config.max_history_entries == 50  # default value

    def test_ignore_parent_local_overrides_project(self) -> None:
        """With ignore_parent_configs, local should still override project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            user_config = tmppath / "user.yaml"
            project_dir = tmppath / "project"
            project_dir.mkdir()

            user_config.write_text(
                yaml.dump({"default_layout": "editor"}),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml").write_text(
                yaml.dump(
                    {
                        "ignore_parent_configs": True,
                        "default_layout": "cc-mon",
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / ".cctmux.yaml.local").write_text(
                yaml.dump({"default_layout": "triple"}),
                encoding="utf-8",
            )

            config = load_config(user_config, project_dir=project_dir)
            # Local overrides project
            assert config.default_layout == LayoutType.TRIPLE


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
