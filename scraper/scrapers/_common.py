"""Shared helpers used by multiple scrapers."""
import json
import re
from urllib.parse import urlparse


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


def _price_from_jsonld_text(text: str) -> float | None:
    """Extract an offer price from one JSON-LD document."""
    try:
        d = json.loads(text)
    except Exception:
        return None
    for item in (d if isinstance(d, list) else [d]):
        if not isinstance(item, dict):
            continue
        offer = item.get("offers")
        if offer:
            if isinstance(offer, list):
                offer = offer[0]
            try:
                pris = float(offer.get("price", 0)) or None
            except Exception:
                pris = None
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
    dropped before matching, so "1 299,00" is 1299.0 rather than 1.0.
    Returns None for zero or unparseable text.
    """
    if not text:
        return None
    compact = re.sub(r"(?<=\d)[\s\u00a0\u202f]+(?=\d)", "", text)
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
