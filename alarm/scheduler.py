"""
alarm/scheduler.py
~~~~~~~~~~~~~~~~~~
Foreground daemon loop that watches for alarms and fires them.

Key design decisions:
  - Hot-reload: The store is re-read from disk on every tick, so alarms
    added or deleted in a *separate* terminal window take effect
    immediately without restarting the daemon.
  - 0.5 s sleep interval: Finer than 1 s so Ctrl-C feels snappy and we
    don't miss alarms that fire on an odd second boundary.
  - Fire window (+-2 s): Compensates for the ~0.5 s loop granularity and
    any minor system clock jitter. A fired alarm is tracked by
    (alarm_id, date) so it never fires twice on the same calendar day.
  - ONCE alarms are disabled in the store after firing so they don't
    re-trigger if the daemon restarts within the same day.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Re-encode stdout/stderr as UTF-8 on Windows (default is often cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

import click

from .audio import play_alert
from .models import Alarm, RecurrenceType, next_fire_time
from .store import DEFAULT_PATH, load_alarms, save_alarms

logger = logging.getLogger(__name__)

# Type alias: (alarm_id, ISO-date-string) uniquely identifies one firing event.
type _FiredKey = tuple[str, str]

# Alarms fire when |now − fire_time| ≤ this many seconds.
_FIRE_WINDOW_SECS: float = 2.0
_TICK_INTERVAL_SECS: float = 0.5


def run_daemon(store_path: Path = DEFAULT_PATH) -> None:
    """Start the foreground alarm daemon.

    Reads *store_path* every tick to pick up changes made by other
    `alarm` commands running in parallel. Exits cleanly on Ctrl-C.
    """
    click.echo(
        click.style("[*] Alarm daemon started.", fg="green", bold=True)
        + click.style("  Press Ctrl-C to stop.", fg="bright_black")
    )
    click.echo(click.style(f"    Store: {store_path}", fg="bright_black"))
    click.echo()

    # Track which alarms have already fired today to prevent double-firing.
    fired: set[_FiredKey] = set()

    try:
        while True:
            now    = datetime.now()
            alarms = load_alarms(store_path)
            dirty  = False  # track whether we need to write back

            for alarm in alarms:
                if not alarm.enabled:
                    continue

                fire_dt = next_fire_time(alarm, now)

                if fire_dt is None:
                    # A ONCE alarm whose time has passed — mark disabled so
                    # it doesn't linger as "expired" in `alarm list`.
                    alarm.enabled = False
                    dirty = True
                    continue

                fire_key: _FiredKey = (alarm.id, fire_dt.date().isoformat())
                delta_secs = abs((now - fire_dt).total_seconds())

                if delta_secs <= _FIRE_WINDOW_SECS and fire_key not in fired:
                    fired.add(fire_key)
                    play_alert(alarm.name)

                    if alarm.recurrence == RecurrenceType.ONCE:
                        alarm.enabled = False
                        dirty = True

            # Write back only if something changed, to avoid redundant I/O.
            if dirty:
                save_alarms(alarms, store_path)

            time.sleep(_TICK_INTERVAL_SECS)

    except KeyboardInterrupt:
        click.echo()
        click.echo(click.style("[.] Daemon stopped.", fg="yellow"))
