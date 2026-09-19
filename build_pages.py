"""Build one product page per item into docs/, ready to publish on GitHub Pages.

Usage:  python build_pages.py

Each page (docs/p/<code>.html) is what the big QR code on the printed card opens:
photo, price (cash + installments), full specs, highlights, and a comparison with
similar products in the store — on size, performance, warranty and value, not just price.
"""
import csv
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
SITE_BASE = "https://yahyagad9.github.io/cairosales-qr-cards"

STORE = {"name": "أسواق القاهرة للمبيعات", "branch": "مصر الجديدة", "hotline": "16141"}
INSTALMENT_MONTHS = 12

BRAND_AR = {
    "LG": "إل جي", "SAMSUNG": "سامسونج", "TORNADO": "تورنيدو", "BEKO": "بيكو",
    "Bompani": "بومباني", "Glem Gas": "جليم جاز", "Simfer": "سيمفر", "Syinix": "سينكس",
    "TCL": "تي سي إل", "Haier": "هاير", "Hisense": "هايسنس", "Fresh": "فريش",
    "Unionaire": "يونيون اير", "Ariston": "أريستون", "Indesit": "إنديست", "Bosch": "بوش",
    "Elica": "إليكا", "Gorenje": "جورينيه", "Fagor": "فاجور", "Franke": "فرانكي",
}


# --------------------------------------------------------------------------- data


def family_of(p):
    """Group products so only comparable things are compared."""
    text = f"{p['site'].get('category','')} {p['site'].get('title','')}"
    if "شاشات" in text or "تليفزيون" in text or "تلفزيون" in text:
        return "tv"
    if "شفاط" in text:
        return "hood"
    if "غسال" in text:
        return "washer"
    return "other"


def num(value):
    m = re.search(r"\d[\d,.]*", str(value or ""))
    return float(m.group().replace(",", "")) if m else None


def size_of(p, family):
    """Screen inches / hood width in cm / washer kilos."""
    s = p["site"]["specs"]
    text = f"{p['site'].get('title','')} {p.get('store_name','')}"
    if family == "tv":
        return num(s.get("الحجم")) or num(re.search(r"(\d{2,3})\s*بوصة", text).group(1) if re.search(r"(\d{2,3})\s*بوصة", text) else None)
    if family == "hood":
        return num(s.get("الأبعاد")) or num(re.search(r"(\d{2,3})\s*سم", text).group(1) if re.search(r"(\d{2,3})\s*سم", text) else None)
    if family == "washer":
        return num(s.get("الحجم"))
    return None


def performance_of(p, family):
    """The number customers actually compare within a family."""
    s = p["site"]["specs"]
    text = " ".join([p["site"].get("title", ""), p["site"].get("short_description", ""), p.get("store_name", "")])
    if family == "tv":
        panel = next((k for k in ("OLED", "QNED", "Neo QLED", "QLED", "Mini LED", "LED")
                      if k.lower() in text.lower()), "LED")
        return {"label": "نوع الشاشة", "text": panel, "value": None, "better": "high"}
    if family == "hood":
        m = re.search(r"(\d{3,4})\s*(?:م ?3|م³|متر مكعب)", text)
        v = float(m.group(1)) if m else None
        return {"label": "قوة الشفط", "text": f"{int(v):,} م³/س" if v else "—", "value": v, "better": "high"}
    if family == "washer":
        m = re.search(r"(\d{3,4})\s*لفة", text)
        v = float(m.group(1)) if m else None
        return {"label": "سرعة العصر", "text": f"{int(v):,} لفة" if v else "—", "value": v, "better": "high"}
    return {"label": "", "text": "—", "value": None, "better": "high"}


def warranty_years(p):
    return num(p["site"]["specs"].get("الضمان")) or (2 if "عامين" in str(p["site"]["specs"].get("الضمان", "")) else None)


def price_of(p):
    return num(p["site"].get("price_cash"))


def size_unit(family):
    return {"tv": "بوصة", "hood": "سم", "washer": "كيلو"}.get(family, "")


