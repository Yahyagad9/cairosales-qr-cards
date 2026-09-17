# Cairo Sales QR cards

Printable product cards with QR codes for Cairo Sales Stores (أسواق القاهرة للمبيعات), plus a product database scraped from [cairosales.com](https://cairosales.com) for in-store product pages and an AI sales assistant.

## What's here

| Path | Purpose |
|---|---|
| `import_items.py` | Merge stock-list `.xls` exports from the store system into `data/items.csv` |
| `scrape_site.py` | Look up each item on cairosales.com and save prices, specs, images, description |
| `make_label.py` + `template.html` | Render an A6 card (PNG + print PDF) for an item code |
| `data/items.csv` | Store items: code, model, name, category, quantity, website link |
| `data/products.json` / `.csv` | Scraped website data per item |
| `assets/` | Logo and fonts (Cairo, Inter — SIL Open Font License) |

## Setup (macOS)

Requires Python 3 and Google Chrome.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```bash
# 1. Import stock lists exported from the store system
.venv/bin/python import_items.py "شاشات 15-9-2026.xls" "شفاط 15-9-2026.xls"

# 2. Scrape product data from the website (Chrome, one page at a time; ~30s per item)
.venv/bin/python scrape_site.py              # items not scraped yet
.venv/bin/python scrape_site.py --refresh    # re-download everything (new prices)

# 3. Make cards (output/label_<code>.png and .pdf)
.venv/bin/python make_label.py 101062465 101001133
```

## Notes

- cairosales.com is behind Cloudflare, which blocks plain HTTP clients, so pages are loaded with headless Chrome.
- The card's small QR code opens the product page on the website; the big QR code's content is still being designed.
