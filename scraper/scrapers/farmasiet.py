"""Farmasiet.no — requests-first price extraction, Playwright fallback."""
import re, time, requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from ._common import (
    extract_stock, code_variants, safe_url,
    extract_price_from_html, extract_price_from_page,
)

BUTIKK       = "farmasiet"
BASE         = "https://www.farmasiet.no"
ALLOWED_HOST = "www.farmasiet.no"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_REQ_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _valid_product_url(url):
    """Product pages end with ,{digits}."""
    return bool(url and re.search(r",\d+$", url))


def run(products):
    results, resolved = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=_UA,
            locale="nb-NO",
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        # Cap every Playwright call — the 30s library default applies per
        # call, and uncapped calls have hung scrape runs for hours.
        context.set_default_timeout(15000)

        for prod in products:
            url = prod.get("url_farmasiet")
            # Discard bad category URLs (no comma+digits = not a product page)
            if not _valid_product_url(url):
                url = None

            # Resolve URL via browser search if not cached
            if not url:
                page = None
                try:
                    page = context.new_page()
                    # Scan results per variant — a bare `goto` loop would only
                    # ever examine the last variant's search page.
                    for code in code_variants(prod["varenummer"]):
                        page.goto(f"{BASE}/search?q={quote(code)}", timeout=12000)
                        try:
                            page.wait_for_selector("a[href*='/catalog/']", timeout=8000)
                        except Exception:
                            pass
                        for link in page.query_selector_all("a[href*='/catalog/']"):
                            href = link.get_attribute("href")
                            if _valid_product_url(href):
                                url = safe_url(href, BASE, ALLOWED_HOST)
                                if url:
                                    resolved[prod["varenummer"]] = url
                                    break
                        if url:
                            break
                    page.close()
                except Exception as e:
                    print(f"  [farmasiet] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            if not url:
                print(f"  [farmasiet] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            # Fetch price: try plain HTTP first (Farmasiet is server-rendered)
            pris = None
            lager = None
            try:
                r = requests.get(url, headers=_REQ_HEADERS, timeout=10)
                if r.status_code == 200:
                    pris = extract_price_from_html(r.text)
                    lager = extract_stock(r.text)
            except Exception as e:
                print(f"  [farmasiet] requests error {prod['varenummer']}: {e}")

            # Playwright fallback if requests didn't get the price
            if pris is None:
                page = None
                try:
                    page = context.new_page()
                    page.goto(url, timeout=12000)
                    # Do NOT use networkidle — it times out and skips extraction
                    try:
                        page.wait_for_selector(
                            "script[type='application/ld+json'], [data-testid*='price'], [class*='price']",
                            timeout=5000
                        )
                    except Exception:
                        pass  # Continue and attempt extraction anyway
                    pris = extract_price_from_page(page)
                    if lager is None:
                        lager = extract_stock(page.content())
                    page.close()
                except Exception as e:
                    print(f"  [farmasiet] browser error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            print(f"  [farmasiet] {prod['varenummer']}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        context.close()
        browser.close()
    return results, resolved
