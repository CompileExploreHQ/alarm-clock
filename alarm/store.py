"""
alarm/store.py
~~~~~~~~~~~~~~
JSON persistence layer for alarm data.

Design choices:
  - Atomic writes via temp-file + os.replace() to prevent corruption if the
    process crashes mid-write.
  - Malformed JSON is treated as "empty store" with a warning, not a fatal
    error — keeps the daemon running even after accidental file edits.
  - No external dependencies; uses only stdlib json/os/pathlib.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from .models import Alarm

logger = logging.getLogger(__name__)

# Default store location — respects the user's home directory on all OSes.
DEFAULT_PATH: Path = Path.home() / ".alarms.json"


def load_alarms(path: Path = DEFAULT_PATH) -> list[Alarm]:
    """Load alarms from *path*.

    Returns an empty list if:
      - The file does not exist yet (first run).
      - The file is empty or contains malformed JSON (logs a warning).

    This ensures the daemon and CLI never crash due to a bad store file.
    """
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("Top-level JSON value must be an array.")
        return [Alarm.from_dict(item) for item in data]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "Could not parse alarm store at %s (%s). "
            "Starting with an empty alarm list.",
            path,
            exc,
        )
        return []


def save_alarms(alarms: list[Alarm], path: Path = DEFAULT_PATH) -> None:
    """Persist *alarms* to *path* atomically.

    Writes to a sibling temp file first, then renames it into place.
    `os.replace()` is atomic on POSIX and as close as Windows supports —
    it prevents a partially-written file from being read by a concurrent
    daemon tick.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [alarm.to_dict() for alarm in alarms]

    # Write to a temp file in the same directory so os.replace() is a
    # same-filesystem rename (not a cross-device copy).
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the temp file on any failure to avoid leftover clutter.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
