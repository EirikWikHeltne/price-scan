"""Farmasiet.no — requests-first price extraction, Playwright fallback."""
import re, time
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from ._common import (
    code_variants, due_for_lookup, safe_url, http_session,
    fetch_price_http, fetch_price_browser,
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


def _search_url_browser(context, varenummer):
    """Find a product URL via the on-site search. Returns URL or None."""
    page = None
    try:
        page = context.new_page()
        # Scan results per variant — a bare `goto` loop would only
        # ever examine the last variant's search page.
        for code in code_variants(varenummer):
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
                        return url
    except Exception as e:
        print(f"  [farmasiet] search error {varenummer}: {e}")
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
    return None


def _fetch_price(context, session, url, varenummer):
    """Plain HTTP first (Farmasiet is server-rendered), Playwright fallback.

    Returns (pris, lager, gone).
    """
    pris, lager = None, None
    try:
        pris, lager, gone = fetch_price_http(session, url)
        if gone:
            return None, None, True
    except Exception as e:
        print(f"  [farmasiet] requests error {varenummer}: {e}")
    if pris is None:
        try:
            pris, browser_lager, gone = fetch_price_browser(
                context, url,
                "script[type='application/ld+json'], [data-testid*='price'], [class*='price']",
                goto_timeout=12000,
            )
            if gone:
                return None, None, True
            if lager is None:
                lager = browser_lager
        except Exception as e:
            print(f"  [farmasiet] browser error {varenummer}: {e}")
    return pris, lager, False


def run(products):
    results, resolved = [], {}
    session = http_session(_REQ_HEADERS)
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

        skipped = 0
        for prod in products:
            vn = prod["varenummer"]
            cached = prod.get("url_farmasiet")
            # Discard bad category URLs (no comma+digits = not a product page)
            if not _valid_product_url(cached):
                cached = None
            if not cached and not due_for_lookup(prod):
                # Not found on earlier runs; searched for again once per cycle.
                skipped += 1
                continue

            url = cached
            if not url:
                url = _search_url_browser(context, vn)
                if url:
                    resolved[vn] = url

            if not url:
                print(f"  [farmasiet] no URL: {vn}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            pris, lager, gone = _fetch_price(context, session, url, vn)

            # A cached URL that now 404s means the product page moved:
            # search for it afresh instead of returning no price forever.
            if gone and cached:
                print(f"  [farmasiet] cached URL is gone for {vn}, re-resolving")
                fresh = _search_url_browser(context, vn)
                if fresh and fresh != cached:
                    resolved[vn] = fresh
                    pris, lager, _ = _fetch_price(context, session, fresh, vn)

            print(f"  [farmasiet] {vn}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        if skipped:
            print(f"  [farmasiet] {skipped} products without a known page not searched for on this run")
        context.close()
        browser.close()
    return results, resolved
