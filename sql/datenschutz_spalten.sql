-- Datenschutz (09.10.2026): E-Mail-Adressen nicht mehr öffentlich lesbar.
-- Der Browser liest nur noch die freigegebenen Spalten; alles mit E-Mail
-- läuft über /api (Service-Key, ist von diesen Rechten nicht betroffen).
-- Ausführen in Supabase → SQL Editor → New query → Run.

-- Kommentare: alles außer email
revoke select on public.kommentare from anon, authenticated;
grant select (id, artikel_id, name, inhalt, erstellt_am, geaendert_am, geloescht, autor_handle)
  on public.kommentare to anon, authenticated;

-- Bewertungen: ohne voter_email
revoke select on public.kommentar_votes from anon, authenticated;
grant select (kommentar_id, vote) on public.kommentar_votes to anon, authenticated;

-- Forum: ohne autor_email
revoke select on public.forum_threads from anon, authenticated;
grant select (id, kategorie, titel, autor_name, autor_handle, erstellt_am, letzter_beitrag, antworten)
  on public.forum_threads to anon, authenticated;
revoke select on public.forum_posts from anon, authenticated;
grant select (id, thread_id, inhalt, autor_name, autor_handle, erstellt_am)
  on public.forum_posts to anon, authenticated;

-- Ausgeblendete Artikel: ohne versteckt_von (Admin-E-Mail)
revoke select on public.hidden_articles from anon, authenticated;
grant select (artikel_id) on public.hidden_articles to anon, authenticated;

-- Sperren: gar nicht mehr öffentlich (Status kommt über /api)
revoke select on public.user_bans from anon, authenticated;
