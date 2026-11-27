create table public.produkter (
  id               bigint generated always as identity primary key,
  varenummer       text unique not null,
  ean              text,
  merke            text not null,
  produkt          text not null,
  kategori         text not null,  -- top level of the category tree
  niva1            text,
  niva2            text,
  niva3            text,
  produsent        text,
  segment          text,           -- 'Karo', 'Egne merker' or 'Andre'
  url_farmasiet    text,
  url_boots        text,
  url_vitusapotek  text,
  url_apotek1      text,
  url_oda          text,
  url_apotera      text,
  aktiv            boolean default true,
  opprettet        timestamptz default now()
);

create table public.priser (
  id          bigint generated always as identity primary key,
  produkt_id  bigint references produkter(id) on delete cascade,
  butikk      text not null check (butikk in ('farmasiet','boots','vitusapotek','apotek1','oda','apotera')),
  pris        numeric(8,2),
  pa_lager    boolean,
  scraped_at  timestamptz default now()
);

create index on priser (produkt_id);
create index on priser (butikk);
create index on priser (scraped_at desc);
create index on priser (produkt_id, scraped_at desc);
create index idx_priser_produkt_butikk_scraped on priser (produkt_id, butikk, scraped_at desc);
create index on produkter (kategori);
create index idx_produkter_kategoritre on produkter (kategori, niva1, niva2);
create index on produkter (merke);

-- Latest price per product and retailer: one index lookup each, so the cost
-- does not grow with the price history.
create view siste_priser as
select
  p.id as produkt_id, p.varenummer, p.merke, p.produkt, p.kategori,
  pr.butikk, pr.pris, pr.pa_lager, pr.scraped_at
from produkter p
cross join (values
  ('farmasiet'), ('boots'), ('vitusapotek'), ('apotek1'), ('oda'), ('apotera')
) as b(butikk)
cross join lateral (
  select x.butikk, x.pris, x.pa_lager, x.scraped_at
  from priser x
  where x.produkt_id = p.id and x.butikk = b.butikk
  order by x.scraped_at desc
  limit 1
) pr;

create view prissammenligning as
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

create view prishistorikk as
select
  p.id          as produkt_id,
  p.varenummer,
  p.merke,
  p.produkt,
  p.kategori,
  pr.butikk,
  pr.pris,
  pr.pa_lager,
  pr.scraped_at,
  pr.scraped_at::date as dato
from produkter p
join priser pr on pr.produkt_id = p.id
order by p.id, pr.butikk, pr.scraped_at desc;

alter table produkter enable row level security;
alter table priser     enable row level security;
create policy "Public read produkter" on produkter for select using (true);
create policy "Public read priser"    on priser    for select using (true);

grant select on public.prishistorikk to anon, authenticated;

-- Aggregates for the frontend, computed in the database so it never has to
-- download raw price rows. Each function returns the finished result as a
-- single JSON value, so it is one request and the PostgREST row cap does
-- not apply.
--
--    Both use one price per product, retailer and day (the latest scrape
--    that found a price), so a manual re-run on the same day does not count
--    twice. Rows without a price are ignored. `dager` <= 0 means all history.

-- Average price per group, retailer and day:
--   [{ dato, kategori, antall, snitt, <butikk>: snitt, ... }, ...]
-- The groups are the top-level categories; with `under_kategori` they are
-- that category's nivå 1 groups, and with `under_niva1` as well, the nivå 2
-- groups below it. The group name is always returned as `kategori`.
-- `snitt` is the mean of the retailer means, so a retailer with more product
-- coverage does not dominate. `antall` is the number of products with a price.
-- Only products that are still tracked (aktiv) are included.
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
