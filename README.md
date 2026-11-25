# Karo Price Scan

Daily price monitoring across 6 Norwegian pharmacy and grocery retailers: Apotek 1, Vitusapotek, Boots, Farmasiet, Oda, and Apotera.

Prices are scraped every night at 02:00 UTC and stored in Supabase. The scraper uses plain HTTP requests where possible, with Playwright as a fallback for JavaScript-rendered pages.

This repository holds both halves: the scraper and database setup (`scraper/`, `supabase_*.sql`) and the web app that shows the prices (`frontend/`, a Next.js app deployed on Vercel).

## Setup

**1. Supabase**

Run `supabase_schema.sql` in the Supabase SQL editor. This creates the `produkter` and `priser` tables, three convenience views (`siste_priser`, `prissammenligning`, and `prishistorikk` for historical price trends), and RLS policies for public read access. It also creates two functions the frontend calls for its history pages, `kategori_historikk(dager)` and `ukesnitt(dager)`, which return category and weekly averages already computed in the database.

For a project created before these functions existed, run `supabase_migration_fast_reads.sql` once.

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

All products are defined in `scraper/scripts/products.csv` with four columns:

```
varenummer,merke,produkt,kategori
003051,PANODIL,TAB 500MG 20ENPAC ZAPP,Paracetamol
017833,IBUX,TAB 400MG 10ENPAC,Ibuprofen
```

To add or remove products, edit the CSV and re-run `seed_products.py`. Current categories are `Paracetamol`, `Ibuprofen`, `Mouthwash`, `Body lotion`, `Intimate`, and `Sun`.

To stop scraping a product without deleting its price history, set `aktiv = false` directly in Supabase. The scraper filters on `aktiv = true` and will skip it silently.

## How it works

The GitHub Actions workflow (`.github/workflows/daily.yml`) runs every night at 02:00 UTC. It seeds products, then runs the scraper against all six retailers in parallel.

Each scraper follows the same pattern:
1. Check if a product URL is already cached in the `produkter` table
2. If not, resolve the URL via sitemap (Apotek 1) or search page
3. Cache the resolved URL back to the database for future runs
4. Fetch the price using HTTP requests first, Playwright as fallback
5. Insert all results into the `priser` table with a timestamp

A cached URL that starts returning 404/410 is resolved afresh on the same run (Apotek 1, Farmasiet, Boots), so a product whose page moved does not stay priceless.

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
