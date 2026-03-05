"""
Seeds the produkter table from products.csv.
Run once after setup, or anytime the product list changes:
  python scripts/seed_products.py
"""
import sys, os, csv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_client

CSV_PATH = os.path.join(os.path.dirname(__file__), "products.csv")


def seed():
    client = get_client()

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = [
            {
                "varenummer": r["varenummer"].strip(),
                "merke":      r["merke"].strip(),
                "produkt":    r["produkt"].strip(),
                "kategori":   r["kategori"].strip(),
            }
            for r in csv.DictReader(f)
            if r.get("varenummer", "").strip()  # skip blank rows
        ]

    client.table("produkter").upsert(rows, on_conflict="varenummer").execute()
    print(f"Seeded {len(rows)} products from {CSV_PATH}")


if __name__ == "__main__":
    seed()
