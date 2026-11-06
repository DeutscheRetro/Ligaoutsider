-- Schnelltipp "Wer gewinnt?" aus der Spielleiste (06.11.2026). Im Supabase SQL-Editor einmal ausführen.
-- Gilt für beide Ligen. Geschrieben und gelesen wird nur über /api mit dem Service-Key.
create table if not exists public.spiel_tipps (
  id           bigint generated always as identity primary key,
  spiel_id     integer not null check (spiel_id > 0),
  email        text not null,
  antwort      smallint not null check (antwort between 0 and 2),
  erstellt_am  timestamptz not null default now(),
  geaendert_am timestamptz not null default now(),
  unique (spiel_id, email)
);
alter table public.spiel_tipps enable row level security;
revoke all on public.spiel_tipps from anon, authenticated;

select relname, relrowsecurity as rls,
  (select count(*) from information_schema.role_table_grants g where g.table_name = 'spiel_tipps' and g.grantee in ('anon','authenticated')) as browser_rechte
from pg_class where relname = 'spiel_tipps';
