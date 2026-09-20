"""Read the scanned stock report (inventory_full.pdf) into rows.

Usage:
  python ocr_inventory.py --pdf "/path/inventory_full.pdf"   # render + OCR + parse
  python ocr_inventory.py --parse-only                       # reuse /tmp/inv_ocr.jsonl

The report is a scan, so this renders each page, runs Apple's Vision OCR
(tools/ocr.swift), then rebuilds the table by grouping recognised text into rows
by vertical position. Item codes are 9 digits and read reliably; model numbers
often come back with 4/A and 5/S confusions, so they are treated as hints and
verified later against the site catalogue.

Writes data/inventory_ocr.csv and merges new items into data/items.csv.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OCR_JSONL = Path("/tmp/inv_ocr.jsonl")
PAGES_DIR = Path("/tmp/invpages")
OUT = DATA / "inventory_ocr.csv"

ARABIC = re.compile(r"[؀-ۿ]")
CODE = re.compile(r"^\d{9}$")
# Column centres on the page, measured from the scan (0 = left edge, 1 = right edge)
COL_CODE = 0.86
COL_MODEL = 0.76
ROW_TOLERANCE = 0.006


def render(pdf):
    import pymupdf
    PAGES_DIR.mkdir(exist_ok=True)
    doc = pymupdf.open(pdf)
    for i, page in enumerate(doc, 1):
        page.get_pixmap(dpi=250).save(PAGES_DIR / f"p{i:02d}.png")
    print(f"rendered {doc.page_count} pages")


def ocr():
    pages = sorted(PAGES_DIR.glob("*.png"))
    with OCR_JSONL.open("w", encoding="utf-8") as f:
        subprocess.run(["swift", str(ROOT / "tools" / "ocr.swift"), *map(str, pages)],
                       stdout=f, check=True)
    print(f"ocr: {sum(1 for _ in OCR_JSONL.open())} lines")


def parse():
    lines = [json.loads(l) for l in OCR_JSONL.open(encoding="utf-8")]
    by_page = {}
    for line in lines:
        by_page.setdefault(line["file"], []).append(line)

    rows, section = [], ""
    for page in sorted(by_page):
        items = sorted(by_page[page], key=lambda r: -r["y"])
        used = set()
        for i, line in enumerate(items):
            text = line["text"].strip()
            # a section header spans the sheet and names the family, e.g. "غسالات ملابس/LG موديلات"
            if ARABIC.search(text) and line["x"] > 0.72 and "موديلات" in text:
                section = text
                continue
            if not CODE.match(text):
                continue
            same_row = [o for j, o in enumerate(items)
                        if j != i and abs(o["y"] - line["y"]) < ROW_TOLERANCE and j not in used]
            model = next((o["text"].strip() for o in sorted(same_row, key=lambda o: -o["x"])
                          if not ARABIC.search(o["text"]) and o["x"] > 0.6
                          and not re.fullmatch(r"[\d.,]+", o["text"].strip())), "")
            name = " ".join(o["text"].strip() for o in sorted(same_row, key=lambda o: -o["x"])
                            if ARABIC.search(o["text"]) and 0.42 < o["x"] < 0.72)
            qty = next((o["text"].strip() for o in same_row
                        if re.fullmatch(r"\d+\.\d{2}", o["text"].strip())), "")
            # the Arabic name usually repeats the model, and that copy is often read
            # more accurately than the model column itself
            from_name = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9./-]{4,}", name)
                         if re.search(r"\d", t)]
            best = max(from_name, key=len) if from_name else ""
            rows.append({"code": text, "model_ocr": model, "model_in_name": best,
                         "name_ocr": name.strip(), "quantity": qty,
                         "section": section, "page": page})
    return rows


def merge(rows):
    """Add anything new to items.csv, leaving existing rows (and their links) alone."""
    path = DATA / "items.csv"
    existing = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    fields = list(existing[0])
    if "model_alt" not in fields:          # OCR gives two readings of the same model
        fields.append("model_alt")
        for row in existing:
            row.setdefault("model_alt", "")
    known = {r["code"] for r in existing}
    added = 0
    for r in rows:
        if r["code"] in known:
            continue
        existing.append({
            "code": r["code"], "model": r["model_ocr"] or r["model_in_name"], "name": r["name_ocr"],
            "full_name": r["name_ocr"], "category": r["section"] or "inventory_full",
            "quantity": r["quantity"], "source": "inventory_full.pdf (OCR)", "url": "",
            "model_alt": r["model_in_name"] if r["model_in_name"] != r["model_ocr"] else "",
        })
        known.add(r["code"])
        added += 1
    existing.sort(key=lambda r: r["code"])
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(existing)
    return added, len(existing)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf")
    ap.add_argument("--parse-only", action="store_true")
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()

    if args.pdf and not args.parse_only:
        render(args.pdf)
        ocr()
    if not OCR_JSONL.exists():
        sys.exit("no OCR output; run with --pdf first")

    rows = parse()
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "model_ocr", "model_in_name", "name_ocr", "quantity", "section", "page"])
        w.writeheader()
        w.writerows(rows)
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} rows · "
          f"{sum(1 for r in rows if r['model_ocr'])} with a model · "
          f"{sum(1 for r in rows if r['name_ocr'])} with a name")

    if not args.no_merge:
        added, total = merge(rows)
        print(f"items.csv: +{added} new items → {total} total")
