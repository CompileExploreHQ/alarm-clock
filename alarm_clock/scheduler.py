"""scheduler.py — Main run loop, alarm firing logic, non-blocking input."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from rich.live import Live

from alarm_clock.audio import ring
from alarm_clock.display import (
    build_countdown_table,
    build_fire_banner,
    console,
    print_success,
    print_warning,
)
from alarm_clock.storage import Alarm, check_missed_alarms, load_alarms, save_alarms

# ─── Non-blocking keyboard input (cross-platform) ─────────────────────────────

_IS_WINDOWS = sys.platform == "win32"


def _get_keypress() -> Optional[str]:
    """Return a pressed key character without blocking, or None if no key was pressed."""
    if _IS_WINDOWS:
        import msvcrt  # type: ignore[import]

        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            return ch.lower() if isinstance(ch, str) else ch.decode("utf-8", errors="ignore").lower()
        return None
    else:
        import select
        import tty
        import termios

        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
            tty.setraw(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                ch = sys.stdin.read(1)
                return ch.lower()
            return None
        except Exception:
            return None
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass


# ─── Constants ────────────────────────────────────────────────────────────────

_POLL_INTERVAL = 1.0  # seconds between alarm checks
_FIRE_WINDOW = 30     # seconds past fire time during which alarm is "now"


# ─── Main run loop ────────────────────────────────────────────────────────────


def run_scheduler() -> None:
    """Blocking run loop — shows live countdown and handles alarm firing.

    Architecture: instead of stopping/restarting Rich Live (unreliable on
    Windows), we use an outer while-True loop.  Each iteration either:
      (a) enters a Live countdown that runs until an alarm fires, then breaks
          out of Live cleanly before handling the fire event, or
      (b) handles a pending fire event (banner + S/D/Q input) outside Live.

    This keeps the Live context always in a well-defined state.
    """
    # ── Startup missed-alarm warnings ──────────────────────────────────────
    alarms = load_alarms()
    missed = check_missed_alarms(alarms)
    if missed:
        console.print()
        for alarm, missed_time in missed:
            print_warning(
                f"Missed alarm [bold]{alarm.name}[/bold] "
                f"(was due at {missed_time.strftime('%H:%M')} "
                f"on {missed_time.strftime('%a %Y-%m-%d')})"
            )
        console.print()

    console.print(
        "\n[bold bright_cyan]Alarm clock started.[/bold bright_cyan]  "
        "Press [bold]Ctrl+C[/bold] to stop.\n"
    )

    # fired_events: maps alarm.id -> fire-key string we already acted on,
    # preventing the same 1-minute event from firing twice.
    fired_events: dict[str, str] = {}

    try:
        while True:
            alarms = load_alarms()

            # ── Phase 1: enter Live countdown ──────────────────────────────
            pending: Optional[Alarm] = None
            with Live(
                build_countdown_table(alarms),
                console=console,
                refresh_per_second=1,
                transient=False,
            ) as live:
                while True:
                    alarms = load_alarms()
                    candidate = _first_firing(alarms, fired_events)
                    if candidate is not None:
                        # Record before we exit Live so it won't re-trigger
                        fk = _fire_key(candidate)
                        if fk:
                            fired_events[candidate.id] = fk
                        pending = candidate
                        break  # exit Live cleanly
                    live.update(build_countdown_table(alarms))
                    time.sleep(_POLL_INTERVAL)

            # ── Phase 2: handle the fire event outside Live ─────────────────
            if pending is not None:
                _handle_fire(pending, alarms)
                alarms = load_alarms()
                pending = None
                # Loop back → re-enter Live with fresh data

    except KeyboardInterrupt:
        console.print("\n[bold bright_yellow]Alarm clock stopped.[/bold bright_yellow]\n")


# ─── Fire detection ───────────────────────────────────────────────────────────


def _first_firing(alarms: list[Alarm], fired_events: dict[str, str]) -> Optional[Alarm]:
    """Return the first alarm that should fire right now and hasn't been handled."""
    for alarm in alarms:
        fk = _fire_key(alarm)
        if fk and fired_events.get(alarm.id) != fk:
            return alarm
    return None


