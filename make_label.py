"""Generate a designed QR shelf card (PNG + print PDF) for one inventory item.

Run from this folder:  python make_label.py <item code> [more codes ...]
Needs: qrcode, Google Chrome (used headless to render template.html).
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import qrcode

import build_pages

ROOT = Path(__file__).parent
OUT = ROOT / "output"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

STORE = {
    "name": "أسواق القاهرة للمبيعات",
    "hotline": "16141",
}

# Headline, category and spec chips are built from the scraped website data
# (data/products.json), so a card can be made for any item that was matched.
# Add an entry here only to override the automatic text for one item.
CARD_OVERRIDES = {
    "101001133": {"title": "غسالة ملابس ال جى", "specs": [("8", "كيلو"), ("1400", "لفة"), ("", "سيلفر")]},
    "101019001": {"title": "شفاط مطبخ إل جى 90 سم", "specs": [("90", "سم"), ("830", "م³/س"), ("", "تاتش")]},
    "101062465": {"title": "شاشة ال جى كيوليد", "specs": [("65", "بوصة"), ("", "4K"), ("", "سمارت")]},
}


def auto_card_text(code, site):
    """Headline + up to three chips, from the family-aware helpers in build_pages."""
    record = {"code": code, "model": site.get("reference", ""), "site": site, "store_name": ""}
    family = build_pages.family_of(record)
    size = build_pages.size_of(record, family)
    perf = build_pages.performance_of(record, family)
    specs = site.get("specs", {})

    brand_ar = build_pages.BRAND_AR.get(site.get("brand", ""), site.get("brand", ""))
    kind = {"tv": "شاشة", "hood": "شفاط مطبخ", "washer": "غسالة ملابس"}.get(family, "")
    head = " ".join(x for x in [kind, brand_ar] if x) or build_pages.clean_title(record)
    if size:
        head += f" {int(size)} {build_pages.size_unit(family)}"

    chips = []
    if family == "tv":
        if perf["text"] != "—":
            chips.append(("", perf["text"]))
        if specs.get("إلترا", "").strip() in ("نعم", "Yes") or "4K" in site.get("title", ""):
            chips.append(("", "4K"))
        if specs.get("سمارت", "").strip() in ("نعم", "Yes"):
            chips.append(("", "سمارت"))
    elif family == "hood":
        if perf["value"]:
            chips.append((f"{int(perf['value'])}", "م³/س"))
        if specs.get("شكل الشفاط"):
            chips.append(("", specs["شكل الشفاط"]))
        if specs.get("اللون"):
            chips.append(("", specs["اللون"]))
    elif family == "washer":
        if perf["value"]:
            chips.append((f"{int(perf['value'])}", "لفة"))
        if specs.get("اللون"):
            chips.append(("", specs["اللون"]))
        if specs.get("بخار", "").strip() in ("نعم", "Yes"):
            chips.append(("", "بخار"))
    if not chips and specs.get("الضمان"):
        chips.append(("", f"ضمان {specs['الضمان']}"))

    return {
        "brand": site.get("brand", "") or "",
        "category": site.get("category", ""),
        "title": head,
        "specs": chips[:3],
    }


def load_item(code):
    with (ROOT / "data" / "items.csv").open(encoding="utf-8-sig", newline="") as f:
        row = next((r for r in csv.DictReader(f) if r["code"] == code), None)
    if row is None:
        sys.exit(f"Item code {code} not found in data/items.csv")
    products = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    site = (products.get(code) or {}).get("site")
    if not site:
        sys.exit(f"No website data for {code}: run scrape_site.py first")
    row = {**row, "url": row.get("url") or site.get("short_url", "")}
    if not row["url"]:
        sys.exit(f"No website link for {code}")
    return {**row, **auto_card_text(code, site), **CARD_OVERRIDES.get(code, {})}


def main_qr_payload(item):
    # The big QR opens the item's own page (docs/p/<code>.html, published on GitHub Pages)
    return f"{build_pages.SITE_BASE}/p/{item['code']}.html"


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
        "TITLE_CLASS": "longer" if len(item["title"]) > 26 else ("long" if len(item["title"]) > 18 else ""),
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
