"""Vitusapotek.no — single browser session for all products."""
import re, time, json
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from ._common import extract_stock, code_variants

BUTIKK       = "vitusapotek"
BASE         = "https://www.vitusapotek.no"
ALLOWED_HOST = "www.vitusapotek.no"


def _safe_url(href):
    """Return absolute URL only if it resolves to the expected host."""
    url = BASE + href if href.startswith("/") else href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, ALLOWED_HOST.removeprefix("www.")):
            return url
    except Exception:
        pass
    return None

def run(products):
    results, resolved = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="nb-NO",
        )
        for prod in products:
            url = prod.get("url_vitusapotek")
            if not url:
                page = None
                try:
                    page = context.new_page()
                    for code in code_variants(prod["varenummer"]):
                        page.goto(f"{BASE}/search?q={quote(code)}", timeout=12000)
                        # Do NOT use networkidle — wrap any wait in try/except
                        try:
                            page.wait_for_selector("a[href*='/p/']", timeout=8000)
                        except Exception:
                            pass
                        link = page.query_selector("a[href*='/p/']")
                        if link:
                            href = link.get_attribute("href")
                            url = _safe_url(href)
                            if url:
                                resolved[prod["varenummer"]] = url
                                break
                    if not url:
                        page.close()
                        page = None
                        raise Exception("no search result")
                    page.close()
                except Exception as e:
                    print(f"  [vitusapotek] search error {prod['varenummer']}: {e}")
                    if page:
                        try: page.close()
                        except Exception: pass
            if not url:
                print(f"  [vitusapotek] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue
            page = None
            try:
                page = context.new_page()
                page.goto(url, timeout=12000)
                # Do NOT use networkidle — it times out and skips extraction
                try:
                    page.wait_for_selector(
                        "script[type='application/ld+json'], [class*='price'], [class*='Price']",
                        timeout=5000
                    )
                except Exception:
                    pass  # Continue and attempt extraction anyway
                pris = None
                for el in page.query_selector_all("script[type='application/ld+json']"):
                    try:
                        d = json.loads(el.inner_text())
                        if isinstance(d, dict) and "offers" in d:
                            pris = float(d["offers"].get("price", 0)) or None
                            if pris: break
                    except Exception: pass
                if not pris:
                    for sel in ["[class*='price']","[class*='Price']","[data-testid*='price']"]:
                        el = page.query_selector(sel)
                        if el:
                            raw = el.inner_text().replace("kr","").replace(",",".").strip()
                            m = re.search(r"(\d+\.?\d*)", raw)
                            if m:
                                pris = float(m.group(1))
                                break
                lager = extract_stock(page.content())
                page.close()
                print(f"  [vitusapotek] {prod['varenummer']}: {pris}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
                time.sleep(0.1)
            except Exception as e:
                print(f"  [vitusapotek] error {prod['varenummer']}: {e}")
                if page:
                    try: page.close()
                    except Exception: pass
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
        context.close()
        browser.close()
    return results, resolved
