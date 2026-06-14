#!/usr/bin/env python3
"""
alarm_cli.py
~~~~~~~~~~~~
Entry-point shim for the alarm-clock CLI.

Usage:
  python alarm_cli.py <command> [options]

If installed via `pip install -e .`, the `alarm` command is available
directly in the shell (see pyproject.toml [project.scripts]).
"""

from alarm.cli import main

if __name__ == "__main__":
    main()
