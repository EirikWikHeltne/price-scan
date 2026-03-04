"""Apotek1.no — single browser session, URL ends in -{varenummer}p"""
import re, time, json
from playwright.sync_api import sync_playwright

BUTIKK = "apotek1"
BASE   = "https://www.apotek1.no"

def run(products):
    results, resolved = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        for prod in products:
            url = prod.get("url_apotek1")
            if not url:
                try:
                    page = browser.new_page()
                    page.goto(f"{BASE}/search?q={prod['varenummer']}", timeout=20000)
                    # Wait for Algolia search results to render
                    try:
                        page.wait_for_selector(
                            f"a[href$='-{prod['varenummer']}p']",
                            timeout=8000
                        )
                    except:
                        pass
                    # URL ends in -{varenummer}p
                    link = page.query_selector(f"a[href$='-{prod['varenummer']}p']")
                    # Fallback: any product link in search results
                    if not link:
                        link = page.query_selector("a[href*='/produkter/']")
                    if link:
                        href = link.get_attribute("href")
                        url = BASE + href if href.startswith("/") else href
                        resolved[prod["varenummer"]] = url
                    page.close()
                except Exception as e:
                    print(f"  [apotek1] search error {prod['varenummer']}: {e}")
                    try: page.close()
                    except: pass
            if not url:
                print(f"  [apotek1] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue
            try:
                page = browser.new_page()
                page.goto(url, timeout=20000)
                page.wait_for_load_state("networkidle", timeout=12000)
                pris = None
                # Layer 1: JSON-LD
                for tag in page.query_selector_all("script[type='application/ld+json']"):
                    try:
                        d = json.loads(tag.inner_text())
                        if isinstance(d, dict) and "offers" in d:
                            pris = float(d["offers"].get("price", 0)) or None
                            if pris: break
                    except: pass
                # Layer 2: data-testid price attributes
                if not pris:
                    el = page.query_selector("[data-testid*='price']")
                    if el:
                        content = el.get_attribute("content")
                        if content:
                            try: pris = float(content)
                            except: pass
                        if not pris:
                            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
                            m = re.search(r"(\d+\.?\d*)", raw)
                            if m: pris = float(m.group(1))
                # Layer 3: Broad CSS class selectors
                if not pris:
                    for sel in ["[class*='price']", "[class*='Price']"]:
                        el = page.query_selector(sel)
                        if el:
                            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
                            m = re.search(r"(\d+\.?\d*)", raw)
                            if m:
                                pris = float(m.group(1))
                                break
                # Layer 4: Regex on page content
                if not pris:
                    m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', page.content())
                    if m: pris = float(m.group(1))
                lager = "på lager" in page.content().lower()
                page.close()
                print(f"  [apotek1] {prod['varenummer']}: {pris}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
                time.sleep(0.3)
            except Exception as e:
                print(f"  [apotek1] error {prod['varenummer']}: {e}")
                try: page.close()
                except: pass
        browser.close()
    return results, resolved
