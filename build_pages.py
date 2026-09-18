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
  --red: #D71F2B; --ink: #0F1216; --body: #656E7A; --line: #E9ECF0;
  --bg: #F2F4F7; --green: #0E8A4F;
}
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
body { background: var(--bg); font-family: "Cairo", system-ui, sans-serif; color: var(--ink); }
.page { max-width: 480px; margin: 0 auto; background: var(--bg); min-height: 100vh; }
.n { font-family: "Inter", sans-serif; direction: ltr; unicode-bidi: isolate; }
img { max-width: 100%; display: block; }

.top { background: var(--ink); color: #fff; padding: 13px 18px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.brandline { display: flex; align-items: center; gap: 9px; }
.brandline img { width: 34px; height: 34px; border-radius: 50%; background: #fff; }
.brandline b { font-size: 13.5px; font-weight: 800; }
.brandline span { display: block; font-size: 10px; color: #98A1AD; font-weight: 600; }
.where { font-size: 10.5px; font-weight: 700; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.16); border-radius: 8px; padding: 6px 9px; white-space: nowrap; }

.stage { position: relative; background: #fff; padding: 18px 18px 24px; overflow: hidden; border-bottom: 1px solid var(--line); }
.stage::before { content: ""; position: absolute; top: -130px; inset-inline-start: -70px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(circle at 40% 60%, rgba(215,31,43,.1), rgba(215,31,43,0) 70%); }
.stage img { position: relative; width: 100%; }
.tags { position: absolute; top: 16px; inset-inline-end: 18px; display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
.tag { font-size: 10.5px; font-weight: 800; border-radius: 7px; padding: 5px 9px; background: #ECF7F1; color: var(--green); }
.tag.grey { background: #F2F4F7; color: var(--body); }
.tag.out { background: #FDECEE; color: var(--red); }

.wrap { padding: 16px 14px 26px; }
.card { background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 16px; margin-bottom: 12px; }
.card h2 { font-size: 13px; font-weight: 800; display: flex; align-items: center; gap: 7px; margin-bottom: 13px; }
.card h2::before { content: ""; width: 3px; height: 14px; border-radius: 3px; background: var(--red); }

.kicker { display: flex; align-items: center; gap: 7px; margin-bottom: 8px; flex-wrap: wrap; }
.kicker .bd { font-family: "Inter"; font-weight: 900; font-size: 13px; color: #fff; background: var(--ink); border-radius: 6px; padding: 3px 8px; }
.kicker span { font-size: 11px; font-weight: 700; color: var(--body); }
h1 { font-size: 20px; font-weight: 800; line-height: 1.4; }
.sub { margin-top: 6px; font-size: 11.5px; font-weight: 600; color: var(--body); }
.sub b { font-family: "Inter"; font-weight: 700; color: var(--ink); }

.price { margin-top: 14px; padding: 14px 15px; border-radius: 13px; background: linear-gradient(180deg, #FFF7F7, #fff); border: 1px solid #F6DDDF; }
.price .lbl { font-size: 10.5px; font-weight: 800; color: var(--body); letter-spacing: .6px; }
.amount { display: flex; align-items: baseline; gap: 6px; margin-top: 2px; flex-wrap: wrap; }
.amount .v { font-family: "Inter"; font-weight: 900; font-size: 34px; letter-spacing: -1px; color: var(--red); }
.amount .c { font-size: 14px; font-weight: 800; color: var(--red); }
.amount .save { margin-inline-start: auto; font-size: 10.5px; font-weight: 800; color: var(--green); background: #ECF7F1; border-radius: 7px; padding: 4px 8px; }
.split { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px; padding-top: 11px; border-top: 1px solid #F1E2E3; }
.split .l { font-size: 11.5px; font-weight: 700; color: var(--body); }
.split .l small { display: block; font-weight: 600; font-size: 10px; color: #94A0AD; margin-top: 2px; }
.split .r b { font-family: "Inter"; font-weight: 800; font-size: 17px; }
.split .r span { font-size: 10.5px; font-weight: 700; color: var(--body); }

.sp { display: flex; align-items: center; gap: 11px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.sp:last-child { border: 0; padding-bottom: 0; }
.sp:first-of-type { padding-top: 0; }
.sp .k { flex: 1; font-size: 12px; font-weight: 600; color: var(--body); }
.sp .v { font-size: 13px; font-weight: 800; text-align: left; }

.hl li { position: relative; padding-inline-start: 17px; font-size: 12.5px; line-height: 1.65; color: #2C333C; margin-bottom: 8px; list-style: none; }
.hl li:last-child { margin-bottom: 0; }
.about { font-size: 12.5px; line-height: 1.85; color: #2C333C; }
.hl li::before { content: ""; position: absolute; inset-inline-start: 0; top: 8px; width: 7px; height: 7px; border-radius: 2px; background: var(--red); }

/* comparison table */
.cmp { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.cmp th, .cmp td { padding: 9px 6px; text-align: center; border-bottom: 1px solid var(--line); }
.cmp th { font-weight: 800; font-size: 11px; line-height: 1.35; vertical-align: bottom; }
.cmp th small { display: block; font-weight: 600; color: var(--body); font-size: 9.5px; margin-top: 2px; }
.cmp tbody th { text-align: right; font-weight: 700; color: var(--body); font-size: 11px; white-space: nowrap; }
.cmp td { font-weight: 700; }
.cmp .me { background: #FFF6F6; }
.cmp thead .me { border-top-left-radius: 10px; border-top-right-radius: 10px; }
.cmp .me .n, .cmp .me { color: var(--ink); }
.cmp .best { color: var(--green); font-weight: 800; }
.cmp .best::after { content: " ✓"; font-size: 10px; }
.mytag { display: inline-block; font-size: 9px; font-weight: 800; color: #fff; background: var(--red); border-radius: 20px; padding: 2px 7px; margin-bottom: 4px; }
.legend { margin-top: 10px; font-size: 10.5px; color: var(--body); font-weight: 600; line-height: 1.6; }

.soldout { margin-top: 14px; padding: 14px 15px; border-radius: 13px; background: #FDF1F2; border: 1px solid #F6D7DA; }
.soldout b { display: block; font-size: 14px; font-weight: 800; color: var(--red); margin-bottom: 4px; }
.soldout span { font-size: 12px; font-weight: 600; color: #7A4247; line-height: 1.6; }

.cta { display: flex; gap: 9px; }
.cta a { flex: 1; text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 13px; padding: 14px 8px; font-size: 12.5px; font-weight: 800; }
.cta .main { background: var(--red); color: #fff; }
.cta .alt { background: #fff; color: var(--ink); border: 1.4px solid var(--line); }
.note { text-align: center; font-size: 10px; color: var(--body); font-weight: 600; margin-top: 12px; line-height: 1.8; }
.note b { font-family: "Inter"; color: var(--ink); }

/* index */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.item { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 10px; text-decoration: none; color: inherit; }
.item img { border-radius: 9px; margin-bottom: 8px; }
.item b { display: block; font-size: 11.5px; font-weight: 700; line-height: 1.4; height: 32px; overflow: hidden; }
.item .p { font-family: "Inter"; font-weight: 800; font-size: 13px; color: var(--red); margin-top: 6px; }
"""


def page_html(code, products):
    p = products[code]
    s = p["site"]
    family = family_of(p)
    perf = performance_of(p, family)
    value = value_row(p, family)
    price = price_of(p)
    inst = num(s.get("price_installment")) or price
    monthly = round(inst / INSTALMENT_MONTHS) if inst else None
    save = int(inst - price) if inst and price and inst > price else 0
    brand = s.get("brand", "")
    brand_ar = BRAND_AR.get(brand, brand)
    others = rivals(code, products, family)
    e = html.escape

    # comparison table: this product + up to 3 rivals, best value marked per row
    cols = [code] + others
    rows = []
    rows.append(("سعر الكاش", [price_of(products[c]) for c in cols], "low", lambda v: f'<span class="n">{fmt(v)}</span>'))
    rows.append((f"المقاس ({size_unit(family)})", [size_of(products[c], family) for c in cols], None,
                 lambda v: f'<span class="n">{fmt(v)}</span>'))
    perfs = [performance_of(products[c], family) for c in cols]
    if any(x["text"] != "—" for x in perfs):
        # numeric perf (suction, spin speed) can be ranked; text perf (panel type) just shown
        ranked = "high" if any(x["value"] for x in perfs) else None
        rows.append((perf["label"], [x["value"] for x in perfs], ranked, None))
    rows.append(("الضمان (سنة)", [warranty_years(products[c]) for c in cols], "high",
                 lambda v: f'<span class="n">{fmt(v)}</span>'))
    if value:
        rows.append((value["label"], [(value_row(products[c], family) or {}).get("value") for c in cols],
                     value["better"], lambda v: f'<span class="n">{fmt(v)}</span>'))

    head = []
    for i, c in enumerate(cols):
        q = products[c]
        nm = e(BRAND_AR.get(q["site"].get("brand", ""), q["site"].get("brand", "")))
        head.append(f'<th class="{"me" if i == 0 else ""}">'
                    + ('<span class="mytag">ده</span><br>' if i == 0 else "")
                    + f'{nm}<small class="n">{e(q["model"])}</small></th>')

    body = []
    for label, values, better, render in rows:
        best = None
        numeric = [v for v in values if isinstance(v, (int, float))]
        # only flag a winner when the values actually differ
        if better and len(set(numeric)) > 1:
            best = min(numeric) if better == "low" else max(numeric)
        cells = []
        for i, v in enumerate(values):
            if label == perf["label"]:
                text = e(perfs[i]["text"])
            elif isinstance(v, (int, float)):
                text = f'<span class="n">{fmt(v)}</span>'
            else:
                text = "—"
            klass = " ".join(x for x in ["me" if i == 0 else "", "best" if best is not None and v == best else ""] if x)
            cells.append(f'<td class="{klass}">{text}</td>')
        body.append(f"<tr><th>{e(label)}</th>{''.join(cells)}</tr>")

    specs = "".join(
        f'<div class="sp"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>'
        for k, v in spec_rows(p)
    )
    bullets = "".join(f"<li>{e(b)}</li>" for b in quick_facts(p, family))
    about = e(s.get("short_description", "")).strip()
    # Stock rule: a price on the website means we have it; no price means it is finished
    in_stock = bool(price)
    warranty = s["specs"].get("الضمان")
    img = f"../img/{code}.jpg" if (DOCS / "img" / f"{code}.jpg").exists() else s["images"][0]

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(clean_title(p))} - {STORE['name']}</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="page">

  <div class="top">
    <div class="brandline">
      <img src="../assets/logo.jpeg" alt="">
      <div><b>{STORE['name']}</b><span>{STORE['branch']}</span></div>
    </div>
    <div class="where">{e(s.get('category',''))}</div>
  </div>

  <div class="stage">
    <div class="tags">
      <span class="tag{'' if in_stock else ' out'}">● {'متوفر في الفرع' if in_stock else 'غير متوفر حاليًا'}</span>
      {f'<span class="tag grey">ضمان {e(warranty)}</span>' if warranty else ''}
    </div>
    <img src="{img}" alt="{e(p['model'])}">
  </div>

  <div class="wrap">

    <div class="card">
      <div class="kicker">
        <span class="bd">{e(brand or '—')}</span>
        <span>{e(brand_ar)} · {e(s.get('category',''))}</span>
      </div>
      <h1>{e(clean_title(p))}</h1>
      <div class="sub">الموديل <b>{e(p['model'])}</b></div>

      {f"""<div class="soldout">
        <b>المنتج ده مش متوفر دلوقتي</b>
        <span>اسأل البائع إمتى هيوصل، أو كلّمنا على {STORE['hotline']}</span>
      </div>""" if not in_stock else f'''<div class="price">
        <div class="lbl">سعر الكاش</div>
        <div class="amount">
          <span class="v n">{fmt(price)}</span><span class="c">جنيه</span>
          {f'<span class="save">وفّر {fmt(save)}</span>' if save else ''}
        </div>
        {f"""<div class="split">
          <div class="l">بالتقسيط<small>الإجمالي {fmt(inst)} جنيه</small></div>
          <div class="r"><b class="n">{fmt(monthly)}</b> <span>جنيه × {INSTALMENT_MONTHS} شهر</span></div>
        </div>""" if inst and inst != price else ''}
      </div>'''}
    </div>

    {f'<div class="card hl"><h2>باختصار</h2><ul>{bullets}</ul></div>' if bullets else ''}

    {f'<div class="card"><h2>نبذة عن المنتج</h2><p class="about">{about}</p></div>' if about else ''}

    <div class="card"><h2>المواصفات الكاملة</h2>{specs}</div>

    {f'''<div class="card">
      <h2>قارن مع اللي عندنا في الفرع</h2>
      <table class="cmp">
        <thead><tr><th></th>{''.join(head)}</tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      <div class="legend">✓ = الأفضل في السطر ده · الأسعار سعر الكاش اليوم</div>
    </div>''' if others else ''}

    <div class="cta">
      <a class="main" href="{e(s.get('short_url',''))}">شوف المنتج على موقعنا</a>
      <a class="alt" href="tel:{STORE['hotline']}">اتصل بنا {STORE['hotline']}</a>
    </div>

    <div class="note">
      الأسعار شاملة الضريبة · التوصيل والتركيب مجانًا داخل القاهرة<br>
      آخر تحديث للأسعار <b class="n">{date.today().isoformat()}</b> · الخط الساخن <b>{STORE['hotline']}</b>
    </div>
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
        <span>اسأل البائع إمتى هيوصل، أو كلّمنا على {STORE['hotline']}</span>
      </div>
    </div>
    <div class="cta">
      <a class="main" href="https://cairosales.com/ar/">تصفّح موقعنا</a>
      <a class="alt" href="tel:{STORE['hotline']}">اتصل بنا {STORE['hotline']}</a>
    </div>
    <div class="note">الخط الساخن <b>{STORE['hotline']}</b> · آخر تحديث <b class="n">{date.today().isoformat()}</b></div>
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
