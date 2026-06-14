"""utils.py — Parse time strings into "HH:MM" 24h format."""

from __future__ import annotations

import re
from datetime import datetime, timedelta


def parse_time(s: str) -> str:
    """Parse a time string and return a "HH:MM" 24h string.

    Supported formats:
        "07:30"      → "07:30"
        "7:30"       → "07:30"
        "7:30am"     → "07:30"
        "7:30pm"     → "19:30"
        "19:30"      → "19:30"
        "in 45m"     → current time + 45 minutes
        "in 2h"      → current time + 2 hours
        "in 1h30m"   → current time + 90 minutes
        "in 90m"     → current time + 90 minutes

    Raises:
        ValueError: if the string cannot be parsed.
    """
    s = s.strip().lower()

    # --- Relative format: "in <N>h<M>m", "in <N>h", "in <N>m" ---
    relative_match = re.fullmatch(
        r"in\s+(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", s
    )
    if relative_match:
        hours_str, mins_str = relative_match.group(1), relative_match.group(2)
        if not hours_str and not mins_str:
            raise ValueError(
                f"Cannot parse relative time '{s}'. "
                "Use 'in 45m', 'in 2h', or 'in 1h30m'."
            )
        total_minutes = int(hours_str or 0) * 60 + int(mins_str or 0)
        if total_minutes <= 0:
            raise ValueError("Relative time must be positive (e.g. 'in 5m').")
        fire_dt = datetime.now() + timedelta(minutes=total_minutes)
        return fire_dt.strftime("%H:%M")

    # --- 12h format: "7:30am", "12:00pm", "1:05AM" ---
    twelve_hour_match = re.fullmatch(
        r"(\d{1,2}):(\d{2})\s*(am|pm)", s
    )
    if twelve_hour_match:
        h, m, meridiem = (
            int(twelve_hour_match.group(1)),
            int(twelve_hour_match.group(2)),
            twelve_hour_match.group(3),
        )
        _validate_hm(h, m, twelve_hour=True)
        if meridiem == "am":
            h = 0 if h == 12 else h          # 12:xx am → 00:xx
        else:
            h = 12 if h == 12 else h + 12    # 12:xx pm → 12:xx; 1:xx pm → 13:xx
        return f"{h:02d}:{m:02d}"

    # --- 24h format: "07:30", "7:30", "19:05" ---
    twenty_four_match = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if twenty_four_match:
        h, m = int(twenty_four_match.group(1)), int(twenty_four_match.group(2))
        _validate_hm(h, m, twelve_hour=False)
        return f"{h:02d}:{m:02d}"

    raise ValueError(
        f"Cannot parse time '{s}'.\n"
        "Valid formats: '07:30', '7:30am', '7:30pm', 'in 45m', 'in 2h', 'in 1h30m'."
    )


def _validate_hm(h: int, m: int, twelve_hour: bool) -> None:
    """Raise ValueError if hour/minute values are out of range."""
    max_h = 12 if twelve_hour else 23
    if not (0 <= h <= max_h):
        raise ValueError(f"Hour {h} is out of range (0–{max_h}).")
    if not (0 <= m <= 59):
        raise ValueError(f"Minute {m} is out of range (0–59).")


def format_timedelta(td: timedelta) -> str:
    """Format a timedelta into a human-readable string like '2h 05m 30s'."""
    total = int(td.total_seconds())
    if total < 0:
        return "overdue"
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def validate_repeat(repeat: str) -> str:
    """Validate and normalise a repeat string. Raises ValueError on bad input."""
    valid_keywords = {"once", "daily", "weekdays", "weekends"}
    day_abbrevs = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

    r = repeat.lower().strip()
    if r in valid_keywords:
        return r

    # comma-separated day list
    parts = [p.strip() for p in r.split(",")]
    if all(p in day_abbrevs for p in parts) and parts:
        return ",".join(parts)

    raise ValueError(
        f"Invalid repeat value '{repeat}'.\n"
        "Valid options: once, daily, weekdays, weekends, or comma-separated days "
        "(e.g. 'mon,wed,fri')."
    )
