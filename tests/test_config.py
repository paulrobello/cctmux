"""Tests for cctmux.config module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from cctmux.config import (
    Config,
    ConfigWarning,
    CustomLayout,
    GitMonitorConfig,
    LayoutType,
    PaneSplit,
    SplitDirection,
    _deep_merge,
    _load_yaml_file,
    display_config_warnings,
    load_config,
    save_config,
    validate_layout_name,
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
        data, warnings = _load_yaml_file(Path("/nonexistent/path/config.yaml"))
        assert data == {}
        assert warnings == []

    def test_valid_yaml(self) -> None:
        """Should parse valid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text(yaml.dump({"key": "value"}), encoding="utf-8")
            data, warnings = _load_yaml_file(path)
            assert data == {"key": "value"}
            assert warnings == []

    def test_empty_file(self) -> None:
        """Should return empty dict for empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text("", encoding="utf-8")
            data, warnings = _load_yaml_file(path)
            assert data == {}
            assert warnings == []

    def test_invalid_yaml(self) -> None:
        """Should return empty dict with warning for invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text("invalid: yaml: content:", encoding="utf-8")
            data, warnings = _load_yaml_file(path)
            assert data == {}
            assert len(warnings) == 1
            assert "YAML parse error" in warnings[0].message

    def test_non_dict_yaml(self) -> None:
        """Should return empty dict when YAML is not a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            path.write_text("- item1\n- item2\n", encoding="utf-8")
            data, warnings = _load_yaml_file(path)
            assert data == {}
            assert warnings == []


class TestLoadConfig:
    """Tests for load_config function."""

    def test_missing_file_returns_defaults(self) -> None:
        """Should return defaults when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yaml"
            config, warnings = load_config(config_path)
            assert config == Config()
            assert warnings == []

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
            config, warnings = load_config(config_path)
            assert config.default_layout == LayoutType.EDITOR
            assert config.status_bar_enabled is True
            assert config.max_history_entries == 25
            assert warnings == []

    def test_invalid_yaml_returns_defaults_with_warning(self) -> None:
        """Should return defaults with warning for invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("invalid: yaml: content:", encoding="utf-8")
            config, warnings = load_config(config_path)
            assert config == Config()
            assert len(warnings) == 1
            assert "YAML parse error" in warnings[0].message

    def test_empty_file_returns_defaults(self) -> None:
        """Should return defaults for empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("", encoding="utf-8")
            config, warnings = load_config(config_path)
            assert config == Config()
            assert warnings == []

    def test_validation_error_returns_warnings(self) -> None:
        """Should return warnings for invalid config values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                yaml.dump({"max_history_entries": "not-a-number"}),
                encoding="utf-8",
            )
            config, warnings = load_config(config_path)
            assert len(warnings) >= 1
            # Should still get a usable config (partial recovery)
            assert isinstance(config, Config)

    def test_strict_mode_no_recovery(self) -> None:
        """Strict mode should not attempt partial recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                yaml.dump({"max_history_entries": "not-a-number"}),
                encoding="utf-8",
            )
            config, warnings = load_config(config_path, strict=True)
            assert len(warnings) >= 1
            assert config == Config()  # defaults, no recovery


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

            config, _warnings = load_config(user_config, project_dir=project_dir)
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

            config, _warnings = load_config(user_config, project_dir=project_dir)
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

            config, _warnings = load_config(user_config, project_dir=project_dir)
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

            config, _warnings = load_config(user_config, project_dir=project_dir)
            assert config.default_layout == LayoutType.EDITOR

    def test_no_project_dir(self) -> None:
        """Should use only user config when no project_dir provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config = Path(tmpdir) / "user.yaml"
            user_config.write_text(
                yaml.dump({"default_layout": "monitor"}),
                encoding="utf-8",
            )

            config, _warnings = load_config(user_config)
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

            config, _warnings = load_config(user_config, project_dir=project_dir)
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

            config, _warnings = load_config(user_config, project_dir=project_dir)
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

            config, _warnings = load_config(user_config, project_dir=project_dir)
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


class TestConfigWarning:
    """Tests for ConfigWarning dataclass."""

    def test_create_warning(self) -> None:
        """Should create a warning with all fields."""
        warning = ConfigWarning(
            file="test.yaml",
            field_name="max_history_entries",
            message="expected int, got str",
            value="abc",
        )
        assert warning.file == "test.yaml"
        assert warning.field_name == "max_history_entries"
        assert warning.message == "expected int, got str"
        assert warning.value == "abc"

    def test_default_value_none(self) -> None:
        """Should default value to None."""
        warning = ConfigWarning(file="test.yaml", field_name="x", message="error")
        assert warning.value is None


class TestDisplayConfigWarnings:
    """Tests for display_config_warnings function."""

    def test_no_warnings_no_output(self) -> None:
        """Should not print anything when no warnings."""
        from io import StringIO

        from rich.console import Console

        output = StringIO()
        test_console = Console(file=output, no_color=True)
        display_config_warnings([], test_console)
        assert output.getvalue() == ""

    def test_displays_warnings(self) -> None:
        """Should display warnings in a panel."""
        from io import StringIO

        from rich.console import Console

        output = StringIO()
        test_console = Console(file=output, no_color=True)
        warnings = [
            ConfigWarning(file="config.yaml", field_name="layout", message="invalid value", value="bad"),
        ]
        display_config_warnings(warnings, test_console)
        result = output.getvalue()
        assert "Config Warnings" in result
        assert "config.yaml" in result
        assert "invalid value" in result


class TestSplitDirection:
    """Tests for SplitDirection enum."""

    def test_horizontal_value(self) -> None:
        """Should have 'h' value."""
        assert SplitDirection.HORIZONTAL.value == "h"

    def test_vertical_value(self) -> None:
        """Should have 'v' value."""
        assert SplitDirection.VERTICAL.value == "v"


class TestPaneSplit:
    """Tests for PaneSplit model."""

    def test_defaults(self) -> None:
        """Should have correct defaults."""
        split = PaneSplit(direction=SplitDirection.HORIZONTAL, size=30)
        assert split.command == ""
        assert split.name == ""
        assert split.target == "main"
        assert split.focus is False

    def test_full_spec(self) -> None:
        """Should accept all fields."""
        split = PaneSplit(
            direction=SplitDirection.VERTICAL,
            size=50,
            command="cctmux-tasks",
            name="tasks",
            target="right",
            focus=True,
        )
        assert split.direction == SplitDirection.VERTICAL
        assert split.size == 50
        assert split.command == "cctmux-tasks"
        assert split.name == "tasks"
        assert split.target == "right"
        assert split.focus is True


class TestCustomLayout:
    """Tests for CustomLayout model."""

    def test_defaults(self) -> None:
        """Should have correct defaults."""
        layout = CustomLayout(name="test")
        assert layout.description == ""
        assert layout.splits == []
        assert layout.focus_main is True

    def test_with_splits(self) -> None:
        """Should accept PaneSplit objects."""
        layout = CustomLayout(
            name="my-layout",
            description="A custom layout",
            splits=[
                PaneSplit(direction=SplitDirection.HORIZONTAL, size=40),
                PaneSplit(direction=SplitDirection.VERTICAL, size=50, target="last"),
            ],
        )
        assert len(layout.splits) == 2
        assert layout.splits[0].direction == SplitDirection.HORIZONTAL

    def test_config_with_custom_layouts(self) -> None:
        """Config should load custom layouts from YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                yaml.dump(
                    {
                        "custom_layouts": [
                            {
                                "name": "my-layout",
                                "description": "Test layout",
                                "splits": [
                                    {"direction": "h", "size": 40},
                                    {"direction": "v", "size": 50, "command": "htop", "target": "last"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config, warnings = load_config(config_path)
            assert warnings == []
            assert len(config.custom_layouts) == 1
            assert config.custom_layouts[0].name == "my-layout"
            assert len(config.custom_layouts[0].splits) == 2


class TestValidateLayoutName:
    """Tests for validate_layout_name function."""

    def test_valid_names(self) -> None:
        """Should accept valid names."""
        assert validate_layout_name("my-layout") == "my-layout"
        assert validate_layout_name("test") == "test"
        assert validate_layout_name("dev-2") == "dev-2"

    def test_empty_name_raises(self) -> None:
        """Should reject empty name."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_layout_name("")

    def test_uppercase_raises(self) -> None:
        """Should reject uppercase names."""
        with pytest.raises(ValueError, match="lowercase"):
            validate_layout_name("MyLayout")

    def test_special_chars_raises(self) -> None:
        """Should reject names with special characters."""
        with pytest.raises(ValueError, match="lowercase"):
            validate_layout_name("my_layout")

    def test_leading_hyphen_raises(self) -> None:
        """Should reject names with leading hyphens."""
        with pytest.raises(ValueError, match="lowercase"):
            validate_layout_name("-layout")

    def test_builtin_collision_raises(self) -> None:
        """Should reject names that collide with built-in layouts."""
        with pytest.raises(ValueError, match="conflicts with built-in"):
            validate_layout_name("editor")

    def test_all_builtins_rejected(self) -> None:
        """Should reject all built-in layout names."""
        for lt in LayoutType:
            with pytest.raises(ValueError, match="conflicts with built-in"):
                validate_layout_name(lt.value)
