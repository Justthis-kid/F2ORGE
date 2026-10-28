"""Shared helpers for the F²ORGE tests."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from f2orge import Interpreter
from f2orge.errors import ForgeError

ROOT = Path(__file__).resolve().parents[1]


def run(src, base_dir=None):
    """Run a program, return the printed lines."""
    out = []
    Interpreter(base_dir=base_dir, out=out.append).run(src, "test.forge")
    return out


def run_it(src, base_dir=None):
    """Run a program, return (interpreter, printed lines)."""
    out = []
    it = Interpreter(base_dir=base_dir, out=out.append)
    it.run(src, "test.forge")
    return it, out


def error_of(src, base_dir=None):
    """Run a program that must fail; return the ForgeError."""
    try:
        run(src, base_dir)
    except ForgeError as err:
        return err
    raise AssertionError(f"expected an error from: {src!r}")


def forge(*args, stdin=None, cwd=None):
    """Run the real command line (python -m f2orge ...)."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"}
    return subprocess.run([sys.executable, "-m", "f2orge", *args], input=stdin, capture_output=True,
                          text=True, env=env, cwd=cwd or ROOT, encoding="utf-8")


class TempDir:
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        return Path(self._t.name)

    def __exit__(self, *exc):
        self._t.cleanup()
