"""Apotera.no — Playwright-based price extraction."""
import re, time, json, requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

BUTIKK       = "apotera"
BASE         = "https://www.apotera.no"
ALLOWED_HOST = "www.apotera.no"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_REQ_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_stealth = Stealth(
    navigator_languages_override=("nb-NO", "nb"),
    navigator_platform_override="Linux x86_64",
)


def _safe_url(href):
    url = BASE + href if href.startswith("/") else href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, ALLOWED_HOST.removeprefix("www.")):
            return url
    except Exception:
        pass
    return None


def _dismiss_cookie_banner(page):
    """Try to dismiss cookie consent banner if present."""
    for selector in [
        "button:has-text('Aksepter')", "button:has-text('Godta')",
        "button:has-text('Godkjenn')", "button:has-text('Accept')",
        "button:has-text('OK')", "button:has-text('Tillat')",
        "[id*='cookie'] button", "[class*='cookie'] button",
        "[id*='consent'] button", "[class*='consent'] button",
    ]:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(500)
                return
        except Exception:
            pass


def _extract_price_from_html(html):
    """Extract price from server-rendered HTML."""
    # Layer 1: JSON-LD
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
    # Layer 2: Magento meta itemprop="price"
    m = re.search(r'itemprop=["\']price["\'][^>]*content=["\']([0-9.,]+)["\']', html, re.IGNORECASE)
    if not m:
        m = re.search(r'content=["\']([0-9.,]+)["\'][^>]*itemprop=["\']price["\']', html, re.IGNORECASE)
    if m:
        try:
            pris = float(m.group(1).replace(",", "."))
            if pris > 0:
                return pris
        except Exception:
            pass
    # Layer 2b: Magento data-price-amount
    m = re.search(r'data-price-amount=["\']([0-9.,]+)["\']', html)
    if m:
        try:
            pris = float(m.group(1).replace(",", "."))
            if pris > 0:
                return pris
        except Exception:
            pass
    # Layer 3: data-testid content attribute
    m = re.search(
        r'data-testid=["\'][^"\']*price[^"\']*["\'][^>]*content=["\']([0-9.]+)["\']',
        html, re.IGNORECASE
    )
    if not m:
        m = re.search(
            r'content=["\']([0-9.]+)["\'][^>]*data-testid=["\'][^"\']*price[^"\']*["\']',
            html, re.IGNORECASE
        )
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    # Layer 3: generic "price" key in page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', html)
    if m:
        try:
            pris = float(m.group(1).replace(",", "."))
            if pris > 0:
                return pris
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
    # Layer 2: Magento price selectors
    # meta itemprop="price"
    meta_price = page.query_selector("meta[itemprop='price']")
    if meta_price:
        content = meta_price.get_attribute("content")
        if content:
            try:
                pris = float(content.replace(",", "."))
                if pris > 0:
                    return pris
            except Exception:
                pass
    # data-price-amount attribute (Magento price wrapper)
    dpa = page.query_selector("[data-price-amount]")
    if dpa:
        try:
            pris = float(dpa.get_attribute("data-price-amount"))
            if pris > 0:
                return pris
        except Exception:
            pass
    # .price-box .price or span.price (Magento default)
    for sel in [".price-box .price", "span.price", ".price-final_price .price"]:
        el = page.query_selector(sel)
        if el:
            raw = el.inner_text().replace("kr", "").replace("\xa0", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                val = float(m.group(1))
                if val > 0:
                    return val
    # Layer 3: data-testid
    for sel in ["[data-testid*='price']", "[data-testid*='Price']"]:
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
    # Layer 4: regex on full page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', page.content())
    if m:
        try:
            pris = float(m.group(1).replace(",", "."))
            if pris > 0:
                return pris
        except Exception:
            pass
    return None


def run(products):
    results, resolved = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            user_agent=_UA,
            locale="nb-NO",
            timezone_id="Europe/Oslo",
            viewport={"width": 1920, "height": 1080},
            screen={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        _stealth.apply_stealth_sync(context)

        for prod in products:
            url = prod.get("url_apotera")

            # Resolve URL via browser search if not cached
            if not url:
                page = None
                try:
                    page = context.new_page()
                    # Try multiple search URL patterns and query terms
                    search_queries = [prod["varenummer"]]
                    if prod.get("produkt"):
                        search_queries.append(prod["produkt"])
                    found = False
                    for query in search_queries:
                        if found:
                            break
                        for search_url in [
                            f"{BASE}/sok?q={quote(query)}",
                            f"{BASE}/search?q={quote(query)}",
                            f"{BASE}/catalogsearch/result/?q={quote(query)}",
                        ]:
                            try:
                                resp = page.goto(search_url, timeout=12000)
                                if resp and resp.status < 400:
                                    found = True
                                    break
                            except Exception:
                                pass
                    _dismiss_cookie_banner(page)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    # Broad scan: collect all hrefs and pick first that looks like a product page
                    all_links = page.query_selector_all("a[href]")
                    nav_skip = {
                        "/", "/search", "/search/", "/sok", "/logg-inn", "/handlekurv",
                        "/om-oss", "/kontakt", "/vilkar", "/personvern", "/cookies",
                        "/kundeservice", "/faq", "/frakt", "/retur", "/min-side",
                        "/kampanjer", "/tilbud", "/kategorier", "/merker",
                    }
                    nav_prefixes = {"kategori", "merke", "brand", "category", "info", "hjelp", "help", "sok", "search"}
                    for link in all_links:
                        href = link.get_attribute("href") or ""
                        # Skip nav/utility links
                        if not href or href in nav_skip or href.startswith("#") or href.startswith("javascript:"):
                            continue
                        candidate = _safe_url(href)
                        if not candidate:
                            continue
                        path = urlparse(candidate).path
                        segments = [s for s in path.strip("/").split("/") if s]
                        if not segments:
                            continue
                        # Skip known non-product prefixes
                        if segments[0].lower() in nav_prefixes:
                            continue
                        # Accept product-like paths (1+ segments with a slug)
                        if len(segments) >= 1 and len(segments[0]) > 5:
                            url = candidate
                            resolved[prod["varenummer"]] = url
                            break
                    if not url:
                        print(f"  [apotera] search found no product link for {prod['varenummer']} (url={page.url})")
                    page.close()
                except Exception as e:
                    print(f"  [apotera] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            if not url:
                print(f"  [apotera] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            # Fetch price via Playwright (Apotera blocks plain HTTP with 403)
            pris = None
            lager = None
            page = None
            try:
                page = context.new_page()
                page.goto(url, timeout=15000)
                _dismiss_cookie_banner(page)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                try:
                    page.wait_for_selector(
                        "script[type='application/ld+json'], [data-testid*='price'], [class*='price'], [class*='pris']",
                        timeout=5000
                    )
                except Exception:
                    pass
                pris = _extract_price_from_page(page)
                lager = "på lager" in page.content().lower()
                page.close()
            except Exception as e:
                print(f"  [apotera] browser error {prod['varenummer']}: {e}")
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass

            print(f"  [apotera] {prod['varenummer']}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        context.close()
        browser.close()
    return results, resolved
