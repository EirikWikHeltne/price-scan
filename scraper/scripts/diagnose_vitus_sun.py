"""One-off CI diagnostic: why do Sun products fail on vitusapotek?

Production symptoms (run 2026-06-09):
  - sitemap index only yields 7 product URLs (should be thousands)
  - search?q=<varenummer> finds nothing for all 245 Sun products

This script probes, from a GitHub runner with real network access:
  1. robots.txt + every sitemap candidate over plain HTTP (status/body)
  2. the same URLs through a Playwright page (bot-protection check)
  3. the search page for a few Sun varenummer + product names, capturing
     every XHR/fetch request so we can spot the real search API
  4. a category browse page to learn the current product-URL format
"""
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.sync_api import sync_playwright

from scrapers.vitusapotek import (
    BASE,
    _REQ_HEADERS,
    _SITEMAP_CANDIDATES,
    _STEALTH,
    _UA,
)

OUT = os.path.join(os.path.dirname(__file__), "..", "diag_out")
os.makedirs(OUT, exist_ok=True)

SUN_SAMPLES = [
    ("800227", "AVENE SUN SPRAY SPF50+ 200ML"),
    ("897789", "COSMICA SUN LOTION SPF50"),
    ("982569", "LRP ANTHELIOS SPRAY F50+"),
]
# A paracetamol product that DOES resolve today, as a control:
CONTROL = ("051946", "PARACET")


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


section("1. plain-HTTP robots.txt + sitemap candidates")
for path in ["/robots.txt"] + _SITEMAP_CANDIDATES:
    url = BASE + path
    try:
        r = requests.get(url, headers=_REQ_HEADERS, timeout=20)
        body = r.text
        n_locs = len(re.findall(r"<loc>", body))
        print(f"  {path}: HTTP {r.status_code}, {len(body)} bytes, {n_locs} <loc>")
        print(f"    head: {body[:300]!r}")
    except Exception as e:
        print(f"  {path}: EXC {e}")

section("2. same URLs via Playwright page.goto")
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
    )
    context = browser.new_context(user_agent=_UA, locale="nb-NO", timezone_id="Europe/Oslo")
    context.add_init_script(_STEALTH)

    page = context.new_page()
    for path in ["/robots.txt", "/sitemap.xml", "/sitemap_index.xml"]:
        try:
            resp = page.goto(BASE + path, timeout=20000)
            body = page.content()
            print(f"  {path}: HTTP {resp.status if resp else '?'}, {len(body)} bytes")
            print(f"    head: {body[:300]!r}")
        except Exception as e:
            print(f"  {path}: EXC {e}")
    page.close()

    section("3. search pages — capture XHR/fetch to find the search API")
    for code, name in SUN_SAMPLES + [CONTROL]:
        for query, label in [(code, "varenummer"), (name, "name")]:
            page = context.new_page()
            api_calls = []
            page.on(
                "request",
                lambda req, calls=api_calls: calls.append(f"{req.method} {req.url}")
                if req.resource_type in ("xhr", "fetch")
                else None,
            )
            try:
                resp = page.goto(f"{BASE}/search?q={requests.utils.quote(query)}", timeout=25000)
                page.wait_for_timeout(5000)
                html = page.content()
                links = sorted(
                    {
                        a.get_attribute("href")
                        for a in page.query_selector_all("a[href]")
                        if (a.get_attribute("href") or "").count("-") >= 2
                    }
                )[:15]
                fname = f"search_{label}_{code}.html"
                with open(os.path.join(OUT, fname), "w") as f:
                    f.write(html)
                print(f"\n  q={query!r} ({label}): HTTP {resp.status if resp else '?'}, {len(html)} bytes -> {fname}")
                print(f"    title: {page.title()!r}")
                print("    product-ish links:")
                for href in links:
                    print(f"      {href}")
                print("    xhr/fetch:")
                for c in api_calls[:25]:
                    print(f"      {c}")
            except Exception as e:
                print(f"\n  q={query!r} ({label}): EXC {e}")
            page.close()

    section("4. category browse — current product URL format for sun care")
    for path in ["/sol", "/solkrem", "/hudpleie/solprodukter", "/merker/cosmica"]:
        page = context.new_page()
        try:
            resp = page.goto(BASE + path, timeout=25000)
            page.wait_for_timeout(4000)
            links = sorted(
                {
                    a.get_attribute("href")
                    for a in page.query_selector_all("a[href]")
                    if re.search(r"-\d{5,7}/?$", a.get_attribute("href") or "")
                    or "/p/" in (a.get_attribute("href") or "")
                }
            )[:20]
            print(f"\n  {path}: HTTP {resp.status if resp else '?'} title={page.title()!r}")
            for href in links:
                print(f"      {href}")
        except Exception as e:
            print(f"\n  {path}: EXC {e}")
        page.close()

    context.close()
    browser.close()

print("\nDONE")