def value_row(p, family):
    """Value for money, e.g. price per inch / per m³ of suction."""
    price, size = price_of(p), size_of(p, family)
    perf = performance_of(p, family)
    if family == "tv" and price and size:
        return {"label": "السعر لكل بوصة", "text": f"{round(price / size):,} ج", "value": price / size, "better": "low"}
    if family == "hood" and price and perf["value"]:
        return {"label": "السعر لكل م³ شفط", "text": f"{round(price / perf['value']):,} ج", "value": price / perf["value"], "better": "low"}
    if family == "washer" and price and size:
        return {"label": "السعر لكل كيلو", "text": f"{round(price / size):,} ج", "value": price / size, "better": "low"}
    return None


def rivals(code, products, family, limit=3):
    """Closest products of the same family, by size then price."""
    me = products[code]
    my_size, my_price = size_of(me, family), price_of(me)
    others = [(c, p) for c, p in products.items()
              if c != code and p.get("site") and family_of(p) == family and price_of(p)]

    def distance(item):
        _, p = item
        s, pr = size_of(p, family), price_of(p)
        size_gap = abs((s or 0) - (my_size or 0)) if my_size and s else 99
        price_gap = abs((pr or 0) - (my_price or 0)) / max(my_price or 1, 1)
        return (size_gap, price_gap)

    return [c for c, _ in sorted(others, key=distance)[:limit]]


# --------------------------------------------------------------------------- text


def clean_title(p):
    title = p["site"].get("title") or p.get("store_name", "")
    title = title.replace(p["model"], "").strip(" -·")
    return re.sub(r"\s+", " ", title)


def quick_facts(p, family):
    """A few headline facts, built from the spec table (no guessing)."""
    s = p["site"]["specs"]
    perf = performance_of(p, family)
    size = size_of(p, family)
    facts = []
    if size:
        facts.append(f"المقاس {int(size)} {size_unit(family)}")
    if perf["text"] and perf["text"] != "—":
        facts.append(f"{perf['label']}: {perf['text']}")
    for key in ("دقة", "نظام التشغيل", "اللون", "شكل الشفاط", "نوع الفتحة", "عدد الفلاتر",
                "ريسيفر داخلي", "سمارت", "مدخنة", "بخار", "مجفف", "حلة ستانلس"):
        v = (s.get(key) or "").strip()
        if v and v.lower() not in ("no", "لا"):
            facts.append(f"{key}: {'نعم' if v.lower() == 'yes' else v}")
    if s.get("الضمان"):
        facts.append(f"ضمان {s['الضمان']}")
    if s.get("بلد الصنع"):
        facts.append(f"بلد الصنع {s['بلد الصنع']}")
    return facts[:6]


def spec_rows(p):
    """All specs from the site, model row dropped (it is shown above)."""
    skip = {"الموديل"}
    return [(k, v) for k, v in p["site"]["specs"].items() if k not in skip and v]


def fmt(n):
    return f"{int(n):,}" if n is not None else "—"


# --------------------------------------------------------------------------- html


