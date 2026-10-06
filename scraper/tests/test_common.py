"""Offline tests for the shared extraction helpers (no network, no browser)."""
import pytest

from scrapers._common import (
    code_variants, extract_price_from_html, extract_stock,
    parse_price_text, safe_url,
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
