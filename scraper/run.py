"""Main entry point: python run.py"""
import logging
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from db import get_active_products, save_resolved_url, bulk_insert_prices
from scrapers import farmasiet, boots, vitusapotek, apotek1, oda, apotera

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

SCRAPERS = {
    "farmasiet":   farmasiet,
    "boots":       boots,
    "vitusapotek": vitusapotek,
    "apotek1":     apotek1,
    "oda":         oda,
    "apotera":     apotera,
}

# Optional allowlist (SCRAPERS_ONLY="vitusapotek,apotek1") to run a subset —
# handy for fast validation runs via workflow_dispatch. Blank = run all.
_only = {s.strip() for s in os.environ.get("SCRAPERS_ONLY", "").split(",") if s.strip()}
if _only:
    unknown = _only - SCRAPERS.keys()
    if unknown:
        raise SystemExit(f"SCRAPERS_ONLY has unknown scrapers: {sorted(unknown)}")
    SCRAPERS = {name: mod for name, mod in SCRAPERS.items() if name in _only}

# Grocery retailers only scrape these categories (pharmacy retailers get all)
GROCERY_SCRAPERS = {"oda"}
GROCERY_CATEGORIES = {"Paracetamol", "Ibuprofen"}

MAX_WORKERS = 4  # run up to 4 scrapers in parallel


def _run_scraper(name, module, products):
    """Run a single scraper; returns (name, rows, resolved) or (name, error)."""
    print(f"\n--- {name} ---")
    try:
        rows, resolved = module.run(products)
        ok = sum(1 for r in rows if r["pris"] is not None)
        print(f"  {name}: {ok}/{len(rows)} prices found")
        return name, rows, resolved
    except Exception as e:
        print(f"  {name} CRASH: {e}")
        return name, [], {}


def run():
    print(f"=== Scrape started {datetime.now().isoformat()} ===")
    products = get_active_products()
    print(f"Loaded {len(products)} products")

    grocery_products = [p for p in products if p.get("kategori") in GROCERY_CATEGORIES]
    print(f"Grocery-filtered: {len(grocery_products)} products (Paracetamol/Ibuprofen)")

    all_rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _run_scraper, name, module,
                grocery_products if name in GROCERY_SCRAPERS else products
            ): name
            for name, module in SCRAPERS.items()
        }
        for future in as_completed(futures):
            name, rows, resolved = future.result()
            for vn, url in resolved.items():
                save_resolved_url(vn, name, url)
                print(f"  Saved URL for {vn} on {name}")
            all_rows.extend(rows)

    bulk_insert_prices(all_rows)
    print(f"\n=== Done — {len(all_rows)} rows inserted ===")

if __name__ == "__main__":
    run()
