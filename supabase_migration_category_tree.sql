-- Migration: the category tree (kategori > nivå 1 > nivå 2 > nivå 3).
-- Run this once in the Supabase SQL editor. It adds columns to `produkter`,
-- adds columns at the end of the `prissammenligning` view, and replaces the
-- two history functions. No price data is changed, and it is safe to run
-- more than once and before or after the code that uses it is deployed.

-- 1. Product attributes from the product list. `kategori` holds the top
--    level; the sub-levels can be empty for products that sit higher up.
alter table public.produkter
  add column if not exists ean       text,
  add column if not exists produsent text,
  add column if not exists segment   text,  -- 'Karo', 'Egne merker' or 'Andre'
  add column if not exists niva1     text,
  add column if not exists niva2     text,
  add column if not exists niva3     text;

create index if not exists idx_produkter_kategoritre
  on public.produkter (kategori, niva1, niva2);

-- 2. Current prices per product, now with the sub-levels (new columns can
--    only be added at the end of an existing view).
create or replace view prissammenligning as
select
  p.id, p.varenummer, p.merke, p.produkt, p.kategori,
  max(case when pr.butikk = 'farmasiet'   then pr.pris end) as farmasiet,
  max(case when pr.butikk = 'boots'       then pr.pris end) as boots,
  max(case when pr.butikk = 'vitusapotek' then pr.pris end) as vitusapotek,
  max(case when pr.butikk = 'apotek1'     then pr.pris end) as apotek1,
  max(case when pr.butikk = 'oda'         then pr.pris end) as oda,
  max(case when pr.butikk = 'apotera'     then pr.pris end) as apotera,
  min(pr.pris) as laveste_pris,
  max(pr.pris) as hoyeste_pris,
  max(pr.scraped_at) as sist_oppdatert,
  p.niva1, p.niva2, p.niva3, p.segment
from produkter p
cross join (values
  ('farmasiet'), ('boots'), ('vitusapotek'), ('apotek1'), ('oda'), ('apotera')
) as b(butikk)
cross join lateral (
  select x.butikk, x.pris, x.scraped_at
  from priser x
  where x.produkt_id = p.id and x.butikk = b.butikk
  order by x.scraped_at desc
  limit 1
) pr
where p.aktiv = true
group by p.id, p.varenummer, p.merke, p.produkt, p.kategori,
         p.niva1, p.niva2, p.niva3, p.segment;

-- 3. History functions: drill-down through the category tree. The old
--    one-argument versions are dropped so a call with only `dager` is not
--    ambiguous.
-- Average price per group, retailer and day:
--   [{ dato, kategori, antall, snitt, <butikk>: snitt, ... }, ...]
-- The groups are the top-level categories; with `under_kategori` they are
-- that category's nivå 1 groups, and with `under_niva1` as well, the nivå 2
-- groups below it. The group name is always returned as `kategori`.
-- `snitt` is the mean of the retailer means, so a retailer with more product
-- coverage does not dominate. `antall` is the number of products with a price.
-- Only products that are still tracked (aktiv) are included.
drop function if exists public.kategori_historikk(integer);
create or replace function public.kategori_historikk(
  dager integer default 90,
  under_kategori text default null,
  under_niva1 text default null
)
returns json
language sql
stable
set search_path = public
as $$
  with gruppert as (
    select p.id as produkt_id,
           case when under_kategori is null then p.kategori
                when under_niva1 is null then p.niva1
                else p.niva2 end as kategori
    from produkter p
    where p.aktiv
      and (under_kategori is null or p.kategori = under_kategori)
      and (under_niva1 is null or p.niva1 = under_niva1)
  ),
  daglig as (
    select distinct on (pr.produkt_id, pr.butikk, pr.scraped_at::date)
      pr.produkt_id, pr.butikk, pr.scraped_at::date as dato, pr.pris, g.kategori
    from priser pr
    join gruppert g on g.produkt_id = pr.produkt_id
    where pr.pris is not null
      and g.kategori is not null
      and pr.scraped_at >= case when dager <= 0 then '-infinity'::timestamptz
                                else (current_date - dager)::timestamptz end
    order by pr.produkt_id, pr.butikk, pr.scraped_at::date, pr.scraped_at desc
  ),
  per_butikk as (
    select dato, kategori, butikk, avg(pris) as snitt
    from daglig
    group by dato, kategori, butikk
  ),
  antall as (
    select dato, kategori, count(distinct produkt_id) as antall
    from daglig
    group by dato, kategori
  ),
  per_dag as (
    select
      b.dato, b.kategori,
      jsonb_build_object(
        'dato', b.dato,
        'kategori', b.kategori,
        'antall', a.antall,
        'snitt', round(avg(b.snitt), 2)
      ) || jsonb_object_agg(b.butikk, round(b.snitt, 2)) as rad
    from per_butikk b
    join antall a on a.dato = b.dato and a.kategori = b.kategori
    group by b.dato, b.kategori, a.antall
  )
  select coalesce(json_agg(rad order by dato, kategori), '[]'::json)
  from per_dag
