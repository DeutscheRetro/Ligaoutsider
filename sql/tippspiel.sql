-- Tippspiel (19.10.2026): Tipps je Nutzer und Spiel. Nur der Server (Service-Key) liest und schreibt,
-- der Browser hat keinen Zugriff. Rangliste und Punkte rechnet /api aus den Ergebnissen von OpenLigaDB.
create table if not exists public.tipps (
  email        text        not null,
  spiel_id     bigint      not null,
  tore_heim    smallint    not null check (tore_heim between 0 and 20),
  tore_gast    smallint    not null check (tore_gast between 0 and 20),
  erstellt_am  timestamptz not null default now(),
  geaendert_am timestamptz not null default now(),
  primary key (email, spiel_id)
);
alter table public.tipps enable row level security;
revoke all on public.tipps from anon, authenticated;
