"""Build the standalone Windows F²ORGE IDE executable."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import shutil


ROOT = Path(__file__).resolve().parents[1]


def create_icon(path: Path) -> None:
    # Preserve the supplied brand icon unchanged in Windows builds.
    shutil.copyfile(ROOT / "src" / "f2orge" / "web" / "brand.ico", path)


def main() -> int:
    if sys.platform != "win32":
        print("The standalone Windows executable must be built on Windows.", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="f2orge-build-") as temporary:
        icon = Path(temporary) / "f2orge.ico"
        create_icon(icon)
        command = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile", "--windowed",
            "--name", "F2ORGE", "--icon", str(icon),
            "--specpath", str(ROOT / "build"),
            "--paths", str(ROOT / "src"),
            "--add-data", f"{ROOT / 'src' / 'f2orge' / 'web'};f2orge/web",
            "--collect-all", "webview",
            "--hidden-import", "webview.platforms.edgechromium",
            "--hidden-import", "pythonnet",
            "--hidden-import", "clr",
            "--collect-submodules", "clr_loader",
            str(ROOT / "tools" / "launch_app.py"),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
    print(f"Built standalone app: {ROOT / 'dist' / 'F2ORGE.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