def _fire_key(alarm: Alarm) -> Optional[str]:
    """Return a unique string for the current fire event, or None if not firing.

    BUG FIX: The previous version used alarm.next_fire() which always returns a
    *future* datetime.  That made (now - nf) always negative, so the alarm never
    fired.  This function instead checks today's HH:MM directly.
    """
    if not alarm.enabled:
        return None

    now = datetime.now()

    # ── Snoozed: fire when snooze time expires ─────────────────────────────
    if alarm.snoozed_until:
        try:
            snooze_dt = datetime.fromisoformat(alarm.snoozed_until)
            if snooze_dt > now:
                return None  # still in snooze
            delta = (now - snooze_dt).total_seconds()
            if 0 <= delta <= _FIRE_WINDOW:
                # Include the snooze timestamp in the key so each snooze event
                # is distinct from a regular fire event.
                return f"snooze:{alarm.snoozed_until[:16]}"
        except ValueError:
            pass  # malformed snoozed_until — fall through to normal check

    # ── Regular: did today's HH:MM just happen? ────────────────────────────
    try:
        h, m = map(int, alarm.time.split(":"))
    except (ValueError, AttributeError):
        return None

    today_fire = now.replace(hour=h, minute=m, second=0, microsecond=0)

    active_days = alarm._active_weekdays()
    if active_days is None or today_fire.weekday() not in active_days:
        return None

    delta = (now - today_fire).total_seconds()
    if 0 <= delta <= _FIRE_WINDOW:
        # Encode the full date+time so the key changes each day for daily alarms.
        return today_fire.strftime("%Y-%m-%d %H:%M")

    return None


# ─── Fire handler ─────────────────────────────────────────────────────────────


def _handle_fire(alarm: Alarm, alarms: list[Alarm]) -> None:
    """Clear screen, show banner, ring bell, wait for S / D / Q."""
    ring(times=3)
    console.clear()
    console.print(build_fire_banner(alarm))

    while True:
        key = _get_keypress()
        if key == "s":
            _do_snooze(alarm, alarms, minutes=5)
            console.clear()
            console.print("\n[bold yellow]  Snoozed for 5 minutes.[/bold yellow]\n")
            time.sleep(1)
            break
        elif key == "d":
            _do_dismiss(alarm, alarms)
            console.clear()
            print_success(f"Alarm '{alarm.name}' dismissed.")
            time.sleep(1)
            break
        elif key == "q":
            console.print(
                "\n[bold bright_yellow]Alarm clock stopped.[/bold bright_yellow]\n"
            )
            raise KeyboardInterrupt
        else:
            time.sleep(0.1)


# ─── Snooze / dismiss helpers ─────────────────────────────────────────────────


def _do_snooze(alarm: Alarm, alarms: list[Alarm], minutes: int = 5) -> None:
    """Snooze an alarm for the given number of minutes and save."""
    snooze_until = datetime.now() + timedelta(minutes=minutes)
    for a in alarms:
        if a.id == alarm.id:
            a.snoozed_until = snooze_until.isoformat()
            break
    save_alarms(alarms)


def _do_dismiss(alarm: Alarm, alarms: list[Alarm]) -> None:
    """Dismiss a firing alarm: clear snooze; delete if one-shot."""
    if alarm.repeat == "once":
        alarms[:] = [a for a in alarms if a.id != alarm.id]
    else:
        for a in alarms:
            if a.id == alarm.id:
                a.snoozed_until = None
                break
    save_alarms(alarms)


# ─── CLI snooze (outside run loop) ────────────────────────────────────────────


def cli_snooze(alarm_id: str, minutes: int = 5) -> bool:
    """Snooze an alarm by ID from a CLI command (outside the run loop).

    Returns True if the alarm was found and snoozed, False otherwise.
    """
    alarms = load_alarms()
    for alarm in alarms:
        if alarm.id == alarm_id:
            _do_snooze(alarm, alarms, minutes=minutes)
            return True
    return False
