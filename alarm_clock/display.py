"""display.py — Rich UI: alarm list table, live countdown, fire banner."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from alarm_clock.storage import Alarm
from alarm_clock.utils import format_timedelta

console = Console()

# ─── ASCII art banner shown when an alarm fires ───────────────────────────────

_BELL_ART = r"""
    ╔═══════════════════════════════════════╗
    ║                                       ║
    ║         .::!!!!!!!:.                  ║
    ║      .!!!!!!!!!!!!!!!!!.              ║
    ║    .:!!!!!!!!!!!!!!!!!!!!!.           ║
    ║   :!!!!!!!!!!!!!!!!!!!!!!!!!          ║
    ║  :!!!!!!!!!!!!!!!!!!!!!!!!!!:         ║
    ║  !!!!!!!!!!!!!!!!!!!!!!!!!!!!         ║
    ║  !!!!!!!!!!!!!!!!!!!!!!!!!!!!         ║
    ║  !!!!!!!!!!!!!!!!!!!!!!!!!!!!         ║
    ║  `!!!!!!!!!!!!!!!!!!!!!!!!!!!         ║
    ║   :!!!!!!!!!!!!!!!!!!!!!!!!!`         ║
    ║    `.!!!!!!!!!!!!!!!!!!!!!`           ║
    ║       .:!!!!!!!!!!!!!:.              ║
    ║           `!!!!!!`                   ║
    ║           !!!!!!!!!                  ║
    ║        .`!!!!!!!!!!`.               ║
    ║                                       ║
    ╚═══════════════════════════════════════╝
"""

_CLOCK_ART = r"""
  ██████╗ ██╗      █████╗ ██████╗ ███╗   ███╗
 ██╔══██╗██║     ██╔══██╗██╔══██╗████╗ ████║
 ███████║██║     ███████║██████╔╝██╔████╔██║
 ██╔══██║██║     ██╔══██║██╔══██╗██║╚██╔╝██║
 ██║  ██║███████╗██║  ██║██║  ██║██║ ╚═╝ ██║
 ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
