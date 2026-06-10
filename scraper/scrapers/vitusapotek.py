"""Vitusapotek.no — prices via the storefront's public /api/products JSON API.

Vitusapotek migrated to a new Next.js storefront (June 2026). The old Hybris
/p/ URLs are gone, the legacy /sitemap/sitemap.xml only lists 7 sub-sitemaps,
and the on-site search no longer resolves varenummer queries at all (it
returns promoted products for any query — this is why the whole Sun range
came back empty). The new storefront exposes the JSON APIs it uses itself:

    GET /api/products?ids=<varenummer,...>        -> price, urlPath, name
    GET /api/products/stock?ids=<varenummer,...>  -> stock status per id

Both accept comma-separated varenummer over plain HTTP with no auth or bot
protection, so no Playwright is needed. Products absent from the response do
not exist in the current assortment.
"""
import time
from datetime import datetime, timezone

import requests

from ._common import code_variants

BUTIKK = "vitusapotek"
BASE   = "https://www.vitusapotek.no"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept": "application/json",
}

_BATCH = 40


def _fetch_json(path, ids):
    r = requests.get(
        f"{BASE}{path}", params={"ids": ",".join(ids)}, headers=_HEADERS, timeout=25
    )
    r.raise_for_status()
    return r.json()


def _batched(path, ids, collect):
    """Fetch ids in batches, calling collect(payload) per batch.

    On a batch error, retry the ids one by one so a single bad id doesn't
    lose the whole batch.
    """
    for i in range(0, len(ids), _BATCH):
        batch = ids[i:i + _BATCH]
        try:
            collect(_fetch_json(path, batch))
        except Exception as e:
            print(f"  [vitusapotek] {path} batch error: {e}")
            for pid in batch:
                try:
                    collect(_fetch_json(path, [pid]))
                except Exception as e2:
                    print(f"  [vitusapotek] {path} error {pid}: {e2}")
        time.sleep(0.2)


def _extract_price(item):
    """Current selling price: campaign price while active, else list price."""
    if item.get("isWithoutPrice"):
        return None
    price = item.get("price") or {}
    discounted = price.get("discountedAmount")
    if discounted:
        end = price.get("discountedEndDate")
        active = True
        if end:
            try:
                active = datetime.fromisoformat(end) > datetime.now(timezone.utc)
            except (ValueError, TypeError):
                # Unparseable or naive timestamp — assume the campaign is on,
                # matching what the storefront shows.
                pass
        if active:
            try:
                return float(discounted) or None
            except (TypeError, ValueError):
                pass
    try:
        return float(price.get("amount", 0)) or None
    except (TypeError, ValueError):
        return None


def _extract_stock(status):
    """Map the stock API's statusCode to pa_lager (online availability)."""
    if not isinstance(status, dict):
        return None
    code = status.get("statusCode") or status.get("stockAvailability")
    if code == "in-stock":
        return True
    if code in ("out-of-stock", "sold-out-online"):
        return False
    return None


def run(products):
    results, resolved = [], {}

    # Query every varenummer variant (with and without leading zeros) and key
    # results by the id the API returns. Each product row then resolves its
    # own variants — the DB has duplicate rows for the same item ("051946"
    # and "51946"), so both must be able to claim the result.
    wanted, seen = [], set()
    for prod in products:
        for code in code_variants(prod["varenummer"]):
            if code not in seen:
                seen.add(code)
                wanted.append(code)

    items_by_id = {}

    def _collect_items(payload):
        for item in (payload if isinstance(payload, list) else []):
            if isinstance(item, dict):
                items_by_id.setdefault(str(item.get("id", "")).strip(), item)

    _batched("/api/products", wanted, _collect_items)

    stock_by_id = {}
    _batched(
        "/api/products/stock", wanted,
        lambda payload: stock_by_id.update(payload if isinstance(payload, dict) else {}),
    )

    for prod in products:
        item, status = None, None
        for code in code_variants(prod["varenummer"]):
            item = item or items_by_id.get(code)
            status = status or stock_by_id.get(code)
        pris = _extract_price(item) if item else None
        lager = _extract_stock(status)
        if item and pris is not None and item.get("urlPath"):
            url = f"{BASE}/{item['urlPath'].lstrip('/')}"
            if url != prod.get("url_vitusapotek"):
                resolved[prod["varenummer"]] = url
        print(f"  [vitusapotek] {prod['varenummer']}: {pris}")
        results.append(
            {"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager}
        )

    return results, resolved
