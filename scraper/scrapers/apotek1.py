"""Apotek1.no — JS-rendered SPA, uses Playwright headless browser."""
import re, time, json
from playwright.sync_api import sync_playwright

BUTIKK = "apotek1"
BASE   = "https://www.apotek1.no"

def _browser(p):
    return p.chromium.launch(headless=True, args=["--no-sandbox"])

def search_url(varenummer):
    try:
        with sync_playwright() as p:
            b = _browser(p)
            page = b.new_page()
            page.goto(f"{BASE}/search?q={varenummer}", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
            link = page.query_selector("a[href*='/produkter/']")
            if link:
                href = link.get_attribute("href")
                b.close()
                return BASE + href if href.startswith("/") else href
            b.close()
    except Exception:
        pass
    return None

def fetch_price(url):
    try:
        with sync_playwright() as p:
            b = _browser(p)
            page = b.new_page()
            page.goto(url, timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
            pris = None
            for el in page.query_selector_all("script[type='application/ld+json']"):
                try:
                    d = json.loads(el.inner_text())
                    if isinstance(d, dict) and "offers" in d:
                        pris = float(d["offers"].get("price", 0)) or None
                        if pris:
                            break
                except Exception:
                    pass
            if not pris:
                for sel in ["[class*='price']","[class*='Price']","[data-testid*='price']",".price"]:
                    el = page.query_selector(sel)
                    if el:
                        raw = el.inner_text().replace("kr","").replace(",",".").strip()
                        m = re.search(r"(\d+\.?\d*)", raw)
                        if m:
                            pris = float(m.group(1))
                            break
            lager = "på lager" in page.content().lower()
            b.close()
            return pris, lager
    except Exception as e:
        print(f"  [apotek1] error: {e}")
        return None, None

def run(products):
    results, resolved = [], {}
    for p in products:
        url = p.get("url_apotek1") or search_url(p["varenummer"])
        if not url:
            print(f"  [apotek1] no URL: {p['varenummer']}")
            continue
        if not p.get("url_apotek1"):
            resolved[p["varenummer"]] = url
        pris, lager = fetch_price(url)
        print(f"  [apotek1] {p['varenummer']}: {pris}")
        results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(1)
    return results, resolved
