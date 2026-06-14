"""
alarm/cli.py
~~~~~~~~~~~~
Click command-line interface.

Commands:
  add     - Add a named alarm with flexible time input and recurrence.
  list    - Display all alarms with next-fire times and status.
  delete  - Remove an alarm by name or ID prefix.
  snooze  - Delay a named alarm by N minutes.
  run     - Start the foreground daemon loop.

All commands accept a hidden ``--store`` option for testing with a
non-default JSON path (e.g., a temp file) without touching ~/.alarms.json.
"""

from __future__ import annotations

import sys

# Re-encode stdout/stderr as UTF-8 on Windows (default is often cp1252)
# so that Unicode box-drawing and status symbols render correctly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

from datetime import datetime, timedelta
from pathlib import Path

import click

from . import __version__
from .models import Alarm, RecurrenceType, next_fire_time, parse_time_str
from .scheduler import run_daemon
from .store import DEFAULT_PATH, load_alarms, save_alarms


# ─────────────────────────────────────────────────────────────────────── #
#  Top-level group                                                           #
# ─────────────────────────────────────────────────────────────────────── #

@click.group()
@click.version_option(__version__, prog_name="alarm-clock")
def main() -> None:
    """alarm-clock -- A simple, persistent CLI alarm manager.

    \b
    Quick start:
      alarm add --time 08:00 --name "Morning" --recur daily
      alarm list
      alarm run
    """


# ─────────────────────────────────────────────────────────────────────── #
#  add                                                                       #
# ─────────────────────────────────────────────────────────────────────── #

@main.command()
@click.option(
    "--time", "-t", "time_input",
    required=True,
    metavar="TIME",
    help="When to fire. Accepts HH:MM, HH:MM:SS, or 12-hour (e.g. 9:30am, 2:15 PM).",
)
@click.option(
    "--name", "-n",
    required=True,
    metavar="NAME",
    help="Human-readable label. Must be unique.",
)
@click.option(
    "--recur", "-r",
    type=click.Choice(["once", "daily", "weekdays"], case_sensitive=False),
    default="once",
    show_default=True,
    help="How often the alarm repeats.",
)
@click.option("--store", default=str(DEFAULT_PATH), hidden=True, help="Path to alarm store.")
def add(time_input: str, name: str, recur: str, store: str) -> None:
    """Add a new alarm."""
    store_path = Path(store)

    # --- Validate and normalise the time string. ---
    try:
        time_str = parse_time_str(time_input)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="'--time'") from exc

    alarms = load_alarms(store_path)

    # --- Guard: reject duplicate names (case-insensitive). ---
    existing_names = {a.name.lower() for a in alarms}
    if name.lower() in existing_names:
        raise click.UsageError(
            f"An alarm named '{name}' already exists. "
            "Delete it first, or choose a different name."
        )

    recurrence = RecurrenceType(recur.lower())
    alarm      = Alarm(name=name, time_str=time_str, recurrence=recurrence)

    # --- Guard: ONCE alarm whose time has already passed today is useless. ---
    # (DAILY/WEEKDAYS will simply schedule for the next valid slot.)
    now     = datetime.now()
    fire_dt = next_fire_time(alarm, now)

    if fire_dt is None:
        # This can only happen for ONCE when the time is already past.
        raise click.UsageError(
            f"A 'once' alarm for {time_str} has already passed today -- it would "
            "never fire.\n"
            "  - To fire tomorrow at the same time, use --recur daily.\n"
            "  - Or specify a future time."
        )

    alarms.append(alarm)
    save_alarms(alarms, store_path)

    # --- Confirmation output. ---
    click.echo(
        click.style("[+] Alarm added", fg="green", bold=True)
        + f"  [{alarm.id}]  "
        + click.style(alarm.name, bold=True)
        + "  |  "
        + click.style(time_str, fg="cyan")
        + f"  |  {recurrence.value}"
    )
    _echo_next_fire(fire_dt, now)


# ─────────────────────────────────────────────────────────────────────── #
#  list                                                                      #
# ─────────────────────────────────────────────────────────────────────── #

@main.command(name="list")
@click.option("--store", default=str(DEFAULT_PATH), hidden=True)
def list_alarms(store: str) -> None:
    """List all alarms and their next scheduled fire times."""
    store_path = Path(store)
    alarms     = load_alarms(store_path)

    if not alarms:
        click.echo(click.style("No alarms configured.", fg="yellow"))
        click.echo(
            "Add one with:  "
            + click.style("alarm add --time 08:00 --name 'Morning'", fg="cyan")
        )
        return

    now = datetime.now()
    click.echo()

    # Header row
    cols: list[tuple[str, int]] = [
        ("ID",       10),
        ("Name",     22),
        ("Time",     10),
        ("Recur",    11),
        ("Next Fire", 28),
        ("Status",    0),
    ]
    header = "".join(
        click.style(label.ljust(width), fg="bright_white", bold=True)
        for label, width in cols
    )
    click.echo(header)
    click.echo(click.style("-" * 90, fg="bright_black"))

    for alarm in alarms:
        fire_dt    = next_fire_time(alarm, now)
        status_str, status_fg = _status(alarm, fire_dt, now)
        fire_str   = _fire_label(fire_dt, now)

        click.echo(
            click.style(f"{alarm.id:<10}", fg="bright_black")
            + f"{alarm.name:<22}"
            + click.style(f"{alarm.time_str:<10}", fg="cyan")
            + f"{alarm.recurrence.value:<11}"
            + f"{fire_str:<28}"
            + click.style(status_str, fg=status_fg)
        )

    click.echo()


