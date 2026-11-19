#!/usr/bin/env python3
"""Launcher for Terminal Tower Defense."""

from __future__ import annotations

import argparse
import curses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.ui import run_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal Tower Defense")
    parser.add_argument("--quick", action="store_true", help="Skip setup menu and start immediately")
    args = parser.parse_args()
    try:
        curses.wrapper(run_app, quick_start=args.quick)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
