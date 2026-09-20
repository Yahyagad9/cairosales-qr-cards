"""Make small WebP versions of every product photo.

Usage:  python optimize_images.py [--force]

The branch Wi-Fi is one connection shared by everyone on the shop floor, so page
weight is the thing that decides whether a scan feels instant. Each photo is written
at two widths in WebP; the original JPEG stays as the fallback for older phones.
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
IMG = ROOT / "docs" / "img"
WIDTHS = (400, 800)
QUALITY = 78


def variants(jpg):
    return [(w, jpg.with_name(f"{jpg.stem}-{w}.webp")) for w in WIDTHS]


def build(jpg, force=False):
    made = []
    for width, out in variants(jpg):
        if out.exists() and not force and out.stat().st_mtime >= jpg.stat().st_mtime:
            continue
        im = Image.open(jpg).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(out, "WEBP", quality=QUALITY, method=6)
        made.append(out)
    return made


def main(force=False):
    jpgs = sorted(IMG.glob("*.jpg"))
    before = sum(p.stat().st_size for p in jpgs)
    made = 0
    for jpg in jpgs:
        made += len(build(jpg, force))
    after = sum(p.stat().st_size for w, p in
                (v for jpg in jpgs for v in variants(jpg)) if p.exists())
    print(f"{len(jpgs)} photos · {made} file(s) written")
    print(f"originals {before / 1e6:.1f}MB → webp set {after / 1e6:.1f}MB "
          f"({(1 - after / before) * 100:.0f}% smaller)")


if __name__ == "__main__":
    main("--force" in sys.argv)
