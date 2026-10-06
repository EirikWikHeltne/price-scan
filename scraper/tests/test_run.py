"""Tests for the pre-insert sanitizing and API-response parsing."""
from datetime import datetime, timedelta, timezone

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
