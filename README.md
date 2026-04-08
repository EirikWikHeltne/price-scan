# Karo Price Scan

Daily price monitoring across 6 Norwegian pharmacy and grocery retailers: Apotek 1, Vitusapotek, Boots, Farmasiet, Oda, and Apotera.

Prices are scraped every night at 02:00 UTC and stored in Supabase. The scraper uses plain HTTP requests where possible, with Playwright as a fallback for JavaScript-rendered pages.

## Setup

**1. Supabase**

Run `supabase_schema.sql` in the Supabase SQL editor. This creates the `produkter` and `priser` tables, three convenience views (`siste_priser`, `prissammenligning`, and `prishistorikk` for historical price trends), and RLS policies for public read access.

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

To add or remove products, edit the CSV and re-run `seed_products.py`. Current categories are `Paracetamol`, `Ibuprofen`, `Mouthwash`, `Body lotion`, and `Intimate`.

To stop scraping a product without deleting its price history, set `aktiv = false` directly in Supabase. The scraper filters on `aktiv = true` and will skip it silently.

## How it works

The GitHub Actions workflow (`.github/workflows/daily.yml`) runs every night at 02:00 UTC. It seeds products, then runs the scraper against all six retailers in parallel.

Each scraper follows the same pattern:
1. Check if a product URL is already cached in the `produkter` table
2. If not, resolve the URL via sitemap (Apotek 1) or search page
3. Cache the resolved URL back to the database for future runs
4. Fetch the price using HTTP requests first, Playwright as fallback
5. Insert all results into the `priser` table with a timestamp

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
│   │   ├── vitusapotek.py        # Playwright
│   │   ├── boots.py              # requests + BeautifulSoup
│   │   ├── farmasiet.py          # requests + Playwright fallback
│   │   ├── oda.py                # API + Playwright (grocery)
│   │   └── apotera.py            # Playwright
│   └── scripts/
│       ├── products.csv          # Product list — edit this to add/remove products
│       └── seed_products.py      # Upserts products.csv into Supabase
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