CSS = """
@font-face { font-family: "Cairo"; src: url("../assets/Cairo.ttf"); font-weight: 200 1000; }
@font-face { font-family: "Inter"; src: url("../assets/Inter.ttf"); font-weight: 100 900; }
:root {
  --red: #D71F2B; --ink: #0E1116; --ink-2: #1B2029; --body: #6B7480; --line: #E7EAEF;
  --bg: #EFF1F5; --green: #0E8A4F; --amber: #B7791F;
}
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
body { background: var(--bg); font-family: "Cairo", system-ui, sans-serif; color: var(--ink); padding: 0 0 22px; }
.sheet { max-width: 460px; margin: 0 auto; background: #fff; min-height: 100vh; box-shadow: 0 0 40px rgba(14,17,22,.07); }
.n { font-family: "Inter", sans-serif; direction: ltr; unicode-bidi: isolate; }
img { max-width: 100%; display: block; }

/* ---------- identity band ---------- */
.band { background: var(--ink); color: #fff; padding: 16px 18px 20px; position: relative; overflow: hidden; }
.band::after { content: ""; position: absolute; inset-inline-end: -60px; top: -80px; width: 220px; height: 220px; border-radius: 50%; background: radial-gradient(circle, rgba(215,31,43,.34), transparent 65%); }
.band .line { display: flex; align-items: center; justify-content: space-between; gap: 10px; position: relative; z-index: 1; }
.band .store { display: flex; align-items: center; gap: 8px; font-size: 10.5px; font-weight: 700; color: #A8B1BD; }
.band .store img { width: 26px; height: 26px; border-radius: 50%; background: #fff; }
.stock { font-size: 10.5px; font-weight: 800; border-radius: 30px; padding: 5px 11px; background: rgba(16,185,129,.16); color: #4ADE80; white-space: nowrap; }
.stock.out { background: rgba(239,68,68,.18); color: #FCA5A5; }
.band h1 { font-size: 21px; font-weight: 800; line-height: 1.4; margin-top: 14px; position: relative; z-index: 1; }
.band .meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; position: relative; z-index: 1; }
.band .meta span { font-size: 10.5px; font-weight: 700; color: #C9D1DB; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); border-radius: 7px; padding: 4px 9px; }
.band .meta .brand { font-family: "Inter"; font-weight: 800; background: #fff; color: var(--ink); border-color: #fff; }

/* ---------- photo ---------- */
.shot { padding: 18px 24px 8px; background: linear-gradient(180deg, #fff, #F7F8FA); }

/* ---------- price ---------- */
.money { padding: 4px 18px 18px; background: linear-gradient(180deg, #F7F8FA, #fff); }
.money .row { display: flex; align-items: flex-end; gap: 10px; }
.money .cash { font-family: "Inter"; font-weight: 900; font-size: 38px; letter-spacing: -1.2px; color: var(--red); line-height: 1; }
.money .cur { font-size: 13px; font-weight: 800; color: var(--red); margin-bottom: 4px; }
.money .lbl { font-size: 10.5px; font-weight: 800; color: var(--body); letter-spacing: .5px; margin-bottom: 4px; }
.money .inst { margin-inline-start: auto; text-align: left; }
.money .inst b { font-family: "Inter"; font-weight: 800; font-size: 16px; display: block; }
.money .inst span { font-size: 10px; font-weight: 700; color: var(--body); }
.soldout { margin: 4px 0 0; padding: 14px 15px; border-radius: 13px; background: #FDF1F2; border: 1px solid #F6D7DA; }
.soldout b { display: block; font-size: 14px; font-weight: 800; color: var(--red); margin-bottom: 4px; }
.soldout span { font-size: 12px; font-weight: 600; color: #7A4247; line-height: 1.6; }

/* ---------- sections ---------- */
section { padding: 18px; border-top: 8px solid var(--bg); }
h2 { font-size: 12.5px; font-weight: 800; letter-spacing: .3px; display: flex; align-items: center; gap: 7px; margin-bottom: 14px; }
h2::before { content: ""; width: 3px; height: 13px; border-radius: 3px; background: var(--red); }
h2 small { margin-inline-start: auto; font-size: 10px; font-weight: 600; color: var(--body); letter-spacing: 0; }

/* stat tiles */
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.stat { border: 1px solid var(--line); border-radius: 13px; padding: 12px; background: #fff; }
.stat .k { font-size: 10.5px; font-weight: 700; color: var(--body); }
.stat .v { font-size: 19px; font-weight: 800; margin-top: 5px; line-height: 1.1; }
.stat .v small { font-size: 11px; font-weight: 700; color: var(--body); }
.stat .note { font-size: 10px; font-weight: 700; margin-top: 5px; }
.up { color: var(--red); } .down { color: var(--green); } .flat { color: var(--body); }

/* price position meter */
.meter { margin-top: 14px; }
.meter .track { position: relative; height: 8px; border-radius: 6px; background: linear-gradient(90deg, #E6F5ED, #FDECEE); }
.meter .dot { position: absolute; top: -4px; width: 16px; height: 16px; border-radius: 50%; background: var(--red); border: 3px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.22); transform: translateX(50%); }
.meter .ends { display: flex; justify-content: space-between; margin-top: 7px; font-size: 10px; font-weight: 700; color: var(--body); }
.meter .cap { font-size: 10.5px; font-weight: 700; color: var(--body); margin-bottom: 8px; }

/* comparison */
.cmp { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.cmp th, .cmp td { padding: 9px 5px; text-align: center; border-bottom: 1px solid var(--line); }
.cmp thead th { font-weight: 800; font-size: 10.5px; line-height: 1.35; vertical-align: bottom; }
.cmp thead th small { display: block; font-weight: 600; color: var(--body); font-size: 9px; margin-top: 2px; }
.cmp tbody th { text-align: right; font-weight: 700; color: var(--body); font-size: 10.5px; white-space: nowrap; }
.cmp td { font-weight: 700; }
.cmp .me { background: #FFF6F6; }
.cmp .best { color: var(--green); font-weight: 800; }
.cmp .best::after { content: " ✓"; font-size: 9px; }
.mytag { display: inline-block; font-size: 9px; font-weight: 800; color: #fff; background: var(--red); border-radius: 20px; padding: 2px 7px; margin-bottom: 4px; }
.legend { margin-top: 10px; font-size: 10px; color: var(--body); font-weight: 600; line-height: 1.6; }

/* facts + specs */
.facts { display: flex; flex-wrap: wrap; gap: 7px; }
.facts span { font-size: 11px; font-weight: 700; background: #F3F5F8; border-radius: 8px; padding: 6px 10px; }
.about { font-size: 12.5px; line-height: 1.85; color: #2C333C; margin-top: 12px; }
.sp { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--line); }
.sp:last-child { border: 0; padding-bottom: 0; }
.sp:first-of-type { padding-top: 0; }
.sp .k { flex: 1; font-size: 11.5px; font-weight: 600; color: var(--body); }
.sp .v { font-size: 12.5px; font-weight: 800; text-align: left; }

.note-foot { padding: 16px 18px 6px; text-align: center; font-size: 10px; color: var(--body); font-weight: 600; line-height: 1.8; }
.note-foot b { font-family: "Inter"; color: var(--ink); }

/* index */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; padding: 16px; }
.item { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 10px; text-decoration: none; color: inherit; }
.item img { border-radius: 9px; margin-bottom: 8px; }
.item b { display: block; font-size: 11.5px; font-weight: 700; line-height: 1.4; height: 32px; overflow: hidden; }
.item .p { font-family: "Inter"; font-weight: 800; font-size: 13px; color: var(--red); margin-top: 6px; }
.page { max-width: 460px; margin: 0 auto; background: #fff; min-height: 100vh; }
.top { background: var(--ink); color: #fff; padding: 13px 18px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.brandline { display: flex; align-items: center; gap: 9px; }
.brandline img { width: 34px; height: 34px; border-radius: 50%; background: #fff; }
.brandline b { font-size: 13.5px; font-weight: 800; }
.brandline span { display: block; font-size: 10px; color: #98A1AD; font-weight: 600; }
.where { font-size: 10.5px; font-weight: 700; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.16); border-radius: 8px; padding: 6px 9px; white-space: nowrap; }
.wrap { padding: 16px 14px 26px; }
.card { background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 16px; margin-bottom: 12px; }
.kicker { font-size: 11px; font-weight: 700; color: var(--body); margin-bottom: 8px; }
.sub { margin-top: 6px; font-size: 11.5px; font-weight: 600; color: var(--body); }
.sub b { font-family: "Inter"; font-weight: 700; color: var(--ink); }
"""

