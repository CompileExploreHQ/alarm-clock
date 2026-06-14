"""storage.py — Alarm dataclass + JSON persistence with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

ALARMS_FILE = Path.home() / ".alarms.json"

# Days of week mapping
_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_WEEKDAY_INDICES = {name: idx for idx, name in enumerate(_DAY_NAMES)}


@dataclass
class Alarm:
    """Represents a single alarm with all its configuration."""

    id: str
    name: str
    time: str  # "HH:MM" 24h format
    repeat: str  # "once" | "daily" | "weekdays" | "weekends" | "mon,wed,fri"
    enabled: bool = True
    snoozed_until: Optional[str] = None  # ISO datetime string if snoozed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def new(
        cls,
        name: str,
        time: str,
        repeat: str = "daily",
        enabled: bool = True,
    ) -> "Alarm":
        """Factory method: create a new Alarm with a generated short ID."""
        short_id = uuid.uuid4().hex[:8]
        return cls(
            id=short_id,
            name=name,
            time=time,
            repeat=repeat,
            enabled=enabled,
            created_at=datetime.now().isoformat(),
        )

    def next_fire(self, from_dt: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next datetime this alarm should fire.

        Returns None if the alarm is disabled or has no valid next fire time.
        """
        if not self.enabled:
            return None

        # If currently snoozed, next fire is the snooze time
        if self.snoozed_until:
            try:
                snooze_dt = datetime.fromisoformat(self.snoozed_until)
                if snooze_dt > datetime.now():
                    return snooze_dt
            except ValueError:
                pass  # malformed — fall through to normal calc

        now = from_dt or datetime.now()

        # Parse alarm HH:MM
        try:
            h, m = map(int, self.time.split(":"))
        except (ValueError, AttributeError):
            return None

        # Build candidate datetime for today at alarm time
        today_fire = now.replace(hour=h, minute=m, second=0, microsecond=0)

        # Determine which weekdays this alarm fires
        active_days = self._active_weekdays()
        if active_days is None:
            return None  # bad repeat config

        # Search up to 8 days ahead to find the next valid fire time
        for day_offset in range(8):
            candidate = today_fire + timedelta(days=day_offset)
            if candidate <= now:
                continue
            if candidate.weekday() in active_days:
                return candidate

        return None

    def _active_weekdays(self) -> Optional[set[int]]:
        """Return a set of weekday indices (0=Mon … 6=Sun) for this alarm's repeat.

        Returns None on invalid repeat value.
        """
        rep = self.repeat.lower().strip()
        if rep in ("once", "daily"):
            return set(range(7))  # any day
        if rep == "weekdays":
            return {0, 1, 2, 3, 4}
        if rep == "weekends":
            return {5, 6}
        # comma-separated day abbreviations: "mon,wed,fri"
        parts = [p.strip() for p in rep.split(",")]
        days: set[int] = set()
        for part in parts:
            if part in _WEEKDAY_INDICES:
                days.add(_WEEKDAY_INDICES[part])
            else:
                return None  # unrecognised token
        return days if days else None

    def time_until(self) -> Optional[timedelta]:
        """Return timedelta until next fire, or None if not applicable."""
        nf = self.next_fire()
        if nf is None:
            return None
        return nf - datetime.now()

    def should_fire_now(self, window_seconds: int = 30) -> bool:
        """Return True if this alarm should fire within the given window (seconds).

        We use a 30s window so a 1s polling loop can't miss a minute boundary.
        """
        if not self.enabled:
            return False
        nf = self.next_fire()
        if nf is None:
            return False
        delta = (nf - datetime.now()).total_seconds()
        return -window_seconds < delta <= 0

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Alarm":
        """Deserialize from a plain dict loaded from JSON."""
        return cls(
            id=d["id"],
            name=d["name"],
            time=d["time"],
            repeat=d.get("repeat", "daily"),
            enabled=d.get("enabled", True),
            snoozed_until=d.get("snoozed_until"),
            created_at=d.get("created_at", datetime.now().isoformat()),
        )


def load_alarms() -> list[Alarm]:
    """Load alarms from ~/.alarms.json. Returns empty list if file is missing or corrupt."""
    if not ALARMS_FILE.exists():
        return []
    try:
        raw = ALARMS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        return [Alarm.from_dict(d) for d in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def save_alarms(alarms: list[Alarm]) -> None:
    """Atomically write alarms to ~/.alarms.json (write-temp-then-rename)."""
    data = [a.to_dict() for a in alarms]
    payload = json.dumps(data, indent=2, ensure_ascii=False)

    # Atomic write: write to a temp file in the same directory, then rename
    dir_path = ALARMS_FILE.parent
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp", prefix=".alarms_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, ALARMS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError:
        # Fallback: direct write if temp approach fails (e.g. permission issues)
        ALARMS_FILE.write_text(payload, encoding="utf-8")


def check_missed_alarms(alarms: list[Alarm]) -> list[tuple[Alarm, datetime]]:
    """Return a list of (alarm, missed_time) for alarms that fired in the last 12h.

    Used on startup to warn the user about alarms they may have missed.
    """
    now = datetime.now()
    window_start = now - timedelta(hours=12)
    missed: list[tuple[Alarm, datetime]] = []

    for alarm in alarms:
        if not alarm.enabled:
            continue
        # Check each hour boundary in the last 12h
        try:
            h, m = map(int, alarm.time.split(":"))
        except (ValueError, AttributeError):
            continue

        active_days = alarm._active_weekdays()
        if active_days is None:
            continue

        # Walk backwards hour by hour to find if this alarm fired in window
        check = now.replace(hour=h, minute=m, second=0, microsecond=0)
        for day_back in range(8):
            candidate = check - timedelta(days=day_back)
            if candidate < window_start:
                break
            if candidate >= now:
                continue
            if candidate.weekday() in active_days:
                missed.append((alarm, candidate))
                break  # only report once per alarm

    return missed
