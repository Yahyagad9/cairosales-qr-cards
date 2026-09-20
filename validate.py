"""Safety checks that run between scraping and publishing.

Usage:
  python validate.py                 # compare data/products.json against the last published snapshot
  python validate.py --accept        # record the current data as the new baseline

A printed card can outlive a mistake, so a build only goes out when the data still
looks sane: no products disappearing, no zero prices, no wild price jumps.

Exit code 0 = safe to publish, 1 = blocked.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PRODUCTS = DATA / "products.json"
BASELINE = DATA / "baseline.json"

# A price that moves more than this in one run is treated as a mistake until a human says otherwise
MAX_PRICE_JUMP = 0.40
# How many matched products may vanish in one run before the build is blocked
MAX_LOST_PRODUCTS = 2


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def priced(products):
    out = {}
    for code, p in products.items():
        if p.get("status") == "ok" and (p.get("site") or {}).get("price_cash"):
            try:
                out[code] = float(p["site"]["price_cash"])
            except ValueError:
                pass
    return out


def check(new, old):
    """Return (blocking, warnings) — plain sentences, ready for the run summary."""
    blocking, warnings = [], []

    ok_new = {c for c, p in new.items() if p.get("status") == "ok"}
    if not ok_new:
        blocking.append("No product has usable data at all.")
        return blocking, warnings

    prices_new, prices_old = priced(new), priced(old)

    if old:
        ok_old = {c for c, p in old.items() if p.get("status") == "ok"}
        lost = sorted(ok_old - ok_new)
        if len(lost) > MAX_LOST_PRODUCTS:
            blocking.append(f"{len(lost)} products lost their data since the last good run "
                            f"({', '.join(lost[:5])}{'…' if len(lost) > 5 else ''}).")
        elif lost:
            warnings.append(f"{len(lost)} product(s) lost their data: {', '.join(lost)}.")

        no_price = sorted(c for c in ok_new & set(prices_old) if c not in prices_new)
        if len(no_price) > MAX_LOST_PRODUCTS:
            blocking.append(f"{len(no_price)} products lost their price, which would mark them out of stock "
                            f"({', '.join(no_price[:5])}{'…' if len(no_price) > 5 else ''}).")
        elif no_price:
            warnings.append(f"{len(no_price)} product(s) now show no price: {', '.join(no_price)}.")

    for code, price in prices_new.items():
        model = new[code].get("model", code)
        if price <= 0:
            blocking.append(f"{model} ({code}) has a price of {price:g}.")
            continue
        before = prices_old.get(code)
        if before and before > 0:
            change = (price - before) / before
            if abs(change) > MAX_PRICE_JUMP:
                blocking.append(f"{model} ({code}) moved {change:+.0%}: {before:,.0f} → {price:,.0f} EGP.")
            elif abs(change) >= 0.05:
                warnings.append(f"{model} ({code}) {change:+.0%}: {before:,.0f} → {price:,.0f} EGP.")

    return blocking, warnings


def summary(new, old):
    prices_new, prices_old = priced(new), priced(old)
    changed = [c for c, v in prices_new.items() if prices_old.get(c) not in (None, v)]
    return {
        "items": len(new),
        "with_data": sum(1 for p in new.values() if p.get("status") == "ok"),
        "with_price": len(prices_new),
        "price_changes": len(changed),
        "new_products": len(set(prices_new) - set(prices_old)) if old else 0,
    }


def accept(products=None):
    """Record the current data as the baseline the next run is compared against."""
    products = products or load(PRODUCTS)
    BASELINE.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(products)


def run():
    new, old = load(PRODUCTS), load(BASELINE)
    blocking, warnings = check(new, old)
    return summary(new, old), blocking, warnings


if __name__ == "__main__":
    if "--accept" in sys.argv:
        print(f"baseline set: {accept()} items ({datetime.now():%Y-%m-%d %H:%M})")
        sys.exit(0)

    stats, blocking, warnings = run()
    print(f"{stats['with_data']}/{stats['items']} items with data · {stats['with_price']} priced "
          f"· {stats['price_changes']} price change(s)")
    for w in warnings:
        print(f"  note: {w}")
    for b in blocking:
        print(f"  BLOCKED: {b}")
    sys.exit(1 if blocking else 0)
