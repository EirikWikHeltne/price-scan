"""Run-loop behaviour of the HTTP scrapers, with the network faked out."""
from datetime import datetime, timedelta, timezone

import run
from scrapers import boots
from scrapers._common import due_for_lookup
from scripts import import_product_list, seed_products


def _prod(**kw):
    return {"id": 1, "varenummer": "051946", **kw}


def test_boots_re_resolves_a_cached_url_that_is_gone(monkeypatch):
    pages = {"https://www.boots.no/old-051946": (None, None, True),
             "https://www.boots.no/new-051946": (79.0, True, False)}
    monkeypatch.setattr(boots, "fetch_price", lambda s, url: pages[url])
    monkeypatch.setattr(boots, "search_url", lambda s, vn: "https://www.boots.no/new-051946")
    monkeypatch.setattr(boots.time, "sleep", lambda _: None)

    rows, resolved = boots.run([_prod(url_boots="https://www.boots.no/old-051946")])

    assert rows == [{"produkt_id": 1, "butikk": "boots", "pris": 79.0, "pa_lager": True}]
    assert resolved == {"051946": "https://www.boots.no/new-051946"}


def test_boots_keeps_cached_url_on_transient_failure(monkeypatch):
    searched = []
    monkeypatch.setattr(boots, "fetch_price", lambda s, url: (None, None, False))
    monkeypatch.setattr(boots, "search_url", lambda s, vn: searched.append(vn))
    monkeypatch.setattr(boots.time, "sleep", lambda _: None)

    rows, resolved = boots.run([_prod(url_boots="https://www.boots.no/old-051946")])

    assert rows[0]["pris"] is None
    assert resolved == {} and searched == []


