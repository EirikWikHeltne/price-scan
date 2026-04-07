"""Oda.com — Next.js CSR grocery store. API + Playwright with response interception."""
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


def _safe_url(href):
    url = href if href.startswith("http") else BASE + href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, "www." + ALLOWED_HOST):
            return url
    except Exception:
        pass
    return None


def _dismiss_cookie_banner(page):
    for selector in [
        "button:has-text('Aksepter')", "button:has-text('Godta')",
        "button:has-text('Accept')", "button:has-text('OK')",
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


def _extract_oda_product_id(url: str) -> str | None:
    """Extract Oda's internal product ID from a product URL.
    URLs look like: /no/products/1125-paracet-paracet-mikstur-24-mg-ml/"""
    m = re.search(r'/products/(\d+)', url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# API-based search and price fetching (fast path, may be blocked)
# ---------------------------------------------------------------------------

def _search_url_api(query: str) -> str | None:
    """Search Oda API. Returns product URL or None. Does NOT throw on 403."""
    try:
        r = requests.get(
            f"{API_BASE}/search/?q={quote(query)}",
            headers=_REQ_HEADERS, timeout=5
        )
        if r.status_code != 200:
            return None
        data = r.json()
        items = data.get("items") or data.get("results") or []
        for entry in items:
            item = entry.get("item", entry) if isinstance(entry, dict) else {}
            front_url = item.get("front_url", "")
            if front_url:
                return _safe_url(front_url)
    except Exception:
        pass
    return None


def _fetch_price_api(url: str) -> tuple[float | None, bool | None]:
    """Fetch price via Oda product API. Returns (price, in_stock)."""
    pid = _extract_oda_product_id(url)
    if not pid:
        return None, None
    try:
        r = requests.get(
            f"{API_BASE}/products/{pid}/",
            headers=_REQ_HEADERS, timeout=5
        )
        if r.status_code != 200:
            return None, None
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


# ---------------------------------------------------------------------------
# Playwright-based search (fallback when API is blocked)
# ---------------------------------------------------------------------------

def _search_url_browser(context, prod: dict) -> str | None:
    """Search for a product on Oda using the browser. Returns URL or None."""
    # Build search queries: product name is much more effective than varenummer
    # since Oda uses its own internal IDs
    queries = []
    if prod.get("merke") and prod.get("produkt"):
        # e.g. "Paracet tabletter 500mg" — clean up the coded product name
        name = prod["produkt"]
        # Simplify coded names: "TAB 500MG 20ENPAC" → "tabletter 500mg"
        name = re.sub(r'\b(\d+)ENPAC\b', '', name)
        name = name.replace("TAB ", "tabletter ").replace("KAPS ", "kapsler ")
        name = name.replace("SUPP ", "stikkpille ").replace("BRUSETA ", "brusetabletter ")
        name = name.replace("MIKSTUR ", "mikstur ").replace("SMELTAB ", "smeltetabletter ")
        queries.append(f"{prod['merke']} {name}".strip())
    if prod.get("merke"):
        queries.append(prod["merke"])
    queries.append(prod["varenummer"])

    page = None
    try:
        page = context.new_page()
        for query in queries:
            try:
                page.goto(
                    f"{BASE}/no/search/?q={quote(query)}",
                    timeout=15000
                )
                _dismiss_cookie_banner(page)
                try:
                    page.wait_for_selector("a[href*='/no/products/']", timeout=8000)
                except Exception:
                    pass
                link = page.query_selector("a[href*='/no/products/']")
                if link:
                    href = link.get_attribute("href")
                    url = _safe_url(href)
                    if url:
                        page.close()
                        return url
            except Exception:
                pass
        page.close()
    except Exception as e:
        print(f"  [oda] browser search error {prod['varenummer']}: {e}")
        if page:
            try:
                page.close()
            except Exception:
                pass
    return None


# ---------------------------------------------------------------------------
# Playwright-based price extraction with response interception
# ---------------------------------------------------------------------------

def _fetch_price_browser(context, url: str) -> tuple[float | None, bool | None]:
    """Fetch price by loading the page in Playwright and intercepting API calls."""
    pris = None
    lager = None
    page = None
    try:
        page = context.new_page()

        # Intercept XHR/fetch responses — Oda's Next.js app makes API calls
        # that return product data including prices
        captured = {}

        def _on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "json" not in ct or response.status != 200:
                    return
                resp_url = response.url
                # Only process product-related API responses
                if "/products/" not in resp_url and "/search/" not in resp_url:
                    return
                body = response.text()
                # Look for price patterns in the JSON
                for pm in re.findall(
                    r'"(?:price|gross_price)"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', body
                ):
                    val = float(pm.replace(",", "."))
                    if 1 < val < 50000 and "price" not in captured:
                        captured["price"] = val
                # Check stock
                if '"availability":"' in body:
                    if '"availability":"in_stock"' in body.lower() or '"in_stock":true' in body.lower():
                        captured["stock"] = True
                    elif '"availability":"out_of_stock"' in body.lower():
                        captured["stock"] = False
            except Exception:
                pass

        page.on("response", _on_response)
        page.goto(url, timeout=15000)
        _dismiss_cookie_banner(page)

        # Wait for content to load (Next.js client-side rendering)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # Check intercepted API data first (most reliable for Next.js)
        if "price" in captured:
            pris = captured["price"]
            lager = captured.get("stock")
        else:
            # Fallback: check __NEXT_DATA__ script tag
            next_data = page.query_selector("script#__NEXT_DATA__")
            if next_data:
                try:
                    nd = json.loads(next_data.inner_text())
                    nd_str = json.dumps(nd)
                    for pm in re.findall(r'"(?:price|gross_price)"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', nd_str):
                        val = float(pm.replace(",", "."))
                        if 1 < val < 50000:
                            pris = val
                            break
                except Exception:
                    pass

            # Fallback: check rendered DOM
            if pris is None:
                for sel in [
                    "[data-testid*='price']", "[data-testid*='Price']",
                    "[class*='price']", "[class*='Price']",
                ]:
                    el = page.query_selector(sel)
                    if el:
                        raw = el.inner_text().replace("kr", "").replace("\xa0", "").replace(",", ".").strip()
                        m = re.search(r"(\d+\.?\d*)", raw)
                        if m:
                            val = float(m.group(1))
                            if val > 0:
                                pris = val
                                break

            # Stock from page content
            if lager is None:
                content_lower = page.content().lower()
                if "utsolgt" in content_lower or "out_of_stock" in content_lower:
                    lager = False
                elif "legg til" in content_lower or "handlekurv" in content_lower:
                    lager = True  # If add-to-cart is available, it's in stock

        page.close()
    except Exception as e:
        print(f"  [oda] browser price error: {e}")
        if page:
            try:
                page.close()
            except Exception:
                pass

    return pris, lager


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(products):
    results, resolved = [], {}

    # Probe API availability once (don't kill everything on first 403)
    api_ok = True
    try:
        r = requests.get(f"{API_BASE}/search/?q=paracet", headers=_REQ_HEADERS, timeout=5)
        if r.status_code == 403:
            print("  [oda] API blocked (403), will use browser only")
            api_ok = False
        elif r.status_code != 200:
            print(f"  [oda] API probe returned {r.status_code}, will try per-request")
    except Exception:
        print("  [oda] API unreachable, will use browser only")
        api_ok = False

    # Start Playwright (Oda is Next.js, browser is always needed as fallback)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
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
        extra_http_headers={"Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8"},
    )
    _stealth.apply_stealth_sync(context)

    for prod in products:
        url = prod.get("url_oda")

        # Step 1: Resolve URL
        if not url and api_ok:
            # API search: try product name first (more effective than varenummer)
            if prod.get("merke"):
                url = _search_url_api(prod["merke"])
            if not url:
                url = _search_url_api(prod["varenummer"])
            if not url and prod.get("ean"):
                url = _search_url_api(prod["ean"])
            if url:
                resolved[prod["varenummer"]] = url

        if not url:
            # Browser search fallback
            url = _search_url_browser(context, prod)
            if url:
                resolved[prod["varenummer"]] = url

        if not url:
            print(f"  [oda] no URL: {prod['varenummer']}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
            continue

        # Step 2: Fetch price
        pris, lager = None, None

        # Try API first (fast)
        if api_ok:
            pris, lager = _fetch_price_api(url)

        # Browser fallback (always available)
        if pris is None:
            pris, lager = _fetch_price_browser(context, url)

        print(f"  [oda] {prod['varenummer']}: {pris}")
        results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.15)

    context.close()
    browser.close()
    pw.stop()

    return results, resolved
