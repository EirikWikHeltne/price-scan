"""
Seeds the produkter table from products.csv.
Run once after setup, or anytime the product list changes:
  python scripts/seed_products.py
"""
import sys, os, csv, re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_client

CSV_PATH = os.path.join(os.path.dirname(__file__), "products.csv")

VALID_CATEGORIES = {"Paracetamol", "Ibuprofen", "Mouthwash", "Body lotion", "Intimate"}


def seed():
    client = get_client()

    rows = []
    skipped = 0
    with open(CSV_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            varenummer = r.get("varenummer", "").strip()
            if not varenummer:
                continue
            if not re.match(r'^\d{1,10}$', varenummer):
                print(f"  [seed] skipping invalid varenummer: {varenummer!r}")
                skipped += 1
                continue
            kategori = r.get("kategori", "").strip()
            if kategori not in VALID_CATEGORIES:
                print(f"  [seed] skipping invalid kategori: {kategori!r}")
                skipped += 1
                continue
            rows.append({
                "varenummer": varenummer,
                "merke":      r.get("merke", "").strip(),
                "produkt":    r.get("produkt", "").strip(),
                "kategori":   kategori,
            })

    if skipped:
        print(f"  [seed] skipped {skipped} invalid rows")
    client.table("produkter").upsert(rows, on_conflict="varenummer").execute()
    print(f"Seeded {len(rows)} products from {CSV_PATH}")


if __name__ == "__main__":
    seed()
