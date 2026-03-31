"""Meny.no — requests-first price extraction, Playwright fallback."""
import re, time, json, requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright

BUTIKK       = "meny"
BASE         = "https://meny.no"
ALLOWED_HOST = "meny.no"

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


def _safe_url(href):
    url = href if href.startswith("http") else BASE + href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, "www." + ALLOWED_HOST):
            return url
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
    # Layer 2: data-testid content attribute
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
    # Layer 2: data-testid
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
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        context.add_init_script(_STEALTH)

        for prod in products:
            url = prod.get("url_meny")

            # Resolve URL via browser search if not cached
            if not url:
                page = None
                try:
                    page = context.new_page()
                    # Try multiple search URL patterns
                    for search_url in [
                        f"{BASE}/search/?q={quote(prod['varenummer'])}",
                        f"{BASE}/search?q={quote(prod['varenummer'])}",
                        f"{BASE}/sok?q={quote(prod['varenummer'])}",
                    ]:
                        try:
                            resp = page.goto(search_url, timeout=10000)
                            if resp and resp.status < 400:
                                break
                        except Exception:
                            pass
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    # Broad scan: collect all hrefs and pick first that looks like a product page
                    all_links = page.query_selector_all("a[href]")
                    nav_skip = {"/", "/search", "/search/", "/sok", "/logg-inn", "/handlekurv", "/min-side"}
                    for link in all_links:
                        href = link.get_attribute("href") or ""
                        if not href or href in nav_skip or href.startswith("#"):
                            continue
                        candidate = _safe_url(href)
                        if not candidate:
                            continue
                        path = urlparse(candidate).path
                        segments = [s for s in path.strip("/").split("/") if s]
                        if len(segments) >= 2:
                            url = candidate
                            resolved[prod["varenummer"]] = url
                            break
                    if not url:
                        print(f"  [meny] search found no product link for {prod['varenummer']} (url={page.url})")
                    page.close()
                except Exception as e:
                    print(f"  [meny] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            if not url:
                print(f"  [meny] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            # Fetch price: try plain HTTP first, Playwright fallback
            pris = None
            lager = None
            try:
                r = requests.get(url, headers=_REQ_HEADERS, timeout=10)
                if r.status_code == 200:
                    pris = _extract_price_from_html(r.text)
                    lager = "på lager" in r.text.lower()
            except Exception as e:
                print(f"  [meny] requests error {prod['varenummer']}: {e}")

            if pris is None:
                page = None
                try:
                    page = context.new_page()
                    page.goto(url, timeout=12000)
                    try:
                        page.wait_for_selector(
                            "script[type='application/ld+json'], [data-testid*='price'], [class*='price']",
                            timeout=5000
                        )
                    except Exception:
                        pass
                    pris = _extract_price_from_page(page)
                    if lager is None:
                        lager = "på lager" in page.content().lower()
                    page.close()
                except Exception as e:
                    print(f"  [meny] browser error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass

            print(f"  [meny] {prod['varenummer']}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.1)

        context.close()
        browser.close()
    return results, resolved
