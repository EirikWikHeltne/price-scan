"""Main entry point: python run.py"""
import logging
import os
import sys
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from db import get_active_products, save_resolved_url, bulk_insert_prices
from scrapers import farmasiet, boots, vitusapotek, apotek1, oda, apotera

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

SCRAPERS = {
    "farmasiet":   farmasiet,
    "boots":       boots,
    "vitusapotek": vitusapotek,
    "apotek1":     apotek1,
    "oda":         oda,
    "apotera":     apotera,
}

# Grocery retailers only scrape these categories (pharmacy retailers get all)
GROCERY_SCRAPERS = {"oda"}
GROCERY_CATEGORIES = {"Paracetamol", "Ibuprofen"}

MAX_WORKERS = 4  # run up to 4 scrapers in parallel

# A wedged Playwright call can block a scraper thread forever (a full run
# normally takes ~1h40m; one stuck scraper once burned the whole 6h GitHub
# Actions limit and the completed results were never inserted). After this
# deadline the results gathered so far are inserted and the process exits.
SCRAPE_TIMEOUT = 2.5 * 60 * 60  # seconds


def _run_scraper(name, module, products):
    """Run a single scraper; returns (name, rows, resolved, crashed)."""
    print(f"\n--- {name} ---")
    try:
        rows, resolved = module.run(products)
        ok = sum(1 for r in rows if r["pris"] is not None)
        print(f"  {name}: {ok}/{len(rows)} prices found")
        return name, rows, resolved, False
    except Exception as e:
        print(f"  {name} CRASH: {e}")
        traceback.print_exc()
        return name, [], {}, True


def _annotate(level, message):
    """Print a message; on GitHub Actions also surface it on the run page."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level}::{message}")
    else:
        print(f"{level.upper()}: {message}")


def _report(counts, crashed, stuck):
    """Print per-retailer coverage and flag retailers that produced nothing.

    Scrapers swallow per-product errors by design, so a retailer that starts
    blocking us or changes its markup shows up only as a run of missing
    prices. Without this the job stays green while a retailer silently
    drops out of the data.
    """
    print("\n=== Coverage ===")
    for name in SCRAPERS:
        if name in stuck:
            print(f"  {name:<12} timed out")
            _annotate("error", f"{name}: scraper timed out, no prices saved")
        elif name in crashed:
            print(f"  {name:<12} crashed")
            _annotate("error", f"{name}: scraper crashed, no prices saved")
        else:
            ok, total = counts.get(name, (0, 0))
            print(f"  {name:<12} {ok}/{total}")
            if total and not ok:
                _annotate("warning", f"{name}: 0/{total} prices found")


# priser.pris is numeric(8,2): anything >= 10^6 overflows the column and fails
# the whole insert chunk (500 rows). No product we track costs anywhere near
# this, so out-of-range values are extraction errors — store them as missing.
MAX_PRICE = 100_000


def _sanitize(rows):
    """Null out impossible prices so one bad value can't sink an insert chunk."""
    for r in rows:
        pris = r.get("pris")
        if pris is None:
            continue
        try:
            pris = round(float(pris), 2)
        except (TypeError, ValueError):
            pris = None
        if pris is not None and not (0 < pris < MAX_PRICE):
            pris = None
        if pris is None:
            print(f"  [{r.get('butikk')}] discarding invalid price {r.get('pris')!r} "
                  f"for produkt_id {r.get('produkt_id')}")
        r["pris"] = pris
    return rows


def run():
    print(f"=== Scrape started {datetime.now().isoformat()} ===")
    products = get_active_products()
    print(f"Loaded {len(products)} products")

    grocery_products = [p for p in products if p.get("kategori") in GROCERY_CATEGORIES]
    print(f"Grocery-filtered: {len(grocery_products)} products (Paracetamol/Ibuprofen)")

    all_rows = []
    # No `with` block: shutdown would join threads, and a hung scraper thread
    # would block the join forever. Results are harvested via as_completed
    # with a deadline instead, and stuck threads are abandoned at exit.
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = {
        pool.submit(
            _run_scraper, name, module,
            grocery_products if name in GROCERY_SCRAPERS else products
        ): name
        for name, module in SCRAPERS.items()
    }
    stuck, crashed, counts = [], [], {}
    try:
        for future in as_completed(futures, timeout=SCRAPE_TIMEOUT):
            name, rows, resolved, did_crash = future.result()
            if did_crash:
                crashed.append(name)
            # Collect rows first: a failed URL cache write must never cost
            # the prices already scraped.
            all_rows.extend(rows)
            for vn, url in resolved.items():
                if not url:
                    continue
                try:
                    save_resolved_url(vn, name, url)
                    print(f"  Saved URL for {vn} on {name}")
                except Exception as e:
                    print(f"  Could not save URL for {vn} on {name}: {e}")
    except TimeoutError:
        stuck = sorted(name for f, name in futures.items() if not f.done())
        print(f"\nTIMEOUT after {SCRAPE_TIMEOUT:.0f}s — gave up on: {', '.join(stuck)}")
    pool.shutdown(wait=False, cancel_futures=True)

    exit_code = 0
    all_rows = _sanitize(all_rows)
    # Counted after sanitizing, so discarded prices don't count as found.
    for r in all_rows:
        ok, total = counts.get(r["butikk"], (0, 0))
        counts[r["butikk"]] = (ok + (r["pris"] is not None), total + 1)
    try:
        bulk_insert_prices(all_rows)
        print(f"\n=== Done — {len(all_rows)} rows inserted ===")
    except Exception as e:
        print(f"\n=== FAILED to insert prices: {e} ===")
        exit_code = 1
    _report(counts, crashed, stuck)
    if crashed or stuck:
        # The other retailers' prices are saved, but a whole retailer is
        # missing from today's data — fail the job so it gets noticed.
        exit_code = 1
    if stuck:
        # Non-daemon scraper threads would keep the interpreter alive at
        # normal exit; results are already saved, so exit hard.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    run()
