# alarm-clock

A clean, persistent CLI alarm manager written in Python 3.10+.

```
alarm add  --time 08:00 --name "Standup" --recur weekdays
alarm add  --time 13:00 --name "Lunch"   --recur daily
alarm list
alarm run          # foreground daemon; fires sound + message when time arrives
```

---

## Features

| Feature | Detail |
|---|---|
| Flexible time input | `HH:MM`, `HH:MM:SS`, 12-hour (`9:30am`, `2:15 PM`) |
| Named alarms | Every alarm has a unique label |
| Recurrence | `once`, `daily`, `weekdays` (Mon-Fri) |
| Persistence | Saved to `~/.alarms.json`; survives restarts |
| Hot-reload daemon | `add`/`delete` in a second terminal window takes effect immediately |
| Sound + banner | Plays a generated chime; falls back to terminal bell on silent systems |
| Snooze | CLI command delays an alarm by N minutes |

---

## Requirements

- **Python 3.10 or later** — `python --version` to check
- **pip** — comes bundled with Python

> **Windows users:** Run all commands in **PowerShell** or **Command Prompt**.
> Use `;` to chain commands in PowerShell (not `&&`).

---

## Installation

### Step 1 — Clone the repository

```
git clone <repo-url>
cd alarm-clock
```

### Step 2 — (Recommended) Create a virtual environment

This keeps the project's dependencies isolated from your system Python.

**Windows (PowerShell):**
```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` appear at the start of your terminal prompt. Run
all subsequent commands inside this activated environment.

> **PowerShell execution policy error?** If you see `cannot be loaded because
> running scripts is disabled`, run this once and then retry:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Step 3 — Install dependencies

```
pip install -r requirements.txt
```

### Step 4 — Install the `alarm` shell command

```
pip install -e .
```

This registers `alarm` as a command available anywhere in your terminal
(not just from the project folder).

**Verify it worked:**
```
alarm --help
```

You should see the list of subcommands. If you get a "not recognized" error,
see the troubleshooting section below.

---

## Quick start

```
alarm add --time 08:00 --name "Morning" --recur daily
alarm list
alarm run
```

Open a second terminal and add more alarms while the daemon is running --
they take effect immediately without restarting.

---

## Usage

### `alarm add`

```
alarm add --time 08:00 --name "Morning"               # once, today
alarm add --time 09:30 --name "Standup" --recur weekdays
alarm add --time 13:00 --name "Lunch"   --recur daily
alarm add --time 9:00am --name "Meeting"              # 12-hour format
alarm add --time "2:30 PM" --name "Call"
```

| Option | Short | Required | Description |
|---|---|---|---|
| `--time` | `-t` | yes | When to fire |
| `--name` | `-n` | yes | Unique label |
| `--recur` | `-r` | no | `once` (default), `daily`, `weekdays` |

**Notes:**
- `once` alarms that have already passed for today are rejected with a clear
  error. If you meant tomorrow, use `--recur daily`.
- Alarm names must be unique (case-insensitive). Delete the existing alarm
  first if you want to reuse a name.

### `alarm list`

```
alarm list
```

Shows every alarm with its ID, next fire time, and status.

### `alarm delete`

```
alarm delete --name "Lunch"       # by name (case-insensitive)
alarm delete --id a1b2c3d4        # by full ID
alarm delete --id a1b2            # by ID prefix (must be unambiguous)
```

### `alarm snooze`

```
alarm snooze --name "Morning"             # snooze 5 minutes (default)
alarm snooze --name "Morning" --minutes 10
```

Creates a one-time `<name> (snoozed)` alarm N minutes from now.
The original alarm is left intact.

### `alarm run`

```
alarm run
```

Starts the foreground daemon. Blocks until `Ctrl-C`. While it is running,
you can add, delete, or snooze alarms from another terminal -- changes are
picked up automatically within 1 second.

---

## Troubleshooting

### `alarm` is not recognized after `pip install -e .`

The `alarm` script is installed into your Python environment's `Scripts`
(Windows) or `bin` (macOS/Linux) folder. If that folder is not on your
`PATH`, the command won't be found.

