-- Migration: gap-free daily price history (prishistorikk_daglig)
-- Run this against your existing Supabase project.
--
-- prishistorikk only has rows for nights the scraper actually ran. When the
-- scraper is offline (a failed workflow, a crashed retailer scraper) those
-- days are simply missing, which breaks line charts, skews per-day averages
-- and makes products look delisted.
--
-- prishistorikk_daglig has exactly one row per product × retailer × day:
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
--
-- It is a materialized view: computing the fill on every request is too slow
-- for the dashboard's paged reads (~4s per 1000-row page at 200 days of data).
-- run.py refreshes it after each nightly insert via
-- refresh_prishistorikk_daglig(); while the scraper is offline it simply keeps
-- the data up to the last scrape, and the next successful run fills the gap.

drop materialized view if exists public.prishistorikk_daglig;

create materialized view public.prishistorikk_daglig as
with daglig as (
  select distinct on (produkt_id, butikk, scraped_at::date)
    produkt_id, butikk, scraped_at::date as dato, pris, pa_lager, scraped_at
  from priser
  order by produkt_id, butikk, scraped_at::date, scraped_at desc
),
spenn as (
  select produkt_id, butikk, min(dato) as forste_dato, max(dato) as siste_dato
  from daglig
  group by produkt_id, butikk
),
kalender as (
  select s.produkt_id, s.butikk, g::date as dato
  from spenn s
  cross join (select max(dato) as dato from daglig) k
  cross join lateral generate_series(
    s.forste_dato, least(k.dato, s.siste_dato + 30), interval '1 day'
  ) g
),
gruppert as (
  -- grp increments on every day with a real observation, so each gap day
  -- shares a group with the observation before it
  select c.produkt_id, c.butikk, c.dato, d.pris, d.pa_lager, d.scraped_at,
         count(d.scraped_at) over (
           partition by c.produkt_id, c.butikk order by c.dato
         ) as grp
  from kalender c
  left join daglig d using (produkt_id, butikk, dato)
),
fylt as (
  select produkt_id, butikk, dato,
         first_value(pris)       over w as pris,
         first_value(pa_lager)   over w as pa_lager,
         first_value(scraped_at) over w as scraped_at
  from gruppert
  window w as (partition by produkt_id, butikk, grp order by dato)
)
select
  p.id          as produkt_id,
  p.varenummer,
  p.merke,
  p.produkt,
  p.kategori,
  f.butikk,
  f.pris,
  f.pa_lager,
  f.scraped_at,
  f.dato,
  f.scraped_at::date <> f.dato   as er_utfylt,
  f.dato - f.scraped_at::date    as dager_siden_scrape
from fylt f
join produkter p on p.id = f.produkt_id;

create unique index on public.prishistorikk_daglig (produkt_id, butikk, dato);
create index on public.prishistorikk_daglig (dato);
create index on public.prishistorikk_daglig (varenummer, dato);

-- Called by the scraper (service role) after each nightly insert
create or replace function public.refresh_prishistorikk_daglig()
returns void
language sql
security definer
set search_path = public
as $$
  refresh materialized view public.prishistorikk_daglig;
$$;

revoke execute on function public.refresh_prishistorikk_daglig() from public, anon, authenticated;
grant execute on function public.refresh_prishistorikk_daglig() to service_role;

-- Read access so the view is queryable via Supabase client SDK
grant select on public.prishistorikk_daglig to anon, authenticated;