def peer_set(code, products, family):
    """Products of the same family and (when possible) the same size, for ranking."""
    my_size = size_of(products[code], family)
    same = [c for c, q in products.items()
            if family_of(q) == family and price_of(q)]
    sized = [c for c in same if my_size and size_of(products[c], family) == my_size]
    return sized if len(sized) >= 3 else same


def analysis(code, products, family):
    """Numbers that help a customer judge the product, all derived from our own data."""
    p = products[code]
    price = price_of(p)
    peers = peer_set(code, products, family)
    prices = sorted(price_of(products[c]) for c in peers)
    out = {"peers": len(peers), "min": prices[0] if prices else None,
           "max": prices[-1] if prices else None}

    if price and prices:
        cheaper = sum(1 for x in prices if x < price)
        out["rank"] = cheaper + 1
        span = (prices[-1] - prices[0]) or 1
        out["position"] = max(0, min(100, round((price - prices[0]) / span * 100)))

    value = value_row(p, family)
    if value:
        peer_values = [v for v in ((value_row(products[c], family) or {}).get("value") for c in peers) if v]
        if peer_values:
            avg = sum(peer_values) / len(peer_values)
            out["value"] = value
            out["value_avg"] = avg
            out["value_diff"] = round((value["value"] - avg) / avg * 100)

    inst = num(p["site"].get("price_installment"))
    if inst and price and inst > price:
        out["cash_saving"] = inst - price
        out["cash_saving_pct"] = round((inst - price) / inst * 100)

    years = warranty_years(p)
    peer_years = [w for w in (warranty_years(products[c]) for c in peers) if w]
    if years:
        out["warranty"] = years
        out["warranty_best"] = bool(peer_years) and years >= max(peer_years) and len(set(peer_years)) > 1
    return out