def _fire_label(fire_dt: datetime | None, now: datetime) -> str:
    """Human-friendly description of when an alarm will next fire."""
    if fire_dt is None:
        return "-- (expired)"
    if fire_dt.date() == now.date():
        return f"Today    {fire_dt.strftime('%H:%M:%S')}"
    if (fire_dt.date() - now.date()).days == 1:
        return f"Tomorrow {fire_dt.strftime('%H:%M:%S')}"
    return fire_dt.strftime("%a %b %d  %H:%M:%S")


def _status(alarm: Alarm, fire_dt: datetime | None, now: datetime) -> tuple[str, str]:
    """Return a (label, colour) pair describing the alarm's current state."""
    if not alarm.enabled or fire_dt is None:
        return ("[x] Expired", "bright_black")
    delta = (fire_dt - now).total_seconds()
    if delta < 60:
        return ("[!] Imminent", "red")
    if delta < 3600:
        return ("[~] Soon",    "yellow")
    return ("[*] Active", "green")


# ─────────────────────────────────────────────────────────────────────── #
#  delete                                                                    #
# ─────────────────────────────────────────────────────────────────────── #

@main.command()
@click.option("--name", "-n", default=None, metavar="NAME",
              help="Delete alarm by exact name (case-insensitive).")
@click.option("--id",   "alarm_id", default=None, metavar="ID",
              help="Delete alarm by ID or ID prefix.")
@click.option("--store", default=str(DEFAULT_PATH), hidden=True)
def delete(name: str | None, alarm_id: str | None, store: str) -> None:
    """Delete an alarm by name or ID."""
    if not name and not alarm_id:
        raise click.UsageError("Provide at least one of --name or --id.")

    store_path = Path(store)
    alarms     = load_alarms(store_path)

    if name:
        matches = [a for a in alarms if a.name.lower() == name.lower()]
    else:
        matches = [a for a in alarms if a.id.startswith(alarm_id)]  # type: ignore[arg-type]

    if not matches:
        identifier = f"name '{name}'" if name else f"ID prefix '{alarm_id}'"
        raise click.UsageError(f"No alarm found with {identifier}.")

    if len(matches) > 1:
        # ID prefix is ambiguous — ask the user to be more specific.
        click.echo(click.style("Multiple alarms match. Please be more specific:", fg="yellow"))
        for a in matches:
            click.echo(f"  [{a.id}]  {a.name}")
        sys.exit(1)

    target = matches[0]
    save_alarms([a for a in alarms if a.id != target.id], store_path)

    click.echo(
        click.style("[-] Deleted", fg="red", bold=True)
        + f"  [{target.id}]  {target.name}"
    )


# ─────────────────────────────────────────────────────────────────────── #
#  snooze                                                                    #
# ─────────────────────────────────────────────────────────────────────── #

@main.command()
@click.option("--name", "-n", required=True, metavar="NAME",
              help="Name of the alarm to snooze.")
@click.option("--minutes", "-m", default=5, show_default=True, metavar="N",
              help="Minutes to snooze for.")
@click.option("--store", default=str(DEFAULT_PATH), hidden=True)
def snooze(name: str, minutes: int, store: str) -> None:
    """Snooze an alarm: adds a one-time alarm N minutes from now.

    The original alarm is left unchanged. The snoozed alarm is named
    '<NAME> (snoozed)' and fires once, then expires automatically.
    """
    if minutes < 1:
        raise click.BadParameter("Must be at least 1.", param_hint="'--minutes'")

    store_path = Path(store)
    alarms     = load_alarms(store_path)

    # Verify the named alarm actually exists.
    if not any(a.name.lower() == name.lower() for a in alarms):
        raise click.UsageError(f"No alarm named '{name}' found.")

    snooze_name = f"{name} (snoozed)"
    if any(a.name.lower() == snooze_name.lower() for a in alarms):
        raise click.UsageError(
            f"A snoozed alarm for '{name}' already exists. "
            "Delete it first with:  "
            + click.style(f"alarm delete --name \"{snooze_name}\"", fg="cyan")
        )

    snooze_dt   = datetime.now() + timedelta(minutes=minutes)
    snooze_time = snooze_dt.strftime("%H:%M:%S")

    snooze_alarm = Alarm(
        name       = snooze_name,
        time_str   = snooze_time,
        recurrence = RecurrenceType.ONCE,
    )
    alarms.append(snooze_alarm)
    save_alarms(alarms, store_path)

    click.echo(
        click.style(f"[z] Snoozed '{name}'", fg="cyan", bold=True)
        + f"  ->  fires at "
        + click.style(snooze_time, fg="cyan")
        + f"  ({minutes} min from now)"
    )


# ─────────────────────────────────────────────────────────────────────── #
#  run                                                                       #
# ─────────────────────────────────────────────────────────────────────── #

@main.command()
@click.option("--store", default=str(DEFAULT_PATH), hidden=True)
def run(store: str) -> None:
    """Start the foreground alarm daemon (blocks until Ctrl-C)."""
    run_daemon(Path(store))


# ─────────────────────────────────────────────────────────────────────── #
#  Shared helpers                                                             #
# ─────────────────────────────────────────────────────────────────────── #

def _echo_next_fire(fire_dt: datetime, now: datetime) -> None:
    """Print a dim line showing when the newly-added alarm will fire."""
    delta     = fire_dt - now
    total_min = int(delta.total_seconds()) // 60
    hours, minutes = divmod(total_min, 60)

    if hours:
        human = f"{hours}h {minutes}m from now"
    else:
        human = f"{minutes}m from now"

    click.echo(
        click.style(
            f"   Next fire: {fire_dt.strftime('%H:%M:%S')}  ({human})",
            fg="bright_black",
        )
    )
