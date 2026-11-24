"""Oda product matching, with the network faked out.

The search responses are trimmed copies of what oda.com/api/v1/search/
returned on 2026-11-24 — the complete painkiller range Oda sells.
"""
import pytest

from scrapers import oda


def _hit(pid, full_name, name_extra, price, brand=None, available=True):
    return {
        "id": pid, "full_name": full_name, "brand": brand, "name_extra": name_extra,
        "gross_price": price, "gross_unit_price": "1.49",
        "availability": {"is_available": available, "code": "available"},
        "front_url": f"https://oda.com/no/products/{pid}-slug/",
    }


PANODIL = _hit(3769, "Panodil 500mg", "20 stk", "29.80", "Panodil")
PARACET_TAB = _hit(608, "Paracet 500 mg Tablett", "Tablett, 20 stk", "44.90", "Paracet")
PARACET_AVLANG = _hit(37235, "Paracet 500 mg Avlang, drasjert", "Avlang, drasjert, 20 stk", "47.90", "Paracet")
PARACET_MIKSTUR = _hit(1125, "Paracet Mikstur, 24 mg / ml", "Mikstur, 24 mg / ml, 60 ml", "62.90", "Paracet")
PARACET_SUPP_250 = _hit(607, "Paracet 250 mg Stikkpille, 13-25kg", "Stikkpille, 13-25kg, 10 stk", "62.90", "Paracet")
PARACET_BRUS = _hit(69887, "Paracet 500mg brusetablett", "20 stk", "79.00", "Paracet")
PARACET_SUPP_125 = _hit(606, "Karo Pharma AS Paracet 125mg Stikkpille, 7-12kg", "Stikkpille, 7-12kg, 10 stk", "62.90", "Karo Pharma AS")
IBUX_TAB = _hit(615, "Ibux 200 mg Tabletter", "Tabletter, 20 stk", "59.90")
IBUX_KAPS = _hit(23742, "Karo Pharma AS Ibux 200mg Kapsler", "Kapsler, 20 stk", "89.90", "Karo Pharma AS")

SEARCH = {
    "PANODIL": [PANODIL],
    # Oda pads a brand search with other brands' products.
    "PARACET": [PARACET_TAB, PARACET_AVLANG, PARACET_MIKSTUR, PARACET_SUPP_250,
                PARACET_BRUS, PARACET_SUPP_125, PANODIL],
    "IBUX": [IBUX_TAB, IBUX_KAPS],
}


class FakeFetcher:
    """Stands in for the HTTP layer; answers like Oda's search API."""
    queries = []

    def get_json(self, url):
        query = url.split("q=")[1]
        FakeFetcher.queries.append(query)
        hits = SEARCH.get(query, [])
        return {"attributes": {"total_hits": len(hits)}, "products": hits, "categories": []}

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_oda(monkeypatch):
    FakeFetcher.queries = []
    monkeypatch.setattr(oda, "_Fetcher", FakeFetcher)
    monkeypatch.setattr(oda.time, "sleep", lambda _: None)


def _prod(pid, varenummer, merke, produkt, **kw):
    return {"id": pid, "varenummer": varenummer, "merke": merke, "produkt": produkt, **kw}


def _prices(products):
    rows, resolved = oda.run(products)
    return {p["varenummer"]: r["pris"] for p, r in zip(products, rows)}, resolved


def test_products_oda_does_not_sell_get_no_price():
    # The two products from the bug report. Oda sells a Panodil and two Ibux,
    # but not Panodil Zapp and no 400 mg Ibux — a near miss must not be used.
    prices, resolved = _prices([
        _prod(1, "003051", "PANODIL", "TAB 500MG 20ENPAC ZAPP"),
        _prod(2, "017833", "IBUX", "TAB 400MG 10ENPAC"),
        _prod(3, "160308", "PARACET", "TAB 500MG 10ENPAC"),   # Oda has 20-packs only
        _prod(4, "171199", "PARACET", "SUPP 500MG 10STK"),    # wrong strength
        _prod(5, "526749", "PINEX", "TAB 500MG 20ENPAC"),     # brand not sold
        _prod(6, "086757", "PARACETAMOL NORFRI", "TAB 500MG 20ENPAC"),
    ])
    assert set(prices.values()) == {None}
    assert resolved == {}


