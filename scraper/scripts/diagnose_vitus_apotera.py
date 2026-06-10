"""One-off CI diagnostic for vitusapotek/apotera price-fetch failures.

Round 2: validates the fixed scraper logic end-to-end and probes Apotera's
search markup + Magento GraphQL endpoint.
"""
import os, re, sys, json, requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

print("=" * 70)
print("PART 1: VITUSAPOTEK — fixed sitemap index")
print("=" * 70)
from scrapers import vitusapotek

index = vitusapotek._build_sitemap_index()
fail_codes = ["804410", "836717", "904683", "922866", "806289", "823877",
              "051946", "927740", "815568", "912155"]
for code in fail_codes:
    print(f"  {code}: {index.get(code)}")

print()
print("PART 1b: VITUSAPOTEK — price extraction on new-format URLs (Playwright)")
from playwright.sync_api import sync_playwright

test_urls = [(c, index[c]) for c in fail_codes if index.get(c)][:4]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage"])
    ctx = browser.new_context(user_agent=UA, locale="nb-NO",
                              timezone_id="Europe/Oslo")
    ctx.add_init_script(vitusapotek._STEALTH)
    for code, url in test_urls:
        page = ctx.new_page()
        try:
            resp = page.goto(url, timeout=20000)
            print(f"  -- {code} {url}")
            print(f"     nav status: {resp.status if resp else None}")
            try:
                page.wait_for_selector(
                    "script[type='application/ld+json'], [class*='price'], [class*='Price']",
                    timeout=5000)
            except Exception:
                print("     (no price/ld+json selector within 5s)")
            pris = vitusapotek._extract_price(page)
            match = vitusapotek._page_matches_varenummer(page, code)
            html = page.content()
            ld = len(re.findall(r"application/ld\+json", html))
            print(f"     extracted price: {pris}  matches_varenummer: {match}  "
                  f"ld+json blocks: {ld}")
            if pris is None:
                for m in re.finditer(r'"price"\s*:\s*"?[\d.,]+"?', html):
                    print(f"     price-key ctx: {html[max(0,m.start()-80):m.end()+20]!r}")
                    break
                cls = set(re.findall(r'class="([^"]*[Pp]rice[^"]*)"', html))
                print(f"     price-ish classes: {list(cls)[:10]}")
        except Exception as e:
            print(f"  -- {code} EXCEPTION {e!r}")
        page.close()
    ctx.close()
    browser.close()

print()
print("=" * 70)
print("PART 2: APOTERA — GraphQL probe (Magento 2)")
print("=" * 70)
ABASE = "https://www.apotera.no"

def gql(query, label):
    try:
        r = requests.post(f"{ABASE}/graphql", json={"query": query},
                          headers={**HEADERS, "Content-Type": "application/json"},
                          timeout=15)
        body = r.text[:1500]
        print(f"  {label}: HTTP {r.status_code}")
        print(f"    {body}")
    except Exception as e:
        print(f"  {label}: EXCEPTION {e!r}")

gql('{ products(filter: {sku: {eq: "051946"}}) { items { sku name url_key '
    'stock_status price_range { minimum_price { final_price { value } } } } } }',
    "sku eq 051946")
gql('{ products(search: "paracet", pageSize: 3) { items { sku name url_key '
    'stock_status price_range { minimum_price { final_price { value } } } } } }',
    "search paracet")
gql('{ products(filter: {sku: {eq: "807862"}}) { items { sku name url_key '
    'stock_status price_range { minimum_price { final_price { value } } } } } }',
    "sku eq 807862")

print()
print("PART 2b: APOTERA — search result markup")
for q in ["paracet", "051946"]:
    try:
        r = requests.get(f"{ABASE}/catalogsearch/result/?q={q}",
                         headers=HEADERS, timeout=15)
        html = r.text
        print(f"  -- q={q}: HTTP {r.status_code} len={len(html)}")
        hits = sorted(set(re.findall(r'href="(https?://www\.apotera\.no/[^"]*paracet[^"]*)"',
                                     html, re.I)))
        print(f"     hrefs containing 'paracet': {hits[:8]}")
        for marker in ['class="search results"', 'product-item', 'data-product',
                       'products-grid', 'klevu', 'algolia', 'instantsearch',
                       'searchResult']:
            print(f"     marker {marker!r}: {html.count(marker)}")
        i = html.find('search results')
        if i == -1:
            i = html.find('result')
        print(f"     snippet around results marker:\n{html[i-200:i+1200]!r}")
    except Exception as e:
        print(f"  -- q={q} EXCEPTION {e!r}")

print()
print("PART 2c: APOTERA — end-to-end with fixed module (2 products from DB)")
try:
    from db import get_active_products
    from scrapers import apotera
    products = get_active_products()
    sample = [p for p in products if p["varenummer"] in ("051946", "807862", "840110")]
    rows, resolved = apotera.run(sample)
    print(f"  rows: {rows}")
    print(f"  resolved: {resolved}")
except Exception as e:
    print(f"  DB/module error: {e!r}")

print("\nDONE")
