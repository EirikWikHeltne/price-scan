"""Vitusapotek.no — sitemap URL discovery + single browser session for prices."""
import re, time, json, requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from ._common import extract_stock, code_variants

BUTIKK       = "vitusapotek"
BASE         = "https://www.vitusapotek.no"
ALLOWED_HOST = "www.vitusapotek.no"

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
    """Return absolute URL only if it resolves to the expected host."""
    url = BASE + href if href.startswith("/") else href
    try:
        host = urlparse(url).netloc
        if host in (ALLOWED_HOST, ALLOWED_HOST.removeprefix("www.")):
            return url
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Sitemap-based URL discovery
# ---------------------------------------------------------------------------
# The per-product search box does not resolve many products (notably the entire
# Sun/suncare range, which returns no /p/ result), so we mirror apotek1 and
# build a varenummer->URL index from the sitemap up front over plain HTTP. This
# also avoids hundreds of slow per-product search timeouts.

def _parse_sitemap_urls(text, index):
    """Extract varenummer->URL pairs from sitemap XML text.

    Vitusapotek product URLs come in two formats:
      - legacy: .../<slug>/p/<varenummer>  (only a handful remain)
      - current: .../<category-path>/<slug>-<varenummer>  (the slug ends with
        the varenummer, e.g. ".../ebastin-orifarm-tab-10mg-100-stk-053259")
    Index both so the sitemap resolves nearly the whole catalogue.
    """
    for url in re.findall(r'<loc>\s*(https?://[^\s<]+)\s*</loc>', text):
        path = urlparse(url).path
        if "/p/" in path:
            for token in re.findall(r'\d{5,10}', path):
                index.setdefault(token, url)
            continue
        m = re.search(r'-(\d{5,10})/?$', path)
        if m:
            index.setdefault(m.group(1), url)


def _fetch_and_index(url, index, depth=0):
    if depth > 2:
        return
    try:
        r = requests.get(url, headers=_REQ_HEADERS, timeout=15)
        r.raise_for_status()
        text = r.text
        if '<sitemapindex' in text or ('<sitemap>' in text and '<loc>' in text):
            # Sitemap index — recurse into sub-sitemaps (trusted domain only).
            # Prefer subs named "product"; only fall back to fetching all subs
            # when none are (avoids downloading category/store/article maps).
            subs = [
                sub for sub in re.findall(r'<loc>\s*(https?://[^\s<]+)\s*</loc>', text)
                if urlparse(sub).netloc in (ALLOWED_HOST, ALLOWED_HOST.removeprefix("www."))
            ]
            product_subs = [s for s in subs if 'product' in s.lower()]
            for sub in (product_subs or subs):
                _fetch_and_index(sub, index, depth + 1)
        else:
            _parse_sitemap_urls(text, index)
    except Exception as e:
        print(f"  [vitusapotek] sitemap error {url}: {e}")


# Conventional sitemap locations, tried in order when robots.txt does not
# advertise one. Vitusapotek moved its sitemap — the old /sitemap.xml now 404s
# — so we no longer hardcode a single path.
_SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap/sitemap.xml",
    "/sitemaps/sitemap.xml",
    "/media/sitemap.xml",
]


def _sitemaps_from_robots():
    """Return sitemap URLs advertised in robots.txt (authoritative source)."""
    urls = []
    try:
        r = requests.get(f"{BASE}/robots.txt", headers=_REQ_HEADERS, timeout=15)
        if r.status_code == 200:
            for line in r.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    loc = line.split(":", 1)[1].strip()
                    if loc and _safe_url(loc):
                        urls.append(loc)
    except Exception as e:
        print(f"  [vitusapotek] robots.txt error: {e}")
    return urls


def _build_sitemap_index():
    """Download Vitusapotek sitemaps and return varenummer->URL dict.

    The sitemap location is discovered from robots.txt first (authoritative),
    then falls back to conventional paths. We stop at the first sitemap that
    actually yields product URLs.
    """
    index = {}
    print("  [vitusapotek] building URL index from sitemap...")
    candidates = _sitemaps_from_robots()
    candidates += [BASE + p for p in _SITEMAP_CANDIDATES]
    seen = set()
    for sm in candidates:
        if sm in seen:
            continue
        seen.add(sm)
        _fetch_and_index(sm, index)
        # A healthy product sitemap yields thousands of URLs; a handful means
        # we hit a stub (e.g. only legacy /p/ leftovers), so keep trying other
        # candidates and merge whatever each one contributes.
        if len(index) >= 100:
            break
    print(f"  [vitusapotek] sitemap: {len(index)} product URLs indexed")
    return index


