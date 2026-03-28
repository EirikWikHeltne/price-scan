"""Main entry point: python run.py"""
import logging
from datetime import datetime
from db import get_active_products, save_resolved_url, bulk_insert_prices
from scrapers import farmasiet, boots, vitusapotek, apotek1, oda, apotera, meny

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

SCRAPERS = {
    "farmasiet":   farmasiet,
    "boots":       boots,
    "vitusapotek": vitusapotek,
    "apotek1":     apotek1,
    "oda":         oda,
    "apotera":     apotera,
    "meny":        meny,
}

def run():
    print(f"=== Scrape started {datetime.now().isoformat()} ===")
    products = get_active_products()
    print(f"Loaded {len(products)} products")

    all_rows = []
    for name, module in SCRAPERS.items():
        print(f"\n--- {name} ---")
        try:
            rows, resolved = module.run(products)
            for vn, url in resolved.items():
                save_resolved_url(vn, name, url)
                print(f"  Saved URL for {vn} on {name}")
            all_rows.extend(rows)
            ok = sum(1 for r in rows if r["pris"])
            print(f"  {ok}/{len(rows)} prices found")
        except Exception as e:
            print(f"  CRASH: {e}")

    bulk_insert_prices(all_rows)
    print(f"\n=== Done — {len(all_rows)} rows inserted ===")

if __name__ == "__main__":
    run()