def page_html(code, products):
    p = products[code]
    s = p["site"]
    e = html.escape
    family = family_of(p)
    perf = performance_of(p, family)
    price = price_of(p)
    inst = num(s.get("price_installment")) or price
    monthly = round(inst / INSTALMENT_MONTHS) if inst else None
    # Stock rule: a price on the website means we have it; no price means it is finished
    in_stock = bool(price)
    a = analysis(code, products, family) if in_stock else {}
    size = size_of(p, family)
    specs = s.get("specs", {})
    img = f"../img/{code}.jpg" if (DOCS / "img" / f"{code}.jpg").exists() else (s.get("images") or [""])[0]

    # ---------- identity chips
    meta = [f'<span class="brand">{e(s.get("brand") or "")}</span>' if s.get("brand") else ""]
    if size:
        meta.append(f'<span>{int(size)} {size_unit(family)}</span>')
    if perf["text"] != "—":
        meta.append(f'<span>{e(perf["text"])}</span>')
    if specs.get("الضمان"):
        meta.append(f'<span>ضمان {e(specs["الضمان"])}</span>')
    if specs.get("بلد الصنع"):
        meta.append(f'<span>صنع في {e(specs["بلد الصنع"])}</span>')

    # ---------- price block
    if in_stock:
        money = f"""
    <div class="money">
      <div class="row">
        <div>
          <div class="lbl">سعر الكاش</div>
          <div style="display:flex;align-items:flex-end;gap:6px">
            <span class="cash n">{fmt(price)}</span><span class="cur">جنيه</span>
          </div>
        </div>
        {f'<div class="inst"><b class="n">{fmt(monthly)}</b><span>جنيه × {INSTALMENT_MONTHS} شهر · إجمالي {fmt(inst)}</span></div>' if inst and inst != price else ''}
      </div>
    </div>"""
    else:
        money = """
    <div class="money">
      <div class="soldout">
        <b>المنتج ده مش متوفر دلوقتي</b>
        <span>اسأل البائع إمتى هيوصل</span>
      </div>
    </div>"""

    # ---------- quick analysis tiles
    tiles = []
    if a.get("rank"):
        tiles.append(f"""<div class="stat"><div class="k">ترتيبه في السعر</div>
          <div class="v"><span class="n">{a['rank']}</span> <small>من {a['peers']}</small></div>
          <div class="note flat">من الأرخص للأغلى في نفس المقاس</div></div>""")
    if a.get("value"):
        diff = a["value_diff"]
        klass = "down" if diff < 0 else ("up" if diff > 0 else "flat")
        word = "أقل من متوسط الفئة" if diff < 0 else ("أعلى من متوسط الفئة" if diff > 0 else "زي متوسط الفئة")
        tiles.append(f"""<div class="stat"><div class="k">{e(a['value']['label'])}</div>
          <div class="v n">{a['value']['text']}</div>
          <div class="note {klass}">{word} بـ <span class="n">{abs(diff)}%</span></div></div>""")
    if a.get("cash_saving"):
        tiles.append(f"""<div class="stat"><div class="k">توفير الكاش</div>
          <div class="v"><span class="n">{fmt(a['cash_saving'])}</span> <small>جنيه</small></div>
          <div class="note down">أقل من سعر التقسيط بـ <span class="n">{a['cash_saving_pct']}%</span></div></div>""")
    if a.get("warranty"):
        tiles.append(f"""<div class="stat"><div class="k">الضمان</div>
          <div class="v"><span class="n">{int(a['warranty'])}</span> <small>سنة</small></div>
          <div class="note {'down' if a.get('warranty_best') else 'flat'}">{'الأطول في فئته' if a.get('warranty_best') else 'ضمان الوكيل'}</div></div>""")

    meter = ""
    if a.get("position") is not None and a.get("min") != a.get("max"):
        meter = f"""
      <div class="meter">
        <div class="cap">سعره بين {a['peers']} منتج بنفس المقاس عندنا</div>
        <div class="track"><span class="dot" style="inset-inline-start:calc({100 - a['position']}% - 8px)"></span></div>
        <div class="ends"><span>الأرخص <b class="n">{fmt(a['min'])}</b></span><span>الأغلى <b class="n">{fmt(a['max'])}</b></span></div>
      </div>"""

    analysis_section = ""
    if tiles:
        analysis_section = f"""
    <section>
      <h2>تحليل سريع <small>مقارنة بالمعروض عندنا</small></h2>
      <div class="stats">{''.join(tiles)}</div>
      {meter}
    </section>"""

    # ---------- comparison table
    others = rivals(code, products, family) if in_stock else []
    table = ""
    if others:
        cols = [code] + others
        rows = [("سعر الكاش", [price_of(products[c]) for c in cols], "low"),
                (f"المقاس ({size_unit(family)})", [size_of(products[c], family) for c in cols], None)]
        perfs = [performance_of(products[c], family) for c in cols]
        if any(x["text"] != "—" for x in perfs):
            rows.append((perf["label"], [x["value"] for x in perfs],
                         "high" if any(x["value"] for x in perfs) else None))
        rows.append(("الضمان (سنة)", [warranty_years(products[c]) for c in cols], "high"))
        vr = value_row(p, family)
        if vr:
            rows.append((vr["label"], [(value_row(products[c], family) or {}).get("value") for c in cols], vr["better"]))
        rows.append(("التقسيط شهريًا", [round((num(products[c]["site"].get("price_installment")) or price_of(products[c])) / INSTALMENT_MONTHS)
                                        for c in cols], "low"))

        head = []
        for i, c in enumerate(cols):
            q = products[c]
            nm = e(BRAND_AR.get(q["site"].get("brand", ""), q["site"].get("brand", "")))
            head.append(f'<th class="{"me" if i == 0 else ""}">'
                        + ('<span class="mytag">ده</span><br>' if i == 0 else "")
                        + f'{nm}<small class="n">{e(q["model"])}</small></th>')

        body = []
        for label, values, better in rows:
            numeric = [v for v in values if isinstance(v, (int, float))]
            best = None
            if better and len(set(numeric)) > 1:
                best = min(numeric) if better == "low" else max(numeric)
            cells = []
            for i, v in enumerate(values):
                if label == perf["label"]:
                    cell = e(perfs[i]["text"])
                elif isinstance(v, (int, float)):
                    cell = f'<span class="n">{fmt(v)}</span>'
                else:
                    cell = "—"
                klass = " ".join(x for x in ["me" if i == 0 else "", "best" if best is not None and v == best else ""] if x)
                cells.append(f'<td class="{klass}">{cell}</td>')
            body.append(f"<tr><th>{e(label)}</th>{''.join(cells)}</tr>")

        table = f"""
    <section>
      <h2>مقارنة بأقرب المنتجات عندنا</h2>
      <table class="cmp">
        <thead><tr><th></th>{''.join(head)}</tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      <div class="legend">✓ = الأفضل في السطر ده · الأسعار سعر الكاش اليوم</div>
    </section>"""

    facts = "".join(f"<span>{e(f)}</span>" for f in quick_facts(p, family))
    about = e(s.get("short_description", "")).strip()
    spec_list = "".join(f'<div class="sp"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>'
                        for k, v in spec_rows(p))

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(clean_title(p))} - {STORE['name']}</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="sheet">

  <div class="band">
    <div class="line">
      <div class="store"><img src="../assets/logo.jpeg" alt=""> {STORE['name']} · {STORE['branch']}</div>
      <span class="stock{'' if in_stock else ' out'}">{'● متوفر في الفرع' if in_stock else '● غير متوفر حاليًا'}</span>
    </div>
    <h1>{e(clean_title(p))}</h1>
    <div class="meta">{''.join(meta)}<span class="n">{e(p['model'])}</span></div>
  </div>

  {f'<div class="shot"><img src="{img}" alt="{e(p["model"])}"></div>' if img else ''}
  {money}
  {analysis_section}
  {table}

  {f'<section><h2>باختصار</h2><div class="facts">{facts}</div>{f"<p class=\'about\'>{about}</p>" if about else ""}</section>' if facts or about else ''}

  <section><h2>المواصفات الكاملة</h2>{spec_list}</section>

  <div class="note-foot">
    الأسعار شاملة الضريبة · التوصيل والتركيب مجانًا داخل القاهرة<br>
    آخر تحديث للأسعار <b class="n">{date.today().isoformat()}</b>
  </div>
