"""Merge stock-list .xls exports into data/items.csv (one row per item code).

Usage:  python import_items.py "<file>.xls" [more.xls ...]
The category is taken from the file name (e.g. "شاشات 15-9-2026.xls" -> "شاشات").
Existing rows are updated by item code; columns added by hand (url, ...) are kept.
"""
import csv
import re
import sys
from pathlib import Path

import xlrd

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "items.csv"
FIELDS = ["code", "model", "name", "full_name", "category", "quantity", "source", "url"]
ARABIC = r"؀-ۿ"


def load():
    if not DATA.exists():
        return {}
    with DATA.open(encoding="utf-8-sig", newline="") as f:
        return {row["code"]: row for row in csv.DictReader(f)}


def save(items):
    DATA.parent.mkdir(exist_ok=True)
    # utf-8-sig so Excel opens the Arabic text correctly
    with DATA.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for code in sorted(items):
            w.writerow({k: items[code].get(k, "") for k in FIELDS})


def clean_name(full, model):
    """Drop the model number the export glues onto the name ("MODEL - name")."""
    name = full.strip()
    if name.startswith(model):
        name = name[len(model):].lstrip(" -")
    # leftover Latin prefix (model spelled differently, barcode number): cut up to the Arabic name
    name = re.sub(rf"^[^{ARABIC}]+?-\s*(?=[{ARABIC}(])", "", name)
    return re.sub(r"\s+", " ", name.strip(" -")).strip()


def read_xls(path):
    category = re.sub(r"\s*\d{1,2}-\d{1,2}-\d{4}$", "", path.stem).strip()
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    header = [str(c).strip() for c in sheet.row_values(0)]
    assert header == ["الكمية", "إسم الصنف", "إسم الصنف", "كود الصنف"], header
    for r in range(1, sheet.nrows):
        qty, full, model, code = sheet.row_values(r)
        if not code:
            continue
        model = str(model).strip()
        yield {
            "code": str(int(code)),
            "model": model,
            "name": clean_name(str(full), model),
            "full_name": str(full).strip(),
            "category": category,
            "quantity": f"{float(qty):g}",
            "source": path.name,
        }


if __name__ == "__main__":
    items = load()
    for arg in sys.argv[1:]:
        path = Path(arg)
        rows = list(read_xls(path))
        for row in rows:
            items[row["code"]] = {**items.get(row["code"], {}), **row}
        print(f"{path.name}: {len(rows)} items")
    save(items)
    print(f"{DATA.relative_to(ROOT)}: {len(items)} items total")
