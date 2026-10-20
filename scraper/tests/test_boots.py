"""Tests for Boots stale-URL re-resolution (network calls stubbed)."""
import pytest

from scrapers import boots

OLD = "https://www.boots.no/old-slug-806289"
NEW = "https://www.boots.no/new-slug-806289"


@pytest.fixture
def stub(monkeypatch):
    calls = {"search": 0}

    def install(pages, search_result):
        def fake_fetch(url):
            if pages.get(url) == 404:
                raise boots.PageGone(url)
            return pages.get(url, (None, None))

        def fake_search(_vn):
            calls["search"] += 1
            return search_result

        monkeypatch.setattr(boots, "fetch_price", fake_fetch)
        monkeypatch.setattr(boots, "search_url", fake_search)
        monkeypatch.setattr(boots.time, "sleep", lambda _s: None)
        return calls

    return install


def _prod(url=None):
    return {"id": 1, "varenummer": "806289", "url_boots": url}


def test_cached_url_is_used_without_searching(stub):
    calls = stub({OLD: (199.0, True)}, NEW)
    rows, resolved = boots.run([_prod(OLD)])
    assert rows[0]["pris"] == 199.0
    assert resolved == {}
    assert calls["search"] == 0


def test_stale_cached_url_is_re_resolved_and_saved(stub):
    stub({OLD: 404, NEW: (149.0, True)}, NEW)
    rows, resolved = boots.run([_prod(OLD)])
    assert rows[0]["pris"] == 149.0
    assert resolved == {"806289": NEW}


def test_stale_url_with_no_replacement_stays_empty(stub):
    stub({OLD: 404}, None)
    rows, resolved = boots.run([_prod(OLD)])
    assert rows[0]["pris"] is None
    assert resolved == {}


def test_search_returning_same_stale_url_is_not_refetched(stub):
    calls = stub({OLD: 404}, OLD)
    rows, resolved = boots.run([_prod(OLD)])
    assert rows[0]["pris"] is None
    assert resolved == {}
    assert calls["search"] == 1
