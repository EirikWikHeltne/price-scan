"""Tests for the pre-insert sanitizing and API-response parsing."""
from datetime import datetime, timedelta, timezone
import pytest

from run import _sanitize
from scrapers.vitusapotek import _extract_price, _extract_stock


def _row(pris):
    return {"produkt_id": 1, "butikk": "boots", "pris": pris, "pa_lager": True}


def test_sanitize_keeps_valid_prices_and_rounds():
    rows = _sanitize([_row(89.9), _row("129.499"), _row(None)])
    assert [r["pris"] for r in rows] == [89.9, 129.5, None]


def test_sanitize_drops_values_that_would_overflow_or_are_bogus():
    # numeric(8,2) overflows at 10^6 and would fail the whole insert chunk
    rows = _sanitize([_row(12345678), _row(0), _row(-5), _row("abc")])
    assert all(r["pris"] is None for r in rows)
    assert all(r["pa_lager"] is True for r in rows)


def _future(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def test_vitus_campaign_price_while_active():
    item = {"price": {"amount": 100, "discountedAmount": 79, "discountedEndDate": _future(3)}}
    assert _extract_price(item) == 79.0


def test_vitus_list_price_after_campaign_ends():
    item = {"price": {"amount": 100, "discountedAmount": 79, "discountedEndDate": _future(-1)}}
    assert _extract_price(item) == 100.0


def test_vitus_without_price():
    assert _extract_price({"isWithoutPrice": True, "price": {"amount": 100}}) is None


def test_vitus_stock_mapping():
    assert _extract_stock({"statusCode": "in-stock"}) is True
    assert _extract_stock({"statusCode": "sold-out-online"}) is False
    assert _extract_stock({"statusCode": "something-new"}) is None
    assert _extract_stock(None) is None


def _stub_run(monkeypatch, refresh):
    import run as run_mod
    inserted = []
    monkeypatch.setattr(run_mod, "SCRAPERS", {})
    monkeypatch.setattr(run_mod, "get_active_products", lambda: [])
    monkeypatch.setattr(run_mod, "bulk_insert_prices", inserted.append)
    monkeypatch.setattr(run_mod, "refresh_prishistorikk_daglig", refresh)
    return run_mod, inserted


def test_run_refreshes_daily_history_after_insert(monkeypatch):
    calls = []
    run_mod, inserted = _stub_run(monkeypatch, lambda: calls.append(1))
    with pytest.raises(SystemExit) as exc:
        run_mod.run()
    assert exc.value.code == 0
    assert inserted and calls == [1]


def test_run_survives_failed_refresh(monkeypatch):
    def boom():
        raise RuntimeError("timeout")
    run_mod, inserted = _stub_run(monkeypatch, boom)
    with pytest.raises(SystemExit) as exc:
        run_mod.run()
    assert exc.value.code == 0
    assert inserted
