"""Print-ready A5 entrance sign: join the branch Wi-Fi, then browse the catalogue.

Usage:
  python make_sign.py --ssid "CairoSales" --password "secret123"
  python make_sign.py --ssid "CairoSales" --open        # network with no password

Two QR codes: the first joins the Wi-Fi (phone cameras understand the WIFI: format),
the second opens the product index. Output: output/sign_wifi.png and .pdf
"""
import argparse
import subprocess
from pathlib import Path

import pymupdf

import build_pages
import make_label

ROOT = Path(__file__).parent
OUT = ROOT / "output"
CHROME = make_label.CHROME


def wifi_payload(ssid, password, hidden=False):
    """WIFI:T:WPA;S:<ssid>;P:<password>;; — the format iPhone and Android cameras read."""
    def esc(v):
        for ch in "\\;,:\"":
            v = v.replace(ch, "\\" + ch)
        return v
    security = "WPA" if password else "nopass"
    parts = [f"T:{security}", f"S:{esc(ssid)}"]
    if password:
        parts.append(f"P:{esc(password)}")
    if hidden:
        parts.append("H:true")
    return "WIFI:" + ";".join(parts) + ";;"


def html_page(ssid, password, hidden):
    wifi_qr = make_label.qr_svg(wifi_payload(ssid, password, hidden), logo_hole=False)
    site_qr = make_label.qr_svg(f"{build_pages.SITE_BASE}/", logo_hole=False)
    store = build_pages.STORE
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<style>
  @font-face {{ font-family: "Cairo"; src: url("assets/fonts/Cairo.ttf"); font-weight: 200 1000; }}
  @font-face {{ font-family: "Inter"; src: url("assets/fonts/Inter.ttf"); font-weight: 100 900; }}
  @font-face {{ font-family: "Naskh"; src: url("assets/fonts/NotoNaskhArabic.ttf"); font-weight: 400 700; }}
  @page {{ size: 148mm 210mm; margin: 0; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 148mm; height: 210mm; background: #F0EEE6; color: #141413;
    font-family: "Cairo", sans-serif; -webkit-print-color-adjust: exact; print-color-adjust: exact;
    display: flex; flex-direction: column; align-items: center; padding: 12mm 10mm;
  }}
  .n {{ font-family: "Inter", sans-serif; direction: ltr; unicode-bidi: isolate; }}
  .logo {{ width: 22mm; height: 22mm; border-radius: 50%; }}
  h1 {{ font-family: "Naskh", serif; font-size: 11mm; font-weight: 700; margin-top: 5mm; text-align: center; line-height: 1.4; }}
  .sub {{ font-size: 4mm; font-weight: 600; color: #6E6B64; margin-top: 2mm; text-align: center; }}
  .steps {{ display: flex; gap: 5mm; margin-top: 8mm; width: 100%; }}
  .step {{
    flex: 1; background: #FAF9F5; border: .4mm solid #E3E0D6; border-radius: 6mm;
    padding: 5mm 4mm; text-align: center;
  }}
  .num {{
    width: 8mm; height: 8mm; border-radius: 50%; background: #D97757; color: #fff;
    font-family: "Inter"; font-weight: 800; font-size: 4.4mm;
    display: flex; align-items: center; justify-content: center; margin: 0 auto 3mm;
  }}
  .step h2 {{ font-size: 4.6mm; font-weight: 800; }}
  .step p {{ font-size: 3.4mm; font-weight: 600; color: #6E6B64; margin-top: 1.5mm; line-height: 1.6; }}
  .qr {{ width: 40mm; height: 40mm; margin: 4mm auto 0; display: block; }}
  .creds {{ margin-top: 3mm; font-size: 3.4mm; font-weight: 700; color: #3D3D3A; }}
  .creds span {{ color: #6E6B64; font-weight: 600; }}
  .foot {{
    margin-top: auto; width: 100%; border-top: .4mm solid #E3E0D6; padding-top: 4mm;
    display: flex; align-items: center; justify-content: space-between; font-size: 3.4mm;
    font-weight: 700; color: #6E6B64;
  }}
  .foot b {{ color: #141413; }}
</style>
</head>
<body>
  <img class="logo" src="assets/logo.jpeg" alt="">
  <h1>اعرف كل حاجة عن أي منتج<br>من موبايلك</h1>
  <div class="sub">امسح الكود اللي على المنتج تشوف السعر والمواصفات والمقارنة</div>

  <div class="steps">
    <div class="step">
      <div class="num">١</div>
      <h2>اتصل بالواي فاي</h2>
      <p>امسح الكود ده بالكاميرا</p>
      {wifi_qr}
      <div class="creds">الشبكة <span class="n">{ssid}</span>{f'<br>الباسورد <span class="n">{password}</span>' if password else '<br><span>من غير باسورد</span>'}</div>
    </div>
    <div class="step">
      <div class="num">٢</div>
      <h2>افتح المنتجات</h2>
      <p>كل الأصناف بأسعار النهاردة</p>
      {site_qr}
      <div class="creds"><span>أو امسح الكود اللي على المنتج نفسه</span></div>
    </div>
  </div>

  <div class="foot">
    <span>{store['name']} · {store['branch']}</span>
    <span>الخط الساخن <b class="n">{store['hotline']}</b></span>
  </div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ssid", required=True, help="Wi-Fi network name")
    ap.add_argument("--password", default="", help="Wi-Fi password")
    ap.add_argument("--open", action="store_true", help="network has no password")
    ap.add_argument("--hidden", action="store_true", help="network does not broadcast its name")
    args = ap.parse_args()
    password = "" if args.open else args.password

    OUT.mkdir(exist_ok=True)
    page = ROOT / ".render_sign.html"
    page.write_text(html_page(args.ssid, password, args.hidden), encoding="utf-8")
    pdf, png = OUT / "sign_wifi.pdf", OUT / "sign_wifi.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=3000",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}", page.resolve().as_uri()],
                   check=True, capture_output=True)
    page.unlink()
    with pymupdf.open(pdf) as doc:
        doc[0].get_pixmap(dpi=300).save(png)
    print(png)
    print(pdf)


if __name__ == "__main__":
    main()
