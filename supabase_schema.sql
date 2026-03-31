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

alter table produkter enable row level security;
alter table priser     enable row level security;
create policy "Public read produkter" on produkter for select using (true);
create policy "Public read priser"    on priser    for select using (true);