$$;

-- Average price per product, retailer and ISO week (keyed by its Monday):
--   [{ varenummer, produkt, merke, kategori, niva1, niva2, niva3,
--      uker: { "2026-11-16": { <butikk>: snitt, ... }, ... } }, ...]
-- `under_kategori` and `under_niva1` limit the answer to one branch of the
-- category tree, which keeps it small enough to send to the browser.
-- Only products that are still tracked (aktiv) are included.
drop function if exists public.ukesnitt(integer);
create or replace function public.ukesnitt(
  dager integer default 84,
  under_kategori text default null,
  under_niva1 text default null
)
returns json
language sql
stable
set search_path = public
as $$
  with utvalg as (
    select p.id
    from produkter p
    where p.aktiv
      and (under_kategori is null or p.kategori = under_kategori)
      and (under_niva1 is null or p.niva1 = under_niva1)
  ),
  daglig as (
    select distinct on (pr.produkt_id, pr.butikk, pr.scraped_at::date)
      pr.produkt_id, pr.butikk, pr.scraped_at::date as dato, pr.pris
    from priser pr
    join utvalg u on u.id = pr.produkt_id
    where pr.pris is not null
      and pr.scraped_at >= case when dager <= 0 then '-infinity'::timestamptz
                                else (current_date - dager)::timestamptz end
    order by pr.produkt_id, pr.butikk, pr.scraped_at::date, pr.scraped_at desc
  ),
  ukentlig as (
    select produkt_id, date_trunc('week', dato)::date as mandag, butikk,
           round(avg(pris), 2) as snitt
    from daglig
    group by produkt_id, date_trunc('week', dato)::date, butikk
  ),
  per_uke as (
    select produkt_id, mandag, jsonb_object_agg(butikk, snitt) as priser
    from ukentlig
    group by produkt_id, mandag
  ),
  per_produkt as (
    select produkt_id, jsonb_object_agg(mandag::text, priser) as uker
    from per_uke
    group by produkt_id
  )
  select coalesce(
    json_agg(
      json_build_object(
        'varenummer', p.varenummer,
        'produkt', p.produkt,
        'merke', p.merke,
        'kategori', p.kategori,
        'niva1', p.niva1,
        'niva2', p.niva2,
        'niva3', p.niva3,
        'uker', pp.uker
      )
      order by p.produkt, p.id
    ),
    '[]'::json
  )
  from per_produkt pp
  join produkter p on p.id = pp.produkt_id
$$;

grant execute on function public.kategori_historikk(integer, text, text) to anon, authenticated, service_role;
grant execute on function public.ukesnitt(integer, text, text) to anon, authenticated, service_role;

-- 4. Make PostgREST pick up the new columns and function signatures now.
notify pgrst, 'reload schema';
