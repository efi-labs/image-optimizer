# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Analyse et optimise des images (cœur partagé par la ligne de commande, l'interface et les agents).

Ligne de commande (uv installe Pillow tout seul) :
  uv run image_optimizer.py analyze IMG [IMG ...]
  uv run image_optimizer.py process IMG [IMG ...] (--preset hd | --width 1000) --out DIR
        [--format webp|keep] [--name NOM] [--originals DIR] [--manifest FICHIER]
        [--object ID] [--note TEXTE]

- `analyze` : format, dimensions, poids, transparence, animation, `needs_work`
  (pas webp, > 1920 px de large ou > 300 Ko).
- `process` : image optimisée à la largeur du preset (jamais agrandie), transparence
  conservée. GIF animé : cadence plafonnée à 15 images/s, en webp animé (`--format webp`)
  ou en GIF réduit (`--format keep`). Avec `--originals`, garde aussi une copie « HD »
  en webp haute qualité, à la taille d'origine plafonnée à 1920 px de large.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageSequence

PRESETS = {
    "icon": 128,
    "logo": 300,
    "classic": 800,
    "hd": 1280,
    "semi-hd": 1400,
    "full-hd": 1920,
}
PRESET_LABELS = {
    "icon": "Icon (128px)",
    "logo": "Logo (300px)",
    "classic": "Classic (800px)",
    "hd": "HD (1280px)",
    "semi-hd": "Semi HD (1400px)",
    "full-hd": "Full HD (1920px)",
}
MAX_WIDTH = 1920
WEIGHT_LIMIT_KB = 300
WEBP_QUALITY = 80
JPEG_QUALITY = 85
ORIGINAL_QUALITY = 92
MAX_FPS = 15
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def has_alpha(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA"):
        return img.getchannel("A").getextrema()[0] < 255
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False


def analyze(path: Path) -> dict:
    with Image.open(path) as img:
        n_frames = getattr(img, "n_frames", 1)
        size_kb = round(path.stat().st_size / 1024, 1)
        info = {
            "path": str(path), "format": img.format, "width": img.width, "height": img.height,
            "size_kb": size_kb, "mode": img.mode, "alpha": has_alpha(img),
            "animated": n_frames > 1, "frames": n_frames,
        }
        if n_frames > 1:
            durations = [f.info.get("duration", 100) or 100 for f in ImageSequence.Iterator(img)]
            info["fps"] = round(1000 / (sum(durations) / len(durations)), 1)
        info["needs_work"] = img.format != "WEBP" or img.width > MAX_WIDTH or size_kb > WEIGHT_LIMIT_KB
    return info


def target_size(w: int, h: int, max_w: int) -> tuple[int, int]:
    if w <= max_w:
        return w, h
    return max_w, max(1, round(h * max_w / w))


def _resized(frame: Image.Image, max_w: int) -> Image.Image:
    size = target_size(frame.width, frame.height, max_w)
    return frame if size == frame.size else frame.resize(size, Image.LANCZOS)


def save_still(img: Image.Image, dest: Path, max_w: int, fmt: str, quality: int) -> None:
    alpha = has_alpha(img)
    frame = _resized(img.convert("RGBA" if alpha else "RGB"), max_w)
    if fmt == "WEBP":
        frame.save(dest, "WEBP", quality=quality, method=6)
    elif fmt == "PNG":
        frame.save(dest, "PNG", optimize=True)
    elif fmt == "JPEG":
        frame.convert("RGB").save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    else:
        frame.save(dest, fmt)


def save_animated(img: Image.Image, dest: Path, max_w: int, fmt: str, quality: int, cap_fps: bool) -> dict:
    frames, durations = [], []
    for f in ImageSequence.Iterator(img):
        frames.append(f.convert("RGBA"))
        durations.append(f.info.get("duration", 100) or 100)
    step = 1
    if cap_fps:
        fps = 1000 / (sum(durations) / len(durations))
        step = max(1, math.ceil(fps / MAX_FPS))
    kept = [_resized(frames[i], max_w) for i in range(0, len(frames), step)]
    kept_d = [sum(durations[i:i + step]) for i in range(0, len(frames), step)]
    loop = img.info.get("loop", 0)
    if fmt == "WEBP":
        kept[0].save(dest, "WEBP", save_all=True, append_images=kept[1:], duration=kept_d,
                     loop=loop, quality=quality, method=6)
    else:
        pal = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=255) for f in kept]
        pal[0].save(dest, "GIF", save_all=True, append_images=pal[1:], duration=kept_d,
                    loop=loop, optimize=True, disposal=2)
    return {"frames_before": len(frames), "frames_after": len(kept)}


