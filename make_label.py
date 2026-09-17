"""Generate a designed QR shelf card (PNG + print PDF) for one inventory item.

Run from this folder:  python make_label.py <item code> [more codes ...]
Needs: qrcode, Google Chrome (used headless to render template.html).
"""
import csv
import subprocess
import sys
from pathlib import Path

import pymupdf
import qrcode

ROOT = Path(__file__).parent
OUT = ROOT / "output"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

STORE = {
    "name": "أسواق القاهرة للمبيعات",
    "hotline": "16141",
}

# Card text per item code. Brand, headline and spec chips are written by hand for now;
# everything else (model, name, website link) comes from data/items.csv.
CARD_DETAILS = {
    "101001133": {
        "brand": "LG",
        "category": "غسالات ملابس",
        "title": "غسالة ملابس ال جى",
        "specs": [("8", "كيلو"), ("1400", "لفة"), ("", "سيلفر")],
    },
    "101062465": {
        "brand": "LG",
        "category": "شاشات",
        "title": "شاشة ال جى كيوليد",
        "specs": [("65", "بوصة"), ("", "4K"), ("", "سمارت")],
    },
}


def load_item(code):
    with (ROOT / "data" / "items.csv").open(encoding="utf-8-sig", newline="") as f:
        row = next((r for r in csv.DictReader(f) if r["code"] == code), None)
    if row is None:
        sys.exit(f"Item code {code} not found in data/items.csv")
    if code not in CARD_DETAILS:
        sys.exit(f"No card details for {code} yet: add brand/title/specs to CARD_DETAILS")
    if not row["url"]:
        sys.exit(f"No website link for {code} in data/items.csv")
    return {**row, **CARD_DETAILS[code]}


def main_qr_payload(item):
    # Placeholder: the big QR's purpose is still to be decided.
    # Internal item code is deliberately left out: customers must not see it.
    return "\n".join([
        "Cairo Sales Stores",
        f"الموديل: {item['model']}",
        item["name"],
    ])


def qr_svg(data, logo_hole=True, dark="#16181D", accent="#D71F2B"):
    """QR as SVG with rounded modules, branded finder 'eyes' and (optionally) a clear centre for the logo."""
    level = qrcode.constants.ERROR_CORRECT_Q if logo_hole else qrcode.constants.ERROR_CORRECT_M
    qr = qrcode.QRCode(error_correction=level, border=0)
    qr.add_data(data.encode("utf-8"))
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)

    def in_finder(r, c):
        return (r < 7 and c < 7) or (r < 7 and c >= n - 7) or (r >= n - 7 and c < 7)

    # Logo covers ~22% of the width (~7% of modules); Q level tolerates ~25% loss
    hole = n * 0.27 if logo_hole else 0
    lo, hi = (n - hole) / 2, (n + hole) / 2

    parts = []
    for r in range(n):
        for c in range(n):
            if not m[r][c] or in_finder(r, c):
                continue
            if hole and lo <= r + 0.5 <= hi and lo <= c + 0.5 <= hi:
                continue
            parts.append(f'<rect x="{c + .06:.2f}" y="{r + .06:.2f}" width=".88" height=".88" rx=".3"/>')

    eyes = []
    for (r, c) in [(0, 0), (0, n - 7), (n - 7, 0)]:
        eyes.append(
            f'<rect x="{c + .5}" y="{r + .5}" width="6" height="6" rx="1.9" fill="none" stroke="{dark}" stroke-width="1"/>'
            f'<rect x="{c + 2}" y="{r + 2}" width="3" height="3" rx=".9" fill="{accent}"/>'
        )

    return (
        f'<svg class="qr" xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 {n + 2} {n + 2}" shape-rendering="geometricPrecision">'
        f'<g fill="{dark}">{"".join(parts)}</g>{"".join(eyes)}</svg>'
    )


def build_html(item):
    specs = "".join(
        f'<span class="spec">{f"<b>{v}</b>" if v else ""}{u}</span>' for v, u in item["specs"]
    )
    html = (ROOT / "template.html").read_text(encoding="utf-8")
    for key, val in {
        "STORE": STORE["name"],
        "HOTLINE": STORE["hotline"],
        "BRAND": item["brand"],
        "CATEGORY": item["category"],
        "TITLE": item["title"],
        "SPECS": specs,
        "MODEL": item["model"],
        "QR_SVG": qr_svg(main_qr_payload(item)),
        # Small QR: opens the item's page on cairosales.com
        "WEB_QR_SVG": qr_svg(item["url"], logo_hole=False),
    }.items():
        html = html.replace("{{" + key + "}}", val)
    return html


def render(item):
    OUT.mkdir(exist_ok=True)
    # Written next to template so relative asset paths resolve
    page = ROOT / f".render_{item['code']}.html"
    page.write_text(build_html(item), encoding="utf-8")
    url = page.resolve().as_uri()
    png = OUT / f"label_{item['code']}.png"
    pdf = OUT / f"label_{item['code']}.pdf"

    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=3000",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}", url],
                   check=True, capture_output=True)
    page.unlink()
    # PNG from the PDF (Chrome screenshots can't go narrower than its minimum window width)
    with pymupdf.open(pdf) as doc:
        doc[0].get_pixmap(dpi=400).save(png)
    return png, pdf


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for code in sys.argv[1:]:
        for path in render(load_item(code)):
            print(path)
