"""audio.py — Cross-platform alarm sound.

Priority chain (each tried in order; first success wins):
  Windows  → winsound.Beep()              (stdlib, zero install)
  macOS    → afplay system sound          (built-in macOS utility)
  macOS    → osascript beep              (AppleScript fallback)
  Linux    → paplay / aplay / pw-play    (system sound via subprocess)
  All      → playsound + bundled .wav    (optional pip install)
  All      → terminal bell \\a            (last resort)
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable


# ─── Public entry point ───────────────────────────────────────────────────────


def ring(times: int = 3) -> None:
    """Ring the alarm using the best available audio method for the current OS.

    Args:
        times: Number of beep cycles (meaning varies by backend).
    """
    backends: list[Callable[[], bool]] = []

    if sys.platform == "win32":
        backends.append(lambda: _ring_winsound(times))
    elif sys.platform == "darwin":
        backends.append(lambda: _ring_macos(times))
    else:
        backends.append(lambda: _ring_linux(times))

    # Cross-platform optional backends
    backends.append(_ring_playsound)
    backends.append(lambda: _terminal_bell(times))

    for backend in backends:
        try:
            if backend():
                return
        except Exception:
            continue


# ─── Windows ──────────────────────────────────────────────────────────────────


def _ring_winsound(times: int) -> bool:
    """Play a rising-tone beep sequence via winsound (Windows stdlib)."""
    try:
        import winsound  # type: ignore[import]

        # Rising attention pattern: A5 → C6 → E6
        pattern = [
            (880,  200),
            (1046, 200),
            (1318, 300),
            (1046, 150),
            (1318, 400),
        ]

        def _play() -> None:
            for _ in range(times):
                for freq, ms in pattern:
                    try:
                        winsound.Beep(freq, ms)
                    except Exception:
                        # Headless / virtual audio: fall back to MessageBeep
                        try:
                            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                        except Exception:
                            pass
                        return

        threading.Thread(target=_play, daemon=True).start()
        return True
    except Exception:
        return False


# ─── macOS ────────────────────────────────────────────────────────────────────

# System sound files guaranteed to exist on macOS 10.11+
_MACOS_SOUNDS = [
    "/System/Library/Sounds/Glass.aiff",
    "/System/Library/Sounds/Ping.aiff",
    "/System/Library/Sounds/Blow.aiff",
    "/System/Library/Sounds/Sosumi.aiff",
]


def _ring_macos(times: int) -> bool:
    """Play a system sound on macOS using afplay (no install needed)."""
    # Pick the first sound file that actually exists
    sound_file = next((f for f in _MACOS_SOUNDS if Path(f).exists()), None)

    if sound_file:
        def _play_afplay() -> None:
            for _ in range(times):
                try:
                    subprocess.run(
                        ["afplay", sound_file],
                        check=False,
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass

        threading.Thread(target=_play_afplay, daemon=True).start()
        return True

    # afplay found but no sound file — try osascript beep
    return _ring_osascript(times)


def _ring_osascript(times: int) -> bool:
    """Trigger the macOS system beep via osascript (AppleScript)."""
    try:
        def _play() -> None:
            try:
                subprocess.run(
                    ["osascript", "-e", f"beep {times}"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()
        return True
    except Exception:
        return False


# ─── Linux ────────────────────────────────────────────────────────────────────

# Common system sound paths (freedesktop / Ubuntu / Fedora / Arch)
_LINUX_SOUNDS = [
    "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/ubuntu/notifications/Rhodes.ogg",
    "/usr/share/sounds/gnome/default/alerts/glass.ogg",
]

# Ordered list of (player_binary, extra_args_before_file)
_LINUX_PLAYERS = [
    ("paplay",  []),          # PulseAudio
    ("pw-play", []),          # PipeWire
    ("aplay",   []),          # ALSA (wav only, but worth trying)
    ("ffplay",  ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("mpg123",  ["-q"]),
    ("cvlc",    ["--play-and-exit"]),
]


def _ring_linux(times: int) -> bool:
    """Play a system sound on Linux using whatever audio player is available."""
    import shutil

    sound_file = next((f for f in _LINUX_SOUNDS if Path(f).exists()), None)
    player_cmd: list[str] | None = None

    if sound_file:
        for binary, extra in _LINUX_PLAYERS:
            if shutil.which(binary):
                player_cmd = [binary] + extra + [sound_file]
                break

    if player_cmd:
        def _play() -> None:
            for _ in range(times):
                try:
                    subprocess.run(
                        player_cmd,
                        check=False,
                        capture_output=True,
                        timeout=15,
                    )
                except Exception:
                    pass

        threading.Thread(target=_play, daemon=True).start()
        return True

    # No player found — try the PC speaker via `beep` utility
    return _ring_linux_beep(times)


def _ring_linux_beep(times: int) -> bool:
    """Use the Linux `beep` utility (PC speaker). Needs beep package installed."""
    import shutil

    if not shutil.which("beep"):
        return False
    try:
        # beep -f <freq> -l <len_ms> -r <repeats>
        def _play() -> None:
            try:
                subprocess.run(
                    ["beep", "-f", "880", "-l", "300", "-r", str(times * 3)],
                    check=False,
                    capture_output=True,
                    timeout=15,
                )
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()
        return True
    except Exception:
        return False


# ─── Optional: playsound + bundled alarm.wav ──────────────────────────────────


def _ring_playsound() -> bool:
    """Play a bundled alarm.wav via the playsound package (optional install)."""
    try:
        import importlib.util

        if importlib.util.find_spec("playsound") is None:
            return False

        from playsound import playsound  # type: ignore[import]

        sound_file = Path(__file__).parent / "alarm.wav"
        if not sound_file.exists():
            return False

        threading.Thread(
            target=playsound, args=(str(sound_file),), daemon=True
        ).start()
        return True
    except Exception:
        return False


# ─── Last resort: terminal bell ───────────────────────────────────────────────


def _terminal_bell(times: int) -> bool:
    """Emit the ASCII bell character (\\a). Silent in many modern terminals."""
    try:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            for _ in range(times):
                buf.write(b"\a")
                buf.flush()
        else:
            for _ in range(times):
                sys.stdout.write("\a")
                sys.stdout.flush()
        return True
    except Exception:
        return False
