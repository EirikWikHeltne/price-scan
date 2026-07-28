"""Apotek1.no — sitemap URL discovery, requests price extraction, Playwright fallback."""
import re, time, requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from ._common import (
    extract_stock, code_variants, safe_url,
    extract_price_from_html, extract_price_from_page,
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


def _fetch_and_index(url, index, depth=0):
    if depth > 2:
        return
    try:
        r = requests.get(url, headers=_REQ_HEADERS, timeout=15)
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
                    _fetch_and_index(sub, index, depth + 1)
        else:
            _parse_sitemap_urls(text, index)
    except Exception as e:
        print(f"  [apotek1] sitemap error {url}: {e}")


def _build_sitemap_index():
    """Download Apotek1 sitemaps and return varenummer→URL dict."""
    index = {}
    print("  [apotek1] building URL index from sitemap...")
    _fetch_and_index(f"{BASE}/sitemap.xml", index)
    print(f"  [apotek1] sitemap: {len(index)} product URLs indexed")
    return index


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(products):
    results, resolved = [], {}

    # Step 1: build sitemap URL index (HTTP, no browser, bypasses bot protection)
    sitemap_index = _build_sitemap_index()

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

        for prod in products:
            url = prod.get("url_apotek1")

            # Resolve URL: DB cache → sitemap index → browser search.
            # Sitemap keys come from the URL slug, which may keep or drop
            # leading zeros ("051946" vs "51946"), so try every variant.
            variants = code_variants(prod["varenummer"])
            if not url:
                for code in variants:
                    url = sitemap_index.get(code)
                    if url:
                        resolved[prod["varenummer"]] = url
                        break

            if not url:
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
                    if href:
                        url = safe_url(href, BASE, ALLOWED_HOST)
                        if url:
                            resolved[prod["varenummer"]] = url
                    else:
                        print(f"  [apotek1] no search result for {prod['varenummer']}")
                    page.close()
                except Exception as e:
                    print(f"  [apotek1] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            if not url:
                print(f"  [apotek1] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            # Fetch price: try plain HTTP first (fast), fall back to Playwright
            pris = None
            lager = None
            try:
                r = requests.get(url, headers=_REQ_HEADERS, timeout=10)
                if r.status_code == 200:
                    pris = extract_price_from_html(r.text)
                    lager = extract_stock(r.text)
            except Exception as e:
                print(f"  [apotek1] requests error {prod['varenummer']}: {e}")

            # Playwright fallback if requests didn't get the price
            if pris is None:
                page = None
                try:
                    page = context.new_page()
                    page.goto(url, timeout=15000)
                    # Do NOT use networkidle — it times out on Apotek1
                    try:
                        page.wait_for_selector(
                            "script[type='application/ld+json'], [data-testid*='price'], [class*='Price']",
                            timeout=5000
                        )
                    except Exception:
                        pass  # Continue and attempt extraction anyway
                    pris = extract_price_from_page(page)
                    if lager is None:
                        lager = extract_stock(page.content())
                    page.close()
                except Exception as e:
                    print(f"  [apotek1] browser error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            print(f"  [apotek1] {prod['varenummer']}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        context.close()
        browser.close()
    return results, resolved
