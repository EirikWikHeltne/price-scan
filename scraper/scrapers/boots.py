"""Boots.no — SSR, URL ends in -{varenummer}. No browser needed."""
import json, re, time
import requests
from bs4 import BeautifulSoup

BUTIKK = "boots"
BASE   = "https://www.boots.no"
HEADS  = {"User-Agent": "Mozilla/5.0", "Accept-Language": "nb-NO"}

def search_url(varenummer):
    try:
        r = requests.get(f"{BASE}/catalogsearch/result/?q={varenummer}", headers=HEADS, timeout=12)
        soup = BeautifulSoup(r.text, "lxml")
        link = soup.find("a", href=re.compile(f"-{varenummer}$"))
        if link:
            href = link["href"]
            return href if href.startswith("http") else BASE + href
    except Exception:
        pass
    return None

def fetch_price(url):
    try:
        r = requests.get(url, headers=HEADS, timeout=12)
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "")
                if isinstance(d, dict) and "offers" in d:
                    price = float(d["offers"].get("price", 0)) or None
                    if price:
                        return price, "på lager" in r.text.lower()
            except Exception:
                pass
        m = re.search(r"Kr\s*([\d\s]+[,.][\d]+)", r.text)
        if m:
            price = float(m.group(1).replace(" ", "").replace(",", "."))
            return price, "på lager" in r.text.lower()
        return None, None
    except Exception as e:
        print(f"  [boots] error: {e}")
        return None, None

def run(products):
    results, resolved = [], {}
    for p in products:
        url = p.get("url_boots") or search_url(p["varenummer"])
        if not url:
            print(f"  [boots] no URL: {p['varenummer']}")
            continue
        if not p.get("url_boots"):
            resolved[p["varenummer"]] = url
        pris, lager = fetch_price(url)
        print(f"  [boots] {p['varenummer']}: {pris}")
        results.append({"produkt_id": p["id"], "butikk": BUTIKK, "pris": pris, "pa_lager": lager})
        time.sleep(0.5)
    return results, resolved