</div>
</body>
</html>
"""


def index_html(products, items=None):
    e = html.escape
    items = items or {}
    cards = []
    for code, p in sorted(products.items(), key=lambda kv: kv[1]["site"]["title"]):
        img = f"img/{code}.jpg" if (DOCS / "img" / f"{code}.jpg").exists() else p["site"]["images"][0]
        cards.append(
            f'<a class="item" href="p/{code}.html"><img src="{img}" alt="">'
            f'<b>{e(clean_title(p))}</b><div class="p n">{fmt(price_of(p))} EGP</div></a>'
        )
    for code, item in sorted(items.items(), key=lambda kv: kv[1]["name"]):
        if code in products:
            continue
        cards.append(
            f'<a class="item" href="p/{code}.html"><b>{e(item["name"])}</b>'
            f'<div class="p" style="color:#656E7A">غير متوفر حاليًا</div></a>'
        )
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>منتجات {STORE['name']}</title>
<link rel="stylesheet" href="assets/style.css">
<style>.wrap{{padding:16px 14px 26px}}</style>
</head>
<body>
<div class="page">
  <div class="top">
    <div class="brandline">
      <img src="assets/logo.jpeg" alt="">
      <div><b>{STORE['name']}</b><span>{STORE['branch']}</span></div>
    </div>
    <div class="where">{len(products)} منتج</div>
  </div>
  <div class="wrap"><div class="grid">{''.join(cards)}</div></div>
</div>
</body>
</html>
"""