def test_report_flags_dead_retailers(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    run._report({"boots": (0, 10), "oda": (5, 10)}, crashed=["apotek1"], stuck=["farmasiet"])
    out = capsys.readouterr().out
    assert "::warning::boots: 0/10 prices found" in out
    assert "::error::apotek1: scraper crashed" in out
    assert "::error::farmasiet: scraper timed out" in out
    assert "::warning::oda" not in out


def test_seed_skips_duplicates_and_reads_bom(tmp_path):
    csv_file = tmp_path / "p.csv"
    csv_file.write_text(
        "﻿varenummer,ean,merke,produkt,produsent,segment,kategori,niva1,niva2,niva3\n"
        "003051,5054563077684,PANODIL,TAB 500MG,HALEON,Andre,Smerte,General pain,Paracetamol,\n"
        "003051,5054563077684,PANODIL,TAB 500MG,HALEON,Andre,Smerte,General pain,Paracetamol,\n"
        "abc,,X,Y,Z,Andre,Smerte,,,\n"
        "017833,,IBUX,TAB 400MG,KARO HEALTHCARE,Karo,Nope,,,\n"
        "017833,,IBUX,TAB 400MG,KARO HEALTHCARE,Karo,Smerte,NSAIDs,Ibuprofen,\n",
        encoding="utf-8",
    )
    rows, skipped = seed_products.load_rows(csv_file)
    assert [r["varenummer"] for r in rows] == ["003051", "017833"]
    assert skipped == 3
    assert rows[0]["niva2"] == "Paracetamol" and rows[0]["ean"] == "5054563077684"
    # Empty cells become NULL, and every row has the same keys.
    assert rows[0]["niva3"] is None and rows[1]["ean"] is None
    assert set(rows[0]) == set(rows[1])


def test_shipped_product_list_is_valid():
    rows, skipped = seed_products.load_rows()
    assert skipped == 0
    assert len(rows) > 4000
    assert {r["kategori"] for r in rows} == seed_products.VALID_CATEGORIES
    assert all(r["merke"] and r["produkt"] and r["niva1"] for r in rows)
    assert {r["segment"] for r in rows} == {"Karo", "Egne merker", "Andre"}


class _FakeTable:
    """Records upserts/updates; rejects payloads with columns it lacks."""

    def __init__(self, columns, active):
        self.columns, self.active = columns, active
        self.upserts, self.deactivated = [], []
        self._op = None

    def upsert(self, rows, on_conflict=None):
        self._op = ("upsert", rows)
        return self

    def update(self, values):
        self._op = ("update", values)
        return self

    def in_(self, _col, values):
        self._op = ("update_in", values)
        return self

    def select(self, *_):
        self._op = ("select", None)
        return self

    def eq(self, *_):    return self
    def order(self, *_): return self

    def range(self, start, end):
        self._op = ("select", (start, end))
        return self

    def execute(self):
        kind, arg = self._op
        if kind == "upsert":
            if any(set(r) - self.columns for r in arg):
                err = Exception("Could not find the 'niva1' column")
                err.code = "PGRST204"
                raise err
            self.upserts.append(arg)
        elif kind == "update_in":
            self.deactivated.extend(arg)
        elif kind == "select":
            start, end = arg
            self.data = [{"varenummer": vn} for vn in self.active[start:end + 1]]
        return self


class _FakeClient:
    def __init__(self, table):
        self._table = table

    def table(self, _):
        return self._table


def _seed_rows(n):
    return [
        {"varenummer": f"{i:06d}", "merke": "M", "produkt": "P", "kategori": "Smerte",
         **{f: None for f in seed_products.TREE_FIELDS}}
        for i in range(n)
    ]


def test_seed_upserts_in_chunks():
    table = _FakeTable(set(seed_products.BASE_FIELDS + seed_products.TREE_FIELDS), [])
    assert seed_products.upsert_products(_FakeClient(table), _seed_rows(1200)) is True
    assert [len(c) for c in table.upserts] == [500, 500, 200]


def test_seed_falls_back_when_migration_has_not_run(capsys):
    table = _FakeTable(set(seed_products.BASE_FIELDS), [])
    assert seed_products.upsert_products(_FakeClient(table), _seed_rows(3)) is False
    assert len(table.upserts) == 1
    assert set(table.upserts[0][0]) == set(seed_products.BASE_FIELDS)
    assert "supabase_migration_category_tree.sql" in capsys.readouterr().out


def test_seed_deactivates_products_removed_from_the_csv():
    rows = _seed_rows(10)
    table = _FakeTable(set(), [r["varenummer"] for r in rows] + ["900001", "900002"])
    assert seed_products.deactivate_removed(_FakeClient(table), rows) == 2
    assert table.deactivated == ["900001", "900002"]


def test_seed_refuses_to_deactivate_most_of_the_list(capsys):
    rows = _seed_rows(2)
    table = _FakeTable(set(), [r["varenummer"] for r in rows] + [f"9{i:05d}" for i in range(10)])
    assert seed_products.deactivate_removed(_FakeClient(table), rows) == 0
    assert table.deactivated == []
    assert "none were deactivated" in capsys.readouterr().out


# --- lookups for products without a known page ------------------------------

_NOW = datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)


def test_new_product_is_looked_up_straight_away():
    prod = {"id": 1, "opprettet": (_NOW - timedelta(hours=5)).isoformat()}
    assert due_for_lookup(prod, _NOW) is True


def test_older_product_is_looked_up_once_per_cycle():
    old = (_NOW - timedelta(days=40)).isoformat()
    due = [
        day for day in range(14)
        if due_for_lookup({"id": 12345, "opprettet": old}, _NOW + timedelta(days=day))
    ]
    assert len(due) == 2 and due[1] - due[0] == 7
    # Each night carries about a seventh of the products.
    tonight = sum(due_for_lookup({"id": i, "opprettet": old}, _NOW) for i in range(700))
    assert tonight == 100


