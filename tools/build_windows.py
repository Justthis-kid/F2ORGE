"""Build the standalone Windows F²ORGE IDE executable."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def create_icon(path: Path) -> None:
    size = 512
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, 498, 498), radius=80, fill="#d97835")

    top = [(256, 55), (449, 159), (256, 264), (63, 159)]
    left = [(63, 159), (256, 264), (256, 463), (63, 358)]
    right = [(449, 159), (256, 264), (256, 463), (449, 358)]
    draw.polygon(top, fill="#f3a05e")
    draw.polygon(left, fill="#dd7a35")
    draw.polygon(right, fill="#b95723")
    for points in (top, left, right):
        draw.line(points + [points[0]], fill="#9d481e", width=9, joint="curve")

    font_path = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    font = ImageFont.truetype(str(font_path), 76) if font_path.exists() else ImageFont.load_default()
    text = Image.new("RGBA", (190, 100), (0, 0, 0, 0))
    ImageDraw.Draw(text).text((12, 4), "F²", font=font, fill="#fff7ed", stroke_width=1)
    text = text.rotate(-27, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(text, (74, 224))
    image.save(path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])


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
