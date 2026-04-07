-- Migration: remove Meny retailer

-- 1. Delete existing meny price rows (required before constraint update)
DELETE FROM public.priser WHERE butikk = 'meny';

-- 2. Drop URL column
ALTER TABLE public.produkter DROP COLUMN IF EXISTS url_meny;

-- 3. Update check constraint
ALTER TABLE public.priser DROP CONSTRAINT IF EXISTS priser_butikk_check;
ALTER TABLE public.priser
  ADD CONSTRAINT priser_butikk_check
  CHECK (butikk IN ('farmasiet','boots','vitusapotek','apotek1','oda','apotera'));

-- 4. Recreate view without meny column (must DROP — CREATE OR REPLACE cannot remove columns)
DROP VIEW IF EXISTS public.prissammenligning;
CREATE VIEW public.prissammenligning AS
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
  ORDER BY produkt_id, butikk, scraped_at desc
) pr ON pr.produkt_id = p.id
WHERE p.aktiv = true
GROUP BY p.id, p.varenummer, p.merke, p.produkt, p.kategori;