**Fix 1 (recommended) -- use a virtual environment (see Step 2 above).**
Activating a venv automatically puts its `Scripts`/`bin` on your `PATH`.

**Fix 2 -- find and add the Scripts folder manually (Windows):**
```
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```
Copy the path that prints (e.g. `C:\Users\you\AppData\Local\Programs\Python\Python313\Scripts`),
then add it to your `PATH` via *System Properties > Environment Variables*.

**Fix 3 -- skip the install, run directly:**
```
python alarm_cli.py --help
python alarm_cli.py add --time 08:00 --name "Morning"
python alarm_cli.py run
```

### `pip install -e .` fails with `BackendUnavailable` or build errors

Make sure you have a recent version of pip and setuptools:
```
pip install --upgrade pip setuptools
pip install -e .
```

### Audio does not play

`playsound3` uses the OS-native audio system (WinMM on Windows, afplay on
macOS, aplay/paplay on Linux). If playback fails the alarm falls back to a
visible terminal banner + a bell character -- the alarm will never fire
silently.

On Linux, install one of: `pulseaudio-utils`, `alsa-utils`, or `ffmpeg`.

### `Set-ExecutionPolicy` is needed on Windows

If PowerShell blocks the venv activation script:
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then re-run `.venv\Scripts\Activate.ps1`.

---

## How it works

### Project structure

```
alarm-clock/
+-- alarm/
|   +-- __init__.py       # version
|   +-- models.py         # Alarm dataclass, RecurrenceType, next_fire_time()
|   +-- store.py          # JSON load/save (atomic writes)
|   +-- audio.py          # playsound3 -> bell fallback; WAV auto-generation
|   +-- scheduler.py      # daemon loop
|   +-- cli.py            # click commands
+-- sounds/               # alert.wav (auto-generated on first run)
+-- alarm_cli.py          # entry-point shim (use if not installed via pip)
+-- pyproject.toml
+-- requirements.txt
+-- README.md
```

### Design decisions

**`click` over `argparse`**
This app has five distinct subcommands. `click`'s decorator model makes
each command a self-contained, independently testable function. `argparse`
subparsers would require significant boilerplate for the same result.

**`playsound3` over `pygame`**
`pygame` is a game engine that happens to play audio -- far too heavy for
a CLI tool. `playsound3` is the maintained fork of `playsound`, wraps the
OS-native audio APIs (WinMM on Windows, afplay on macOS, aplay on Linux),
and plays a file with a single function call.

**WAV generated from stdlib, not bundled**
The alert chime is generated programmatically using Python's `wave` and
`math` modules on first run. This keeps the repository free of binary
assets and avoids any licensing questions.

**Hot-reload daemon**
The daemon re-reads `~/.alarms.json` every 0.5 s. This means `alarm add`
and `alarm delete` in a second terminal window take effect without
restarting the daemon -- a useful property when adding alarms on the fly.

**Atomic JSON writes**
The store is written to a sibling temp file and renamed into place
(`os.replace()`). A crash mid-write cannot produce a half-written file
that breaks subsequent reads.

**+-2 s fire window**
With a 0.5 s sleep interval, the worst-case scheduling jitter is ~0.5 s.
The +-2 s window absorbs that plus any system clock jitter. A fired alarm
is tracked by `(alarm_id, calendar-date)` so it never fires more than once
per day regardless of daemon restarts.

---

## Known limitations

- **Foreground only.** The daemon runs in the terminal and stops when the
  window is closed. There is no OS-level background service. For a
  production tool you would wrap `alarm run` with systemd (Linux),
  launchd (macOS), or Task Scheduler (Windows).

- **Local time only.** All times are in the system's local timezone.
  There is no per-alarm timezone support.

- **Single-user.** The store lives in the user's home directory
  (`~/.alarms.json`); multi-user or shared stores are out of scope.

- **No interactive snooze.** Pressing a key while the alarm is ringing
  does not snooze it. Use `alarm snooze --name <NAME>` from a second
  terminal window immediately after the alarm fires.

- **Audio on headless systems.** If no audio device is present,
  `playsound3` will fail and the fallback is a terminal bell + visible
  banner. The alarm is never silently missed.