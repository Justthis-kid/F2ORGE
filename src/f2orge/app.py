"""Windowed entry point for the standalone F²ORGE desktop application."""
from __future__ import annotations

import ctypes
import sys

from .errors import ForgeError


def main() -> int:
    """Open the IDE, falling back the way `forge ide` does when the webview cannot start.

    A packaged windowed app has no terminal to report to, so a final failure is shown in a message
    box on Windows and on stderr elsewhere.  The browser IDE is the last resort: it always works,
    because it is served by the same process.
    """
    from .desktop import launch_desktop_ide
    from .web_ide import serve_browser_ide, serve_desktop_ide

    problems = []
    for attempt in (serve_desktop_ide, launch_desktop_ide):
        try:
            attempt()
            return 0
        except ForgeError as err:
            problems.append(err.message)
    try:
        serve_browser_ide()
        return 0
    except OSError as err:
        problems.append(f"cannot start the browser IDE: {err}")
    message = "\n".join(problems)
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "F²ORGE — Startup error", 0x10)
    else:
        print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
