"""One-off CI diagnostic for vitusapotek/apotera price-fetch failures.

Runs in GitHub Actions (which can reach the sites) and prints everything we
need to see what the scrapers actually receive: HTTP statuses, sitemap
contents, search-result pages and product-page HTML markers.
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

OUT = os.path.join(os.path.dirname(__file__), "..", "diag_out")
os.makedirs(OUT, exist_ok=True)


def dump(name, text):
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        f.write(text)
    print(f"    [dumped {name}, {len(text)} chars]")


def http_get(url, label):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        print(f"  GET {url} -> {r.status_code} len={len(r.text)} "
              f"ct={r.headers.get('content-type')} final={r.url}")
        return r
    except Exception as e:
        print(f"  GET {url} -> EXCEPTION {e!r}")
        return None


def html_markers(html):
    """Print the structural markers our extractors rely on."""
    soup_title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
    print(f"    title: {soup_title.group(1).strip()[:120] if soup_title else 'NONE'}")
    ld = re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S)
    print(f"    ld+json blocks: {len(ld)}")
    for blob in ld[:3]:
        print(f"      ld+json head: {blob.strip()[:300]}")
    print(f"    data-price-amount occurrences: {html.count('data-price-amount')}")
    print(f"    itemprop=price occurrences: {len(re.findall(r'itemprop=.price', html))}")
    for m in re.finditer(r'"price"\s*:\s*"?[\d.,]+"?', html):
        print(f"      price-key: {html[max(0, m.start()-60):m.end()+20]!r}")
        break
    print(f"    'captcha' in html: {'captcha' in html.lower()}, "
          f"'cloudflare' in html: {'cloudflare' in html.lower()}, "
          f"'incapsula/imperva': {('incapsula' in html.lower() or 'imperva' in html.lower())}")


# ---------------------------------------------------------------------------
print("=" * 70)
print("PART 1: VITUSAPOTEK sitemap discovery")
print("=" * 70)
VBASE = "https://www.vitusapotek.no"

r = http_get(f"{VBASE}/robots.txt", "robots")
robots_sitemaps = []
if r is not None and r.status_code == 200:
    for line in r.text.splitlines():
        if line.lower().startswith("sitemap:"):
            robots_sitemaps.append(line.split(":", 1)[1].strip())
    print(f"  robots.txt sitemap lines: {robots_sitemaps}")
    dump("vitus_robots.txt", r.text)

candidates = robots_sitemaps + [
    VBASE + p for p in [
        "/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
        "/sitemap/sitemap.xml", "/sitemaps/sitemap.xml", "/media/sitemap.xml",
    ]
]
seen = set()
for sm in candidates:
    if sm in seen:
        continue
    seen.add(sm)
    r = http_get(sm, "sitemap")
    if r is None or r.status_code != 200:
        continue
    locs = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", r.text)
    p_locs = [u for u in locs if "/p/" in u]
    is_index = "<sitemapindex" in r.text or ("<sitemap>" in r.text and "<loc>" in r.text)
    print(f"    index={is_index} locs={len(locs)} /p/-locs={len(p_locs)}")
    for u in locs[:15]:
        print(f"      loc: {u}")
    if is_index:
        for sub in locs:
            r2 = http_get(sub, "subsitemap")
            if r2 is None or r2.status_code != 200:
                continue
            locs2 = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", r2.text)
            p2 = [u for u in locs2 if "/p/" in u]
            print(f"      sub {sub}: locs={len(locs2)} /p/-locs={len(p2)} "
                  f"sample={locs2[:3]}")

print()
print("=" * 70)
print("PART 2: VITUSAPOTEK search + product page (Playwright)")
print("=" * 70)
from playwright.sync_api import sync_playwright

VITUS_FAIL_SEARCH = ["804410", "836717", "904683"]   # "no search result" in logs
VITUS_FAIL_PRICE = ["922866", "806289", "823877"]    # URL loads but price=None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage"])
    ctx = browser.new_context(user_agent=UA, locale="nb-NO",
                              timezone_id="Europe/Oslo")
    for code in VITUS_FAIL_SEARCH:
        print(f"  -- search q={code}")
        page = ctx.new_page()
        try:
            resp = page.goto(f"{VBASE}/search?q={code}", timeout=20000)
            print(f"    nav status: {resp.status if resp else None} url={page.url}")
            try:
                page.wait_for_selector("a[href*='/p/']", timeout=8000)
            except Exception:
                print("    no a[href*='/p/'] within 8s")
            links = page.query_selector_all("a[href]")
            hrefs = []
            for a in links[:400]:
                h = a.get_attribute("href") or ""
                if h and h not in hrefs:
                    hrefs.append(h)
            p_links = [h for h in hrefs if "/p/" in h]
            print(f"    total links={len(hrefs)} /p/ links={len(p_links)} sample={p_links[:5]}")
            print(f"    title={page.title()[:120]!r}")
            dump(f"vitus_search_{code}.html", page.content())
        except Exception as e:
            print(f"    EXCEPTION {e!r}")
        page.close()

    for code in VITUS_FAIL_PRICE:
        # We don't know cached URLs locally; resolve via search first
        print(f"  -- product page for {code} (via search)")
        page = ctx.new_page()
        try:
            page.goto(f"{VBASE}/search?q={code}", timeout=20000)
            try:
                page.wait_for_selector("a[href*='/p/']", timeout=8000)
            except Exception:
                pass
            link = page.query_selector("a[href*='/p/']")
            href = link.get_attribute("href") if link else None
            print(f"    first /p/ link: {href}")
            if href:
                url = VBASE + href if href.startswith("/") else href
                page.goto(url, timeout=20000)
                page.wait_for_timeout(3000)
                html = page.content()
                html_markers(html)
                dump(f"vitus_product_{code}.html", html)
        except Exception as e:
            print(f"    EXCEPTION {e!r}")
        page.close()
    ctx.close()
    browser.close()

print()
print("=" * 70)
print("PART 3: APOTERA — platform, search, cached product URLs")
print("=" * 70)
ABASE = "https://www.apotera.no"

r = http_get(ABASE + "/", "home")
if r is not None and r.status_code == 200:
    html_markers(r.text)
    gen = re.search(r'<meta name="generator" content="([^"]+)"', r.text)
    print(f"  generator meta: {gen.group(1) if gen else 'NONE'}")
    dump("apotera_home.html", r.text)

for q in ["051946", "paracet"]:
    r = http_get(f"{ABASE}/catalogsearch/result/?q={q}", f"search {q}")
    if r is not None and r.status_code == 200:
        links = re.findall(r'href="(https?://www\.apotera\.no/[^"]+)"', r.text)
        uniq = sorted(set(links))
        print(f"    links found: {len(uniq)}; sample: {uniq[:10]}")
        print(f"    product-item-link occurrences: {r.text.count('product-item-link')}")
        dump(f"apotera_search_{q}.html", r.text)

# Cached URLs from DB (secrets available in the workflow)
print("  -- cached url_apotera from DB")
try:
    from db import get_active_products
    products = get_active_products()
    with_url = [p for p in products if p.get("url_apotera")]
    print(f"  products={len(products)} with url_apotera={len(with_url)}")
    fail_codes = {"051946", "804410", "807862", "840110", "823877"}
    sample = [p for p in with_url if p["varenummer"] in fail_codes] or with_url[:5]
    for prod in sample[:5]:
        url = prod["url_apotera"]
        print(f"  -- {prod['varenummer']} cached: {url}")
        r = http_get(url, "cached product")
        if r is not None and r.status_code == 200:
            html_markers(r.text)
            dump(f"apotera_prod_{prod['varenummer']}.html", r.text)
    vit_with_url = [p for p in products if p.get("url_vitusapotek")]
    print(f"  with url_vitusapotek={len(vit_with_url)}; sample:")
    for prod in vit_with_url[:5]:
        print(f"    {prod['varenummer']}: {prod['url_vitusapotek']}")
except Exception as e:
    print(f"  DB unavailable: {e!r}")

print("\nDONE")
