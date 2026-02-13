"""Utility functions for cctmux."""

import re
import subprocess
from pathlib import Path


def sanitize_session_name(name: str) -> str:
    """Sanitize a folder name to be a valid tmux session name.

    Args:
        name: The original folder name.

    Returns:
        A sanitized session name (lowercase, hyphens, no special chars).
    """
    # Convert to lowercase
    result = name.lower()
    # Replace underscores and spaces with hyphens
    result = result.replace("_", "-").replace(" ", "-")
    # Remove any character that isn't alphanumeric or hyphen
    result = re.sub(r"[^a-z0-9-]", "", result)
    # Collapse multiple hyphens
    result = re.sub(r"-+", "-", result)
    # Remove leading/trailing hyphens
    result = result.strip("-")
    # Ensure we have something left
    return result or "session"


def get_project_name(path: Path) -> str:
    """Get the project name from a path.

    Args:
        path: The project directory path.

    Returns:
        The folder name from the path.
    """
    return path.resolve().name


def select_with_fzf(entries: list[str], prompt: str = "Select: ") -> str | None:
    """Use fzf to select from a list of entries.

    Args:
        entries: List of entries to choose from.
        prompt: The prompt to display.

    Returns:
        The selected entry, or None if cancelled or fzf not available.
    """
    if not entries:
        return None

    try:
        result = subprocess.run(
            ["fzf", "--prompt", prompt, "--height", "40%", "--reverse"],
            input="\n".join(entries),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        # fzf not installed
        pass
    return None


def is_fzf_available() -> bool:
    """Check if fzf is available on the system."""
    try:
        subprocess.run(["fzf", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


DEFAULT_PATH_MAX_LEN = 50


def compress_path(path: str, max_len: int = DEFAULT_PATH_MAX_LEN) -> str:
    """Compress a file path by replacing home with ~ and truncating from the start.

    Args:
        path: The path to compress.
        max_len: Maximum length before truncation.

    Returns:
        Compressed path with ~ for home directory.
    """
    if not path:
        return ""

    # Replace home directory with ~
    home = str(Path.home())
    if path.startswith(home):
        path = "~" + path[len(home) :]

    # If short enough, return as-is
    if len(path) <= max_len:
        return path

    # Truncate from the beginning, preserving filename
    return "..." + path[-(max_len - 3) :]


def compress_paths_in_text(text: str) -> str:
    """Replace home directory paths with ~ throughout the text.

    Args:
        text: Text containing paths.

    Returns:
        Text with home directory replaced by ~.
    """
    if not text:
        return ""
    home = str(Path.home())
    return text.replace(home, "~")
