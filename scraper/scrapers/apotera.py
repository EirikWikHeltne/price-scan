"""Apotera.no — Magento 2 store. Prices via the public GraphQL API.

The storefront renders search results client-side (the server HTML contains
no product links), and an older scraper version poisoned the URL cache with
customer-login redirects, so HTML scraping is a dead end here. Magento's
/graphql endpoint returns price, stock and the canonical url_key for an
exact SKU match — and Apotera's SKUs are the pharmacy varenummer.
"""
import time, requests
from ._common import code_variants

BUTIKK  = "apotera"
BASE    = "https://www.apotera.no"
GRAPHQL = f"{BASE}/graphql"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Content-Type": "application/json",
}

_BATCH = 50

_QUERY = """
query ($skus: [String!], $pageSize: Int!) {
  products(filter: {sku: {in: $skus}}, pageSize: $pageSize) {
    items {
      sku
      url_key
      stock_status
      price_range { minimum_price { final_price { value } } }
    }
  }
}
"""


def _fetch_items(skus):
    """Fetch product items for a list of SKUs. Raises on transport/API errors."""
    r = requests.post(
        GRAPHQL,
        json={"query": _QUERY, "variables": {"skus": skus, "pageSize": len(skus)}},
        headers=_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data and not data.get("data"):
        raise RuntimeError(data["errors"])
    return data["data"]["products"]["items"]


def run(products):
    results, resolved = [], {}

    # Map every SKU variant (with and without leading zeros) back to the
    # product's varenummer so GraphQL results can be matched up again.
    sku_to_vn = {}
    for prod in products:
        for code in code_variants(prod["varenummer"]):
            sku_to_vn.setdefault(code, prod["varenummer"])

    items_by_vn = {}
    skus = list(sku_to_vn)
    for i in range(0, len(skus), _BATCH):
        batch = skus[i:i + _BATCH]
        try:
            items = _fetch_items(batch)
        except Exception as e:
            print(f"  [apotera] GraphQL batch error: {e}")
            # Retry one by one so a single bad SKU doesn't lose the batch.
            items = []
            for sku in batch:
                try:
                    items.extend(_fetch_items([sku]))
                except Exception as e2:
                    print(f"  [apotera] GraphQL error {sku}: {e2}")
        for item in items:
            vn = sku_to_vn.get(str(item.get("sku", "")).strip())
            if vn:
                items_by_vn.setdefault(vn, item)
        time.sleep(0.2)

    for prod in products:
        item = items_by_vn.get(prod["varenummer"])
        pris, lager = None, None
        if item:
            try:
                pris = float(
                    item["price_range"]["minimum_price"]["final_price"]["value"]
                ) or None
            except (KeyError, TypeError, ValueError):
                pris = None
            lager = {"IN_STOCK": True, "OUT_OF_STOCK": False}.get(
                item.get("stock_status")
            )
            url_key = item.get("url_key")
            if pris is not None and url_key:
                url = f"{BASE}/{url_key}"
                # Also heals cache entries poisoned by an old scraper version
                # (customer-login redirects were saved for the whole catalogue).
                if url != prod.get("url_apotera"):
                    resolved[prod["varenummer"]] = url
        print(f"  [apotera] {prod['varenummer']}: {pris}")
        results.append(
            {"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager}
        )

    return results, resolved
