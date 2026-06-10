-- Migration: purge bogus Apotera prices
--
-- Before 2026-06-10 the Apotera scraper extracted "95" (the shipping cost on
-- the customer-login page it was redirected to) as the price for every
-- product it "found". The scraper was rewritten to use the Magento GraphQL
-- API (PR #22), but the old rows still dominate prishistorikk and — until a
-- new scrape lands — siste_priser/prissammenligning.
--
-- Every apotera row scraped before the fix is from the broken scraper, so
-- delete them all rather than filtering on pris = 95.

DELETE FROM public.priser
WHERE butikk = 'apotera'
  AND scraped_at < '2026-06-10';
