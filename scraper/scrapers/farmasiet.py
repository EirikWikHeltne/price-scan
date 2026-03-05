"""Farmasiet.no — requests-first price extraction, Playwright fallback."""
import re, time, json, requests
from playwright.sync_api import sync_playwright

BUTIKK = "farmasiet"
BASE   = "https://www.farmasiet.no"

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
        except:
            pass
    # Layer 2: data-testid content attribute
    m = re.search(r'data-testid=["\'][^"\']*price[^"\']*["\'][^>]*content=["\']([0-9.]+)["\']', html, re.IGNORECASE)
    if not m:
        m = re.search(r'content=["\']([0-9.]+)["\'][^>]*data-testid=["\'][^"\']*price[^"\']*["\']', html, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except:
            pass
    # Layer 3: generic "price" key in page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', html)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except:
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
        except:
            pass
    # Layer 2: data-testid
    el = page.query_selector("[data-testid*='price']")
    if el:
        content = el.get_attribute("content")
        if content:
            try:
                pris = float(content)
                if pris:
                    return pris
            except:
                pass
        raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
        m = re.search(r"(\d+\.?\d*)", raw)
        if m:
            return float(m.group(1))
    # Layer 3: CSS class selectors
    for sel in ["[class*='price']", "[class*='Price']"]:
        el = page.query_selector(sel)
        if el:
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                return float(m.group(1))
    # Layer 4: regex on full source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', page.content())
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except:
            pass
    return None


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
                    page.goto(f"{BASE}/search?q={prod['varenummer']}", timeout=20000)
                    try:
                        page.wait_for_selector("a[href*='/catalog/']", timeout=8000)
                    except:
                        pass
                    for link in page.query_selector_all("a[href*='/catalog/']"):
                        href = link.get_attribute("href")
                        if _valid_product_url(href):
                            url = BASE + href if href.startswith("/") else href
                            resolved[prod["varenummer"]] = url
                            break
                    page.close()
                except Exception as e:
                    print(f"  [farmasiet] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except:
                            pass

            if not url:
                print(f"  [farmasiet] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            # Fetch price: try plain HTTP first (Farmasiet is server-rendered)
            pris = None
            lager = None
            try:
                r = requests.get(url, headers=_REQ_HEADERS, timeout=20)
                if r.status_code == 200:
                    pris = _extract_price_from_html(r.text)
                    lager = "på lager" in r.text.lower()
            except Exception as e:
                print(f"  [farmasiet] requests error {prod['varenummer']}: {e}")

            # Playwright fallback if requests didn't get the price
            if pris is None:
                page = None
                try:
                    page = context.new_page()
                    page.goto(url, timeout=20000)
                    # Do NOT use networkidle — it times out and skips extraction
                    try:
                        page.wait_for_selector(
                            "script[type='application/ld+json'], [data-testid*='price'], [class*='price']",
                            timeout=10000
                        )
                    except:
                        pass  # Continue and attempt extraction anyway
                    pris = _extract_price_from_page(page)
                    if lager is None:
                        lager = "på lager" in page.content().lower()
                    page.close()
                except Exception as e:
                    print(f"  [farmasiet] browser error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except:
                            pass

            print(f"  [farmasiet] {prod['varenummer']}: {pris}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
            time.sleep(0.3)

        context.close()
        browser.close()
    return results, resolved
