"""Shared helpers used by multiple scrapers."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def http_session(headers: dict | None = None) -> requests.Session:
    """Session with keep-alive and retries for transient failures.

    One scraper makes hundreds of requests to the same host; reusing the
    connection is faster, and a single dropped connection or 502 should not
    cost a product its price for the day. Not shared between threads — each
    scraper creates its own.
    """
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        # POST is included for Apotera's GraphQL endpoint, which is a read.
        allowed_methods=("GET", "POST"),
        # Hand the final response back instead of raising, so callers keep
        # their own status handling.
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if headers:
        session.headers.update(headers)
    return session


# A dead product page: the product was removed or its URL changed. Bot
# protection answers 403/429, so these two are safe to treat as "gone".
GONE_STATUSES = (404, 410)


def safe_url(href: str | None, base: str, allowed_host: str) -> str | None:
    """Return an absolute URL only if it resolves to the expected host.

    Accepts absolute http(s) URLs and root-relative paths; anything else
    (javascript:, protocol-relative, bare fragments) is rejected.
    """
    if not href:
        return None
    if href.startswith("/"):
        url = base + href
    elif href.startswith("http"):
        url = href
    else:
        return None
    try:
        host = urlparse(url).netloc
        bare = allowed_host.removeprefix("www.")
        if host in (bare, "www." + bare):
            return url
    except Exception:
        pass
    return None


_PRICE_KEY_RE = re.compile(r'"price"\s*:\s*"?(\d+(?:[.,]\d+)?)"?')


def _to_price(value) -> float | None:
    """Convert a JSON price value (number or string) to a positive float."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = re.sub(r"[\s\u00a0\u202f]", "", value).replace(",", ".")
    try:
        pris = float(value)
    except (TypeError, ValueError):
        return None
    return pris if pris > 0 else None


def _price_from_jsonld_text(text: str) -> float | None:
    """Extract an offer price from one JSON-LD document."""
    try:
        d = json.loads(text)
    except Exception:
        return None
    items = d if isinstance(d, list) else [d]
    # Some sites wrap every entity in a top-level {"@graph": [...]}.
    for item in list(items):
        if isinstance(item, dict) and isinstance(item.get("@graph"), list):
            items.extend(item["@graph"])
    for item in items:
        if not isinstance(item, dict):
            continue
        offers = item.get("offers")
        for offer in (offers if isinstance(offers, list) else [offers]):
            if not isinstance(offer, dict):
                continue
            # AggregateOffer carries lowPrice instead of price.
            pris = _to_price(offer.get("price")) or _to_price(offer.get("lowPrice"))
            if pris:
                return pris
    return None


