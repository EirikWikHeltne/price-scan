"""One-off CI diagnostic for vitusapotek/apotera price-fetch failures.

Round 3: full-catalogue validation of the GraphQL-based apotera scraper and
a spot-check of the fixed vitusapotek scraper.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import get_active_products
from scrapers import apotera, vitusapotek

products = get_active_products()
print(f"Loaded {len(products)} products")

print("=" * 70)
print("PART 1: APOTERA — GraphQL scraper, full catalogue")
print("=" * 70)
rows, resolved = apotera.run(products)
ok = sum(1 for r in rows if r["pris"] is not None)
print(f"\n  apotera: {ok}/{len(rows)} prices found, {len(resolved)} URLs to re-save")
for vn, url in list(resolved.items())[:5]:
    print(f"    resolved sample: {vn} -> {url}")

print()
print("=" * 70)
print("PART 2: VITUSAPOTEK — fixed scraper, 15-product sample")
print("=" * 70)
sample = products[:15]
rows, resolved = vitusapotek.run(sample)
ok = sum(1 for r in rows if r["pris"] is not None)
print(f"\n  vitusapotek sample: {ok}/{len(rows)} prices found, "
      f"{len(resolved)} URLs to re-save")
for vn, url in resolved.items():
    print(f"    resolved: {vn} -> {url}")

print("\nDONE")
