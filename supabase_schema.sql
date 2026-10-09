create table public.produkter (
  id               bigint generated always as identity primary key,
  varenummer       text unique not null,
  ean              text,
  merke            text not null,
  produkt          text not null,
  kategori         text not null,
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
create index on produkter (kategori);
create index on produkter (merke);

create view siste_priser as
select distinct on (p.id, pr.butikk)
  p.id as produkt_id, p.varenummer, p.merke, p.produkt, p.kategori,
  pr.butikk, pr.pris, pr.pa_lager, pr.scraped_at
from produkter p
join priser pr on pr.produkt_id = p.id
order by p.id, pr.butikk, pr.scraped_at desc;

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
  max(pr.scraped_at) as sist_oppdatert
from produkter p
join (
  select distinct on (produkt_id, butikk)
    produkt_id, butikk, pris, scraped_at
  from priser
  order by produkt_id, butikk, scraped_at desc
) pr on pr.produkt_id = p.id
where p.aktiv = true
group by p.id, p.varenummer, p.merke, p.produkt, p.kategori;

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

-- One row per product × retailer × day; days the scraper didn't run carry the
-- last known observation forward (er_utfylt = true). Refreshed by run.py after
-- each scrape. See supabase_migration_prishistorikk_daglig.sql for details.
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
