-- Migration: purge unverified Oda prices and cached Oda URLs
--
-- NOT RUN AUTOMATICALLY. Review the SELECTs in step 0, set the cutoff date
-- in step 1, then run the statements by hand in the Supabase SQL editor.
--
-- Until the fix in scraper/scrapers/oda.py the Oda scraper never checked
-- that the page it priced was the product it was asked for. It took the
-- first "/no/products/" link on Oda's search page — a menu entry such as
-- /no/products/discounts/, or whichever product Oda listed first — cached
-- that in produkter.url_oda, and stored the first price-like value found on
-- that page. Unrelated products therefore share the same Oda price on a
-- given day, and prices jump between days (e.g. Ibuprofen category average
-- 27.84 -> 79.16 -> 38.29).
--
-- No row from that scraper is verifiable, including the ones that happen to
-- look plausible, so all of them are deleted rather than filtering on value.
-- Oda sells 9 of the tracked Paracetamol/Ibuprofen products; the fixed
-- scraper re-prices those, and re-fills their url_oda, on its next run.

-- 0. Look before deleting.
--    Rows per day that would be removed:
-- SELECT scraped_at::date AS dag, count(*) AS rader, count(pris) AS med_pris
-- FROM public.priser WHERE butikk = 'oda' GROUP BY 1 ORDER BY 1;
--    Cached URLs that would be cleared:
-- SELECT varenummer, merke, produkt, url_oda
-- FROM public.produkter WHERE url_oda IS NOT NULL ORDER BY url_oda;

-- 1. Delete the Oda prices scraped by the broken scraper.
--    Set the date to the day of the first scrape that ran WITH the fix
--    (the daily job runs at 02:00 UTC), so its rows are kept.
DELETE FROM public.priser
WHERE butikk = 'oda'
  AND scraped_at < '2026-11-25';  -- <-- adjust to the first fixed run

-- 2. Clear every cached Oda URL. The fixed scraper no longer trusts
--    url_oda for pricing, but it only ever overwrites the URL of a product
--    it matches — the wrong URLs of products Oda does not sell would
--    otherwise stay in the table forever.
UPDATE public.produkter
SET url_oda = NULL
WHERE url_oda IS NOT NULL;
