"""Apotera.no — Magento 2 store. HTTP-first with Playwright fallback."""
import re, time, json, requests
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup
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


# ---------------------------------------------------------------------------
# URL resolution via HTTP (Magento catalogsearch)
# ---------------------------------------------------------------------------

def _search_url_http(varenummer: str, produkt: str = "") -> str | None:
    """Search Apotera via Magento catalogsearch and find a product link."""
    # Try varenummer first (SKU match), then product name
    queries = [varenummer]
    if produkt:
        queries.append(produkt)

    for query in queries:
        try:
            r = requests.get(
                f"{BASE}/catalogsearch/result/?q={quote(query)}",
                headers=_REQ_HEADERS, timeout=12
            )
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")

            # Magento product list: look for product links in the results grid
            # Typical Magento selectors: .product-item a, .product-item-link
            for link in soup.select("a.product-item-link, .product-item a[href], .products-list a[href]"):
                href = link.get("href", "")
                url = _safe_url(href)
                if url and _is_product_url(url):
                    return url

            # Broader fallback: any link on the page that looks like a product
            for link in soup.find_all("a", href=True):
                href = link["href"]
                url = _safe_url(href)
                if url and _is_product_url(url):
                    return url
        except Exception as e:
            print(f"  [apotera] search HTTP error for {query}: {e}")
    return None


def _is_product_url(url: str) -> bool:
    """Heuristic: Apotera product URLs are clean slugs with multiple hyphenated words.
    They do NOT contain paths like /catalogsearch/, /customer/, /checkout/ etc."""
    path = urlparse(url).path.strip("/")
    if not path:
        return False
    # Reject known non-product paths
    non_product = {
        "catalogsearch", "customer", "checkout", "search", "sok",
        "om-apotera", "kontakt-oss", "personvern", "salgsbetingelser",
        "cookies", "privacy-policy-cookie-restriction-mode",
        "ofte-stilte-sporsmal", "frakt-og-levering", "retur-og-reklamasjon",
        "tips-og-rad", "kjop-reseptvare", "varemerker", "apotera-i-media",
    }
    segments = path.split("/")
    if segments[0] in non_product:
        return False
    # Product slugs are typically 4+ words separated by hyphens
    # e.g. "paracet-500-mg-tabletter-20-stk"
    if len(path) > 10 and "-" in path:
        return True
    return False


# ---------------------------------------------------------------------------
# Price extraction from HTML (Magento 2 patterns)
# ---------------------------------------------------------------------------

