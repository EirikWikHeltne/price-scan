"""Boots.no — SSR, URL ends in -{varenummer}. No browser needed."""
import re, time
from bs4 import BeautifulSoup
from urllib.parse import quote
from ._common import (
    GONE_STATUSES, due_for_lookup, extract_stock, code_variants, safe_url,
    extract_jsonld_price, http_session,
)

BUTIKK       = "boots"
BASE         = "https://www.boots.no"
ALLOWED_HOST = "www.boots.no"
HEADS        = {"User-Agent": "Mozilla/5.0", "Accept-Language": "nb-NO"}


def search_url(session, varenummer):
    for code in code_variants(varenummer):
        try:
            r = session.get(f"{BASE}/catalogsearch/result/?q={quote(code)}", timeout=12)
            if r.status_code != 200:
                print(f"  [boots] search HTTP {r.status_code} for {code}")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            link = soup.find("a", href=re.compile(f"-{re.escape(code)}$"))
            if link:
                return safe_url(link["href"], BASE, ALLOWED_HOST)
        except Exception as e:
            print(f"  [boots] search error {code}: {e}")
    return None

def fetch_price(session, url):
    """Returns (pris, lager, gone); gone means the product page no longer exists."""
    try:
        r = session.get(url, timeout=12)
        if r.status_code != 200:
            # A 404/error page still contains prices (related products,
            # header promos) that the regex fallbacks below would pick up.
            print(f"  [boots] HTTP {r.status_code} for {url}")
            return None, None, r.status_code in GONE_STATUSES
        soup = BeautifulSoup(r.text, "lxml")
        lager = extract_stock(r.text)

        # Primary: JSON-LD
        price = extract_jsonld_price(r.text)
        if price:
            return price, lager, False

        # Fallback: search raw HTML for price pattern like "90,90" or "90.90"
        # Boots renders price as plain text near the product title
        m = re.search(r'(\d{2,4})[,.](\d{2})\s*(?:kr|,-|</)', r.text)
        if m:
            price = float(f"{m.group(1)}.{m.group(2)}")
            return price, lager, False

        # Last resort: any element with price-related class
        for sel in ["[class*='price']", "[class*='Price']", ".price", "span.price"]:
            el = soup.select_one(sel)
            if el:
                raw = re.sub(r'[^\d,.]', '', el.get_text().strip())
                raw = raw.replace(",", ".")
                m = re.search(r"(\d+\.?\d*)", raw)
                if m and float(m.group(1)) > 0:
                    return float(m.group(1)), lager, False

        # The page loaded, so the stock status is still worth keeping.
        return None, lager, False
    except Exception as e:
        print(f"  [boots] error: {e}")
        return None, None, False

def run(products):
    results, resolved = [], {}
    session = http_session(HEADS)
    skipped = 0
    for p in products:
        vn = p["varenummer"]
        cached = p.get("url_boots")
        if not cached and not due_for_lookup(p):
            # Not found on earlier runs; searched for again once per cycle.
            skipped += 1
            continue
        url = cached or search_url(session, vn)
        if not url:
            print(f"  [boots] no URL: {vn}")
            results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
            continue
        if not cached:
            resolved[vn] = url
        pris, lager, gone = fetch_price(session, url)
        # A cached URL that now 404s means the product page moved: search
        # for it afresh instead of returning no price forever.
        if gone and cached:
            fresh = search_url(session, vn)
            if fresh and fresh != cached:
                resolved[vn] = fresh
                pris, lager, _ = fetch_price(session, fresh)
        print(f"  [boots] {vn}: {pris}")
        results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.1)
    if skipped:
        print(f"  [boots] {skipped} products without a known page not searched for on this run")
    return results, resolved
