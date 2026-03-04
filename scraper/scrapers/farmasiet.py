"""Farmasiet.no — browser-based scraper using Playwright."""
import re, time, json
from playwright.sync_api import sync_playwright

BUTIKK = "farmasiet"
BASE   = "https://www.farmasiet.no"

def run(products):
    results, resolved = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        for prod in products:
            url = prod.get("url_farmasiet")
            # Discard bad category URLs (no comma = not a product page)
            if url and not re.search(r",\d+$", url):
                url = None
            if not url:
                try:
                    page = browser.new_page()
                    page.goto(f"{BASE}/search?q={prod['varenummer']}", timeout=20000)
                    try:
                        page.wait_for_selector("a[href*='/catalog/']", timeout=8000)
                    except:
                        pass
                    # Product URLs end with ,{digits}
                    for link in page.query_selector_all("a[href*='/catalog/']"):
                        href = link.get_attribute("href")
                        if href and re.search(r",\d+$", href):
                            url = BASE + href if href.startswith("/") else href
                            resolved[prod["varenummer"]] = url
                            break
                    page.close()
                except Exception as e:
                    print(f"  [farmasiet] search error {prod['varenummer']}: {e}")
                    try: page.close()
                    except: pass
            elif not prod.get("url_farmasiet") or not re.search(r",\d+$", prod.get("url_farmasiet", "")):
                resolved[prod["varenummer"]] = url
            if not url:
                print(f"  [farmasiet] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue
            try:
                page = browser.new_page()
                page.goto(url, timeout=20000)
                page.wait_for_load_state("networkidle", timeout=12000)
                pris = None
                # Layer 1: JSON-LD
                for el in page.query_selector_all("script[type='application/ld+json']"):
                    try:
                        d = json.loads(el.inner_text())
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
                print(f"  [farmasiet] {prod['varenummer']}: {pris}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
                time.sleep(0.5)
            except Exception as e:
                print(f"  [farmasiet] error {prod['varenummer']}: {e}")
                try: page.close()
                except: pass
        browser.close()
    return results, resolved
