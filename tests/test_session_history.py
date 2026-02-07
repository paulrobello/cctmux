"""Tests for cctmux.session_history module."""

import tempfile
from datetime import datetime
from pathlib import Path

import yaml

from cctmux.session_history import (
    SessionEntry,
    SessionHistory,
    add_or_update_entry,
    get_entry_by_name,
    get_recent_session_names,
    load_history,
    save_history,
)


class TestSessionEntry:
    """Tests for SessionEntry model."""

    def test_creation(self) -> None:
        """Should create entry with all fields."""
        now = datetime.now()
        entry = SessionEntry(
            session_name="test-project",
            project_dir="/home/user/test-project",
            last_accessed=now,
            created=now,
        )
        assert entry.session_name == "test-project"
        assert entry.project_dir == "/home/user/test-project"
        assert entry.last_accessed == now
        assert entry.created == now


class TestSessionHistory:
    """Tests for SessionHistory model."""

    def test_default_empty(self) -> None:
        """Should default to empty entries list."""
        history = SessionHistory()
        assert history.entries == []

    def test_with_entries(self) -> None:
        """Should accept entries list."""
        now = datetime.now()
        entry = SessionEntry(
            session_name="test",
            project_dir="/test",
            last_accessed=now,
            created=now,
        )
        history = SessionHistory(entries=[entry])
        assert len(history.entries) == 1
        assert history.entries[0].session_name == "test"


class TestLoadHistory:
    """Tests for load_history function."""

    def test_missing_file_returns_empty(self) -> None:
        """Should return empty history when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "nonexistent.yaml"
            history = load_history(history_path)
            assert history.entries == []

    def test_loads_valid_history(self) -> None:
        """Should load valid history from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.yaml"
            history_path.write_text(
                yaml.dump(
                    {
                        "entries": [
                            {
                                "session_name": "project-a",
                                "project_dir": "/home/user/project-a",
                                "last_accessed": "2024-01-15T10:30:00",
                                "created": "2024-01-10T09:00:00",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            history = load_history(history_path)
            assert len(history.entries) == 1
            assert history.entries[0].session_name == "project-a"


class TestSaveHistory:
    """Tests for save_history function."""

    def test_saves_history(self) -> None:
        """Should save history to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.yaml"
            now = datetime.now()
            entry = SessionEntry(
                session_name="test-project",
                project_dir="/home/user/test",
                last_accessed=now,
                created=now,
            )
            history = SessionHistory(entries=[entry])
            save_history(history, history_path)

            assert history_path.exists()
            with history_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert len(data["entries"]) == 1
            assert data["entries"][0]["session_name"] == "test-project"


class TestAddOrUpdateEntry:
    """Tests for add_or_update_entry function."""

    def test_adds_new_entry(self) -> None:
        """Should add new entry to empty history."""
        history = SessionHistory()
        updated = add_or_update_entry(history, "new-project", "/home/user/new")
        assert len(updated.entries) == 1
        assert updated.entries[0].session_name == "new-project"

    def test_updates_existing_entry(self) -> None:
        """Should update last_accessed for existing entry."""
        now = datetime.now()
        entry = SessionEntry(
            session_name="existing",
            project_dir="/home/user/existing",
            last_accessed=now,
            created=now,
        )
        history = SessionHistory(entries=[entry])
        updated = add_or_update_entry(history, "existing", "/home/user/existing")

        assert len(updated.entries) == 1
        assert updated.entries[0].last_accessed > now
        assert updated.entries[0].created == now  # Created should not change

    def test_moves_updated_to_front(self) -> None:
        """Should move updated entry to front of list."""
        now = datetime.now()
        entry1 = SessionEntry(
            session_name="project-a",
            project_dir="/a",
            last_accessed=now,
            created=now,
        )
        entry2 = SessionEntry(
            session_name="project-b",
            project_dir="/b",
            last_accessed=now,
            created=now,
        )
        history = SessionHistory(entries=[entry1, entry2])
        updated = add_or_update_entry(history, "project-b", "/b")

        assert updated.entries[0].session_name == "project-b"

    def test_prunes_excess_entries(self) -> None:
        """Should prune entries beyond max_entries."""
        now = datetime.now()
        entries = [
            SessionEntry(
                session_name=f"project-{i}",
                project_dir=f"/project-{i}",
                last_accessed=now,
                created=now,
            )
            for i in range(10)
        ]
        history = SessionHistory(entries=entries)
        updated = add_or_update_entry(history, "new-project", "/new", max_entries=5)

        assert len(updated.entries) == 5


class TestGetRecentSessionNames:
    """Tests for get_recent_session_names function."""

    def test_returns_names_in_order(self) -> None:
        """Should return session names in order."""
        now = datetime.now()
        entries = [
            SessionEntry(
                session_name="first",
                project_dir="/first",
                last_accessed=now,
                created=now,
            ),
            SessionEntry(
                session_name="second",
                project_dir="/second",
                last_accessed=now,
                created=now,
            ),
        ]
        history = SessionHistory(entries=entries)
        names = get_recent_session_names(history)
        assert names == ["first", "second"]

    def test_empty_history(self) -> None:
        """Should return empty list for empty history."""
        history = SessionHistory()
        names = get_recent_session_names(history)
        assert names == []


class TestGetEntryByName:
    """Tests for get_entry_by_name function."""

    def test_finds_existing_entry(self) -> None:
        """Should find entry by name."""
        now = datetime.now()
        entry = SessionEntry(
            session_name="target",
            project_dir="/target",
            last_accessed=now,
            created=now,
        )
        history = SessionHistory(entries=[entry])
        found = get_entry_by_name(history, "target")

        assert found is not None
        assert found.session_name == "target"

    def test_returns_none_for_missing(self) -> None:
        """Should return None when entry not found."""
        history = SessionHistory()
        found = get_entry_by_name(history, "nonexistent")
        assert found is None
