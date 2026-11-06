-- Ein-Klick-Umfragen unter Artikeln (06.11.2026). Im Supabase SQL-Editor einmal ausführen.
-- Gilt für beide Ligen (gleiche Datenbank). Geschrieben und gelesen wird nur über /api mit dem Service-Key.

create table if not exists public.umfrage_stimmen (
  id          bigint generated always as identity primary key,
  artikel_id  text not null check (artikel_id ~ '^[0-9a-f]{10}$'),
  antwort     smallint not null check (antwort between 0 and 2),
  geraet      text not null check (length(geraet) = 36),
  ip_hash     text not null,
  erstellt_am timestamptz not null default now(),
  unique (artikel_id, geraet)
);
create index if not exists umfrage_stimmen_ip_idx on public.umfrage_stimmen (ip_hash, erstellt_am desc);

-- Kein Zugriff für den Browser-Schlüssel: RLS an, keine Policies, alle Rechte weg
alter table public.umfrage_stimmen enable row level security;
revoke all on public.umfrage_stimmen from anon, authenticated;

-- Kontrolle, erwartet: rls = true, keine Zeile in der zweiten Abfrage
select relname, relrowsecurity as rls from pg_class where relname = 'umfrage_stimmen';
select grantee, privilege_type from information_schema.role_table_grants
where table_name = 'umfrage_stimmen' and grantee in ('anon', 'authenticated');
