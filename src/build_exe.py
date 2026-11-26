# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "pyinstaller>=6"]
# ///
"""Construit ../ImageOptimizer.exe et le raccourci du menu Démarrer.

  uv run src/build_exe.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ICON = HERE / "image_optimizer.ico"
EXE = HERE.parent / "ImageOptimizer.exe"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Image Optimizer.lnk"


def make_icon() -> None:
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, s - 8, s - 8), radius=48, fill="#007AFF")
    d.rounded_rectangle((48, 64, s - 48, s - 64), radius=14, fill="white")
    d.polygon([(64, 176), (112, 112), (144, 152), (164, 128), (192, 176)], fill="#007AFF")
    d.ellipse((152, 80, 176, 104), fill="#FFCC00")
    img.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def build() -> None:
    # Fichiers de travail de PyInstaller dans un dossier temporaire : seul l'exe reste.
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
            "--name", "ImageOptimizer", "--icon", str(ICON),
            "--distpath", str(EXE.parent), "--workpath", tmp, "--specpath", tmp,
            str(HERE / "image_optimizer_gui.py"),
        ], cwd=HERE, check=True)


def shortcut() -> None:
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
        "$s.TargetPath=$env:EXE;$s.WorkingDirectory=$env:DIR;$s.IconLocation=$env:EXE+',0';"
        "$s.Description='Image Optimizer';$s.Save()"
    )
    env = {**os.environ, "LNK": str(SHORTCUT), "EXE": str(EXE), "DIR": str(EXE.parent)}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True)


if __name__ == "__main__":
    make_icon()
    build()
    shortcut()
    print(f"\nOK : {EXE}\nRaccourci : {SHORTCUT}")
