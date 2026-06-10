"""Shared helpers used by multiple scrapers."""

def code_variants(code: str) -> list[str]:
    """Return search variants for product codes.

    Some retailers index product codes without leading zeros. Keep the
    original code first, then add a zero-stripped variant if different.
    """
    value = str(code or "").strip()
    if not value:
        return []
    variants = [value]
    stripped = value.lstrip("0")
    if stripped and stripped != value:
        variants.append(stripped)
    # Nordic varenummer are 6 digits, but some sources drop leading zeros
    # (e.g. "86757" for "086757"), so add the zero-padded form as well.
    if value.isdigit() and len(value) < 6:
        variants.append(value.zfill(6))
    return variants


def extract_stock(text: str) -> bool | None:
    """Detect stock status from page text.

    Order matters: out-of-stock indicators must be checked before in-stock
    ones, because Norwegian "ikke på lager" (not in stock) contains the
    substring "på lager" (in stock), and English "not in stock" contains
    "in stock". A naive `"på lager" in text` check returns True for both.
    """
    lower = text.lower()
    if (
        "ikke på lager" in lower
        or "utsolgt" in lower
        or "not in stock" in lower
        or "out of stock" in lower
        or '"outofstock"' in lower
        or '"out_of_stock"' in lower
    ):
        return False
    if (
        "på lager" in lower
        or "in stock" in lower
        or '"instock"' in lower
        or '"in_stock":true' in lower
    ):
        return True
    return None
