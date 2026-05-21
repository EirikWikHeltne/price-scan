"""Shared helpers used by multiple scrapers."""


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
