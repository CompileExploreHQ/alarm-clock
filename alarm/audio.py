"""
alarm/audio.py
~~~~~~~~~~~~~~
Sound playback for alarm notifications.

Strategy (applied in order):
  1. playsound3  - plays the bundled alert.wav (cross-platform, async).
  2. Terminal bell - ASCII BEL char as a silent-system fallback.

A visible banner is *always* printed regardless of audio availability, so
the alarm is never silently missed on headless or muted systems.

The bundled WAV is auto-generated on first use using only Python stdlib
(wave + math) -- no binary blobs in the repository.
"""

from __future__ import annotations

import sys

# Re-encode stdout/stderr as UTF-8 on Windows (default is often cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

import math
import struct
import wave
from pathlib import Path

import click

# Resolve the sounds directory relative to this file so the path is correct
# regardless of the user's current working directory.
_SOUNDS_DIR = Path(__file__).parent.parent / "sounds"
_ALERT_WAV  = _SOUNDS_DIR / "alert.wav"

# ─────────────────────────────────────────────────────────────────────── #
#  Public API                                                                #
# ─────────────────────────────────────────────────────────────────────── #

def play_alert(label: str = "") -> None:
    """Play the alarm sound and print a visible banner.

    Args:
        label: The alarm name to show in the terminal banner.
    """
    _print_alarm_banner(label)
    _ensure_alert_wav()

    if _try_playsound():
        return
    # Audio unavailable — at minimum emit a terminal bell.
    _terminal_bell()


# ─────────────────────────────────────────────────────────────────────── #
#  Internal helpers                                                          #
# ─────────────────────────────────────────────────────────────────────── #

def _try_playsound() -> bool:
    """Attempt playback via playsound3. Returns True on success."""
    try:
        from playsound3 import playsound  # type: ignore[import]
    except ImportError:
        # playsound3 not installed — fall through to bell fallback.
        return False

    if not _ALERT_WAV.exists():
        return False

    try:
        playsound(str(_ALERT_WAV))
        return True
    except Exception:
        # Audio device missing, codec error, etc. — fall through.
        return False


def _terminal_bell() -> None:
    """Emit the ASCII BEL character. Works in most terminals."""
    import sys
    sys.stdout.write("\a")
    sys.stdout.flush()


def _print_alarm_banner(label: str) -> None:
    """Print a prominent, colour-coded alarm banner to stdout."""
    width  = 58
    border = click.style("=" * width, fg="yellow", bold=True)
    title  = "  *** ALARM ***"
    if label:
        title += f"  --  {label}"

    click.echo()
    click.echo(border)
    click.echo(click.style(title, fg="yellow", bold=True))
    click.echo(border)
    click.echo()


# ─────────────────────────────────────────────────────────────────────── #
#  WAV auto-generation                                                       #
# ─────────────────────────────────────────────────────────────────────── #

_SAMPLE_RATE = 44_100
_AMPLITUDE   = 28_000   # 16-bit range is ±32 767; leave headroom


def _ensure_alert_wav() -> None:
    """Generate sounds/alert.wav on first use if it doesn't exist."""
    if _ALERT_WAV.exists():
        return
    try:
        _generate_alert_wav()
    except Exception as exc:
        # Non-fatal; audio simply won't play but the banner will still show.
        click.echo(
            click.style(f"[audio] Could not generate alert.wav: {exc}", fg="bright_black"),
            err=True,
        )


def _generate_alert_wav() -> None:
    """Write a short A-major chime to sounds/alert.wav using stdlib only.

    Three tones form an ascending arpeggio: A4 (440 Hz), C#5 (554 Hz),
    E5 (659 Hz). Each tone has a brief linear fade-in and fade-out to
    avoid the audible "pop" that a hard-cut sine wave produces.
    """
    _SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    # (frequency_hz, duration_seconds)
    notes = [(440.0, 0.25), (554.37, 0.25), (659.25, 0.40)]
    samples: list[int] = []

    for freq, duration in notes:
        samples.extend(_sine_tone(freq, duration))

    with wave.open(str(_ALERT_WAV), "w") as wf:
        wf.setnchannels(1)                  # mono
        wf.setsampwidth(2)                  # 16-bit PCM
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _sine_tone(freq: float, duration: float) -> list[int]:
    """Generate a single sine-wave tone with a linear fade envelope."""
    n    = int(_SAMPLE_RATE * duration)
    fade = int(_SAMPLE_RATE * 0.02)  # 20 ms ramp at start and end
    result: list[int] = []

    for i in range(n):
        t   = i / _SAMPLE_RATE
        val = _AMPLITUDE * math.sin(2 * math.pi * freq * t)

        # Apply fade-in / fade-out envelope.
        if i < fade:
            val *= i / fade
        elif i > n - fade:
            val *= (n - i) / fade

        result.append(int(val))

    return result
