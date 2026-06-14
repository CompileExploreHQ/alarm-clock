"""main.py — Click CLI entry point for the alarm clock application."""

from __future__ import annotations

import io
import os
import sys

# Force UTF-8 output on Windows so emoji in rich output renders correctly.
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from typing import Optional

import click
from rich.console import Console

from alarm_clock.display import (
    print_alarm_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from alarm_clock.scheduler import cli_snooze, run_scheduler
from alarm_clock.storage import Alarm, load_alarms, save_alarms
from alarm_clock.utils import parse_time, validate_repeat

console = Console()

# ─── CLI group ────────────────────────────────────────────────────────────────


@click.group()
@click.version_option("1.0.0", prog_name="alarm-clock")
def cli() -> None:
    """Alarm Clock -- a terminal alarm manager.

    \b
    Quick start:
      python main.py add 07:30 --name "Morning standup" --repeat weekdays
      python main.py add "in 45m" --name "Take a break" --once
      python main.py list
      python main.py run
    """


# ─── add ──────────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("time_str", metavar="TIME")
@click.option("--name", "-n", default="Alarm", show_default=True, help="Display name.")
@click.option(
    "--repeat",
    "-r",
    default="daily",
    show_default=True,
    help="Repeat schedule: once | daily | weekdays | weekends | mon,wed,fri",
)
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="One-shot alarm that auto-deletes after firing (shorthand for --repeat once).",
)
def add(time_str: str, name: str, repeat: str, once: bool) -> None:
    """Add a new alarm.

    \b
    TIME can be:
      07:30          24-hour format
      7:30am         12-hour format
      "in 45m"       relative from now (also: "in 2h", "in 1h30m")

    \b
    Examples:
      python main.py add 07:30 --name "Standup" --repeat weekdays
      python main.py add 7:30pm --name "Dinner"
      python main.py add "in 1h" --name "Focus break" --once
    """
    if once:
        repeat = "once"

    # Validate time
    try:
        normalized_time = parse_time(time_str)
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)

    # Validate repeat
    try:
        normalized_repeat = validate_repeat(repeat)
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)

    alarms = load_alarms()

    # Warn on duplicate name (but allow it)
    existing_names = [a.name.lower() for a in alarms]
    if name.lower() in existing_names:
        print_warning(
            f"An alarm named '{name}' already exists. "
            "Creating anyway — use ID to distinguish them."
        )

    alarm = Alarm.new(name=name, time=normalized_time, repeat=normalized_repeat)
    alarms.append(alarm)
    save_alarms(alarms)

    next_fire = alarm.next_fire()
    next_str = next_fire.strftime("%a %Y-%m-%d %H:%M") if next_fire else "—"

    print_success(
        f"Added alarm [bold]{alarm.name}[/bold] "
        f"(ID: [dim]{alarm.id}[/dim]) → fires at [bold]{alarm.time}[/bold] "
        f"([cyan]{normalized_repeat}[/cyan])"
    )
    print_info(f"Next fire: [cyan]{next_str}[/cyan]")


# ─── list ─────────────────────────────────────────────────────────────────────


@cli.command(name="list")
def list_alarms() -> None:
    """List all alarms in a rich table."""
    alarms = load_alarms()
    print_alarm_table(alarms)
    if alarms:
        print_info(
            f"{sum(1 for a in alarms if a.enabled)} of {len(alarms)} alarm(s) enabled."
        )


# ─── delete ───────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("alarm_id")
def delete(alarm_id: str) -> None:
    """Delete an alarm by ID (or partial ID prefix)."""
    alarms = load_alarms()
    matched = _find_alarm(alarms, alarm_id)

    if matched is None:
        print_error(f"No alarm found with ID '{alarm_id}'.")
        print_info("Run [bold]python main.py list[/bold] to see alarm IDs.")
        sys.exit(1)

    alarms.remove(matched)
    save_alarms(alarms)
    print_success(f"Deleted alarm [bold]{matched.name}[/bold] (ID: {matched.id}).")


# ─── toggle ───────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("alarm_id")
def toggle(alarm_id: str) -> None:
    """Enable or disable an alarm by ID (or partial ID prefix)."""
    alarms = load_alarms()
    matched = _find_alarm(alarms, alarm_id)

    if matched is None:
        print_error(f"No alarm found with ID '{alarm_id}'.")
        sys.exit(1)

    matched.enabled = not matched.enabled
    save_alarms(alarms)

    state = "enabled" if matched.enabled else "disabled"
    style = "bright_green" if matched.enabled else "dim red"
    print_success(
        f"Alarm [bold]{matched.name}[/bold] is now [{style}]{state}[/{style}]."
    )


# ─── snooze ───────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("alarm_id")
@click.option(
    "--minutes",
    "-m",
    default=5,
    show_default=True,
    type=click.IntRange(1, 1440),
    help="Number of minutes to snooze.",
)
def snooze(alarm_id: str, minutes: int) -> None:
    """Snooze an alarm by ID for N minutes (default: 5)."""
    found = cli_snooze(alarm_id, minutes=minutes)
    if found:
        print_success(f"Snoozed alarm [bold]{alarm_id}[/bold] for {minutes} minute(s).")
    else:
        print_error(f"No alarm found with ID '{alarm_id}'.")
        print_info("Run [bold]python main.py list[/bold] to see alarm IDs.")
        sys.exit(1)


# ─── run ──────────────────────────────────────────────────────────────────────


@cli.command()
def run() -> None:
    """Run the alarm daemon (blocking, with live countdown display).

    Shows a live table of all enabled alarms and time until each fires.
    When an alarm fires: clears screen, shows an ASCII art banner, rings the
    bell, and prompts [S]nooze / [D]ismiss / [Q]uit.

    Press Ctrl+C at any time to stop.
    """
    run_scheduler()


# ─── Helper ───────────────────────────────────────────────────────────────────


def _find_alarm(alarms: list[Alarm], id_prefix: str) -> Optional[Alarm]:
    """Find an alarm by exact ID or ID prefix match (case-insensitive)."""
    prefix = id_prefix.lower()
    # Exact match first
    for a in alarms:
        if a.id.lower() == prefix:
            return a
    # Prefix match
    matches = [a for a in alarms if a.id.lower().startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    return None  # None if 0 or ambiguous (>1)


# ─── Entry point ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    cli()
