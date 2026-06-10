"""One-off CI validation of the rewritten /api/products-based vitusapotek scraper.

Runs the scraper against the full products.csv (no DB) and reports the
price/stock hit rate, Sun category in particular.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers import vitusapotek

rows = list(csv.DictReader(open(os.path.join(os.path.dirname(__file__), "products.csv"))))
products = [
    {"id": n, "varenummer": r["varenummer"], "kategori": r["kategori"]}
    for n, r in enumerate(rows)
]
print(f"Loaded {len(products)} products ({sum(1 for r in rows if r['kategori'] == 'Sun')} Sun)")

results, resolved = vitusapotek.run(products)

by_id = {p["id"]: p for p in products}
ok = [r for r in results if r["pris"] is not None]
ok_sun = [r for r in ok if by_id[r["produkt_id"]]["kategori"] == "Sun"]
n_sun = sum(1 for p in products if p["kategori"] == "Sun")
stock_known = sum(1 for r in results if r["pa_lager"] is not None)

print("\n" + "=" * 70)
print(f"prices:  {len(ok)}/{len(results)} total, {len(ok_sun)}/{n_sun} Sun")
print(f"stock:   {stock_known}/{len(results)} known")
print(f"resolved URLs: {len(resolved)}")
print("sample Sun prices:")
for r in ok_sun[:10]:
    p = by_id[r["produkt_id"]]
    print(f"  {p['varenummer']}: {r['pris']} (lager={r['pa_lager']})")
print("\nDONE")