def _extract_price_from_html(html: str) -> float | None:
    """Extract price from Magento 2 server-rendered HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Layer 1: JSON-LD (most reliable)
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(tag.string or "")
            items = d if isinstance(d, list) else [d]
            for item in items:
                if not isinstance(item, dict):
                    continue
                offer = item.get("offers")
                if offer:
                    if isinstance(offer, list):
                        offer = offer[0]
                    pris = float(offer.get("price", 0)) or None
                    if pris and pris > 0:
                        return pris
        except Exception:
            pass

    # Layer 2: Magento data-price-amount attribute (very reliable)
    el = soup.find(attrs={"data-price-amount": True})
    if el:
        try:
            pris = float(el["data-price-amount"])
            if pris > 0:
                return pris
        except (ValueError, TypeError):
            pass

    # Layer 3: meta itemprop="price"
    meta = soup.find("meta", attrs={"itemprop": "price"})
    if meta and meta.get("content"):
        try:
            pris = float(meta["content"].replace(",", "."))
            if pris > 0:
                return pris
        except (ValueError, TypeError):
            pass

    # Layer 4: Magento price box CSS selectors
    for sel in [".price-box .price", "span.price", ".price-final_price .price"]:
        el = soup.select_one(sel)
        if el:
            raw = el.get_text().replace("kr", "").replace("\xa0", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                val = float(m.group(1))
                if val > 0:
                    return val

    # Layer 5: "price" key in page source (JSON embedded in scripts)
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', html)
    if m:
        try:
            pris = float(m.group(1).replace(",", "."))
            if pris > 0:
                return pris
        except Exception:
            pass

    return None


def _extract_stock_from_html(html: str) -> bool | None:
    """Check stock status from HTML."""
    lower = html.lower()
    if "på lager" in lower or "in stock" in lower or '"instock"' in lower:
        return True
    if "ikke på lager" in lower or "utsolgt" in lower or '"outofstock"' in lower:
        return False
    return None


# ---------------------------------------------------------------------------
# Playwright fallback for price extraction
# ---------------------------------------------------------------------------

def _extract_price_playwright(page) -> float | None:
    """Extract price from a Playwright-rendered Magento page."""
    # data-price-amount (Magento standard)
    dpa = page.query_selector("[data-price-amount]")
    if dpa:
        try:
            pris = float(dpa.get_attribute("data-price-amount"))
            if pris > 0:
                return pris
        except Exception:
            pass

    # meta itemprop="price"
    meta = page.query_selector("meta[itemprop='price']")
    if meta:
        content = meta.get_attribute("content")
        if content:
            try:
                pris = float(content.replace(",", "."))
                if pris > 0:
                    return pris
            except Exception:
                pass

    # JSON-LD
    for tag in page.query_selector_all("script[type='application/ld+json']"):
        try:
            d = json.loads(tag.inner_text())
            items = d if isinstance(d, list) else [d]
            for item in items:
                if not isinstance(item, dict):
                    continue
                offer = item.get("offers")
                if offer:
                    if isinstance(offer, list):
                        offer = offer[0]
                    pris = float(offer.get("price", 0)) or None
                    if pris and pris > 0:
                        return pris
        except Exception:
            pass

    # Price box CSS
    for sel in [".price-box .price", "span.price", ".price-final_price .price"]:
        el = page.query_selector(sel)
        if el:
            raw = el.inner_text().replace("kr", "").replace("\xa0", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                val = float(m.group(1))
                if val > 0:
                    return val

    return None


def _dismiss_cookie_banner(page):
    """Dismiss Magento cookie banner if present."""
    for selector in [
        "button:has-text('Aksepter')", "button:has-text('Godta')",
        "button:has-text('Godkjenn')", "button:has-text('OK')",
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


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(products):
    results, resolved = [], {}
    browser = None

    for prod in products:
        url = prod.get("url_apotera")

        # Step 1: Resolve URL via HTTP search (fast, no browser)
        if not url:
            url = _search_url_http(prod["varenummer"], prod.get("produkt", ""))
            if url:
                resolved[prod["varenummer"]] = url

        if not url:
            print(f"  [apotera] no URL: {prod['varenummer']}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
            continue

        # Step 2: Fetch price via HTTP first (Magento renders server-side)
        pris = None
        lager = None
        try:
            r = requests.get(url, headers=_REQ_HEADERS, timeout=12)
            if r.status_code == 200:
                pris = _extract_price_from_html(r.text)
                lager = _extract_stock_from_html(r.text)
        except Exception as e:
            print(f"  [apotera] HTTP error {prod['varenummer']}: {e}")

        # Step 3: Playwright fallback only if HTTP failed
        if pris is None:
            if browser is None:
                pw = sync_playwright().start()
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                           "--disable-dev-shm-usage"]
                )
                context = browser.new_context(
                    user_agent=_UA, locale="nb-NO", timezone_id="Europe/Oslo",
                    viewport={"width": 1920, "height": 1080},
                    extra_http_headers={"Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8"},
                )
                _stealth.apply_stealth_sync(context)

            page = None
            try:
                page = context.new_page()
                page.goto(url, timeout=15000)
                _dismiss_cookie_banner(page)
                try:
                    page.wait_for_selector(
                        "[data-price-amount], meta[itemprop='price'], span.price, "
                        "script[type='application/ld+json']",
                        timeout=6000
                    )
                except Exception:
                    pass
                pris = _extract_price_playwright(page)
                if lager is None:
                    content = page.content().lower()
                    if "på lager" in content:
                        lager = True
                    elif "utsolgt" in content:
                        lager = False
                page.close()
            except Exception as e:
                print(f"  [apotera] Playwright error {prod['varenummer']}: {e}")
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass

        print(f"  [apotera] {prod['varenummer']}: {pris}")
        results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.15)

    # Clean up browser only if it was started
    if browser:
        try:
            context.close()
            browser.close()
            pw.stop()
        except Exception:
            pass

    return results, resolved
