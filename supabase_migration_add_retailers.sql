-- Migration: add ODA and Apotera retailers
-- Run this against your existing Supabase project.

-- 1. New URL columns on produkter
alter table public.produkter
  add column if not exists url_oda     text,
  add column if not exists url_apotera text;

-- 2. Expand the butikk check constraint on priser
alter table public.priser
  drop constraint if exists priser_butikk_check;

alter table public.priser
  add constraint priser_butikk_check
  check (butikk in ('farmasiet','boots','vitusapotek','apotek1','oda','apotera'));

-- 3. Recreate prissammenligning view with new retailer columns
create or replace view public.prissammenligning as
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
