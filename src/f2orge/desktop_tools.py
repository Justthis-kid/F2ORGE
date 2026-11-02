"""Optional native-window launchers for generated F²ORGE companion tools."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path

from .errors import ForgeError


def _webview():
    try:
        import webview
        from webview.errors import WebViewException
    except ModuleNotFoundError as err:
        if err.name != "webview":
            raise
        raise ForgeError(
            "desktop windows require the pywebview desktop extra",
            title="Desktop tool unavailable",
            hint='Install it with: pip install "f2orge[desktop]".',
        ) from err
    return webview, WebViewException


def show_html_window(title: str, page: str, width: int = 1024, height: int = 760) -> None:
    """Display a self-contained offline HTML tool in a native desktop window."""
    webview, exception_type = _webview()
    try:
        webview.create_window(title, html=page, width=width, height=height, min_size=(640, 480))
        webview.start()
    except (OSError, RuntimeError, exception_type) as err:
        raise ForgeError(
            f"cannot start the desktop window: {err}",
            title="Desktop tool unavailable",
            hint="Check that a supported WebView runtime is installed and available.",
        ) from err


def build_calculator_executable(page: str, output: Path, title: str) -> None:
    """Bundle a self-contained calculator page and pywebview as a one-file Windows app."""
    if sys.platform != "win32":
        raise ForgeError(
            "standalone calculator executables are currently built on Windows",
            title="Calculator build unavailable",
            hint="Export the offline HTML calculator with forge calc, or build on Windows.",
        )
    if importlib.util.find_spec("PyInstaller") is None:
        raise ForgeError(
            "PyInstaller is not installed",
            title="Calculator build unavailable",
            hint='Install the build extra with: pip install "f2orge[build]".',
        )
    if importlib.util.find_spec("webview") is None:
        raise ForgeError(
            "pywebview is not installed",
            title="Calculator build unavailable",
            hint='Install the desktop extra with: pip install "f2orge[desktop]".',
        )
    output = output.expanduser().resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise ForgeError(f"cannot create output directory: {err}", title="Calculator build failed") from err

    project_source = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="f2orge-calculator-") as work:
        workdir = Path(work)
        html_path = workdir / "calculator.html"
        launcher_path = workdir / "launch_calculator.py"
        html_path.write_text(page, encoding="utf-8")
        launcher_path.write_text(
            "from f2orge.desktop_tools import launch_calculator_bundle\n"
            f"raise SystemExit(launch_calculator_bundle({title!r}))\n",
            encoding="utf-8",
        )
        command = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile", "--windowed",
            "--name", output.stem, "--distpath", str(output.parent),
            "--workpath", str(workdir / "build"), "--specpath", str(workdir),
            "--paths", str(project_source),
            "--add-data", f"{html_path};.",
            "--collect-all", "webview",
            "--hidden-import", "webview.platforms.edgechromium",
            "--hidden-import", "pythonnet", "--hidden-import", "clr",
            "--collect-submodules", "clr_loader",
            str(launcher_path),
        ]
        try:
            subprocess.run(command, cwd=workdir, check=True, capture_output=True, text=True)
        except FileNotFoundError as err:
            raise ForgeError(
                "PyInstaller is not installed",
                title="Calculator build unavailable",
                hint='Install the build extra with: pip install "f2orge[build]".',
            ) from err
        except subprocess.CalledProcessError as err:
            details = (err.stderr or err.stdout or str(err)).strip()
            raise ForgeError(
                f"PyInstaller could not build the calculator: {details[-1200:]}",
                title="Calculator build failed",
            ) from err


def launch_calculator_bundle(title: str) -> int:
    """Entry point used by a bundled one-file calculator executable."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    page_path = bundle_root / "calculator.html"
    try:
        page = page_path.read_text(encoding="utf-8")
    except OSError as err:
        raise ForgeError(f"cannot read the bundled calculator: {err}", title="Calculator startup failed") from err
    show_html_window(f"{title} — F²ORGE Calculator", page)
    return 0
