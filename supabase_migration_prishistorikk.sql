-- Migration: add historical price view (prishistorikk)
-- Run this against your existing Supabase project.

-- 1. Composite index for fast per-product history queries
create index if not exists idx_priser_produkt_scraped
  on priser (produkt_id, scraped_at desc);

-- 2. Create the view
create view public.prishistorikk as
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

-- 3. Grant read access so the view is queryable via Supabase client SDK
grant select on public.prishistorikk to anon, authenticated;
