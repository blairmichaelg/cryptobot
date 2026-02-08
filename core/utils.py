"""Shared utility functions for the cryptobot core modules.

Provides corruption-safe JSON read/write helpers with automatic backup
rotation and atomic write semantics.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def safe_json_read(
    filepath: str, max_backups: int = 3,
) -> Optional[Dict[str, Any]]:
    """Read JSON with fallback to backups if corrupted.

    Tries the primary file first, then checks numbered backup files
    (e.g. ``file.json.backup.1``, ``file.json.backup.2``) in order
    until a valid JSON file is found.

    Args:
        filepath: Path to the primary JSON file.
        max_backups: Maximum number of backup files to check
            (default ``3``).

    Returns:
        Parsed dictionary on success, or ``None`` if all files are
        missing or corrupted.
    """
    paths = [filepath] + [
        f"{filepath}.backup.{i}"
        for i in range(1, max_backups + 1)
    ]
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            continue
    return None


def safe_json_write(
    filepath: str,
    data: Dict[str, Any],
    max_backups: int = 3,
) -> None:
    """Atomic JSON write with corruption protection and backups.

    The write sequence is:
        1. Rotate existing backups (``backup.2`` -> ``backup.3``, etc.).
        2. Move current file to ``backup.1``.
        3. Write new data to a temporary file.
        4. Validate the temporary file by re-reading it.
        5. Atomically replace the target with the temporary file.

    Args:
        filepath: Destination path for the JSON file.
        data: Dictionary to serialise and write.
        max_backups: Number of backup generations to keep
            (default ``3``).
    """
    try:
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        if os.path.exists(filepath):
            backup_base = filepath + ".backup"
            for i in range(max_backups - 1, 0, -1):
                old = f"{backup_base}.{i}"
                new = f"{backup_base}.{i + 1}"
                if os.path.exists(old):
                    os.replace(old, new)
            os.replace(filepath, f"{backup_base}.1")

        temp_file = filepath + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        # Validate by re-reading before committing
        with open(temp_file, "r", encoding="utf-8") as fh:
            json.load(fh)

        os.replace(temp_file, filepath)
    except Exception as e:
        logger.warning(
            "Could not safely write JSON to %s: %s",
            filepath, e,
        )
