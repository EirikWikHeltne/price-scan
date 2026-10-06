"""Boots.no — SSR, URL ends in -{varenummer}. No browser needed."""
import re, time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from ._common import extract_stock, code_variants, safe_url, extract_jsonld_price

BUTIKK       = "boots"
BASE         = "https://www.boots.no"
ALLOWED_HOST = "www.boots.no"
HEADS        = {"User-Agent": "Mozilla/5.0", "Accept-Language": "nb-NO"}


def search_url(varenummer):
    for code in code_variants(varenummer):
        try:
            r = requests.get(
                f"{BASE}/catalogsearch/result/?q={quote(code)}", headers=HEADS, timeout=12
            )
            soup = BeautifulSoup(r.text, "lxml")
            link = soup.find("a", href=re.compile(f"-{code}$"))
            if link:
                return safe_url(link["href"], BASE, ALLOWED_HOST)
        except Exception:
            pass
    return None

def fetch_price(url):
    try:
        r = requests.get(url, headers=HEADS, timeout=12)
        if r.status_code != 200:
            # A 404/error page still contains prices (related products,
            # header promos) that the regex fallbacks below would pick up.
            print(f"  [boots] HTTP {r.status_code} for {url}")
            return None, None
        soup = BeautifulSoup(r.text, "lxml")
        lager = extract_stock(r.text)

        # Primary: JSON-LD
        price = extract_jsonld_price(r.text)
        if price:
            return price, lager

        # Fallback: search raw HTML for price pattern like "90,90" or "90.90"
        # Boots renders price as plain text near the product title
        m = re.search(r'(\d{2,4})[,.](\d{2})\s*(?:kr|,-|</)', r.text)
        if m:
            price = float(f"{m.group(1)}.{m.group(2)}")
            return price, lager

        # Last resort: any element with price-related class
        for sel in ["[class*='price']", "[class*='Price']", ".price", "span.price"]:
            el = soup.select_one(sel)
            if el:
                raw = re.sub(r'[^\d,.]', '', el.get_text().strip())
                raw = raw.replace(",", ".")
                m = re.search(r"(\d+\.?\d*)", raw)
                if m and float(m.group(1)) > 0:
                    return float(m.group(1)), lager

        return None, None
    except Exception as e:
        print(f"  [boots] error: {e}")
        return None, None

def run(products):
    results, resolved = [], {}
    for p in products:
        url = p.get("url_boots") or search_url(p["varenummer"])
        if not url:
            print(f"  [boots] no URL: {p['varenummer']}")
            results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
            continue
        if not p.get("url_boots"):
            resolved[p["varenummer"]] = url
        pris, lager = fetch_price(url)
        print(f"  [boots] {p['varenummer']}: {pris}")
        results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.1)
    return results, resolved
