"""Farmasiet.no — SSR, prices via content attribute."""
import json, re, time
import requests
from bs4 import BeautifulSoup

BUTIKK = "farmasiet"
BASE   = "https://www.farmasiet.no"
HEADS  = {"User-Agent": "Mozilla/5.0", "Accept-Language": "nb-NO"}

def search_url(varenummer):
    try:
        r = requests.get(f"{BASE}/search?q={varenummer}", headers=HEADS, timeout=12)
        soup = BeautifulSoup(r.text, "lxml")
        # Product URLs end with ,{internal_id}
        for link in soup.find_all("a", href=re.compile(r",\d+$")):
            href = link["href"]
            return BASE + href if href.startswith("/") else href
    except Exception:
        pass
    return None

def fetch_price(url):
    try:
        r = requests.get(url, headers=HEADS, timeout=12)
        soup = BeautifulSoup(r.text, "lxml")
        # Primary: content attribute on price element
        el = soup.find(attrs={"data-testid": "product-page-default-price"})
        if el:
            content = el.get("content") or el.get("itemprop")
            try:
                pris = float(content)
                return pris, "på lager" in r.text.lower()
            except: pass
        # Fallback: JSON-LD
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "")
                if isinstance(d, dict) and "offers" in d:
                    price = float(d["offers"].get("price", 0)) or None
                    if price:
                        return price, "på lager" in r.text.lower()
            except: pass
        # Last resort: regex
        m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', r.text)
        price = float(m.group(1)) if m else None
        return price, "på lager" in r.text.lower()
    except Exception as e:
        print(f"  [farmasiet] error: {e}")
        return None, None

def run(products):
    results, resolved = [], {}
    for p in products:
        url = p.get("url_farmasiet")
        # Discard bad category URLs (no comma = not a product page)
        if url and not re.search(r",\d+$", url):
            url = None
        if not url:
            url = search_url(p["varenummer"])
        if not url:
            print(f"  [farmasiet] no URL: {p['varenummer']}")
            results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
            continue
        if not p.get("url_farmasiet") or not re.search(r",\d+$", p.get("url_farmasiet", "")):
            resolved[p["varenummer"]] = url
        pris, lager = fetch_price(url)
        print(f"  [farmasiet] {p['varenummer']}: {pris}")
        results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.5)
    return results, resolved