def test_matching_products_get_their_own_price():
    prices, resolved = _prices([
        _prod(1, "083621", "PANODIL", "TAB 500MG 20ENPAC"),
        _prod(2, "517128", "PARACET", "TAB 500MG 20ENPAC"),
        _prod(3, "489492", "PARACET", "BRUSETA 500MG 20STK"),
        _prod(4, "106383", "PARACET", "MIKSTUR 24MG/ML 60ML"),
        _prod(5, "084970", "PARACET", "SUPP 250MG 10STK"),
        _prod(6, "503078", "PARACET", "SUPP 125MG 10STK"),
        _prod(7, "153569", "IBUX", "TAB 200MG 20ENPAC"),
        _prod(8, "095352", "IBUX", "KAPS 200MG 20ENPAC"),
    ])
    assert prices == {
        "083621": 29.80, "517128": 44.90, "489492": 79.00, "106383": 62.90,
        "084970": 62.90, "503078": 62.90, "153569": 59.90, "095352": 89.90,
    }
    assert resolved["083621"] == "https://oda.com/no/products/3769-slug/"
    assert resolved["095352"] == "https://oda.com/no/products/23742-slug/"
    # One search per brand, not per product.
    assert sorted(FakeFetcher.queries) == ["IBUX", "PANODIL", "PARACET"]


def test_cached_url_is_never_trusted_without_a_match():
    # The old scraper cached whatever link came first on the search page,
    # e.g. the "discounts" menu entry or another product.
    rows, resolved = oda.run([
        _prod(1, "003051", "PANODIL", "TAB 500MG 20ENPAC ZAPP",
              url_oda="https://oda.com/no/products/discounts/"),
        _prod(2, "083621", "PANODIL", "TAB 500MG 20ENPAC",
              url_oda="https://oda.com/no/products/615-ibux-200-mg-tabletter/"),
        _prod(3, "153569", "IBUX", "TAB 200MG 20ENPAC",
              url_oda="https://oda.com/no/products/615-slug/"),
    ])
    assert [r["pris"] for r in rows] == [None, 29.80, 59.90]
    # Only the wrong cached URL of a matched product is replaced; a correct
    # one is not rewritten.
    assert resolved == {"083621": "https://oda.com/no/products/3769-slug/"}


def test_stock_comes_from_the_matched_product():
    SEARCH["PANODIL"] = [dict(PANODIL, availability={"is_available": False})]
    try:
        rows, _ = oda.run([_prod(1, "083621", "PANODIL", "TAB 500MG 20ENPAC")])
    finally:
        SEARCH["PANODIL"] = [PANODIL]
    assert rows == [{"produkt_id": 1, "butikk": "oda", "pris": 29.80, "pa_lager": False}]


def test_failed_search_yields_no_price(monkeypatch):
    monkeypatch.setattr(FakeFetcher, "get_json", lambda self, url: None)
    rows, resolved = oda.run([_prod(1, "083621", "PANODIL", "TAB 500MG 20ENPAC")])
    assert rows == [{"produkt_id": 1, "butikk": "oda", "pris": None, "pa_lager": None}]
    assert resolved == {}


@pytest.mark.parametrize("merke, produkt, hit, expected", [
    ("PARACET", "TAB 500MG 20ENPAC", PARACET_BRUS, False),      # other form
    ("PARACET", "BRUSETA 500MG 20STK", PARACET_AVLANG, False),  # form not stated
    ("PARACET", "TAB 500MG 20ENPAC", PARACET_AVLANG, True),     # plain tablet
    ("PARACET", "TAB 500MG 20ENPAC", PANODIL, False),           # other brand
    ("PARACET", "MIKSTUR 24MG/ML 100ML", PARACET_MIKSTUR, False),
    ("IBUX", "TAB 200MG 20ENPAC", _hit(1, "Ibux 1200 mg Tabletter", "20 stk", "9"), False),
    ("IBUX", "TAB 200MG 20ENPAC", _hit(1, "Ibux 200 mg Tabletter", "120 stk", "9"), False),
])
def test_matches(merke, produkt, hit, expected):
    assert bool(oda.matches({"merke": merke, "produkt": produkt}, hit)) is expected