def output_format(src_format: str | None, mode: str) -> tuple[str, str]:
    """(format Pillow, extension) selon le mode 'webp' ou 'keep'."""
    if mode == "webp":
        return "WEBP", ".webp"
    table = {"JPEG": ("JPEG", ".jpg"), "PNG": ("PNG", ".png"), "GIF": ("GIF", ".gif"), "WEBP": ("WEBP", ".webp")}
    return table.get(src_format or "", ("WEBP", ".webp"))


def process_one(src: Path, out_dir: Path, max_w: int, mode: str = "webp", name: str | None = None,
                originals: Path | None = None) -> dict:
    before = analyze(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt, ext = output_format(before["format"], mode)
    dest = out_dir / f"{name or src.stem}{ext}"
    result = {"source": str(src), "before": before, "max_width": max_w}
    with Image.open(src) as img:
        if before["animated"]:
            result.update(save_animated(img, dest, max_w, fmt, WEBP_QUALITY, cap_fps=True))
        else:
            save_still(img, dest, max_w, fmt, WEBP_QUALITY)
        if originals:
            originals.mkdir(parents=True, exist_ok=True)
            orig = originals / f"{name or src.stem}.webp"
            img.seek(0)
            if before["animated"]:
                save_animated(img, orig, MAX_WIDTH, "WEBP", ORIGINAL_QUALITY, cap_fps=False)
            else:
                save_still(img, orig, MAX_WIDTH, "WEBP", ORIGINAL_QUALITY)
            result["original"] = str(orig)
            result["original_kb"] = round(orig.stat().st_size / 1024, 1)
    with Image.open(dest) as out:
        result["width"], result["height"] = out.size
    result["output"] = str(dest)
    result["size_kb"] = round(dest.stat().st_size / 1024, 1)
    return result


def append_manifest(manifest: Path, result: dict, name: str, preset: str, obj: str = "", note: str = "") -> None:
    new = not manifest.exists()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        if new:
            w.writerow(["date", "name", "object", "preset", "width", "kb_before", "kb_after", "original", "note"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), name, obj, preset, result["width"],
                    result["before"]["size_kb"], result["size_kb"], result.get("original", ""), note])


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXT)
        elif p.is_file():
            files.append(p)
    return files


def run_batch(files: list[Path], out_dir: Path, max_w: int, mode: str, originals: Path | None,
              progress: Callable[[int, int, dict | Exception, Path], None] | None = None) -> list[dict]:
    results = []
    for i, f in enumerate(files, 1):
        try:
            r = process_one(f, out_dir, max_w, mode, originals=originals)
            results.append(r)
            if progress:
                progress(i, len(files), r, f)
        except Exception as exc:  # une image illisible ne doit pas arrêter le lot
            if progress:
                progress(i, len(files), exc, f)
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("images", nargs="+")
    pr = sub.add_parser("process")
    pr.add_argument("images", nargs="+")
    g = pr.add_mutually_exclusive_group(required=True)
    g.add_argument("--preset", choices=PRESETS)
    g.add_argument("--width", type=int)
    pr.add_argument("--out", required=True)
    pr.add_argument("--format", choices=["webp", "keep"], default="webp")
    pr.add_argument("--name", help="nom de sortie (une seule image)")
    pr.add_argument("--originals")
    pr.add_argument("--manifest")
    pr.add_argument("--object")
    pr.add_argument("--note")
    args = p.parse_args()

    if args.cmd == "analyze":
        print(json.dumps([analyze(f) for f in collect(args.images)], ensure_ascii=False, indent=1))
        return 0

    max_w = args.width or PRESETS[args.preset]
    files = collect(args.images)
    originals = Path(args.originals) if args.originals else None
    out = []
    for f in files:
        name = args.name if args.name and len(files) == 1 else f.stem
        r = process_one(f, Path(args.out), max_w, args.format, name, originals)
        if args.manifest:
            append_manifest(Path(args.manifest), r, name, args.preset or f"{max_w}px", args.object or "", args.note or "")
        out.append(r)
    print(json.dumps(out if len(out) > 1 else out[0], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
