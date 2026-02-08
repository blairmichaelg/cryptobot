"""Shared utility functions for the cryptobot core modules."""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def safe_json_read(filepath: str, max_backups: int = 3) -> Optional[dict]:
    """Read JSON with fallback to backups if corrupted."""
    paths = [filepath] + [f"{filepath}.backup.{i}" for i in range(1, max_backups + 1)]
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return None


def safe_json_write(filepath: str, data: dict, max_backups: int = 3) -> None:
    """Atomic JSON write with corruption protection and backups."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        if os.path.exists(filepath):
            backup_base = filepath + ".backup"
            for i in range(max_backups - 1, 0, -1):
                old = f"{backup_base}.{i}"
                new = f"{backup_base}.{i + 1}"
                if os.path.exists(old):
                    os.replace(old, new)
            os.replace(filepath, f"{backup_base}.1")

        temp_file = filepath + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with open(temp_file, "r", encoding="utf-8") as f:
            json.load(f)
        os.replace(temp_file, filepath)
    except Exception as e:
        logger.warning(f"Could not safely write JSON to {filepath}: {e}")
