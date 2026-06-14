# ⏰ Alarm Clock CLI

A feature-rich terminal alarm clock built with Python, `click`, and `rich`.

---

## Features

- **Named alarms** — give each alarm a meaningful name
- **Persistent** — alarms saved to `~/.alarms.json` (survives restarts)
- **Flexible time input** — `07:30`, `7:30am`, `"in 45m"`, `"in 1h30m"`
- **Recurring alarms** — `daily`, `weekdays`, `weekends`, or `mon,wed,fri`
- **One-shot alarms** — auto-delete after firing with `--once`
- **Live countdown** — refreshing rich table while running
- **Alarm banner** — full-screen ASCII art when alarm fires
- **Snooze & dismiss** — interactive `[S]/[D]/[Q]` prompt during alarm
- **Missed alarm warnings** — notified on startup if alarms fired while closed
- **Sound support** — plays a `.wav` file via `playsound`, falls back to terminal bell

---

## Installation

```bash
# 1. Enter the project directory
cd alarm-clock

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
#    Windows (PowerShell)
.venv\Scripts\Activate.ps1
#    Windows (CMD)
.venv\Scripts\activate.bat
#    macOS / Linux
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

> **Tip:** You'll see `(.venv)` in your prompt when the environment is active.  
> To deactivate at any time, run `deactivate`.

> **Python 3.10+** required.

### Audio — no extra install needed

Sound works out of the box on all platforms using native OS utilities:

| OS | Audio method | Requires |
|---|---|---|
| Windows | `winsound.Beep()` | Nothing — Python stdlib |
| macOS | `afplay` + system `.aiff` | Nothing — built into macOS |
| Linux | `paplay` / `aplay` / `pw-play` | PulseAudio / ALSA / PipeWire (usually pre-installed) |

If none of the above work in your environment, optionally install `playsound`
and drop an `alarm.wav` file inside `alarm_clock/`:

```bash
pip install playsound
# then add alarm_clock/alarm.wav
```



---

## Usage

### Add alarms

```bash
# 24h format, repeat on weekdays
python main.py add 07:30 --name "Morning standup" --repeat weekdays

# 12h format, daily (default)
python main.py add 7:30am --name "Gym"

# Relative time, one-shot (auto-deletes after firing)
python main.py add "in 45m" --name "Take a break" --once

# Custom days
python main.py add 09:00 --name "Mon/Wed workout" --repeat mon,wed

# Weekend alarm
python main.py add 10:00 --name "Lazy morning" --repeat weekends
```

### Manage alarms

```bash
# List all alarms (rich table)
python main.py list

# Delete by ID (or ID prefix)
python main.py delete a1b2c3d4

# Enable / disable (toggle)
python main.py toggle a1b2c3d4

# Snooze for 10 minutes
python main.py snooze a1b2c3d4 --minutes 10
```

### Run the daemon

```bash
python main.py run
```

While running:
- Live countdown table refreshes every second
- When an alarm fires: full-screen banner + bell sound
- Press **`S`** to snooze (5 min), **`D`** to dismiss, **`Q`** to quit
- Press **Ctrl+C** to stop gracefully

---

## Time formats

| Input | Meaning |
|---|---|
| `07:30` | 7:30 AM (24h) |
| `19:00` | 7:00 PM (24h) |
| `7:30am` | 7:30 AM (12h) |
| `7:30pm` | 7:30 PM (12h) |
| `in 45m` | 45 minutes from now |
| `in 2h` | 2 hours from now |
| `in 1h30m` | 1 hour 30 minutes from now |

## Repeat values

| Value | Fires on |
|---|---|
| `daily` | Every day (default) |
| `once` | Once, then auto-deletes |
| `weekdays` | Monday – Friday |
| `weekends` | Saturday – Sunday |
| `mon,wed,fri` | Specific days (any combination) |

---

## Data storage

Alarms are stored in `~/.alarms.json` as plain JSON — you can inspect or edit this file directly.

```json
[
  {
    "id": "a1b2c3d4",
    "name": "Morning standup",
    "time": "07:30",
    "repeat": "weekdays",
    "enabled": true,
    "snoozed_until": null,
    "created_at": "2026-06-14T08:00:00.000000"
  }
]
```

---

## Project structure

```
alarm-clock/
├── main.py              # CLI entry point (click)
├── requirements.txt
├── README.md
└── alarm_clock/
    ├── __init__.py
    ├── storage.py       # Alarm dataclass + JSON persistence
    ├── scheduler.py     # Run loop + alarm firing logic
    ├── display.py       # Rich tables + ASCII art banner
    ├── audio.py         # Sound playback + bell fallback
    └── utils.py         # Time string parsing
```

---

## Tips

- Use ID prefix shortcuts: if your alarm ID is `a1b2c3d4`, typing `a1b2` is enough as long as it's unambiguous
- Alarms with `--once` are automatically removed after you dismiss them
- `snoozed_until` is cleared on the next successful dismiss
- The alarm fires within a ±30s window of its scheduled time, so a 1-second poll loop never misses a minute boundary