"""


# ─── Alarm list table (for `list` command) ────────────────────────────────────


def build_alarm_table(alarms: list[Alarm]) -> Table:
    """Build a rich Table showing all alarms with status and next-fire time."""
    table = Table(
        title="⏰  Alarms",
        box=box.ROUNDED,
        border_style="bright_cyan",
        header_style="bold bright_white",
        title_style="bold bright_cyan",
        show_lines=True,
        expand=False,
        min_width=70,
    )

    table.add_column("ID", style="dim", width=10)
    table.add_column("Name", style="bright_white", min_width=16)
    table.add_column("Time", justify="center", width=7)
    table.add_column("Repeat", justify="center", width=10)
    table.add_column("Next Fire", justify="right", min_width=22)
    table.add_column("Countdown", justify="right", min_width=12)
    table.add_column("Status", justify="center", width=10)

    if not alarms:
        table.add_row(
            *[""] * 6,
            "[dim]No alarms yet — use [bold]add[/bold] to create one.[/dim]",
        )
        return table

    for alarm in sorted(alarms, key=lambda a: a.time):
        status_text, status_style = _status(alarm)
        next_fire = alarm.next_fire()
        next_fire_str = (
            next_fire.strftime("%a %Y-%m-%d %H:%M") if next_fire else "—"
        )
        countdown_str = (
            format_timedelta(alarm.time_until()) if alarm.time_until() else "—"
        )

        # Colour the time column based on countdown proximity
        nf_td = alarm.time_until()
        if nf_td is not None and nf_td.total_seconds() < 60:
            time_style = "bold red blink"
        elif nf_td is not None and nf_td.total_seconds() < 600:
            time_style = "bold yellow"
        else:
            time_style = "bright_green" if alarm.enabled else "dim"

        table.add_row(
            f"[dim]{alarm.id}[/dim]",
            f"[{time_style}]{alarm.name}[/{time_style}]",
            f"[bold]{alarm.time}[/bold]",
            _repeat_badge(alarm.repeat),
            f"[cyan]{next_fire_str}[/cyan]",
            f"[yellow]{countdown_str}[/yellow]",
            f"[{status_style}]{status_text}[/{status_style}]",
        )

    return table


def print_alarm_table(alarms: list[Alarm]) -> None:
    """Print the alarm list table to stdout."""
    console.print()
    console.print(build_alarm_table(alarms))
    console.print()


# ─── Live countdown table (used inside `run` mode) ────────────────────────────


def build_countdown_table(alarms: list[Alarm]) -> Table:
    """Build a compact live countdown table for the run loop."""
    now_str = datetime.now().strftime("%A, %Y-%m-%d  %H:%M:%S")

    table = Table(
        title=f"⏰  Alarm Clock  ·  [dim]{now_str}[/dim]",
        box=box.SIMPLE_HEAVY,
        border_style="bright_blue",
        header_style="bold bright_blue",
        title_style="bold bright_cyan",
        show_lines=False,
        expand=True,
    )

    table.add_column("ID", style="dim", width=10)
    table.add_column("Name", style="bright_white")
    table.add_column("Time", justify="center", width=7)
    table.add_column("Repeat", justify="center", width=10)
    table.add_column("Fires In", justify="right", min_width=14)
    table.add_column("Status", justify="center", width=11)

    enabled_alarms = [a for a in alarms if a.enabled]
    if not enabled_alarms:
        table.add_row(*[""] * 5, "[dim]No enabled alarms.[/dim]")
        return table

    for alarm in sorted(enabled_alarms, key=lambda a: a.next_fire() or datetime.max):
        status_text, status_style = _status(alarm)
        nf_td = alarm.time_until()
        countdown_str = format_timedelta(nf_td) if nf_td is not None else "—"

        if nf_td is not None and nf_td.total_seconds() < 60:
            countdown_style = "bold red blink"
        elif nf_td is not None and nf_td.total_seconds() < 600:
            countdown_style = "bold yellow"
        else:
            countdown_style = "bright_cyan"

        table.add_row(
            alarm.id,
            alarm.name,
            f"[bold]{alarm.time}[/bold]",
            _repeat_badge(alarm.repeat),
            f"[{countdown_style}]{countdown_str}[/{countdown_style}]",
            f"[{status_style}]{status_text}[/{status_style}]",
        )

    return table


# ─── Alarm fire banner ────────────────────────────────────────────────────────


def build_fire_banner(alarm: Alarm) -> Panel:
    """Build a full-width fire banner panel for when an alarm fires."""
    fire_time = datetime.now().strftime("%H:%M:%S")

    art = Text(_CLOCK_ART, style="bold bright_yellow", justify="center")
    bell = Text(_BELL_ART, style="bright_yellow", justify="center")

    alarm_title = Text(f"\n⏰  {alarm.name.upper()}  ⏰", style="bold bright_red", justify="center")
    alarm_title.stylize("blink")

    time_text = Text(f"  {fire_time}  ", style="bold white on red", justify="center")
    prompt = Text(
        "\n\n  [S] Snooze  ·  [D] Dismiss  ·  [Q] Quit\n",
        style="bold bright_white",
        justify="center",
    )

    content = Align.center(art + bell + alarm_title + Text("\n") + time_text + prompt)

    return Panel(
        content,
        title="[bold bright_red blink]🔔  ALARM FIRING  🔔[/bold bright_red blink]",
        border_style="bright_red",
        box=box.DOUBLE,
        expand=True,
        padding=(1, 4),
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _status(alarm: Alarm) -> tuple[str, str]:
    """Return (label, style) for an alarm's current status."""
    if not alarm.enabled:
        return "Disabled", "dim red"
    if alarm.snoozed_until:
        try:
            snooze_dt = datetime.fromisoformat(alarm.snoozed_until)
            if snooze_dt > datetime.now():
                return "Snoozed", "yellow"
        except ValueError:
            pass
    return "Active", "bright_green"


def _repeat_badge(repeat: str) -> str:
    """Return a styled repeat badge string."""
    badges = {
        "once": "[bold magenta]Once[/bold magenta]",
        "daily": "[bold cyan]Daily[/bold cyan]",
        "weekdays": "[bold blue]Weekdays[/bold blue]",
        "weekends": "[bold green]Weekends[/bold green]",
    }
    if repeat in badges:
        return badges[repeat]
    # custom day list
    return f"[bold bright_yellow]{repeat}[/bold bright_yellow]"


def print_success(msg: str) -> None:
    """Print a success message."""
    console.print(f"[bold bright_green]✓[/bold bright_green]  {msg}")


def print_error(msg: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✗[/bold red]  {msg}")


def print_warning(msg: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow]  {msg}")


def print_info(msg: str) -> None:
    """Print an informational message."""
    console.print(f"[bold bright_blue]ℹ[/bold bright_blue]  {msg}")
