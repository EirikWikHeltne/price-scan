"""Run-loop behaviour of the HTTP scrapers, with the network faked out."""
import run
from scrapers import boots
from scripts import seed_products


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
        "﻿varenummer,merke,produkt,kategori\n"
        "003051,PANODIL,TAB 500MG,Paracetamol\n"
        "003051,PANODIL,TAB 500MG,Paracetamol\n"
        "abc,X,Y,Paracetamol\n"
        "017833,IBUX,TAB 400MG,Nope\n"
        "017833,IBUX,TAB 400MG,Ibuprofen\n",
        encoding="utf-8",
    )
    rows, skipped = seed_products.load_rows(csv_file)
    assert [r["varenummer"] for r in rows] == ["003051", "017833"]
    assert skipped == 3
