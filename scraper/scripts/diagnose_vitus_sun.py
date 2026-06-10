"""One-off CI diagnostic: why do Sun products fail on vitusapotek?

Round 2. Round 1 showed:
  - robots.txt advertises Sitemap: /api/be/sitemap/sitemap.xml (not probed yet)
  - /sitemap/sitemap.xml is a 7-entry sitemapindex (matches the "7 URLs" prod log)
  - search?q=<varenummer> returns only promoted products -> search is dead
  - the site calls /api/products/stock?ids=<varenummer,...> -> JSON APIs keyed
    by varenummer exist

This round probes the real sitemap, its product sub-sitemaps, Sun coverage,
a known Sun product page (993232 LRP ANTI-SHINE MIST), and candidate JSON
price APIs.
"""
import csv
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.sync_api import sync_playwright

from scrapers.vitusapotek import BASE, _REQ_HEADERS, _STEALTH, _UA, _extract_price

OUT = os.path.join(os.path.dirname(__file__), "..", "diag_out")
os.makedirs(OUT, exist_ok=True)

SUN = [
    r["varenummer"]
    for r in csv.DictReader(open(os.path.join(os.path.dirname(__file__), "products.csv")))
    if r["kategori"] == "Sun"
]

PRODUCT_PAGE = (
    BASE
    + "/sol-fritid-og-reise/solkrem/solkrem-spray/"
    + "la-roche-posay-anthelios-anti-shine-solmist-spf50-75-ml-993232"
)


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def get(url, **kw):
    return requests.get(url, headers=_REQ_HEADERS, timeout=25, **kw)


section("1. real sitemap from robots.txt: /api/be/sitemap/sitemap.xml")
locs = []
try:
    r = get(f"{BASE}/api/be/sitemap/sitemap.xml")
    print(f"  HTTP {r.status_code}, {len(r.text)} bytes")
    print(f"  head: {r.text[:600]!r}")
    locs = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", r.text)
    print(f"  {len(locs)} <loc> entries:")
    for l in locs[:20]:
        print(f"    {l}")
except Exception as e:
    print(f"  EXC {e}")

section("2. product sub-sitemaps: Sun coverage")
index = {}
for sub in locs:
    if "product" not in sub.lower():
        continue
    try:
        r = get(sub)
        urls = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", r.text)
        print(f"  {sub}: HTTP {r.status_code}, {len(urls)} URLs")
        for u in urls[:3]:
            print(f"    e.g. {u}")
        for u in urls:
            m = re.search(r"-(\d{5,10})/?$", u.split("?")[0])
            if m:
                index.setdefault(m.group(1), u)
            elif "/p/" in u:
                for token in re.findall(r"\d{5,10}", u):
                    index.setdefault(token, u)
    except Exception as e:
        print(f"  {sub}: EXC {e}")
print(f"\n  total indexed: {len(index)}")
hits = [v for v in SUN if v in index or v.lstrip("0") in index]
print(f"  Sun products: {len(SUN)}, found in index: {len(hits)}")
missing = [v for v in SUN if v not in index and v.lstrip("0") not in index]
print(f"  missing: {missing[:15]}")
for v in hits[:5]:
    print(f"    {v} -> {index.get(v) or index.get(v.lstrip('0'))}")

section("3. plain-requests fetch of a Sun product page (993232)")
try:
    r = get(PRODUCT_PAGE)
    print(f"  HTTP {r.status_code}, {len(r.text)} bytes")
    with open(os.path.join(OUT, "product_993232_requests.html"), "w") as f:
        f.write(r.text)
    for m in re.finditer(r'"price"\s*:\s*"?[\d.,]+"?', r.text):
        print(f"    price match: {m.group(0)}")
    n_ld = len(re.findall(r'application/ld\+json', r.text))
    print(f"  ld+json blocks: {n_ld}")
except Exception as e:
    print(f"  EXC {e}")

section("4. candidate JSON APIs (plain requests)")
ids = "993232,800227,897789,982569,051946"
for path in [
    f"/api/products/stock?ids={ids}",
    f"/api/reviews/summaries?ids={ids}",
    f"/api/products?ids={ids}",
    f"/api/products/prices?ids={ids}",
    f"/api/products/993232",
    f"/api/search/suggestions?q=800227",
    f"/api/search/suggestions?query=800227",
    f"/api/search/suggestions?q=cosmica%20sun%20lotion",
]:
    try:
        r = get(BASE + path)
        body = r.text[:400].replace("\n", " ")
        print(f"  {path}\n    HTTP {r.status_code}, {len(r.text)} bytes: {body!r}")
    except Exception as e:
        print(f"  {path}: EXC {e}")

section("5. Playwright on the Sun product page: XHRs + price extraction")
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
    )
    context = browser.new_context(user_agent=_UA, locale="nb-NO", timezone_id="Europe/Oslo")
    context.add_init_script(_STEALTH)
    page = context.new_page()
    api_calls = []
    page.on(
        "request",
        lambda req: api_calls.append(f"{req.method} {req.url}")
        if req.resource_type in ("xhr", "fetch")
        else None,
    )
    try:
        resp = page.goto(PRODUCT_PAGE, timeout=25000)
        page.wait_for_timeout(5000)
        html = page.content()
        with open(os.path.join(OUT, "product_993232_browser.html"), "w") as f:
            f.write(html)
        print(f"  HTTP {resp.status if resp else '?'}, title={page.title()!r}")
        print(f"  _extract_price -> {_extract_price(page)}")
        for el in page.query_selector_all("script[type='application/ld+json']"):
            txt = el.inner_text()
            print(f"  ld+json ({len(txt)}b): {txt[:400]}")
        print("  xhr/fetch (vitusapotek only):")
        for c in api_calls:
            if "vitusapotek" in c:
                print(f"    {c}")
    except Exception as e:
        print(f"  EXC {e}")
    page.close()
    context.close()
    browser.close()

print("\nDONE")