def minimal_page(code, item):
    """Item not on the website: no price, so it counts as out of stock."""
    e = html.escape
    name = e(item.get("name") or item.get("store_name") or "")
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - {STORE['name']}</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="page">
  <div class="top">
    <div class="brandline">
      <img src="../assets/logo.jpeg" alt="">
      <div><b>{STORE['name']}</b><span>{STORE['branch']}</span></div>
    </div>
    <div class="where">{e(item.get('category',''))}</div>
  </div>
  <div class="wrap">
    <div class="card">
      <div class="kicker"><span>{e(item.get('category',''))}</span></div>
      <h1>{name}</h1>
      <div class="sub">الموديل <b>{e(item.get('model',''))}</b></div>
      <div class="soldout">
        <b>المنتج ده مش متوفر دلوقتي</b>
        <span>اسأل البائع إمتى هيوصل</span>
      </div>
    </div>
    <div class="note">آخر تحديث <b class="n">{date.today().isoformat()}</b></div>
  </div>
</div>
</body>
</html>
"""


def main():
    products = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    products = {c: p for c, p in products.items() if p.get("status") == "ok" and p.get("site")}
    with (ROOT / "data" / "items.csv").open(encoding="utf-8-sig", newline="") as f:
        items = {row["code"]: row for row in csv.DictReader(f)}

    (DOCS / "p").mkdir(parents=True, exist_ok=True)
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (DOCS / "assets" / "style.css").write_text(CSS, encoding="utf-8")
    for name, src in (("logo.jpeg", "logo.jpeg"), ("Cairo.ttf", "fonts/Cairo.ttf"), ("Inter.ttf", "fonts/Inter.ttf")):
        (DOCS / "assets" / name).write_bytes((ROOT / "assets" / src).read_bytes())
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    for code in products:
        (DOCS / "p" / f"{code}.html").write_text(page_html(code, products), encoding="utf-8")
    missing = [c for c in items if c not in products]
    for code in missing:
        (DOCS / "p" / f"{code}.html").write_text(minimal_page(code, items[code]), encoding="utf-8")
    (DOCS / "index.html").write_text(index_html(products, items), encoding="utf-8")
    print(f"built {len(products) + len(missing)} pages in docs/ "
          f"({len(products)} with website data, {len(missing)} marked out of stock)"
          f"  →  {SITE_BASE}/p/<code>.html")


if __name__ == "__main__":
    main()
