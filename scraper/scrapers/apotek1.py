"""Apotek1.no — sitemap URL discovery, requests price extraction, Playwright fallback."""
import re, time, json, requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright

BUTIKK       = "apotek1"
BASE         = "https://www.apotek1.no"
ALLOWED_HOST = "www.apotek1.no"


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
        r = requests.get(url, headers=_REQ_HEADERS, timeout=30)
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
# Price extraction helpers
# ---------------------------------------------------------------------------

def _extract_price_from_html(html):
    """Try to extract price from server-rendered HTML (no JS required)."""
    # JSON-LD blocks
    for block in re.findall(
        r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        try:
            d = json.loads(block)
            for item in (d if isinstance(d, list) else [d]):
                if not isinstance(item, dict):
                    continue
                offer = item.get("offers")
                if offer:
                    if isinstance(offer, list):
                        offer = offer[0]
                    pris = float(offer.get("price", 0)) or None
                    if pris:
                        return pris
        except Exception:
            pass
    # Generic "price" key anywhere in page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', html)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            pass
    return None


def _extract_price_from_page(page):
    """Extract price from a rendered Playwright page."""
    # Layer 1: JSON-LD
    for tag in page.query_selector_all("script[type='application/ld+json']"):
        try:
            d = json.loads(tag.inner_text())
            for item in (d if isinstance(d, list) else [d]):
                if not isinstance(item, dict):
                    continue
                offer = item.get("offers")
                if offer:
                    if isinstance(offer, list):
                        offer = offer[0]
                    pris = float(offer.get("price", 0)) or None
                    if pris:
                        return pris
        except Exception:
            pass
    # Layer 2: data-testid
    for sel in ["[data-testid='price']", "[data-testid*='price']", "[data-testid*='Price']"]:
        el = page.query_selector(sel)
        if el:
            content = el.get_attribute("content")
            if content:
                try:
                    pris = float(content)
                    if pris:
                        return pris
                except Exception:
                    pass
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                return float(m.group(1))
    # Layer 3: CSS class selectors
    for sel in ["[class*='price']", "[class*='Price']", "[class*='pris']", "[class*='Pris']"]:
        el = page.query_selector(sel)
        if el:
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                return float(m.group(1))
    # Layer 4: Regex on full page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', page.content())
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            pass
    return None


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

        for prod in products:
            url = prod.get("url_apotek1")

            # Resolve URL: DB cache → sitemap index → browser search
            if not url:
                url = sitemap_index.get(prod["varenummer"])
                if url:
                    resolved[prod["varenummer"]] = url

            if not url:
                page = None
                try:
                    page = context.new_page()
                    page.goto(f"{BASE}/search?q={quote(prod['varenummer'])}", timeout=30000)
                    try:
                        page.wait_for_selector(
                            f"a[href$='-{prod['varenummer']}p']", timeout=10000
                        )
                    except Exception:
                        try:
                            page.wait_for_selector("a[href*='/produkter/']", timeout=5000)
                        except Exception:
                            pass
                    link = page.query_selector(f"a[href$='-{prod['varenummer']}p']")
                    if not link:
                        link = page.query_selector("a[href*='/produkter/']")
                    if link:
                        href = link.get_attribute("href")
                        url = _safe_url(href)
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
                r = requests.get(url, headers=_REQ_HEADERS, timeout=20)
                if r.status_code == 200:
                    pris = _extract_price_from_html(r.text)
                    lager = "på lager" in r.text.lower()
            except Exception as e:
                print(f"  [apotek1] requests error {prod['varenummer']}: {e}")

            # Playwright fallback if requests didn't get the price
            if pris is None:
                page = None
                try:
                    page = context.new_page()
                    page.goto(url, timeout=30000)
                    # Do NOT use networkidle — it times out on Apotek1
                    try:
                        page.wait_for_selector(
                            "script[type='application/ld+json'], [data-testid*='price'], [class*='Price']",
                            timeout=15000
                        )
                    except Exception:
                        pass  # Continue and attempt extraction anyway
                    pris = _extract_price_from_page(page)
                    if lager is None:
                        lager = "på lager" in page.content().lower()
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
            time.sleep(0.3)

        context.close()
        browser.close()
    return results, resolved
