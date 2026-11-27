"""Apotek1.no — sitemap URL discovery, requests price extraction, Playwright fallback."""
import re, time
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from ._common import (
    code_variants, due_for_lookup, safe_url, http_session,
    fetch_price_http, fetch_price_browser,
)

BUTIKK       = "apotek1"
BASE         = "https://www.apotek1.no"
ALLOWED_HOST = "www.apotek1.no"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_REQ_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}};
Object.defineProperty(navigator, 'languages', {get: () => ['nb-NO','nb','no','en-US','en']});
"""


# ---------------------------------------------------------------------------
# Sitemap-based URL discovery
# ---------------------------------------------------------------------------

def _parse_sitemap_urls(text, index):
    """Extract varenummer→URL pairs from sitemap XML text."""
    for url in re.findall(r'<loc>\s*(https?://[^\s<]+)\s*</loc>', text):
        m = re.search(r'-(\d{4,8})p/?$', url)
        if m:
            index[m.group(1)] = url


def _fetch_and_index(session, url, index, depth=0):
    if depth > 2:
        return
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        text = r.text
        if '<sitemapindex' in text or ('<sitemap>' in text and '<loc>' in text):
            # Sitemap index — recurse into sub-sitemaps (only trusted domain)
            sub_urls = re.findall(r'<loc>\s*(https?://[^\s<]+)\s*</loc>', text)
            for sub in sub_urls:
                host = urlparse(sub).netloc
                if host not in (ALLOWED_HOST, ALLOWED_HOST.removeprefix("www.")):
                    continue
                # Prefer product sitemaps; at depth 0 fetch all
                if depth == 0 or 'product' in sub.lower():
                    _fetch_and_index(session, sub, index, depth + 1)
        else:
            _parse_sitemap_urls(text, index)
    except Exception as e:
        print(f"  [apotek1] sitemap error {url}: {e}")


def _build_sitemap_index(session):
    """Download Apotek1 sitemaps and return varenummer→URL dict."""
    index = {}
    print("  [apotek1] building URL index from sitemap...")
    _fetch_and_index(session, f"{BASE}/sitemap.xml", index)
    print(f"  [apotek1] sitemap: {len(index)} product URLs indexed")
    return index


# ---------------------------------------------------------------------------
# URL resolution and price fetching
# ---------------------------------------------------------------------------

def _search_url_browser(context, varenummer, variants):
    """Find a product URL via the on-site search. Returns URL or None."""
    page = None
    try:
        page = context.new_page()
        href, fallback_href = None, None
        for code in variants:
            page.goto(f"{BASE}/search?q={quote(code)}", timeout=15000)
            try:
                page.wait_for_selector(
                    f"a[href$='-{code}p'], a[href*='/produkter/']", timeout=5000
                )
            except Exception:
                pass
            # The product URL may use any variant of the code,
            # regardless of which one the search was queried with.
            for v in variants:
                link = page.query_selector(f"a[href$='-{v}p']")
                if link:
                    href = link.get_attribute("href")
                    break
            if href:
                break
            if not fallback_href:
                link = page.query_selector("a[href*='/produkter/']")
                if link:
                    fallback_href = link.get_attribute("href")
        href = href or fallback_href
        if not href:
            print(f"  [apotek1] no search result for {varenummer}")
            return None
        return safe_url(href, BASE, ALLOWED_HOST)
    except Exception as e:
        print(f"  [apotek1] search error {varenummer}: {e}")
        return None
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


def _resolve_url(context, sitemap_index, varenummer, search=True):
    """Sitemap index → browser search (skipped when `search` is false).

    Sitemap keys come from the URL slug, which may keep or drop leading
    zeros ("051946" vs "51946"), so try every variant.
    """
    variants = code_variants(varenummer)
    for code in variants:
        url = sitemap_index.get(code)
        if url:
            return url
    if not search:
        return None
    return _search_url_browser(context, varenummer, variants)


def _fetch_price(context, session, url, varenummer):
    """Plain HTTP first (fast), Playwright fallback. Returns (pris, lager, gone)."""
    pris, lager = None, None
    try:
        pris, lager, gone = fetch_price_http(session, url)
        if gone:
            return None, None, True
    except Exception as e:
        print(f"  [apotek1] requests error {varenummer}: {e}")
    if pris is None:
        try:
            pris, browser_lager, gone = fetch_price_browser(
                context, url,
                "script[type='application/ld+json'], [data-testid*='price'], [class*='Price']",
            )
            if gone:
                return None, None, True
            if lager is None:
                lager = browser_lager
        except Exception as e:
            print(f"  [apotek1] browser error {varenummer}: {e}")
    return pris, lager, False


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(products):
    results, resolved = [], {}
    session = http_session(_REQ_HEADERS)

    # Step 1: build sitemap URL index (HTTP, no browser, bypasses bot protection)
    sitemap_index = _build_sitemap_index(session)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ]
        )
        context = browser.new_context(
            user_agent=_UA,
            locale="nb-NO",
            timezone_id="Europe/Oslo",
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,nn;q=0.7,en-US;q=0.6,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            }
        )
        context.add_init_script(_STEALTH)
        # Cap every Playwright call (query_selector, get_attribute, ...) —
        # the library default of 30s applies per call, and calls without an
        # explicit timeout have hung scrape runs for hours.
        context.set_default_timeout(15000)

        skipped = 0
        for prod in products:
            vn = prod["varenummer"]
            cached = prod.get("url_apotek1")
            url = cached
            if not url:
                # The sitemap lookup is free and done every run; the slow
                # on-site search only when the product is due for one.
                search = due_for_lookup(prod)
                url = _resolve_url(context, sitemap_index, vn, search=search)
                if url:
                    resolved[vn] = url
                elif not search:
                    skipped += 1
                    continue

            if not url:
                print(f"  [apotek1] no URL: {vn}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            pris, lager, gone = _fetch_price(context, session, url, vn)

            # A cached URL that now 404s means the product page moved:
            # resolve it afresh instead of returning no price forever.
            if gone and cached:
                print(f"  [apotek1] cached URL is gone for {vn}, re-resolving")
                fresh = _resolve_url(context, sitemap_index, vn)
                if fresh and fresh != cached:
                    resolved[vn] = fresh
                    pris, lager, _ = _fetch_price(context, session, fresh, vn)

            print(f"  [apotek1] {vn}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        if skipped:
            print(f"  [apotek1] {skipped} products without a known page not searched for on this run")
        context.close()
        browser.close()
    return results, resolved
