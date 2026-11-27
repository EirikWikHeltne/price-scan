"""
Rebuilds products.csv from the category-tree product list (an .xlsx workbook).

  pip install openpyxl
  python scripts/import_product_list.py path/to/produktliste.xlsx

The workbook must have a sheet with these columns (the largest such sheet is
used): Kategori, Nivå 1, Nivå 2, Nivå 3, Artikkelnummer, EAN, Produsent,
Merke, Produkt, and a "Karo, egne merker eller andre" column.

Products that are already in products.csv keep their varenummer exactly as it
is written there (the database key, so the price history stays attached) and
keep their product name when the brand is unchanged. Products that are in
products.csv but not in the workbook are left out; seed_products.py then
stops tracking them without deleting their history.
"""
import csv
import os
import re
import sys

CSV_PATH = os.path.join(os.path.dirname(__file__), "products.csv")

FIELDS = [
    "varenummer", "ean", "merke", "produkt", "produsent", "segment",
    "kategori", "niva1", "niva2", "niva3",
]

# Header prefix (lower case) -> our field name.
_HEADERS = {
    "kategori": "kategori",
    "nivå 1": "niva1",
    "nivå 2": "niva2",
    "nivå 3": "niva3",
    "artikkelnummer": "varenummer",
    "ean": "ean",
    "produsent": "produsent",
    "merke": "merke",
    "produkt": "produkt",
    "karo": "segment",
}

_SEGMENTS = {"karo": "Karo", "egne merker": "Egne merker", "andre": "Andre"}

# Brand names the workbook cuts short.
_BRAND_FIXES = {"PARACETAMOL NORF": "PARACETAMOL NORFRI"}


def _clean(value) -> str:
    """Cell value as single-spaced text (the workbook has non-breaking spaces)."""
    return re.sub(r"\s+", " ", str(value if value is not None else "").replace("\xa0", " ")).strip()


def _key(text: str) -> str:
    """Letters and digits only, so "A-DERMA" and "ADERMA" compare equal."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _initials(brand: str) -> str:
    """"LA ROCHE POSAY" -> "LRP"."""
    return "".join(w[0] for w in re.findall(r"[A-Z0-9]+", brand.upper()))


def strip_brand(name: str, brand: str) -> str:
    """"ACO BODY LOTION 200ML" -> "BODY LOTION 200ML" for brand ACO.

    The brand is shown in its own column, so it is dropped from the front of
    the name when the name starts with it, spelled out or as initials ("LRP
    LIPIKAR ..." for LA ROCHE POSAY). Otherwise the name is kept whole.
    """
    target = _key(brand)
    words = name.split()
    initials = _initials(brand)
    if len(words) > 1 and len(initials) > 1 and _key(words[0]) == initials:
        return " ".join(words[1:])
    for i in range(1, len(words)):
        head = _key("".join(words[:i]))
        if head == target:
            return " ".join(words[i:])
        if not target.startswith(head):
            break
    return name


def product_name(file_name: str, brand: str, old: dict | None) -> str:
    """The name to store: the existing one when the brand still fits it."""
    if old:
        old_brand, new_brand = _key(old["merke"]), _key(brand)
        if old_brand.startswith(new_brand):
            # "FLUX JR" filed under FLUX: keep the "JR" with the name.
            rest = old_brand[len(new_brand):]
            return f"{rest} {old['produkt']}".strip() if rest else old["produkt"]
        if new_brand.startswith(old_brand) or old_brand == _initials(brand):
            return old["produkt"]
    return strip_brand(file_name, brand)


def _find_table(workbook):
    """(sheet, header_row_number, {column_index: field}) for the product sheet."""
    best = None
    for sheet in workbook:
        for row_no, row in enumerate(sheet.iter_rows(max_row=15, values_only=True), start=1):
            columns = {}
            for idx, cell in enumerate(row):
                text = _clean(cell).lower()
                for prefix, field in _HEADERS.items():
                    if text.startswith(prefix) and field not in columns.values():
                        columns[idx] = field
                        break
            if set(columns.values()) == set(_HEADERS.values()):
                if best is None or sheet.max_row > best[0].max_row:
                    best = (sheet, row_no, columns)
                break
    if best is None:
        sys.exit("No sheet with the expected product columns was found")
    return best


def read_workbook(path: str) -> list[dict]:
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet, header_row, columns = _find_table(workbook)
    rows = []
    for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        rec = {field: _clean(row[idx]) if idx < len(row) else "" for idx, field in columns.items()}
        if rec["varenummer"]:
            rows.append(rec)
    return rows


def read_existing(path: str = CSV_PATH) -> dict:
    """Current products.csv keyed by 6-digit varenummer."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {
            r["varenummer"].strip().zfill(6): {k: (v or "").strip() for k, v in r.items()}
            for r in csv.DictReader(f) if (r.get("varenummer") or "").strip()
        }


def build_rows(source: list[dict], existing: dict) -> tuple[list[dict], list[str]]:
    """Rows for products.csv, plus the problems that made a row be left out."""
    rows, problems, seen = [], [], set()
    for rec in source:
        number = rec["varenummer"]
        if not re.fullmatch(r"\d{1,6}", number):
            problems.append(f"invalid varenummer {number!r}")
            continue
        number = number.zfill(6)
        if number in seen:
            problems.append(f"duplicate varenummer {number}")
            continue
        seen.add(number)
        if not rec["kategori"] or not rec["merke"] or not rec["produkt"]:
            problems.append(f"{number}: missing kategori, merke or produkt")
            continue
        old = existing.get(number)
        brand = _BRAND_FIXES.get(rec["merke"], rec["merke"])
        segment = next(
            (v for k, v in _SEGMENTS.items() if rec["segment"].lower().startswith(k)), "Andre"
        )
        rows.append({
            "varenummer": old["varenummer"] if old else number,
            "ean": rec["ean"] if re.fullmatch(r"\d{8,14}", rec["ean"]) else "",
            "merke": brand,
            "produkt": product_name(rec["produkt"], brand, old),
            "produsent": rec["produsent"],
            "segment": segment,
            "kategori": rec["kategori"],
            "niva1": rec["niva1"],
            "niva2": rec["niva2"],
            "niva3": rec["niva3"],
        })
    return rows, problems


def main(xlsx_path: str, csv_path: str = CSV_PATH):
    existing = read_existing(csv_path)
    rows, problems = build_rows(read_workbook(xlsx_path), existing)
    for problem in problems:
        print(f"  [import] skipped: {problem}")
    if not rows:
        sys.exit("No products found in the workbook; products.csv left unchanged")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    kept = {r["varenummer"].zfill(6) for r in rows}
    dropped = sorted(set(existing) - kept)
    print(f"Wrote {len(rows)} products to {csv_path}")
    print(f"  {len(kept & set(existing))} already tracked, {len(kept - set(existing))} new")
    if dropped:
        print(f"  {len(dropped)} tracked products are not in the workbook and were left out:")
        for number in dropped:
            old = existing[number]
            print(f"    {old['varenummer']} {old['merke']} {old['produkt']}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
