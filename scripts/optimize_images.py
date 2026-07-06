#!/usr/bin/env python3
"""Downscale + recompress oversized image assets so they don't bloat the
container image and every Explorer page payload.

Thesis covers are rendered in a fixed 210px-tall card (`.thesis-cover-image`,
object-fit: cover) yet many source PNGs are 1500-2500px / up to 2.5 MB. They are
base64-embedded straight into the page HTML, so their raw size is paid on every
render. Capping the longest edge at 600px (crisp even at 2x retina) and
re-optimising typically cuts each cover ~10x with no visible change.

The front-page `background image.jpg` (~1.8 MB) is base64-inlined into the CSS on
every load; it is recompressed to a sensible width/quality too.

Safe to re-run: images already within the target are skipped. Formats and
filenames are preserved (covers stay `.png` so render_cover_html's hardcoded
`image/png` MIME keeps working).

Usage:
    python3 scripts/optimize_images.py            # optimize everything
    python3 scripts/optimize_images.py --dry-run  # report only, change nothing
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COVER_GLOBS = [
    os.path.join(REPO_ROOT, "programs", "*", "covers", "*.png"),
    os.path.join(REPO_ROOT, "programs", "*", "covers", "*.jpg"),
    os.path.join(REPO_ROOT, "programs", "*", "covers", "*.jpeg"),
]
COVER_MAX_EDGE = 600           # display box is only 210px tall

BACKGROUND = os.path.join(REPO_ROOT, "background image.jpg")
BACKGROUND_MAX_EDGE = 1920     # full-viewport background
JPEG_QUALITY = 82


def _human(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.2f} {unit}" if unit == "MB" else f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.2f} MB"


def optimize_one(path: str, max_edge: int, dry_run: bool) -> tuple[int, int]:
    """Return (bytes_before, bytes_after). after == before when unchanged."""
    before = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    try:
        with Image.open(path) as im:
            im.load()
            w, h = im.size
            fmt = im.format  # remember source format
            needs_resize = max(w, h) > max_edge
            if not needs_resize and ext in (".jpg", ".jpeg"):
                # Already small JPEG — leave it be (re-encoding only loses quality).
                return before, before
            work = im
            if needs_resize:
                scale = max_edge / float(max(w, h))
                work = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)

            if dry_run:
                return before, before

            if ext in (".jpg", ".jpeg") or fmt == "JPEG":
                rgb = work.convert("RGB")
                rgb.save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            else:  # PNG (preserve alpha/palette so covers keep their look)
                save_img = work
                if work.mode in ("P", "RGBA", "LA"):
                    pass  # keep as-is
                elif work.mode not in ("RGB", "L"):
                    save_img = work.convert("RGB")
                save_img.save(path, format="PNG", optimize=True)
    except Exception as exc:  # never hard-fail the whole run on one bad file
        print(f"  ! skipped {os.path.relpath(path, REPO_ROOT)}: {exc}", file=sys.stderr)
        return before, before
    return before, os.path.getsize(path)


def run(dry_run: bool) -> None:
    covers = sorted({p for g in COVER_GLOBS for p in glob.glob(g)})
    targets = [(p, COVER_MAX_EDGE) for p in covers]
    if os.path.exists(BACKGROUND):
        targets.append((BACKGROUND, BACKGROUND_MAX_EDGE))

    total_before = total_after = 0
    shrunk = 0
    for path, max_edge in targets:
        b, a = optimize_one(path, max_edge, dry_run)
        total_before += b
        total_after += a
        if a < b:
            shrunk += 1

    print(f"Processed {len(targets)} images ({len(covers)} covers)")
    print(f"  changed:  {shrunk}")
    print(f"  before:   {_human(total_before)}")
    print(f"  after:    {_human(total_after)}")
    if total_before:
        print(f"  reduction: {100 * (1 - total_after / total_before):.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only; do not modify files")
    run(ap.parse_args().dry_run)
