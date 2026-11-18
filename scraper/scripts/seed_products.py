"""
Seeds the produkter table from products.csv.
Run once after setup, or anytime the product list changes:
  python scripts/seed_products.py
"""
import sys, os, csv, re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_client

CSV_PATH = os.path.join(os.path.dirname(__file__), "products.csv")

VALID_CATEGORIES = {"Paracetamol", "Ibuprofen", "Mouthwash", "Body lotion", "Intimate", "Sun"}


def load_rows(path=CSV_PATH):
    """Read and validate the CSV. Returns (rows, skipped_count)."""
    rows = []
    seen = set()
    skipped = 0
    # utf-8-sig: a BOM (Excel adds one on save) would otherwise become part
    # of the first header name and every row would be skipped as empty.
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            varenummer = (r.get("varenummer") or "").strip()
            if not varenummer:
                continue
            if not re.match(r'^\d{1,10}$', varenummer):
                print(f"  [seed] skipping invalid varenummer: {varenummer!r}")
                skipped += 1
                continue
            kategori = (r.get("kategori") or "").strip()
            if kategori not in VALID_CATEGORIES:
                print(f"  [seed] skipping invalid kategori: {kategori!r}")
                skipped += 1
                continue
            if varenummer in seen:
                # Two rows with the same key in one upsert make Postgres
                # reject the whole statement, which would fail the nightly
                # job before any scraping starts.
                print(f"  [seed] skipping duplicate varenummer: {varenummer!r}")
                skipped += 1
                continue
            seen.add(varenummer)
            rows.append({
                "varenummer": varenummer,
                "merke":      (r.get("merke") or "").strip(),
                "produkt":    (r.get("produkt") or "").strip(),
                "kategori":   kategori,
            })

    return rows, skipped


def seed():
    rows, skipped = load_rows()
    if skipped:
        print(f"  [seed] skipped {skipped} invalid rows")
    if not rows:
        # An empty CSV almost certainly means a broken file, not "no products".
        sys.exit(f"No valid products found in {CSV_PATH}")
    get_client().table("produkter").upsert(rows, on_conflict="varenummer").execute()
    print(f"Seeded {len(rows)} products from {CSV_PATH}")


if __name__ == "__main__":
    seed()
