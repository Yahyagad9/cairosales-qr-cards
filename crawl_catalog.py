"""Index every product in the relevant categories of cairosales.com.

Usage:  python crawl_catalog.py

The site's search box misses many model numbers, so instead we walk the category
listings page by page and store every product URL. data/catalog.json is then used
by scrape_site.py to find an item by matching its model against the URL slug.
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

import scrape_site as sc

ROOT = Path(__file__).parent
CATALOG = ROOT / "data" / "catalog.json"
PER_PAGE = 100

CATEGORIES = [
    # every category that can hold an item from the branch stock report
    "led-plasma-tvs", "kitchen-bath-hoods", "built-in-kitchen-products", "washers-dryers",
    "refrigerators", "freezers", "cookers-ovens", "air-conditioners", "dishwashers",
    "microwaves", "water-heaters", "small-appliances", "vacuums-steam-cleaners",
    "water-dispenser", "home-theaters-speakers", "electronics-tv-accessories",
    "mobiles-tablets", "air-purifiers", "cookware-tableware", "home-accessories",
]


def listing(category, page):
    url = f"{sc.SITE}/ar/{category}/?n={PER_PAGE}&p={page}"
    soup = BeautifulSoup(sc.fetch(url), "html.parser")
    out = {}
    for a in soup.select("#center_column .product_list a.product-name"):
        href = (a.get("href") or "").split("?")[0]
        if href:
            out[href] = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
    return out


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {}
    for category in CATEGORIES:
        page, seen_here = 1, 0
        while True:
            found = listing(category, page)
            fresh = {u: t for u, t in found.items() if u not in catalog}
            catalog.update({u: {"title": t, "category": category} for u, t in found.items()})
            seen_here += len(found)
            print(f"{category} p{page}: {len(found)} products ({len(fresh)} new)", flush=True)
            CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
            if len(found) < PER_PAGE:
                break
            page += 1
        print(f"{category}: {seen_here} total", flush=True)
    print(f"catalog: {len(catalog)} products in data/catalog.json")


if __name__ == "__main__":
    main()