def test_boots_skips_search_for_product_not_due(monkeypatch):
    searched = []
    monkeypatch.setattr(boots, "due_for_lookup", lambda p: p["id"] == 2)
    monkeypatch.setattr(boots, "search_url", lambda s, vn: searched.append(vn))
    monkeypatch.setattr(boots.time, "sleep", lambda _: None)

    rows, resolved = boots.run([_prod(), {"id": 2, "varenummer": "999999"}])

    # Not due: no search and no row. Due but not found: a row without a price.
    assert searched == ["999999"]
    assert rows == [{"produkt_id": 2, "butikk": "boots", "pris": None, "pa_lager": None}]
    assert resolved == {}


# --- sharding ----------------------------------------------------------------

def test_shards_cover_every_product_exactly_once(monkeypatch):
    products = [{"id": i} for i in range(1, 101)]
    monkeypatch.setenv("SHARD_TOTAL", "8")
    seen = []
    for index in range(8):
        monkeypatch.setenv("SHARD_INDEX", str(index))
        seen.extend(p["id"] for p in run._shard(products))
    assert sorted(seen) == list(range(1, 101))


def test_no_shard_variables_means_all_products(monkeypatch):
    monkeypatch.delenv("SHARD_TOTAL", raising=False)
    monkeypatch.delenv("SHARD_INDEX", raising=False)
    products = [{"id": i} for i in range(5)]
    assert run._shard(products) == products


# --- importing the product list ------------------------------------------------

def test_import_strips_brand_from_product_name():
    strip = import_product_list.strip_brand
    assert strip("ACO BODY LOTION 200ML", "ACO") == "BODY LOTION 200ML"
    assert strip("ADERMA EXOMEGA BALM 200ML", "A-DERMA") == "EXOMEGA BALM 200ML"
    assert strip("LRP LIPIKAR BALM 200ML", "LA ROCHE POSAY") == "LIPIKAR BALM 200ML"
    assert strip("BABY APO1 BOX", "APOTEK1") == "BABY APO1 BOX"
    assert strip("COSMICA", "COSMICA") == "COSMICA"


def test_import_keeps_existing_key_and_name():
    source = [
        {"varenummer": "003051", "ean": "5054563077684", "merke": "PANODIL",
         "produkt": "PANODIL TAB ZAPP 500MG 20", "produsent": "HALEON",
         "segment": "Andre", "kategori": "Smerte", "niva1": "N1", "niva2": "N2", "niva3": ""},
        {"varenummer": "540973", "ean": "Mangler EAN", "merke": "PARACET",
         "produkt": "PARACET DUO TAB 500/65MG 20", "produsent": "KARO HEALTHCARE",
         "segment": "Karo", "kategori": "Smerte", "niva1": "N1", "niva2": "N2", "niva3": ""},
        {"varenummer": "999999", "ean": "", "merke": "ACO", "produkt": "ACO NEW 50ML",
         "produsent": "KARO HEALTHCARE", "segment": "Egne merker (PL)",
         "kategori": "Hudpleie", "niva1": "Body", "niva2": "", "niva3": ""},
        {"varenummer": "999999", "ean": "", "merke": "ACO", "produkt": "DUPLICATE",
         "produsent": "", "segment": "", "kategori": "Hudpleie", "niva1": "", "niva2": "", "niva3": ""},
    ]
    existing = {
        "003051": {"varenummer": "3051", "merke": "PANODIL", "produkt": "TAB 500MG 20ENPAC ZAPP"},
        "540973": {"varenummer": "540973", "merke": "PARACETDUO", "produkt": "TAB 500/65MG 20ENPAC"},
    }
    rows, problems = import_product_list.build_rows(source, existing)

    assert [(r["varenummer"], r["merke"], r["produkt"]) for r in rows] == [
        ("3051", "PANODIL", "TAB 500MG 20ENPAC ZAPP"),
        ("540973", "PARACET", "DUO TAB 500/65MG 20ENPAC"),
        ("999999", "ACO", "NEW 50ML"),
    ]
    assert [r["ean"] for r in rows] == ["5054563077684", "", ""]
    assert [r["segment"] for r in rows] == ["Andre", "Karo", "Egne merker"]
    assert problems == ["duplicate varenummer 999999"]
