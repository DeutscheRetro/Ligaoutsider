-- Härtung der Datenbank (Stand 01.11.2026), Ergebnis des Datenbank-Reviews.
-- Im Supabase SQL-Editor ausführen. NICHTS davon ist bisher ausgeführt.
-- Reihenfolge: erst Teil 1 (nur lesen) ansehen, dann Teil 2 (Indizes), dann Teil 3 (Rechte, einzeln und mit Test).

-- ═══ Teil 1: Prüfen (ändert nichts) ═══════════════════════════════════════════
-- Dürfen anon/authenticated noch E-Mail-Spalten lesen? Erwartet: keine Zeilen.
select grantee, table_name, column_name, privilege_type
from information_schema.column_privileges
where table_schema = 'public' and column_name in ('email', 'voter_email', 'autor_email', 'versteckt_von')
  and grantee in ('anon', 'authenticated');

-- Welche Rechte haben anon/authenticated auf Tabellen? Erwartet: höchstens SELECT auf freigegebene Tabellen.
select grantee, table_name, privilege_type
from information_schema.role_table_grants
where table_schema = 'public' and grantee in ('anon', 'authenticated')
order by table_name, grantee;

-- Welche Indizes gibt es?
select tablename, indexname from pg_indexes where schemaname = 'public' order by 1, 2;

-- Doppelte Votes (müssen vor Teil 2 verschwinden)?
select kommentar_id, voter_email, count(*) from kommentar_votes group by 1, 2 having count(*) > 1;

-- ═══ Teil 2: Indizes (sicher, Daten bleiben unverändert) ═══════════════════
-- Doppelte Votes vorher entfernen (je Paar bleibt eine Zeile).
delete from kommentar_votes a using kommentar_votes b
where a.ctid > b.ctid and a.kommentar_id = b.kommentar_id and a.voter_email = b.voter_email;

create unique index if not exists kommentar_votes_uni on public.kommentar_votes (kommentar_id, voter_email);
create index if not exists kommentare_email_idx   on public.kommentare (email, erstellt_am desc);
create index if not exists kommentare_artikel_idx on public.kommentare (artikel_id, erstellt_am) where geloescht is not true;
create index if not exists forum_threads_email_idx on public.forum_threads (autor_email, erstellt_am desc);
create index if not exists forum_posts_email_idx   on public.forum_posts (autor_email, erstellt_am desc);
create index if not exists forum_threads_kat_idx   on public.forum_threads (kategorie, letzter_beitrag desc);
create index if not exists forum_posts_thread_idx  on public.forum_posts (thread_id, erstellt_am);
create index if not exists freundschaften_von_idx  on public.freundschaften (von_email) include (an_email, status);
create index if not exists freundschaften_an_idx   on public.freundschaften (an_email) include (von_email, status);
create index if not exists gaestebuch_autor_idx    on public.gaestebuch (autor_email);
create index if not exists tipps_spiel_idx         on public.tipps (spiel_id);

-- ═══ Teil 3: Rechte (Bruchgefahr: erst Teil 1 lesen, dann Block für Block ausführen und die Seite testen) ═══
-- Die öffentlichen Ansichten laufen mit Besitzerrechten und sollten weiter funktionieren.
-- 3a: Schreibrechte für anon/authenticated entziehen (geschrieben wird nur über /api mit dem Service-Key).
-- revoke insert, update, delete, truncate, references, trigger on all tables in schema public from anon, authenticated;
-- 3b: Interne Tabellen komplett sperren.
-- revoke all on public.profile, public.gaestebuch, public.freundschaften, public.blockierungen,
--   public.benutzer_rollen, public.nachrichten, public.submitted_urls, public.user_bans from anon, authenticated;
-- 3c: Neue Tabellen bekommen künftig keine Rechte für anon/authenticated.
-- alter default privileges in schema public revoke all on tables from anon, authenticated;
-- alter default privileges in schema public revoke all on functions from anon, authenticated;
-- 3d: Lese-Policies auch für angemeldete Nutzer (heute nutzt der Browser nur den anon-Key).
-- do $$ declare r record; begin
--   for r in select tablename, policyname from pg_policies
--            where schemaname = 'public' and policyname like 'anon_liest_%' and tablename <> 'user_bans' loop
--     execute format('alter policy %I on public.%I to anon, authenticated', r.policyname, r.tablename);
--   end loop; end $$;
-- drop policy if exists anon_liest_bans on public.user_bans;
-- 3e: Ansichten abdichten.
-- alter view public.profile_oeffentlich    set (security_barrier = true);
-- alter view public.gaestebuch_oeffentlich set (security_barrier = true);
-- alter view public.freunde_oeffentlich    set (security_barrier = true);
