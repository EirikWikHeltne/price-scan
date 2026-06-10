"""One-off CI diagnostic: why do Sun products fail on vitusapotek?

Round 3. Round 2 showed GET /api/products?ids=<varenummer,...> returns full
product JSON over plain HTTP. This round maps the schema (price/stock fields)
and measures coverage across all active products, Sun in particular.
"""
import csv
import json
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.vitusapotek import BASE, _REQ_HEADERS

rows = list(csv.DictReader(open(os.path.join(os.path.dirname(__file__), "products.csv"))))
SUN = [r["varenummer"] for r in rows if r["kategori"] == "Sun"]
ALL = [r["varenummer"] for r in rows]


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def fetch_products(ids):
    r = requests.get(
        f"{BASE}/api/products", params={"ids": ",".join(ids)}, headers=_REQ_HEADERS, timeout=25
    )
    r.raise_for_status()
    return r.json()


section("1. schema of one product payload")
data = fetch_products(["993232", "051946", "51946"])
print(f"  returned {len(data)} items for ids 993232,051946,51946")
for item in data:
    print(f"  id={item.get('id')!r} name={item.get('name')!r}")
print("\n  top-level keys of 993232:")
item = next(i for i in data if i.get("id") == "993232")
for k, v in item.items():
    s = json.dumps(v, ensure_ascii=False)
    print(f"    {k}: {s[:160]}")

section("2. coverage: all products in chunks of 25")
found, prices, stocks = {}, {}, {}
for i in range(0, len(ALL), 25):
    chunk = ALL[i : i + 25]
    try:
        for item in fetch_products(chunk):
            pid = str(item.get("id"))
            found[pid] = item
    except Exception as e:
        print(f"  chunk {i}: EXC {e}")

def lookup(v):
    return found.get(v) or found.get(v.lstrip("0"))

ok_all = [v for v in ALL if lookup(v)]
ok_sun = [v for v in SUN if lookup(v)]
print(f"  all: {len(ok_all)}/{len(ALL)} returned")
print(f"  Sun: {len(ok_sun)}/{len(SUN)} returned")
print(f"  Sun missing: {[v for v in SUN if not lookup(v)][:20]}")

section("3. price/stock extraction rate on Sun")
def deep_find(obj, names, path=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if any(n in k.lower() for n in names) and isinstance(v, (int, float, str)):
                out.append((p, v))
            out += deep_find(v, names, p)
    elif isinstance(obj, list):
        for n, v in enumerate(obj[:3]):
            out += deep_find(v, names, f"{path}[{n}]")
    return out

sample = lookup(SUN[0])
print(f"  price-ish fields of {SUN[0]}:")
for p, v in deep_find(sample, ["price", "pris"]):
    print(f"    {p} = {v!r}")
print(f"  stock-ish fields of {SUN[0]}:")
for p, v in deep_find(sample, ["stock", "lager", "avail"]):
    print(f"    {p} = {v!r}")

print("\n  urlPath sample:", sample.get("urlPath"))

n_price = sum(1 for v in ok_sun if deep_find(lookup(v), ["price"]))
print(f"\n  Sun items with at least one price field: {n_price}/{len(ok_sun)}")

print("\nDONE")
