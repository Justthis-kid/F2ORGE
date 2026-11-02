"""Windowed entry point for the standalone F²ORGE desktop application."""
from __future__ import annotations

import ctypes
import sys

from .errors import ForgeError
from .web_ide import serve_desktop_ide


def main() -> int:
    try:
        serve_desktop_ide()
    except ForgeError as err:
        message = err.format()
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, message, "F²ORGE — Startup error", 0x10)
        else:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
