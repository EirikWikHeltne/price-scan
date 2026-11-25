"""Oda.com — grocery store with a small range of non-prescription painkillers.

Prices come from Oda's search API, and only from a hit that is verified to be
the product asked for (brand, form, strength and pack size). Oda has no
varenummer/EAN search and pads thin results with unrelated products, so an
unverified hit is far more likely to be wrong than right; a product Oda does
not sell must get no price.
"""
import re, time, requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from ._common import _to_price, http_session, safe_url

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


# ---------------------------------------------------------------------------
# Product matching
# ---------------------------------------------------------------------------

# Our form abbreviation -> the word Oda uses. Ordered: "tablett" is also part
# of "brusetablett"/"smeltetablett", so those are checked first.
_FORMS = (
    ("bruseta", "brusetablett"),
    ("smeltab", "smeltetablett"),
    ("tab",     "tablett"),
    ("kaps",    "kaps"),
    ("supp",    "stikkpille"),
    ("mikstur", "mikstur"),
)
_FORM_WORDS = dict(_FORMS)


def _norm(text: str | None) -> str:
    """Lower-case and write measures one way: "24 mg / ml" -> "24mg/ml"."""
    t = (text or "").lower().replace(" ", " ")
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    t = re.sub(r"\s*/\s*", "/", t)
    return re.sub(r"(\d)\s+(mg|ml|g|kg|stk|mcg|µg)\b", r"\1\2", t)


def _oda_form(text: str) -> str | None:
    for form, word in _FORMS:
        if word in text:
            return form
    return None


def matches(prod: dict, hit: dict) -> str | None:
    """Is this Oda search hit the product we track?

    Returns "exact" when everything including the form is confirmed, "plain"
    when Oda's name states no form and we want an ordinary tablet, and None
    when the hit is a different product (or cannot be told apart from one).
    """
    text = _norm(f"{hit.get('full_name') or ''} {hit.get('name_extra') or ''}")
    name = _norm(hit.get("full_name"))

    brand = _norm(prod.get("merke")).split()
    if not brand or not all(re.search(rf"\b{re.escape(w)}\b", name) for w in brand):
        return None

    form = None
    for token in _norm(prod.get("produkt")).split():
        if token in _FORM_WORDS:
            form = token
        elif any(c.isdigit() for c in token):
            # Strength, volume or pack size: "500mg", "24mg/ml", "20enpac".
            token = re.sub(r"^(\d+)enpac$", r"\1stk", token)
            if not re.search(rf"(?<![\w./]){re.escape(token)}(?![\w/])", text):
                return None
        elif not re.search(rf"\b{re.escape(token)}", text):
            # Variant name such as ZAPP: a different product without it.
            return None

    oda_form = _oda_form(text)
    if form and oda_form == form:
        return "exact"
    if oda_form is None and form in (None, "tab"):
        return "plain"
    return None


def pick_match(prod: dict, hits: list[dict]) -> dict | None:
    """The verified hit for a product, preferring one with a confirmed form."""
    plain = None
    for hit in hits:
        kind = matches(prod, hit)
        if kind == "exact":
            return hit
        if kind == "plain" and plain is None:
            plain = hit
    return plain


def _oda_product_id(url: str | None) -> str | None:
    """Oda's product ID from a URL like /no/products/1125-paracet-mikstur/."""
    m = re.search(r"/products/(\d+)-", url or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# API access: plain HTTP, through a real browser if that is blocked
# ---------------------------------------------------------------------------

class _Fetcher:
    """GETs Oda API JSON. Returns None when no usable answer was obtained."""

    def __init__(self):
        self._session = http_session(_REQ_HEADERS)
        self._blocked = False
        self._pw = self._browser = self._context = None

    def get_json(self, url: str) -> dict | None:
        if not self._blocked:
            try:
                r = self._session.get(url, timeout=10)
                if r.status_code == 200:
                    return r.json()
            except (requests.RequestException, ValueError) as e:
                print(f"  [oda] API error: {e}")
                return None
            if r.status_code != 403:
                print(f"  [oda] API returned {r.status_code}")
                return None
            print("  [oda] API blocked (403), fetching through a browser instead")
            self._blocked = True
        return self._get_json_browser(url)

    def _launch(self, pw):
        return pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

    def _get_json_browser(self, url: str) -> dict | None:
        page = None
        try:
            if self._context is None:
                self._pw = sync_playwright().start()
                self._browser = self._launch(self._pw)
                self._context = self._browser.new_context(
                    user_agent=_UA,
                    locale="nb-NO",
                    timezone_id="Europe/Oslo",
                    viewport={"width": 1920, "height": 1080},
                    extra_http_headers={"Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8"},
                )
                # Cap every Playwright call — the 30s library default applies
                # per call, and uncapped calls have hung scrape runs for hours.
                self._context.set_default_timeout(15000)
                _stealth.apply_stealth_sync(self._context)
            page = self._context.new_page()
            # The API response itself is the document: nothing is read from a
            # rendered page, where prices of other products are everywhere.
            response = page.goto(url, timeout=15000)
            if response is None or response.status != 200:
                print(f"  [oda] browser got {response.status if response else 'no response'}")
                return None
            return response.json()
        except Exception as e:
            print(f"  [oda] browser fetch error: {e}")
            return None
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def close(self):
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._pw, "stop", None),
        ):
            try:
                if closer:
                    closer()
            except Exception:
                pass


def _search(fetcher, query: str) -> list[dict]:
    data = fetcher.get_json(f"{API_BASE}/search/?q={quote(query)}")
    hits = data.get("products") if isinstance(data, dict) else None
    return [h for h in hits if isinstance(h, dict)] if isinstance(hits, list) else []


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(products):
    results, resolved = [], {}
    searches = {}  # brand -> hits; Oda's range is a handful of brands
    fetcher = _Fetcher()
    try:
        for prod in products:
            # A cached url_oda is not trusted: the product is looked up and
            # verified on every run, which costs one search per brand.
            brand = (prod.get("merke") or "").strip()
            if brand and brand not in searches:
                searches[brand] = _search(fetcher, brand)
                time.sleep(0.15)
            hit = pick_match(prod, searches.get(brand, []))

            pris = lager = None
            if hit:
                pris = _to_price(hit.get("gross_price"))
                available = (hit.get("availability") or {}).get("is_available")
                lager = available if isinstance(available, bool) else None
                url = safe_url(hit.get("front_url"), BASE, ALLOWED_HOST)
                # Compared by product ID so a renamed slug is not a rewrite.
                pid = _oda_product_id(url)
                if pid and pid == str(hit.get("id")) and pid != _oda_product_id(prod.get("url_oda")):
                    resolved[prod["varenummer"]] = url
                print(f"  [oda] {prod['varenummer']}: {pris} ({hit.get('full_name')}, {hit.get('name_extra')})")
            else:
                print(f"  [oda] no match: {prod['varenummer']}")
            results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
    finally:
        fetcher.close()

    return results, resolved
