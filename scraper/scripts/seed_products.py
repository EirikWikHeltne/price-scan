"""
Seeds the produkter table from products.csv.
Run once after setup, or anytime the product list changes:
  python scripts/seed_products.py
"""
import sys, os, csv, re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_client

CSV_PATH = os.path.join(os.path.dirname(__file__), "products.csv")

VALID_CATEGORIES = {"Hudpleie", "Fotpleie", "Munnpleie", "Intimpleie", "Mage og tarm", "Smerte"}

# Columns every installation has, and the ones added by
# supabase_migration_category_tree.sql.
BASE_FIELDS = ("varenummer", "merke", "produkt", "kategori")
TREE_FIELDS = ("ean", "produsent", "segment", "niva1", "niva2", "niva3")

_CHUNK = 500


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
            row = {
                "varenummer": varenummer,
                "merke":      (r.get("merke") or "").strip(),
                "produkt":    (r.get("produkt") or "").strip(),
                "kategori":   kategori,
            }
            # Every row carries the same keys (PostgREST requires that of a
            # bulk upsert); an empty cell is stored as NULL.
            for field in TREE_FIELDS:
                row[field] = (r.get(field) or "").strip() or None
            rows.append(row)

    return rows, skipped


def _annotate(level, message):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level}::{message}")
    else:
        print(f"{level.upper()}: {message}")


def _upsert(client, rows):
    for i in range(0, len(rows), _CHUNK):
        client.table("produkter").upsert(rows[i:i + _CHUNK], on_conflict="varenummer").execute()


def upsert_products(client, rows):
    """Upsert all rows. Returns False if the category-tree columns are missing.

    Without the migration the products are still seeded with the original
    columns, so the nightly scrape keeps working; only the sub-levels wait.
    """
    try:
        _upsert(client, rows)
        return True
    except Exception as e:
        # PGRST204: a column in the payload does not exist in the table.
        if getattr(e, "code", None) != "PGRST204":
            raise
    _annotate(
        "warning",
        "produkter lacks the category-tree columns; seeded without sub-levels. "
        "Run supabase_migration_category_tree.sql in the Supabase SQL editor.",
    )
    _upsert(client, [{k: r[k] for k in BASE_FIELDS} for r in rows])
    return False


def _active_varenummer(client):
    found = []
    while True:
        page = (
            client.table("produkter").select("varenummer").eq("aktiv", True)
            .order("id").range(len(found), len(found) + 999).execute().data
        )
        found.extend(r["varenummer"] for r in page)
        if len(page) < 1000:
            return found


def deactivate_removed(client, rows):
    """Stop tracking active products that are no longer in the CSV.

    Their price history is kept. Nothing is ever switched back on here, so a
    product set to aktiv = false by hand stays off.
    """
    listed = {r["varenummer"] for r in rows}
    active = _active_varenummer(client)
    removed = [vn for vn in active if vn not in listed]
    if not removed:
        return 0
    if len(removed) > len(active) / 2:
        # More likely a damaged CSV than a real decision to drop half the list.
        _annotate(
            "error",
            f"{len(removed)} of {len(active)} active products are missing from "
            "products.csv; none were deactivated. Check the file.",
        )
        return 0
    for i in range(0, len(removed), 100):
        chunk = removed[i:i + 100]
        client.table("produkter").update({"aktiv": False}).in_("varenummer", chunk).execute()
    print(f"Deactivated {len(removed)} products that are no longer in the CSV")
    return len(removed)


def seed():
    rows, skipped = load_rows()
    if skipped:
        print(f"  [seed] skipped {skipped} invalid rows")
    if not rows:
        # An empty CSV almost certainly means a broken file, not "no products".
        sys.exit(f"No valid products found in {CSV_PATH}")
    client = get_client()
    upsert_products(client, rows)
    print(f"Seeded {len(rows)} products from {CSV_PATH}")
    deactivate_removed(client, rows)


if __name__ == "__main__":
    seed()