def extract_jsonld_price(html: str) -> float | None:
    """Extract an offer price from any JSON-LD block in raw HTML."""
    for block in re.findall(
        r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        pris = _price_from_jsonld_text(block)
        if pris:
            return pris
    return None


def extract_price_from_html(html: str) -> float | None:
    """Extract price from server-rendered HTML (no JS required)."""
    # Layer 1: JSON-LD
    pris = extract_jsonld_price(html)
    if pris:
        return pris
    # Layer 2: data-testid content attribute
    m = re.search(
        r'data-testid=["\'][^"\']*price[^"\']*["\'][^>]*content=["\']([0-9.]+)["\']',
        html, re.IGNORECASE,
    ) or re.search(
        r'content=["\']([0-9.]+)["\'][^>]*data-testid=["\'][^"\']*price[^"\']*["\']',
        html, re.IGNORECASE,
    )
    if m:
        try:
            pris = float(m.group(1))
            if pris:
                return pris
        except ValueError:
            pass
    # Layer 3: generic "price" key anywhere in page source
    m = _PRICE_KEY_RE.search(html)
    if m:
        try:
            return float(m.group(1).replace(",", ".")) or None
        except ValueError:
            pass
    return None


def parse_price_text(text: str | None) -> float | None:
    """Parse a displayed Norwegian price such as "1 299,00 kr" or "kr 89,-".

    Spaces (incl. no-break/thin spaces) are thousands separators and are
    dropped before matching, so "1 299,00" is 1299.0 rather than 1.0; the
    same goes for the dot in "1.299,00".
    Returns None for zero or unparseable text.
    """
    if not text:
        return None
    compact = re.sub(r"(?<=\d)[\s\u00a0\u202f]+(?=\d)", "", text)
    # "1.299,00": a dot followed by exactly three digits and then a decimal
    # comma is a thousands separator, not a decimal point.
    compact = re.sub(r"(?<=\d)\.(?=\d{3},\d)", "", compact)
    m = re.search(r"(\d+)(?:[.,](\d{1,2}))?", compact)
    if not m:
        return None
    pris = float(f"{m.group(1)}.{m.group(2) or 0}")
    return pris or None


def extract_price_from_page(page) -> float | None:
    """Extract price from a rendered Playwright page."""
    # Layer 1: JSON-LD
    for tag in page.query_selector_all("script[type='application/ld+json']"):
        try:
            pris = _price_from_jsonld_text(tag.inner_text())
        except Exception:
            pris = None
        if pris:
            return pris
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
                except ValueError:
                    pass
            pris = parse_price_text(el.inner_text())
            if pris:
                return pris
    # Layer 3: CSS class selectors
    for sel in ["[class*='price']", "[class*='Price']", "[class*='pris']", "[class*='Pris']"]:
        el = page.query_selector(sel)
        if el:
            pris = parse_price_text(el.inner_text())
            if pris:
                return pris
    # Layer 4: regex on full page source
    m = _PRICE_KEY_RE.search(page.content())
    if m:
        try:
            return float(m.group(1).replace(",", ".")) or None
        except ValueError:
            pass
    return None


def fetch_price_http(session, url: str, timeout: float = 10):
    """Fetch a server-rendered product page over plain HTTP.

    Returns (pris, pa_lager, gone). `gone` is True when the page no longer
    exists, in which case there is nothing for a browser to find either.
    """
    r = session.get(url, timeout=timeout)
    if r.status_code in GONE_STATUSES:
        return None, None, True
    if r.status_code != 200:
        return None, None, False
    return extract_price_from_html(r.text), extract_stock(r.text), False


def fetch_price_browser(context, url: str, wait_selector: str, goto_timeout: int = 15000):
    """Fetch a product page in Playwright. Returns (pris, pa_lager, gone).

    Nothing is extracted from a 404/410 page: error pages still carry prices
    (related products, promos) that the extraction fallbacks would pick up
    and store as this product's price.
    """
    page = context.new_page()
    try:
        response = page.goto(url, timeout=goto_timeout)
        if response is not None and response.status in GONE_STATUSES:
            return None, None, True
        # Not networkidle — it times out on these storefronts.
        try:
            page.wait_for_selector(wait_selector, timeout=5000)
        except Exception:
            pass  # Attempt extraction anyway
        return extract_price_from_page(page), extract_stock(page.content()), False
    finally:
        try:
            page.close()
        except Exception:
            pass


# A product with no known page at a retailer is usually one the retailer does
# not sell, and searching for it costs a request or a browser page load. With
# thousands of products that must not happen every night: a new product is
# searched for on its first nights, after that once per cycle.
LOOKUP_NEW_DAYS = 2
LOOKUP_CYCLE_DAYS = 7


def due_for_lookup(prod: dict, now: datetime | None = None) -> bool:
    """Should a product without a known page be searched for on this run?"""
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(str(prod.get("opprettet")).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if now - created < timedelta(days=LOOKUP_NEW_DAYS):
            return True
    except ValueError:
        pass
    try:
        slot = int(prod.get("id"))
    except (TypeError, ValueError):
        return True
    # Spread by product ID so each night carries an even share of the retries.
    return (slot + now.toordinal()) % LOOKUP_CYCLE_DAYS == 0


def code_variants(code: str) -> list[str]:
    """Return search variants for product codes.

    Some retailers index product codes without leading zeros. Keep the
    original code first, then add a zero-stripped variant if different.
    """
    value = str(code or "").strip()
    if not value:
        return []
    variants = [value]
    stripped = value.lstrip("0")
    if stripped and stripped != value:
        variants.append(stripped)
    # Nordic varenummer are 6 digits, but some sources drop leading zeros
    # (e.g. "86757" for "086757"), so add the zero-padded form as well.
    if value.isdigit() and len(value) < 6:
        variants.append(value.zfill(6))
    return variants


def extract_stock(text: str) -> bool | None:
    """Detect stock status from page text.

    Order matters: out-of-stock indicators must be checked before in-stock
    ones, because Norwegian "ikke på lager" (not in stock) contains the
    substring "på lager" (in stock), and English "not in stock" contains
    "in stock". A naive `"på lager" in text` check returns True for both.
    """
    lower = text.lower()
    if (
        "ikke på lager" in lower
        or "utsolgt" in lower
        or "not in stock" in lower
        or "out of stock" in lower
        or '"outofstock"' in lower
        or '"out_of_stock"' in lower
    ):
        return False
    if (
        "på lager" in lower
        or "in stock" in lower
        or '"instock"' in lower
        or '"in_stock":true' in lower
    ):
        return True
    return None
