"""
alarm/models.py
~~~~~~~~~~~~~~~
Core data model: Alarm dataclass, RecurrenceType enum, time parsing,
and the central next_fire_time() scheduling function.

All logic here is pure (no I/O) so it is straightforward to unit-test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


# ─────────────────────────────────────────────────────────────────────── #
#  Enums & constants                                                         #
# ─────────────────────────────────────────────────────────────────────── #

class RecurrenceType(str, Enum):
    """How often an alarm repeats.

    Using `str` as a mixin means the value serialises directly to JSON
    as a plain string without extra conversion.
    """
    ONCE     = "once"
    DAILY    = "daily"
    WEEKDAYS = "weekdays"


# ─────────────────────────────────────────────────────────────────────── #
#  Alarm dataclass                                                           #
# ─────────────────────────────────────────────────────────────────────── #

@dataclass
class Alarm:
    """A single alarm entry.

    Attributes:
        name:       Human-readable label (must be unique in the store).
        time_str:   Normalised "HH:MM:SS" string (always 24-hour).
        recurrence: How often the alarm repeats.
        id:         Short 8-hex-char UUID, auto-generated on creation.
        enabled:    False once a ONCE alarm has fired or the user disables it.
        created_at: ISO-8601 timestamp of when the alarm was added.
    """

    name:       str
    time_str:   str            # "HH:MM:SS"
    recurrence: RecurrenceType

    # Fields with defaults must come after fields without defaults.
    id:         str  = field(default_factory=lambda: uuid.uuid4().hex[:8])
    enabled:    bool = True
    created_at: str  = field(default_factory=lambda: datetime.now().isoformat())

    # ------------------------------------------------------------------ #
    # Serialisation                                                         #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        """Convert to a JSON-serialisable dict."""
        return {
            "id":         self.id,
            "name":       self.name,
            "time_str":   self.time_str,
            "recurrence": self.recurrence.value,
            "enabled":    self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Alarm:
        """Reconstruct an Alarm from a JSON-decoded dict."""
        return cls(
            id         = data["id"],
            name       = data["name"],
            time_str   = data["time_str"],
            recurrence = RecurrenceType(data["recurrence"]),
            enabled    = data.get("enabled", True),
            created_at = data.get("created_at", datetime.now().isoformat()),
        )


# ─────────────────────────────────────────────────────────────────────── #
#  Time parsing                                                              #
# ─────────────────────────────────────────────────────────────────────── #

# All formats we attempt to parse, in priority order.
_TIME_FORMATS_12H = ["%I:%M %p", "%I:%M%p", "%I %p", "%I%p"]
_TIME_FORMATS_24H = ["%H:%M:%S", "%H:%M"]


def parse_time_str(time_input: str) -> str:
    """Accept flexible time strings and return a normalised "HH:MM:SS".

    Supported inputs:
      - 24-hour: "14:30", "14:30:00"
      - 12-hour: "2:30 PM", "2:30pm", "9am", "9 AM"

    Raises:
        ValueError: If the string cannot be parsed in any known format.
    """
    text = time_input.strip()

    # Try 12-hour formats first (they require the AM/PM suffix).
    for fmt in _TIME_FORMATS_12H:
        try:
            t = datetime.strptime(text.upper(), fmt.upper())
            return t.strftime("%H:%M:00")
        except ValueError:
            pass

    # Fall back to 24-hour formats.
    for fmt in _TIME_FORMATS_24H:
        try:
            t = datetime.strptime(text, fmt)
            return t.strftime("%H:%M:%S")
        except ValueError:
            pass

    raise ValueError(
        f"Cannot parse time '{time_input}'. "
        "Use HH:MM, HH:MM:SS, or 12-hour format like '9:30am' or '2:15 PM'."
    )


# ─────────────────────────────────────────────────────────────────────── #
#  Scheduling logic                                                          #
# ─────────────────────────────────────────────────────────────────────── #

def next_fire_time(alarm: Alarm, now: datetime) -> datetime | None:
    """Compute the next datetime this alarm should fire.

    Rules:
      - Disabled alarms → None.
      - ONCE: fire today if time is still in the future; None if already past.
      - DAILY: fire today if time is in the future, otherwise tomorrow.
      - WEEKDAYS (Mon–Fri): like DAILY but skips Sat/Sun.

    Returns:
        A timezone-naive datetime in local time, or None if the alarm
        will never fire again.
    """
    if not alarm.enabled:
        return None

    hour, minute, second = (int(x) for x in alarm.time_str.split(":"))

    # Build a candidate datetime for today at the alarm's clock time.
    today_fire = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

    match alarm.recurrence:
        case RecurrenceType.ONCE:
            # Only fire if the time is still upcoming today.
            return today_fire if today_fire > now else None

        case RecurrenceType.DAILY:
            if today_fire > now:
                return today_fire
            # Time has passed today — schedule for same time tomorrow.
            return today_fire + timedelta(days=1)

        case RecurrenceType.WEEKDAYS:
            # Start from today's slot; if past, move to tomorrow.
            candidate = today_fire if today_fire > now else today_fire + timedelta(days=1)
            # Advance until we land on a Monday–Friday (weekday() 0–4).
            for _ in range(7):
                if candidate.weekday() < 5:
                    return candidate
                candidate += timedelta(days=1)
            # Unreachable in practice, but be safe.
            return None

    return None  # pragma: no cover
