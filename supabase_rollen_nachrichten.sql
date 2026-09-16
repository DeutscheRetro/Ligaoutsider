-- Ligaoutsider – Rollenverwaltung und Direktnachrichten
--
-- Im Supabase SQL-Editor ausfuehren.
--
-- Zwei neue Tabellen, beide komplett vor dem anon-Key verschlossen: Rollen und
-- private Nachrichten gehen niemanden etwas an, der nur den oeffentlichen
-- Schluessel hat. Gelesen und geschrieben wird ausschliesslich ueber
-- netlify/functions/api.js mit dem Service-Key.

-- ─── Rollen ──────────────────────────────────────────────────────────────────
-- Bisher lagen Rollen in Netlify Identity. Das hatte zwei Nachteile: sie liessen
-- sich nur im Netlify-Dashboard aendern, und sie greifen erst nach einem
-- erneuten Login, weil sie im Token stecken. Hier wirken sie sofort.
create table if not exists benutzer_rollen (
  email         text primary key,
  rollen        text[] not null default '{}',
  notiz         text,
  geaendert_am  timestamptz default now(),
  geaendert_von text
);

-- Startadmin, damit niemand ausgesperrt ist. Die Rolle aus dem Netlify-Token
-- gilt zusaetzlich weiter, beide Quellen werden vereinigt.
insert into benutzer_rollen (email, rollen, notiz, geaendert_von)
values ('twitchpre@gmail.com', array['admin'], 'Startadmin', 'system')
on conflict (email) do update set rollen = excluded.rollen;

-- ─── Direktnachrichten ───────────────────────────────────────────────────────
create table if not exists nachrichten (
  id            uuid primary key default gen_random_uuid(),
  von_email     text not null,
  von_name      text not null,
  an_email      text not null,
  inhalt        text not null,
  gelesen       boolean not null default false,
  erstellt_am   timestamptz default now(),
  -- Loescht einer der beiden das Gespraech, verschwindet es nur bei ihm
  geloescht_von text[] not null default '{}'
);

create index if not exists nachrichten_an_idx  on nachrichten (an_email, erstellt_am desc);
create index if not exists nachrichten_von_idx on nachrichten (von_email, erstellt_am desc);

-- ─── Zugriff ─────────────────────────────────────────────────────────────────
alter table benutzer_rollen enable row level security;
alter table nachrichten     enable row level security;

do $$
declare t text; p text;
begin
  foreach t in array array['benutzer_rollen','nachrichten']
  loop
    for p in select policyname from pg_policies
             where schemaname = 'public' and tablename = t
    loop
      execute format('drop policy %I on public.%I', p, t);
    end loop;
  end loop;
end $$;

-- Bewusst keine einzige Policy fuer anon: ohne Policy verweigert RLS jeden
-- Zugriff. Der Service-Key der Function ist davon nicht betroffen.

-- ─── Kontrolle ───────────────────────────────────────────────────────────────
--   select tablename, policyname, cmd, roles from pg_policies
--   where schemaname = 'public' and tablename in ('benutzer_rollen','nachrichten');
--   -> muss leer sein
