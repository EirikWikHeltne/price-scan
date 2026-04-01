"""Oda.com — JSON API search, requests price extraction, Playwright fallback."""
import re, time, json, requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

BUTIKK       = "oda"
BASE         = "https://oda.com"
API_BASE     = "https://oda.com/api/v1"
ALLOWED_HOST = "oda.com"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_REQ_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept": "application/json, text/html, */*;q=0.8",
}
_stealth = Stealth(
    navigator_languages_override=("nb-NO", "nb"),
    navigator_platform_override="Linux x86_64",
)


_api_available = True  # circuit breaker: skip API after first 403


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


def _safe_url(href):
    url = href if href.startswith("http") else BASE + href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, "www." + ALLOWED_HOST):
            return url
    except Exception:
        pass
    return None


def _search_url(query):
    """Search ODA API for a product, return product page URL if found."""
    global _api_available
    if not _api_available:
        return None
    try:
        r = requests.get(
            f"{API_BASE}/search/?q={quote(query)}",
            headers=_REQ_HEADERS, timeout=5
        )
        if r.status_code == 403:
            print("  [oda] API returned 403, disabling API calls")
            _api_available = False
            return None
        if r.status_code == 200:
            data = r.json()
            # Results may be nested under 'items' or 'results'
            items = data.get("items") or data.get("results") or []
            for entry in items:
                # Items can be wrapped: {"type": "oda-product", "item": {...}}
                item = entry.get("item", entry) if isinstance(entry, dict) else {}
                front_url = item.get("front_url", "")
                if front_url:
                    return _safe_url(front_url)
    except Exception:
        pass
    return None


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
    # Layer 2: __NEXT_DATA__
    next_match = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if next_match:
        try:
            nd = json.loads(next_match.group(1))
            props_str = json.dumps(nd)
            for pm in re.findall(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', props_str):
                val = float(pm.replace(",", "."))
                if 1 < val < 10000:
                    return val
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
    # Layer 2: __NEXT_DATA__
    next_data_el = page.query_selector("script#__NEXT_DATA__")
    if next_data_el:
        try:
            nd = json.loads(next_data_el.inner_text())
            props_str = json.dumps(nd)
            for pm in re.findall(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', props_str):
                val = float(pm.replace(",", "."))
                if 1 < val < 10000:
                    return val
        except Exception:
            pass
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
                val = float(m.group(1))
                if val > 0:
                    return val
    # Layer 4: CSS class selectors
    for sel in ["[class*='price']", "[class*='Price']", "[class*='pris']", "[class*='Pris']"]:
        el = page.query_selector(sel)
        if el:
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                val = float(m.group(1))
                if val > 0:
                    return val
    # Layer 5: regex on full page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', page.content())
    if m:
        try:
            pris = float(m.group(1).replace(",", "."))
            if pris > 0:
                return pris
        except Exception:
            pass
    return None


def _fetch_price_via_api(url):
    """Try to fetch price from ODA product API given a product page URL."""
    global _api_available
    if not _api_available:
        return None, None
    m = re.search(r'/products/(\d+)', url)
    if not m:
        return None, None
    pid = m.group(1)
    try:
        r = requests.get(
            f"{API_BASE}/products/{pid}/",
            headers=_REQ_HEADERS, timeout=5
        )
        if r.status_code == 403:
            print("  [oda] product API returned 403, disabling API calls")
            _api_available = False
            return None, None
        if r.status_code == 200:
            d = r.json()
            price_obj = d.get("current_price") or {}
            price_val = price_obj.get("price") if isinstance(price_obj, dict) else None
            if price_val:
                price_float = float(price_val)
                if price_float > 0:
                    return price_float, d.get("in_stock", True)
    except Exception:
        pass
    return None, None


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
            }
        )
        _stealth.apply_stealth_sync(context)

        for prod in products:
            url = prod.get("url_oda")

            # Resolve URL: DB cache → API search by varenummer → API search by EAN
            if not url:
                url = _search_url(prod["varenummer"])
                if not url and prod.get("ean"):
                    url = _search_url(prod["ean"])
                if url:
                    resolved[prod["varenummer"]] = url

            if not url:
                # Browser search fallback
                page = None
                try:
                    page = context.new_page()
                    # Try varenummer first, then product name
                    search_queries = [prod["varenummer"]]
                    if prod.get("produkt"):
                        search_queries.append(prod["produkt"])
                    for query in search_queries:
                        page.goto(
                            f"{BASE}/no/search/?q={quote(query)}",
                            timeout=15000
                        )
                        _dismiss_cookie_banner(page)
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        try:
                            page.wait_for_selector("a[href*='/no/products/']", timeout=8000)
                        except Exception:
                            pass
                        link = page.query_selector("a[href*='/no/products/']")
                        if link:
                            href = link.get_attribute("href")
                            url = _safe_url(href)
                            if url:
                                resolved[prod["varenummer"]] = url
                                break
                    page.close()
                except Exception as e:
                    print(f"  [oda] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            if not url:
                print(f"  [oda] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            # Fetch price: try API → HTTP → Playwright
            pris, lager = _fetch_price_via_api(url)

            if pris is None:
                try:
                    r = requests.get(url, headers=_REQ_HEADERS, timeout=10)
                    if r.status_code == 200:
                        pris = _extract_price_from_html(r.text)
                        lager = "på lager" in r.text.lower() or "in_stock" in r.text.lower()
                except Exception as e:
                    print(f"  [oda] requests error {prod['varenummer']}: {e}")

            if pris is None:
                page = None
                try:
                    page = context.new_page()
                    # Intercept API responses for price data
                    captured_price = {}
                    def _on_response(response):
                        try:
                            ct = response.headers.get("content-type", "")
                            if "json" in ct and response.status == 200:
                                body = response.text()
                                for pm in re.findall(r'"(?:price|gross_price|current_price)"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', body):
                                    val = float(pm.replace(",", "."))
                                    if 1 < val < 10000 and "price" not in captured_price:
                                        captured_price["price"] = val
                        except Exception:
                            pass
                    page.on("response", _on_response)
                    page.goto(url, timeout=15000)
                    _dismiss_cookie_banner(page)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    # Check intercepted API responses first
                    if "price" in captured_price:
                        pris = captured_price["price"]
                    else:
                        try:
                            page.wait_for_selector(
                                "script[type='application/ld+json'], script#__NEXT_DATA__, [data-testid*='price'], [class*='price']",
                                timeout=5000
                            )
                        except Exception:
                            pass
                        pris = _extract_price_from_page(page)
                    if lager is None:
                        lager = "på lager" in page.content().lower()
                    page.close()
                except Exception as e:
                    print(f"  [oda] browser error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            print(f"  [oda] {prod['varenummer']}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        context.close()
        browser.close()
    return results, resolved
