"""One-off CI diagnostic for vitusapotek/apotera price-fetch failures.

Round 4: re-validate apotera after adding zero-padded varenummer variants.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import get_active_products
from scrapers import apotera

products = get_active_products()
print(f"Loaded {len(products)} products")

print("=" * 70)
print("APOTERA — GraphQL scraper with zero-padded SKU variants, full catalogue")
print("=" * 70)
rows, resolved = apotera.run(products)
ok = sum(1 for r in rows if r["pris"] is not None)
print(f"\n  apotera: {ok}/{len(rows)} prices found, {len(resolved)} URLs to re-save")

print("\nDONE")
