"""Offline tests for the shared extraction helpers (no network, no browser)."""
import pytest

from scrapers._common import (
    code_variants, extract_jsonld_price, extract_price_from_html, extract_stock,
    fetch_price_browser, fetch_price_http, parse_price_text, safe_url,
)


@pytest.mark.parametrize("text, expected", [
    ("89,90 kr", 89.90),
    ("kr 89,-", 89.0),
    ("1 299,00 kr", 1299.0),
    ("1 299,50", 1299.50),
    ("Pris: 129.5", 129.5),
    ("0,00 kr", None),
    ("Ikke tilgjengelig", None),
    ("", None),
    (None, None),
])
def test_parse_price_text(text, expected):
    assert parse_price_text(text) == expected


def test_jsonld_price_wins_over_other_markup():
    html = """
      <script type="application/ld+json">
        {"@type": "Product", "offers": {"price": "149.00"}}
      </script>
      <span data-testid="price" content="9.99"></span>
    """
    assert extract_price_from_html(html) == 149.0


def test_jsonld_offer_list():
    html = '<script type="application/ld+json">[{"offers": [{"price": 59.9}]}]</script>'
    assert extract_price_from_html(html) == 59.9


def test_price_falls_back_to_testid_content():
    assert extract_price_from_html('<meta data-testid="product-price" content="79.00">') == 79.0


def test_no_price():
    assert extract_price_from_html("<html><body>Ingen treff</body></html>") is None


@pytest.mark.parametrize("text, expected", [
    ("Ikke på lager", False),
    ("Produktet er utsolgt", False),
    ('"availability": "OutOfStock"', False),
    ("Not in stock", False),
    ("På lager i nettbutikk", True),
    ('"availability":"InStock"', True),
    ("Ingen informasjon", None),
])
def test_extract_stock(text, expected):
    assert extract_stock(text) is expected


@pytest.mark.parametrize("code, expected", [
    ("051946", ["051946", "51946"]),
    ("51946", ["51946", "051946"]),
    ("802633", ["802633"]),
    ("", []),
    (None, []),
])
def test_code_variants(code, expected):
    assert code_variants(code) == expected


@pytest.mark.parametrize("href, expected", [
    ("/produkt-123p", "https://www.apotek1.no/produkt-123p"),
    ("https://apotek1.no/x", "https://apotek1.no/x"),
    ("https://evil.example/x", None),
    ("javascript:alert(1)", None),
    ("#top", None),
    (None, None),
])
def test_safe_url(href, expected):
    assert safe_url(href, "https://www.apotek1.no", "www.apotek1.no") == expected


@pytest.mark.parametrize("text, expected", [
    ("1.299,00 kr", 1299.0),      # dot as thousands separator
    ("12.345,50", 12345.50),
    ("1.299", 1.29),              # ambiguous without a decimal comma: unchanged
])
def test_parse_price_text_dot_thousands(text, expected):
    assert parse_price_text(text) == expected


@pytest.mark.parametrize("jsonld, expected", [
    ('{"@graph": [{"@type": "WebPage"}, {"@type": "Product", "offers": {"price": "89.00"}}]}', 89.0),
    ('{"offers": {"@type": "AggregateOffer", "lowPrice": "45.50"}}', 45.5),
    ('{"offers": {"price": "129,90"}}', 129.9),
    ('{"offers": [{"price": 0}, {"price": 59}]}', 59.0),   # skips a zero-priced offer
    ('{"offers": "see website"}', None),                   # non-dict offer must not raise
    ('{"offers": {"price": -5}}', None),
])
def test_jsonld_variants(jsonld, expected):
    html = f'<script type="application/ld+json">{jsonld}</script>'
    assert extract_jsonld_price(html) == expected


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


class _Session:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, timeout=None):
        return self._resp


_PRODUCT_HTML = (
    '<script type="application/ld+json">{"offers": {"price": "99.00"}}</script>'
    "<p>På lager</p>"
)


def test_fetch_price_http_ok():
    assert fetch_price_http(_Session(_Resp(200, _PRODUCT_HTML)), "u") == (99.0, True, False)


@pytest.mark.parametrize("status, gone", [(404, True), (410, True), (403, False), (503, False)])
def test_fetch_price_http_never_reads_error_pages(status, gone):
    # Error pages carry other products' prices; only 404/410 mean "moved".
    assert fetch_price_http(_Session(_Resp(status, _PRODUCT_HTML)), "u") == (None, None, gone)


class _Page:
    def __init__(self, status):
        self._status, self.closed = status, False

    def goto(self, url, timeout=None):
        return type("R", (), {"status": self._status})()

    def wait_for_selector(self, *a, **k): pass
    def query_selector(self, sel): return None
    def content(self): return '{"price": "42.00"} utsolgt'
    def close(self): self.closed = True

    def query_selector_all(self, sel):
        return []


class _Context:
    def __init__(self, status):
        self.page = _Page(status)

    def new_page(self):
        return self.page


def test_fetch_price_browser_skips_404_and_closes_page():
    ctx = _Context(404)
    assert fetch_price_browser(ctx, "u", "sel") == (None, None, True)
    assert ctx.page.closed


def test_fetch_price_browser_extracts_and_closes_page():
    ctx = _Context(200)
    assert fetch_price_browser(ctx, "u", "sel") == (42.0, False, False)
    assert ctx.page.closed
