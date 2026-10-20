-- Migration: stop a single failed scrape from blanking a known price
--
-- prissammenligning used to show the newest priser row per product and
-- store, even when that row was NULL. One night where a scraper missed a
-- product (timeout, search hiccup) hid a price that was correct the day
-- before. Now the newest non-null price from the last 7 days wins; only when
-- there is none does the view fall back to the newest row (as before), so a
-- product that is really gone still goes blank after a week.
--
-- Columns are unchanged, so CREATE OR REPLACE is enough.

CREATE OR REPLACE VIEW public.prissammenligning AS
SELECT
  p.id, p.varenummer, p.merke, p.produkt, p.kategori,
  max(case when pr.butikk = 'farmasiet'   then pr.pris end) as farmasiet,
  max(case when pr.butikk = 'boots'       then pr.pris end) as boots,
  max(case when pr.butikk = 'vitusapotek' then pr.pris end) as vitusapotek,
  max(case when pr.butikk = 'apotek1'     then pr.pris end) as apotek1,
  max(case when pr.butikk = 'oda'         then pr.pris end) as oda,
  max(case when pr.butikk = 'apotera'     then pr.pris end) as apotera,
  min(pr.pris) as laveste_pris,
  max(pr.pris) as hoyeste_pris,
  max(pr.scraped_at) as sist_oppdatert
FROM produkter p
JOIN (
  SELECT DISTINCT ON (produkt_id, butikk)
    produkt_id, butikk, pris, scraped_at
  FROM priser
  ORDER BY produkt_id, butikk,
    (pris IS NOT NULL AND scraped_at > now() - interval '7 days') DESC,
    scraped_at DESC
) pr ON pr.produkt_id = p.id
WHERE p.aktiv = true
GROUP BY p.id, p.varenummer, p.merke, p.produkt, p.kategori;
