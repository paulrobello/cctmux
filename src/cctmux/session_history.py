"""Session history management for cctmux."""

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from cctmux.xdg_paths import ensure_directories, get_history_file_path


class SessionEntry(BaseModel):
    """A single session history entry."""

    session_name: str
    project_dir: str
    last_accessed: datetime
    created: datetime


class SessionHistory(BaseModel):
    """Container for session history."""

    entries: list[SessionEntry] = []


def load_history(history_path: Path | None = None) -> SessionHistory:
    """Load session history from YAML file.

    Args:
        history_path: Optional path to history file. Uses default if None.

    Returns:
        The loaded history, or empty history if file doesn't exist.
    """
    path = history_path or get_history_file_path()

    if not path.exists():
        return SessionHistory()

    try:
        with path.open(encoding="utf-8") as f:
            data: dict[str, object] = yaml.safe_load(f) or {}
        return SessionHistory.model_validate(data)
    except (yaml.YAMLError, ValueError):
        return SessionHistory()


def save_history(history: SessionHistory, history_path: Path | None = None) -> None:
    """Save session history to YAML file.

    Args:
        history: The history to save.
        history_path: Optional path to history file. Uses default if None.
    """
    ensure_directories()
    path = history_path or get_history_file_path()

    # Convert to serializable format
    data = {"entries": [entry.model_dump(mode="json") for entry in history.entries]}

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)


def add_or_update_entry(
    history: SessionHistory,
    session_name: str,
    project_dir: str,
    max_entries: int = 50,
) -> SessionHistory:
    """Add or update a session entry in history.

    Args:
        history: The current history.
        session_name: The session name.
        project_dir: The project directory path.
        max_entries: Maximum number of entries to keep.

    Returns:
        Updated history with the new/updated entry.
    """
    now = datetime.now()

    # Check if entry exists
    existing_idx: int | None = None
    for idx, entry in enumerate(history.entries):
        if entry.session_name == session_name:
            existing_idx = idx
            break

    if existing_idx is not None:
        # Update existing entry
        existing = history.entries[existing_idx]
        updated = SessionEntry(
            session_name=session_name,
            project_dir=project_dir,
            last_accessed=now,
            created=existing.created,
        )
        entries = [e for i, e in enumerate(history.entries) if i != existing_idx]
        entries.insert(0, updated)
    else:
        # Add new entry
        new_entry = SessionEntry(
            session_name=session_name,
            project_dir=project_dir,
            last_accessed=now,
            created=now,
        )
        entries = [new_entry, *history.entries]

    # Sort by last_accessed (most recent first)
    entries.sort(key=lambda e: e.last_accessed, reverse=True)

    # Prune if needed
    entries = entries[:max_entries]

    return SessionHistory(entries=entries)


def get_recent_session_names(history: SessionHistory) -> list[str]:
    """Get list of session names sorted by last access time.

    Args:
        history: The session history.

    Returns:
        List of session names, most recent first.
    """
    return [entry.session_name for entry in history.entries]


def get_entry_by_name(history: SessionHistory, session_name: str) -> SessionEntry | None:
    """Get a session entry by name.

    Args:
        history: The session history.
        session_name: The session name to find.

    Returns:
        The matching entry, or None if not found.
    """
    for entry in history.entries:
        if entry.session_name == session_name:
            return entry
    return None
