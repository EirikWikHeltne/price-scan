# Karo Price Scan

Daily price monitoring across 6 Norwegian pharmacy and grocery retailers: Apotek 1, Vitusapotek, Boots, Farmasiet, Oda, and Apotera.

Prices are scraped every night at 02:00 UTC and stored in Supabase. The scraper uses plain HTTP requests where possible, with Playwright as a fallback for JavaScript-rendered pages.

This repository holds both halves: the scraper and database setup (`scraper/`, `supabase_*.sql`) and the web app that shows the prices (`frontend/`, a Next.js app deployed on Vercel).

## Setup

**1. Supabase**

Run `supabase_schema.sql` in the Supabase SQL editor. This creates the `produkter` and `priser` tables, three convenience views (`siste_priser`, `prissammenligning`, and `prishistorikk` for historical price trends), and RLS policies for public read access. It also creates two functions the frontend calls for its history pages, `kategori_historikk(dager)` and `ukesnitt(dager)`, which return category and weekly averages already computed in the database.

For a project created before these functions existed, run `supabase_migration_fast_reads.sql` once.

For a project created before the category tree (below), run `supabase_migration_category_tree.sql` once. Until it has run, products are still seeded and scraped, but without their sub-levels, and the nightly job shows a warning saying so.

**2. GitHub Secrets**

Add the following secrets to your repository (Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `SUPABASE_URL` | Your project URL, e.g. `https://xyz.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Service role key (bypasses RLS for writes) |

**3. Seed products**

Trigger the workflow manually once from the Actions tab, or run locally:

```bash
cd scraper
pip install -r requirements.txt
python scripts/seed_products.py
```

This upserts all products from `scripts/products.csv` into the `produkter` table. Safe to re-run at any time — existing rows are updated, nothing is duplicated.

## Managing products

All products are defined in `scraper/scripts/products.csv`, one row per article:

```
varenummer,ean,merke,produkt,produsent,segment,kategori,niva1,niva2,niva3
977150,7319861025729,ACO,INTENSIVE FOOT CREAM UP 100ML,KARO HEALTHCARE,Karo,Fotpleie,Foot creams,"Dry, cracked & hard-skin creams",
```

Products are placed in a category tree. `kategori` is the top level and must be one of `Hudpleie`, `Fotpleie`, `Munnpleie`, `Intimpleie`, `Mage og tarm` or `Smerte`; `niva1`, `niva2` and `niva3` are the levels below it and may be empty. `segment` is `Karo`, `Egne merker` (retailer private label) or `Andre`. `ean`, `produsent`, `segment` and the three levels are optional.

`seed_products.py` upserts the CSV into the `produkter` table. It is safe to re-run at any time: existing rows are updated and nothing is duplicated. A product that is active in the database but no longer in the CSV is set to `aktiv = false`, which stops the scraping and hides it from the web app while keeping its price history. (As a safeguard, nothing is deactivated if more than half of the active products are missing from the file.)

To stop scraping a single product by hand, set `aktiv = false` directly in Supabase. The seed script never switches a product back on, so to resume one, set `aktiv = true` there.

### Replacing the whole list

When a new version of the product list workbook arrives, rebuild the CSV from it:

```bash
cd scraper
pip install openpyxl
python scripts/import_product_list.py path/to/produktliste.xlsx
```

The workbook needs a sheet with the columns Kategori, Nivå 1 to 3, Artikkelnummer, EAN, Produsent, Merke, Produkt and "Karo, egne merker eller andre". Products already in the CSV keep their varenummer as written (it is the database key, so the history stays attached) and their name; the script lists the tracked products that are not in the workbook, which the next seed will deactivate. Review the diff of `products.csv` before committing it.

## How it works

The GitHub Actions workflow (`.github/workflows/daily.yml`) runs every night at 02:00 UTC. It seeds products once, then splits the product list over eight scrape jobs (four at a time), each running the scraper against all six retailers in parallel. A job picks its share of the list from `SHARD_INDEX` and `SHARD_TOTAL`; without them, as in a local run, `run.py` scrapes everything. Oda, a grocery store, is only asked for the `Smerte` products.

Each scraper follows the same pattern:
1. Check if a product URL is already cached in the `produkter` table
2. If not, resolve the URL via sitemap (Apotek 1) or search page
3. Cache the resolved URL back to the database for future runs
4. Fetch the price using HTTP requests first, Playwright as fallback
5. Insert all results into the `priser` table with a timestamp

A cached URL that starts returning 404/410 is resolved afresh on the same run (Apotek 1, Farmasiet, Boots), so a product whose page moved does not stay priceless.

Most products are not sold by every retailer, and searching a retailer's site for a product it does not have is the slowest part of a run. So a product with no known page at Apotek 1, Farmasiet or Boots is searched for on its first two nights and after that once a week (`due_for_lookup` in `scrapers/_common.py`); on the other nights no price row is stored for it at that retailer. Vitusapotek and Apotera answer for many products per request and are asked about every product every night.

At the end of each run a coverage table lists prices found per retailer. The job fails if a scraper crashed or timed out (the other retailers' prices are still saved), and a retailer that returned no prices at all is flagged as a warning on the run page.

## Tests

Offline unit tests cover the shared price/stock parsing, API-response parsing and the pre-insert sanity checks. They run on every pull request (`.github/workflows/tests.yml`) and locally with:

```bash
cd scraper
pip install -r requirements.txt pytest
python -m pytest
```

## Project structure

```
.
├── .github/workflows/daily.yml   # Scheduled GitHub Actions job
├── scraper/
│   ├── run.py                    # Main entry point
│   ├── db.py                     # Supabase client and query helpers
│   ├── requirements.txt
│   ├── scrapers/
│   │   ├── apotek1.py            # Sitemap + requests + Playwright
│   │   ├── vitusapotek.py        # JSON API (/api/products)
│   │   ├── boots.py              # requests + BeautifulSoup
│   │   ├── farmasiet.py          # requests + Playwright fallback
│   │   ├── oda.py                # Search API, verified product match (grocery)
│   │   └── apotera.py            # Playwright
│   ├── tests/                    # Offline unit tests (pytest)
│   └── scripts/
│       ├── products.csv          # Product list — edit this to add/remove products
│       ├── import_product_list.py # Rebuilds products.csv from the product list workbook
│       └── seed_products.py      # Upserts products.csv into Supabase
├── frontend/                     # Next.js web app (Vercel root directory)
│   ├── app/                      # Pages and API routes
│   ├── components/
│   ├── lib/                      # Shared helpers, covered by `npm test`
│   └── test/
└── supabase_schema.sql           # Full DB schema, views, and RLS policies
```

## Local development

```bash
cd scraper
cp .env.example .env              # add SUPABASE_URL and SUPABASE_SERVICE_KEY
pip install -r requirements.txt
playwright install chromium
python run.py
```

### Frontend

```bash
cd frontend
npm ci
# .env.local: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
npm run dev
npm test && npm run lint
```

The Vercel project builds from the `frontend/` directory (Settings → Build and Deployment → Root Directory).
