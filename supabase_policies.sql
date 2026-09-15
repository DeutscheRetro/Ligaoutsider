-- Ligaoutsider – Zugriffsrechte der Datenbank
--
-- Ausgangslage: der anon-Key durfte auf allen Tabellen SELECT, UPDATE und
-- DELETE. Da dieser Key zwangslaeufig in jeder Artikelseite steht, konnte
-- jeder Besucher saemtliche Kommentare und Forenbeitraege loeschen oder
-- umschreiben.
--
-- Neue Regel: der anon-Key darf ausschliesslich lesen. Jede Aenderung laeuft
-- ueber netlify/functions/api.js, das den Service-Key benutzt (der umgeht RLS)
-- und vorher das Netlify-Identity-Token samt Rolle prueft.
--
-- Im Supabase SQL-Editor ausfuehren.

-- ─── Tabelle fuer sofort ausgeblendete Artikel ───────────────────────────────
create table if not exists hidden_articles (
  artikel_id    text primary key,
  versteckt_von text,
  erstellt_am   timestamptz default now()
);

-- Einsendungen laufen jetzt ueber die Function und tragen den Absender
alter table submitted_urls add column if not exists eingereicht_von text;

-- ─── RLS ueberall einschalten ────────────────────────────────────────────────
alter table kommentare      enable row level security;
alter table kommentar_votes enable row level security;
alter table user_bans       enable row level security;
alter table forum_threads   enable row level security;
alter table forum_posts     enable row level security;
alter table submitted_urls  enable row level security;
alter table hidden_articles enable row level security;

-- ─── Alte, zu weite Policies entfernen ───────────────────────────────────────
do $$
declare t text; p text;
begin
  foreach t in array array['kommentare','kommentar_votes','user_bans',
                           'forum_threads','forum_posts','submitted_urls',
                           'hidden_articles']
  loop
    for p in select policyname from pg_policies
             where schemaname = 'public' and tablename = t
    loop
      execute format('drop policy %I on public.%I', p, t);
    end loop;
  end loop;
end $$;

-- ─── Nur noch Lesen fuer anon ────────────────────────────────────────────────
-- Die Seite rendert Kommentare, Forum und ausgeblendete IDs direkt im Browser.
create policy anon_liest_kommentare      on kommentare      for select to anon using (true);
create policy anon_liest_votes           on kommentar_votes for select to anon using (true);
create policy anon_liest_threads         on forum_threads   for select to anon using (true);
create policy anon_liest_posts           on forum_posts     for select to anon using (true);
create policy anon_liest_hidden          on hidden_articles for select to anon using (true);

-- user_bans: nur die Sperrdaten, damit die Seite gesperrte Nutzer erkennt.
create policy anon_liest_bans            on user_bans       for select to anon using (true);

-- submitted_urls bleibt komplett zu: Einsendungen laufen ueber die Function,
-- und niemand soll die Vorschlaege anderer auslesen koennen.

-- Kein INSERT, UPDATE oder DELETE fuer anon. Ohne passende Policy verweigert
-- RLS diese Operationen automatisch – der Service-Key der Function ist davon
-- nicht betroffen.

-- ─── Kontrolle ───────────────────────────────────────────────────────────────
-- Muss ausschliesslich SELECT-Zeilen liefern:
--   select tablename, policyname, cmd, roles from pg_policies
--   where schemaname = 'public' order by tablename;
