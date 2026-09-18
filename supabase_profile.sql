-- Ligaoutsider – Nutzerprofile, Gästebuch, Freundschaften, Blockieren
--
-- Im Supabase SQL-Editor ausführen.
--
-- Die Tabellen selbst sind für den anon-Key komplett gesperrt, weil sie
-- E-Mail-Adressen enthalten. Öffentlich lesbar sind nur die drei Views
-- darunter, die ausschließlich Profilnamen (handle) zeigen. Geschrieben wird
-- nur über netlify/functions/api.js mit dem Service-Key.

-- ─── Profile ─────────────────────────────────────────────────────────────────
create table if not exists profile (
  email             text primary key,
  handle            text not null unique check (handle ~ '^[a-z0-9-]{3,30}$'),
  anzeigename       text not null,
  ueber_mich        text not null default '',
  wohnort           text not null default '',
  lieblings         jsonb not null default '{}'::jsonb,
  gaestebuch_offen  boolean not null default true,
  erstellt_am       timestamptz default now(),
  aktualisiert_am   timestamptz default now()
);

-- ─── Gästebuch ───────────────────────────────────────────────────────────────
create table if not exists gaestebuch (
  id            uuid primary key default gen_random_uuid(),
  profil_email  text not null references profile(email) on delete cascade,
  autor_email   text not null,
  inhalt        text not null,
  erstellt_am   timestamptz default now(),
  geloescht     boolean not null default false
);
create index if not exists gaestebuch_profil_idx on gaestebuch (profil_email, erstellt_am desc);

-- ─── Freundschaften ──────────────────────────────────────────────────────────
-- status 'offen' = Anfrage von von_email an an_email, 'ok' = befreundet
create table if not exists freundschaften (
  id           uuid primary key default gen_random_uuid(),
  von_email    text not null,
  an_email     text not null,
  status       text not null default 'offen' check (status in ('offen', 'ok')),
  erstellt_am  timestamptz default now(),
  unique (von_email, an_email)
);

-- ─── Blockieren ──────────────────────────────────────────────────────────────
create table if not exists blockierungen (
  blocker_email    text not null,
  blockiert_email  text not null,
  erstellt_am      timestamptz default now(),
  primary key (blocker_email, blockiert_email)
);

-- Kommentare und Forum merken sich den Profilnamen, damit Namen auf das
-- Profil verlinken können, ohne die E-Mail zu brauchen
alter table kommentare  add column if not exists autor_handle text;
alter table forum_posts add column if not exists autor_handle text;
alter table forum_threads add column if not exists autor_handle text;

-- ─── Zugriff ─────────────────────────────────────────────────────────────────
alter table profile        enable row level security;
alter table gaestebuch     enable row level security;
alter table freundschaften enable row level security;
alter table blockierungen  enable row level security;

do $$
declare t text; p text;
begin
  foreach t in array array['profile','gaestebuch','freundschaften','blockierungen']
  loop
    for p in select policyname from pg_policies where schemaname = 'public' and tablename = t
    loop
      execute format('drop policy %I on public.%I', p, t);
    end loop;
  end loop;
end $$;
-- Keine Policy = kein Zugriff für anon. Die Views unten laufen mit den
-- Rechten ihres Besitzers und geben nur unkritische Spalten heraus.

-- ─── Öffentliche Ansichten (ohne E-Mail) ─────────────────────────────────────
create or replace view profile_oeffentlich as
  select handle, anzeigename, ueber_mich, wohnort, lieblings, gaestebuch_offen, erstellt_am
  from profile;

create or replace view gaestebuch_oeffentlich as
  select g.id, p.handle as profil_handle, a.handle as autor_handle,
         coalesce(a.anzeigename, 'Unbekannt') as autor_name, g.inhalt, g.erstellt_am
  from gaestebuch g
  join profile p on p.email = g.profil_email
  left join profile a on a.email = g.autor_email
  where not g.geloescht;

create or replace view freunde_oeffentlich as
  select p1.handle as handle, p2.handle as freund_handle, p2.anzeigename as freund_name
  from freundschaften f
  join profile p1 on p1.email = f.von_email
  join profile p2 on p2.email = f.an_email
  where f.status = 'ok'
  union all
  select p2.handle, p1.handle, p1.anzeigename
  from freundschaften f
  join profile p1 on p1.email = f.von_email
  join profile p2 on p2.email = f.an_email
  where f.status = 'ok';

grant select on profile_oeffentlich, gaestebuch_oeffentlich, freunde_oeffentlich to anon, authenticated;

-- ─── Kontrolle ───────────────────────────────────────────────────────────────
--   select * from profile_oeffentlich limit 1;         -- geht mit anon
--   select * from profile limit 1;                     -- muss mit anon leer/verboten sein
