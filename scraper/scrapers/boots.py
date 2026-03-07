"""Boots.no — SSR, URL ends in -{varenummer}. No browser needed."""
import json, re, time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse

BUTIKK       = "boots"
BASE         = "https://www.boots.no"
ALLOWED_HOST = "www.boots.no"
HEADS        = {"User-Agent": "Mozilla/5.0", "Accept-Language": "nb-NO"}


def _safe_url(href):
    """Return absolute URL only if it resolves to the expected host."""
    url = href if href.startswith("http") else BASE + href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, ALLOWED_HOST.removeprefix("www.")):
            return url
    except Exception:
        pass
    return None


def search_url(varenummer):
    try:
        r = requests.get(
            f"{BASE}/catalogsearch/result/?q={quote(varenummer)}", headers=HEADS, timeout=12
        )
        soup = BeautifulSoup(r.text, "lxml")
        link = soup.find("a", href=re.compile(f"-{varenummer}$"))
        if link:
            return _safe_url(link["href"])
    except Exception:
        pass
    return None

def fetch_price(url):
    try:
        r = requests.get(url, headers=HEADS, timeout=12)
        soup = BeautifulSoup(r.text, "lxml")

        # Primary: JSON-LD
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "")
                if isinstance(d, dict) and "offers" in d:
                    price = float(d["offers"].get("price", 0)) or None
                    if price:
                        return price, "på lager" in r.text.lower()
            except Exception:
                pass

        # Fallback: search raw HTML for price pattern like "90,90" or "90.90"
        # Boots renders price as plain text near the product title
        m = re.search(r'(\d{2,4})[,.](\d{2})\s*(?:kr|,-|</)', r.text)
        if m:
            price = float(f"{m.group(1)}.{m.group(2)}")
            return price, "på lager" in r.text.lower()

        # Last resort: any element with price-related class
        for sel in ["[class*='price']", "[class*='Price']", ".price", "span.price"]:
            el = soup.select_one(sel)
            if el:
                raw = re.sub(r'[^\d,.]', '', el.get_text().strip())
                raw = raw.replace(",", ".")
                m = re.search(r"(\d+\.?\d*)", raw)
                if m and float(m.group(1)) > 0:
                    return float(m.group(1)), "på lager" in r.text.lower()

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
            continue
        if not p.get("url_boots"):
            resolved[p["varenummer"]] = url
        pris, lager = fetch_price(url)
        print(f"  [boots] {p['varenummer']}: {pris}")
        results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.5)
    return results, resolved
