-- Migration: gap-free daily price history (prishistorikk_daglig)
-- Run this against your existing Supabase project.
--
-- prishistorikk only has rows for nights the scraper actually ran. When the
-- scraper is offline (a failed workflow, a crashed retailer scraper) those
-- days are simply missing, which breaks line charts, skews per-day averages
-- and makes products look delisted.
--
-- This view returns exactly one row per product × retailer × calendar day:
--   * a day with a scrape uses that day's latest observation (er_utfylt = false)
--   * a day with NO scrape carries the last known observation forward
--     (er_utfylt = true, dager_siden_scrape = age of that observation)
--
-- Only days with no rows at all are filled. A scrape that ran but found no
-- price (pris null) is a real observation and is kept as-is.
--
-- The series runs from a pair's first observation up to the latest scrape in
-- the database (never into the future), and stops 30 days after the pair's
-- last observation so retailers/products that are no longer scraped don't
-- get carried forward forever.

-- 1. Index for the per-pair "latest observation on or before day X" lookup
create index if not exists idx_priser_produkt_butikk_scraped
  on priser (produkt_id, butikk, scraped_at desc);

-- 2. The view
create or replace view public.prishistorikk_daglig as
with spenn as (
  select produkt_id, butikk,
         min(scraped_at)::date as forste_dato,
         max(scraped_at)::date as siste_dato
  from priser
  group by produkt_id, butikk
),
siste_kjoring as (
  select max(scraped_at)::date as dato from priser
)
select
  p.id          as produkt_id,
  p.varenummer,
  p.merke,
  p.produkt,
  p.kategori,
  s.butikk,
  obs.pris,
  obs.pa_lager,
  obs.scraped_at,
  d.dato,
  obs.scraped_at::date <> d.dato         as er_utfylt,
  d.dato - obs.scraped_at::date          as dager_siden_scrape
from spenn s
cross join siste_kjoring k
cross join lateral (
  select g::date as dato
  from generate_series(s.forste_dato, least(k.dato, s.siste_dato + 30), interval '1 day') g
) d
cross join lateral (
  select pr.pris, pr.pa_lager, pr.scraped_at
  from priser pr
  where pr.produkt_id = s.produkt_id
    and pr.butikk     = s.butikk
    and pr.scraped_at < d.dato + 1
  order by pr.scraped_at desc
  limit 1
) obs
join produkter p on p.id = s.produkt_id;

-- 3. Grant read access so the view is queryable via Supabase client SDK
grant select on public.prishistorikk_daglig to anon, authenticated;
