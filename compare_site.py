"""Compare the store's Excel stock lists with what cairosales.com shows.

Usage:  python compare_site.py

Writes data/comparison.csv (opens in Excel) with one row per stock item:
what the Excel export says, what the website says, and where they differ.
For items with no match, the closest product found on the website is listed
so someone can check by hand.
"""
import csv
import difflib
import json
from pathlib import Path

import scrape_site as sc

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "comparison.csv"

FIELDS = [
    "كود الصنف", "موديل (الإكسيل)", "اسم الصنف (الإكسيل)", "القسم (الإكسيل)", "الكمية",
    "الحالة", "موديل (الموقع)", "اسم المنتج (الموقع)", "القسم (الموقع)", "الماركة",
    "سعر الكاش", "سعر التقسيط", "فرق الكاش", "عدد المواصفات", "رابط المنتج",
    "أقرب منتج على الموقع", "ملاحظة",
]

STATUS_AR = {
    "ok": "موجود على الموقع",
    "not_found": "مش لاقيينه على الموقع",
    "no_exact_match": "لقينا منتج قريب بس الموديل مختلف",
}


def closest(model, catalog_slugs):
    """Best-looking product on the site for an unmatched model."""
    key = sc.norm_model(model)
    best = max(catalog_slugs.items(),
               key=lambda kv: difflib.SequenceMatcher(None, key, kv[1][-len(key) - 8:]).ratio(),
               default=(None, None))
    if not best[0]:
        return "", 0.0
    ratio = difflib.SequenceMatcher(None, key, best[1][-len(key) - 8:]).ratio()
    return best[0], ratio


def main():
    items = list(csv.DictReader((DATA / "items.csv").open(encoding="utf-8-sig")))
    products = json.loads((DATA / "products.json").read_text(encoding="utf-8"))
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8")) if (DATA / "catalog.json").exists() else {}
    slugs = {u: sc.norm_model(u.rsplit("/", 1)[-1].replace(".html", "")) for u in catalog}

    rows, counts = [], {"ok": 0, "not_found": 0, "no_exact_match": 0}
    for item in items:
        code = item["code"]
        rec = products.get(code, {})
        status = rec.get("status", "not_found").split(":")[0]
        counts[status] = counts.get(status, 0) + 1
        site = rec.get("site") or {}

        cash = sc.num(site.get("price_cash")) if hasattr(sc, "num") else site.get("price_cash")
        cash = float(site["price_cash"]) if site.get("price_cash") else None
        inst = float(site["price_installment"]) if site.get("price_installment") else None

        note = ""
        near = ""
        if status == "ok":
            if not inst:
                note = "مفيش سعر تقسيط على الموقع"
            if sc.norm_model(item["model"]) != sc.norm_model(site.get("reference", "")):
                note = (note + " · " if note else "") + f"الموديل مكتوب على الموقع: {site.get('reference','')}"
        else:
            url, ratio = closest(item["model"], slugs)
            if url and ratio > 0.45:
                near = url

        rows.append({
            "كود الصنف": code,
            "موديل (الإكسيل)": item["model"],
            "اسم الصنف (الإكسيل)": item["name"],
            "القسم (الإكسيل)": item["category"],
            "الكمية": item.get("quantity", ""),
            "الحالة": STATUS_AR.get(status, status),
            "موديل (الموقع)": site.get("reference", ""),
            "اسم المنتج (الموقع)": site.get("title", ""),
            "القسم (الموقع)": site.get("category", ""),
            "الماركة": site.get("brand", ""),
            "سعر الكاش": int(cash) if cash else "",
            "سعر التقسيط": int(inst) if inst else "",
            "فرق الكاش": int(inst - cash) if cash and inst else "",
            "عدد المواصفات": len(site.get("specs", {})) if site else "",
            "رابط المنتج": site.get("short_url", ""),
            "أقرب منتج على الموقع": near,
            "ملاحظة": note,
        })

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{OUT.relative_to(ROOT)}: {len(rows)} items")
    for key, label in STATUS_AR.items():
        print(f"  {label}: {counts.get(key, 0)}")
    priced = sum(1 for r in rows if r["سعر الكاش"])
    with_inst = sum(1 for r in rows if r["سعر التقسيط"])
    diff_model = sum(1 for r in rows if "الموديل مكتوب على الموقع" in r["ملاحظة"])
    print(f"  بسعر كاش: {priced} · بسعر تقسيط: {with_inst} · الموديل مكتوب بشكل مختلف: {diff_model}")


if __name__ == "__main__":
    main()