def _page_matches_varenummer(page, varenummer):
    """Confirm the loaded product page actually corresponds to varenummer.

    Vitusapotek's search returns the first product even when there is no exact
    match (e.g. promoted or "related" suncare items), so blindly trusting the
    first /p/ link caches the wrong URL and reports a wrong/empty price. We
    verify against the product's structured-data identifiers when available.

    Returns True on a positive match, False on a positive mismatch, and None
    when the page exposes no identifier to compare (caller should be lenient).
    """
    wanted = set(code_variants(varenummer))
    found_any = False
    for el in page.query_selector_all("script[type='application/ld+json']"):
        try:
            d = json.loads(el.inner_text())
        except Exception:
            continue
        for item in (d if isinstance(d, list) else [d]):
            if not isinstance(item, dict):
                continue
            for key in ("sku", "mpn", "gtin", "gtin13", "productID"):
                val = item.get(key)
                if val is None:
                    continue
                found_any = True
                ident = str(val).strip()
                if ident in wanted or ident.lstrip("0") in {w.lstrip("0") for w in wanted}:
                    return True
    return False if found_any else None


def _extract_price(page):
    """Extract price from a rendered Vitusapotek product page."""
    # Layer 1: JSON-LD offers
    for el in page.query_selector_all("script[type='application/ld+json']"):
        try:
            d = json.loads(el.inner_text())
        except Exception:
            continue
        for item in (d if isinstance(d, list) else [d]):
            if not isinstance(item, dict):
                continue
            offer = item.get("offers")
            if not offer:
                continue
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            if isinstance(offer, dict):
                try:
                    pris = float(offer.get("price", 0)) or None
                except (TypeError, ValueError):
                    pris = None
                if pris:
                    return pris
    # Layer 2: CSS class / data-testid selectors
    for sel in ["[data-testid*='price']", "[class*='price']", "[class*='Price']"]:
        el = page.query_selector(sel)
        if el:
            content = el.get_attribute("content")
            if content:
                try:
                    pris = float(content)
                    if pris:
                        return pris
                except ValueError:
                    pass
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                return float(m.group(1))
    # Layer 3: regex on full page source
    m = re.search(r'"price"\s*:\s*"?([\d]+(?:[.,]\d+)?)"?', page.content())
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


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
            ],
        )
        context = browser.new_context(
            user_agent=_UA,
            locale="nb-NO",
            timezone_id="Europe/Oslo",
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,nn;q=0.7,en-US;q=0.6,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )
        context.add_init_script(_STEALTH)
        for prod in products:
            url = prod.get("url_vitusapotek")
            # Cache and sitemap hits map varenummer->URL exactly, so they are
            # trusted. Only search results (fuzzy) need page-level verification.
            verify = False

            # The sitemap is fresh and authoritative: prefer it even over a
            # cached URL, which may be a stale legacy /p/ link that now 404s.
            for code in code_variants(prod["varenummer"]):
                sitemap_url = sitemap_index.get(code)
                if sitemap_url:
                    if sitemap_url != url:
                        url = sitemap_url
                        resolved[prod["varenummer"]] = sitemap_url
                    break

            if not url:
                verify = True
                page = None
                try:
                    page = context.new_page()
                    for code in code_variants(prod["varenummer"]):
                        page.goto(f"{BASE}/search?q={quote(code)}", timeout=12000)
                        # Do NOT use networkidle — wrap any wait in try/except
                        try:
                            page.wait_for_selector(
                                f"a[href*='/p/'], a[href$='-{code}']", timeout=8000
                            )
                        except Exception:
                            pass
                        # Product links either use the legacy /p/ path or end
                        # with "-<varenummer>" in the current URL scheme.
                        for a in page.query_selector_all("a[href]"):
                            href = a.get_attribute("href") or ""
                            if "/p/" in href or href.rstrip("/").endswith(f"-{code}"):
                                url = _safe_url(href)
                                if url:
                                    break
                        if url:
                            break
                    if not url:
                        page.close()
                        page = None
                        raise Exception("no search result")
                    page.close()
                except Exception as e:
                    print(f"  [vitusapotek] search error {prod['varenummer']}: {e}")
                    if page:
                        try: page.close()
                        except Exception: pass
            if not url:
                print(f"  [vitusapotek] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue
            page = None
            try:
                page = context.new_page()
                page.goto(url, timeout=12000)
                # Do NOT use networkidle — it times out and skips extraction
                try:
                    page.wait_for_selector(
                        "script[type='application/ld+json'], [class*='price'], [class*='Price']",
                        timeout=5000
                    )
                except Exception:
                    pass  # Continue and attempt extraction anyway
                # For URLs resolved via search, verify the page is the right
                # product before trusting the price or caching the URL.
                if verify and _page_matches_varenummer(page, prod["varenummer"]) is False:
                    page.close()
                    print(f"  [vitusapotek] search mismatch {prod['varenummer']}: {url}")
                    results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                    continue
                pris = _extract_price(page)
                lager = extract_stock(page.content())
                page.close()
                if verify and pris is not None:
                    resolved[prod["varenummer"]] = url
                print(f"  [vitusapotek] {prod['varenummer']}: {pris}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
                time.sleep(0.1)
            except Exception as e:
                print(f"  [vitusapotek] error {prod['varenummer']}: {e}")
                if page:
                    try: page.close()
                    except Exception: pass
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
        context.close()
        browser.close()
    return results, resolved
