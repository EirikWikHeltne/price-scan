"""Apotek1.no — single browser context, URL ends in -{varenummer}p"""
import re, time, json
from playwright.sync_api import sync_playwright

BUTIKK = "apotek1"
BASE   = "https://www.apotek1.no"

# Injected into every page to hide automation signals
_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}};
Object.defineProperty(navigator, 'languages', {get: () => ['nb-NO','nb','no','en-US','en']});
"""

def _extract_price(page):
    # Layer 1: JSON-LD structured data
    for tag in page.query_selector_all("script[type='application/ld+json']"):
        try:
            d = json.loads(tag.inner_text())
            items = d if isinstance(d, list) else [d]
            for item in items:
                if not isinstance(item, dict):
                    continue
                offer = item.get("offers")
                if offer:
                    if isinstance(offer, list):
                        offer = offer[0]
                    pris = float(offer.get("price", 0)) or None
                    if pris:
                        return pris
        except:
            pass
    # Layer 2: data-testid price attributes
    for sel in ["[data-testid='price']", "[data-testid*='price']", "[data-testid*='Price']"]:
        el = page.query_selector(sel)
        if el:
            content = el.get_attribute("content")
            if content:
                try:
                    pris = float(content)
                    if pris:
                        return pris
                except:
                    pass
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                return float(m.group(1))
    # Layer 3: Broad CSS class selectors
    for sel in ["[class*='price']", "[class*='Price']", "[class*='pris']", "[class*='Pris']"]:
        el = page.query_selector(sel)
        if el:
            raw = el.inner_text().replace("kr", "").replace(",", ".").strip()
            m = re.search(r"(\d+\.?\d*)", raw)
            if m:
                return float(m.group(1))
    # Layer 4: Regex on page source
    m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', page.content())
    if m:
        return float(m.group(1))
    return None


def run(products):
    results, resolved = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="nb-NO",
            timezone_id="Europe/Oslo",
            extra_http_headers={
                "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,nn;q=0.7,en-US;q=0.6,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            }
        )
        context.add_init_script(_STEALTH)

        for prod in products:
            url = prod.get("url_apotek1")
            if not url:
                page = None
                try:
                    page = context.new_page()
                    page.goto(f"{BASE}/search?q={prod['varenummer']}", timeout=30000)
                    # Wait for Algolia search results — exact product match first
                    try:
                        page.wait_for_selector(
                            f"a[href$='-{prod['varenummer']}p']",
                            timeout=10000
                        )
                    except:
                        # Fallback: any product link
                        try:
                            page.wait_for_selector("a[href*='/produkter/']", timeout=5000)
                        except:
                            pass
                    link = page.query_selector(f"a[href$='-{prod['varenummer']}p']")
                    if not link:
                        link = page.query_selector("a[href*='/produkter/']")
                    if link:
                        href = link.get_attribute("href")
                        url = BASE + href if href.startswith("/") else href
                        resolved[prod["varenummer"]] = url
                    else:
                        print(f"  [apotek1] no search result for {prod['varenummer']}")
                    page.close()
                except Exception as e:
                    print(f"  [apotek1] search error {prod['varenummer']}: {e}")
                    if page:
                        try:
                            page.close()
                        except:
                            pass

            if not url:
                print(f"  [apotek1] no URL: {prod['varenummer']}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})
                continue

            page = None
            try:
                page = context.new_page()
                page.goto(url, timeout=30000)
                # Wait for price element — do NOT use networkidle (it times out on Apotek1)
                try:
                    page.wait_for_selector(
                        "script[type='application/ld+json'], [data-testid*='price'], [class*='Price']",
                        timeout=15000
                    )
                except:
                    pass  # Continue and attempt extraction anyway
                pris = _extract_price(page)
                lager = "på lager" in page.content().lower()
                page.close()
                print(f"  [apotek1] {prod['varenummer']}: {pris}")
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
                time.sleep(0.3)
            except Exception as e:
                print(f"  [apotek1] error {prod['varenummer']}: {e}")
                if page:
                    try:
                        page.close()
                    except:
                        pass
                results.append({"produkt_id": prod["id"], "butikk": BUTIKK, "pris": None, "pa_lager": None})

        context.close()
        browser.close()
    return results, resolved
