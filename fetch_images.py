"""Download the main product photo for every scraped item into docs/img/<code>.jpg.

Usage:  python fetch_images.py [code ...]

cairosales.com is behind Cloudflare, so images are captured with headless Chrome
(a plain download returns 403). Chrome shows an image centred on a dark page at
1000x1000, so the middle 500x500 square is cropped back out.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
IMG = ROOT / "docs" / "img"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def grab(url, out):
    tmp = out.with_suffix(".png")
    try:
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--virtual-time-budget=12000", f"--user-agent={USER_AGENT}",
             f"--screenshot={tmp}", "--window-size=1000,1000", url],
            capture_output=True, timeout=90,
        )
    except subprocess.TimeoutExpired:
        return False  # retried on the next run
    if not tmp.exists():
        return False
    Image.open(tmp).convert("RGB").crop((250, 250, 750, 750)).save(out, quality=92)
    tmp.unlink()
    time.sleep(2)
    return True


def main(codes):
    IMG.mkdir(parents=True, exist_ok=True)
    products = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    todo = {c: p for c, p in products.items()
            if (p.get("site") or {}).get("images") and (not codes or c in codes)}
    for n, (code, p) in enumerate(sorted(todo.items()), 1):
        out = IMG / f"{code}.jpg"
        if out.exists() and not codes:
            continue
        # thickbox is the large version; fall back to whatever the page listed
        url = p["site"]["images"][0].replace("thickbox_default", "large_default")
        ok = grab(url, out)
        print(f"[{n}/{len(todo)}] {code}: {'saved' if ok else 'FAILED'}", flush=True)


if __name__ == "__main__":
    main([a for a in sys.argv[1:]])
