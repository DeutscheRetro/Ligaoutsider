"""
Ligaoutsider – Artikel-Generator
Ablauf: RSS holen → KI filtert → KI schreibt → HTML speichern → feed.json aktualisieren

Starten mit:  python generate.py
"""

import os
import json
import hashlib
import datetime
import re
import time
from pathlib import Path
from dotenv import load_dotenv
import feedparser
import anthropic
from slugify import slugify

load_dotenv()

# ─── Konfiguration ────────────────────────────────────────────────────────────

RSS_FEEDS = [
    # Deutsche Quellen
    "https://newsfeed.kicker.de/news/bundesliga",
    "https://www.sportschau.de/fussball/bundesliga/index~rss2.xml",
    "https://sportbild.bild.de/feed/sportbild-home.xml",
    "https://www.transfermarkt.de/rss/news",
    "https://rss.dw.com/xml/sport-de",

    # Englische Quellen
    "https://bulinews.com/rss",
    "https://www.eyefootball.com/rss_news_main.xml",
    "https://feeds.skysports.com/skysports/bundesliga",
    "https://www.goal.com/feeds/de/news",

    # Reddit (100 Einträge)
    "https://www.reddit.com/r/bundesliga/new.rss?limit=100",
    "https://www.reddit.com/r/soccer/new.rss?limit=100",
]

# Artikel bis zu X Tage alt akzeptieren
MAX_ALTER_TAGE = 3

# Wie viele neue Artikel maximal pro Durchlauf generieren
MAX_ARTIKEL_PRO_LAUF = 50

# Wo Artikel gespeichert werden
ARTIKEL_ORDNER = Path("artikel")
FEED_JSON      = Path("feed.json")

DISQUS_SHORTNAME = "ligaoutsider"  # <-- später auf disqus.com eintragen

# ─── 1. Bundesliga Klubs 2025/26 ──────────────────────────────────────────────

BL1_KLUBS = [
    "FC Bayern", "Bayern München", "Bayern",
    "Borussia Dortmund", "BVB",
    "RB Leipzig", "Leipzig",
    "Bayer Leverkusen", "Leverkusen",
    "Eintracht Frankfurt", "Frankfurt",
    "VfB Stuttgart", "Stuttgart",
    "Borussia Mönchengladbach", "Gladbach", "Mönchengladbach",
    "SC Freiburg", "Freiburg",
    "1. FC Union Berlin", "Union Berlin", "Union",
    "1. FSV Mainz", "Mainz",
    "FC Augsburg", "Augsburg",
    "SV Werder Bremen", "Werder",
    "TSG Hoffenheim", "Hoffenheim",
    "Hamburger SV", "HSV",
    "1. FC Köln", "Köln",
    "FC Schalke 04", "Schalke",
    "SC Paderborn", "Paderborn",
    "SV Elversberg", "Elversberg",
]

# ─── Wappen-URLs für die Feed-Anzeige ─────────────────────────────────────────

BL_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/d/df/Bundesliga_logo_%282017%29.svg/120px-Bundesliga_logo_%282017%29.svg.png"

W = "https://upload.wikimedia.org/wikipedia"  # Abkürzung

VEREIN_WAPPEN = {
    # Bayern (verifiziert ✓)
    "fc bayern münchen": f"{W}/commons/thumb/8/8d/FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg.png",
    "fc bayern":        f"{W}/commons/thumb/8/8d/FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg.png",
    "bayern":           f"{W}/commons/thumb/8/8d/FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg.png",
    "fcb":              f"{W}/commons/thumb/8/8d/FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg.png",
    # Dortmund (verifiziert ✓)
    "borussia dortmund":f"{W}/commons/thumb/6/67/Borussia_Dortmund_logo.svg/60px-Borussia_Dortmund_logo.svg.png",
    "dortmund":         f"{W}/commons/thumb/6/67/Borussia_Dortmund_logo.svg/60px-Borussia_Dortmund_logo.svg.png",
    "bvb":              f"{W}/commons/thumb/6/67/Borussia_Dortmund_logo.svg/60px-Borussia_Dortmund_logo.svg.png",
    # Leipzig (verifiziert ✓)
    "rb leipzig":       f"{W}/commons/thumb/d/d6/VEREINFACHTES_LOGO_-_RB_Leipzig.svg/60px-VEREINFACHTES_LOGO_-_RB_Leipzig.svg.png",
    "leipzig":          f"{W}/commons/thumb/d/d6/VEREINFACHTES_LOGO_-_RB_Leipzig.svg/60px-VEREINFACHTES_LOGO_-_RB_Leipzig.svg.png",
    # Leverkusen (verifiziert ✓)
    "bayer 04":         f"{W}/de/thumb/f/f7/Bayer_Leverkusen_Logo.svg/60px-Bayer_Leverkusen_Logo.svg.png",
    "leverkusen":       f"{W}/de/thumb/f/f7/Bayer_Leverkusen_Logo.svg/60px-Bayer_Leverkusen_Logo.svg.png",
    # Frankfurt (verifiziert ✓)
    "eintracht frankfurt": f"{W}/de/thumb/3/32/Logo_Eintracht_Frankfurt_1998.svg/60px-Logo_Eintracht_Frankfurt_1998.svg.png",
    "eintracht":        f"{W}/de/thumb/3/32/Logo_Eintracht_Frankfurt_1998.svg/60px-Logo_Eintracht_Frankfurt_1998.svg.png",
    "frankfurt":        f"{W}/de/thumb/3/32/Logo_Eintracht_Frankfurt_1998.svg/60px-Logo_Eintracht_Frankfurt_1998.svg.png",
    "sge":              f"{W}/de/thumb/3/32/Logo_Eintracht_Frankfurt_1998.svg/60px-Logo_Eintracht_Frankfurt_1998.svg.png",
    # Stuttgart
    "vfb stuttgart":    f"{W}/commons/thumb/e/eb/VfB_Stuttgart_1893_Logo.svg/60px-VfB_Stuttgart_1893_Logo.svg.png",
    "stuttgart":        f"{W}/commons/thumb/e/eb/VfB_Stuttgart_1893_Logo.svg/60px-VfB_Stuttgart_1893_Logo.svg.png",
    # Gladbach
    "mönchengladbach":  f"{W}/commons/thumb/8/81/Borussia_M%C3%B6nchengladbach_logo.svg/60px-Borussia_M%C3%B6nchengladbach_logo.svg.png",
    "gladbach":         f"{W}/commons/thumb/8/81/Borussia_M%C3%B6nchengladbach_logo.svg/60px-Borussia_M%C3%B6nchengladbach_logo.svg.png",
    "borussia m":       f"{W}/commons/thumb/8/81/Borussia_M%C3%B6nchengladbach_logo.svg/60px-Borussia_M%C3%B6nchengladbach_logo.svg.png",
    # Freiburg (verifiziert ✓)
    "sc freiburg":      f"{W}/de/thumb/b/bf/SC_Freiburg_Logo.svg/60px-SC_Freiburg_Logo.svg.png",
    "freiburg":         f"{W}/de/thumb/b/bf/SC_Freiburg_Logo.svg/60px-SC_Freiburg_Logo.svg.png",
    # Union Berlin
    "union berlin":     f"{W}/commons/thumb/4/44/1._FC_Union_Berlin_Logo.svg/60px-1._FC_Union_Berlin_Logo.svg.png",
    "1. fc union":      f"{W}/commons/thumb/4/44/1._FC_Union_Berlin_Logo.svg/60px-1._FC_Union_Berlin_Logo.svg.png",
    # Mainz
    "fsv mainz":        f"{W}/commons/thumb/9/9e/Logo_Mainz_05.svg/60px-Logo_Mainz_05.svg.png",
    "mainz":            f"{W}/commons/thumb/9/9e/Logo_Mainz_05.svg/60px-Logo_Mainz_05.svg.png",
    # Augsburg
    "fc augsburg":      f"{W}/de/thumb/b/b5/Logo_FC_Augsburg.svg/60px-Logo_FC_Augsburg.svg.png",
    "augsburg":         f"{W}/de/thumb/b/b5/Logo_FC_Augsburg.svg/60px-Logo_FC_Augsburg.svg.png",
    # Werder
    "sv werder":        f"{W}/commons/thumb/b/be/SV-Werder-Bremen-Logo.svg/60px-SV-Werder-Bremen-Logo.svg.png",
    "werder":           f"{W}/commons/thumb/b/be/SV-Werder-Bremen-Logo.svg/60px-SV-Werder-Bremen-Logo.svg.png",
    # Hoffenheim
    "tsg hoffenheim":   f"{W}/commons/thumb/e/e7/Logo_TSG_Hoffenheim.svg/60px-Logo_TSG_Hoffenheim.svg.png",
    "hoffenheim":       f"{W}/commons/thumb/e/e7/Logo_TSG_Hoffenheim.svg/60px-Logo_TSG_Hoffenheim.svg.png",
    "tsg 1899":         f"{W}/commons/thumb/e/e7/Logo_TSG_Hoffenheim.svg/60px-Logo_TSG_Hoffenheim.svg.png",
    # HSV
    "hamburger sv":     f"{W}/commons/thumb/f/f7/Hamburger_SV_logo.svg/60px-Hamburger_SV_logo.svg.png",
    "hamburger":        f"{W}/commons/thumb/f/f7/Hamburger_SV_logo.svg/60px-Hamburger_SV_logo.svg.png",
    "hsv":              f"{W}/commons/thumb/f/f7/Hamburger_SV_logo.svg/60px-Hamburger_SV_logo.svg.png",
    # Köln
    "1. fc köln":       f"{W}/commons/thumb/0/01/1._FC_Koeln_Logo_2014%E2%80%93.svg/60px-1._FC_Koeln_Logo_2014%E2%80%93.svg.png",
    "köln":             f"{W}/commons/thumb/0/01/1._FC_Koeln_Logo_2014%E2%80%93.svg/60px-1._FC_Koeln_Logo_2014%E2%80%93.svg.png",
    "effzeh":           f"{W}/commons/thumb/0/01/1._FC_Koeln_Logo_2014%E2%80%93.svg/60px-1._FC_Koeln_Logo_2014%E2%80%93.svg.png",
    # Schalke
    "fc schalke":       f"{W}/commons/thumb/6/6d/FC_Schalke_04_Logo.svg/60px-FC_Schalke_04_Logo.svg.png",
    "schalke":          f"{W}/commons/thumb/6/6d/FC_Schalke_04_Logo.svg/60px-FC_Schalke_04_Logo.svg.png",
    # Paderborn
    "sc paderborn":     "https://upload.wikimedia.org/wikipedia/commons/thumb/6/67/SC_Paderborn_07_Logo_new.svg/60px-SC_Paderborn_07_Logo_new.svg.png",
    "paderborn":        "https://upload.wikimedia.org/wikipedia/commons/thumb/6/67/SC_Paderborn_07_Logo_new.svg/60px-SC_Paderborn_07_Logo_new.svg.png",
    # Elversberg
    "sv elversberg":    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/SV_Elversberg_Logo_2021.svg/60px-SV_Elversberg_Logo_2021.svg.png",
    "elversberg":       "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/SV_Elversberg_Logo_2021.svg/60px-SV_Elversberg_Logo_2021.svg.png",
}

BADGE_KATEGORIEN = {
    "transfer":    ("Transfer",    "#e8c000", "#000"),
    "verletzung":  ("Verletzung",  "#e53935", "#fff"),
    "aufstellung": ("Aufstellung", "#2e7d32", "#fff"),
    "interview":   ("Interview",   "#1976d2", "#fff"),
    "analyse":     ("Analyse",     "#6a1fbf", "#fff"),
    "news":        ("News",        "#e8c000", "#000"),
}

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def artikel_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:10]


def schon_verarbeitet(url: str) -> bool:
    aid = artikel_id(url)
    return (ARTIKEL_ORDNER / f"{aid}.html").exists()


def verein_wappen_url(text: str) -> str:
    # Längere/spezifischere Namen zuerst prüfen (verhindert z.B. "Bayern" vor "Leipzig")
    text_lower = text.lower()
    sortiert = sorted(VEREIN_WAPPEN.keys(), key=len, reverse=True)
    for key in sortiert:
        if key in text_lower:
            return VEREIN_WAPPEN[key]
    return BL_LOGO


def badge_fuer_kategorie(kategorie: str) -> tuple:
    return BADGE_KATEGORIEN.get(kategorie.lower(), ("News", "#e8c000", "#000"))


def feed_laden() -> list:
    if FEED_JSON.exists():
        return json.loads(FEED_JSON.read_text(encoding="utf-8"))
    return []


def feed_speichern(artikel_liste: list):
    # Neueste zuerst, maximal 100 im Index
    artikel_liste.sort(key=lambda x: x["datum"], reverse=True)
    FEED_JSON.write_text(
        json.dumps(artikel_liste[:100], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ─── KI-Funktionen ────────────────────────────────────────────────────────────

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=60.0)


def ist_duplikat(neuer_titel: str, bestehende_titel: list) -> bool:
    """Prüft ob ein Artikel inhaltlich schon vorhanden ist.
    Gerücht ≠ Bestätigung → kein Duplikat.
    Gleiches Gerücht nochmal → Duplikat.
    """
    if not bestehende_titel:
        return False
    titel_liste = "\n".join(f"- {t}" for t in bestehende_titel[-40:])
    antwort = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                f"Ist diese neue Meldung ein Duplikat einer bereits vorhandenen?\n\n"
                f"Regeln:\n"
                f"- JA (Duplikat): Gleiches Ereignis, gleicher Stand, nur andere Quelle\n"
                f"- JA (Duplikat): Gleiches Gerücht das schon berichtet wurde\n"
                f"- NEIN (neu): Neue Entwicklung einer laufenden Geschichte (z.B. Gerücht → Bestätigung, Spekulation → offiziell)\n"
                f"- NEIN (neu): Komplett anderes Thema\n\n"
                f"NEUE MELDUNG: {neuer_titel}\n\n"
                f"BEREITS VORHANDENE ARTIKEL:\n{titel_liste}\n\n"
                f"Antworte nur mit JA oder NEIN."
            )
        }]
    )
    return "JA" in antwort.content[0].text.upper()


def ist_relevant(titel: str, beschreibung: str) -> bool:
    """Fragt Claude: Ist das eine echte 1. Bundesliga-News?"""
    klubs = ", ".join(BL1_KLUBS)
    antwort = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                f"Ist das eine relevante News über die 1. Bundesliga (Saison 2025/26)?\n"
                f"Die 18 Klubs der 1. Bundesliga sind: {klubs}.\n"
                f"Antworte NUR mit JA wenn:\n"
                f"- Es um mindestens einen dieser Klubs geht\n"
                f"- Es eine echte redaktionelle News ist (kein Reddit-Userpost, kein Werbeartikel, kein Quiz)\n"
                f"- Es KEIN WM-, EM- oder Nationalmansschaft-Thema ist\n"
                f"- Es KEINE 2. Liga oder niedrigere Liga ist\n\n"
                f"Titel: {titel}\nBeschreibung: {beschreibung}\n\n"
                f"Antworte nur mit JA oder NEIN."
            )
        }]
    )
    return "JA" in antwort.content[0].text.upper()


def artikel_generieren(titel: str, beschreibung: str, quelle_name: str, quelle_url: str) -> dict:
    """Lässt Claude einen eigenen Artikel schreiben und eine Kategorie wählen."""
    prompt = f"""Du bist Sportredakteur bei Ligaoutsider.de. Dein Stil orientiert sich an Bild.de: kurze Sätze, direkte Sprache, emotional, nah am Leser. Keine Füllwörter, keine gestelzte KI-Sprache.

Strikte Regeln:
- KEINE Gedankenstriche oder Bindestriche als Satzzeichen (kein " – ", kein " - " mitten im Satz)
- Stattdessen: Punkte, Ausrufezeichen, neue Sätze
- Kurze knackige Sätze. Maximal 20 Wörter pro Satz.
- Schreib wie ein Mensch, nicht wie eine KI
- Keine Aufzählungen, keine Bullet Points
- Sprich den Leser gelegentlich direkt an

Basierend auf dieser Meldung:
TITEL: {titel}
BESCHREIBUNG: {beschreibung}
QUELLE: {quelle_name} ({quelle_url})

Erstelle:
1. Einen packenden Titel im Bild-Stil (max. 80 Zeichen, kein Bindestrich als Satzzeichen)
2. Drei bis vier Absätze eigener Text auf Deutsch
3. Eine Kategorie aus: transfer, verletzung, aufstellung, interview, analyse, news

Antworte ausschließlich im folgenden JSON-Format (kein Markdown drumherum):
{{
  "titel": "...",
  "text": "Absatz 1.\\n\\nAbsatz 2.\\n\\nAbsatz 3.",
  "kategorie": "..."
}}"""

    antwort = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    roh = antwort.content[0].text.strip()
    # JSON aus der Antwort extrahieren (Claude hält sich fast immer dran)
    match = re.search(r'\{.*\}', roh, re.DOTALL)
    if not match:
        raise ValueError(f"Kein JSON in Antwort: {roh}")
    return json.loads(match.group())


# ─── HTML-Erzeugung ───────────────────────────────────────────────────────────

def artikel_html(
    datei_id: str,
    titel: str,
    text: str,
    kategorie: str,
    quelle_name: str,
    quelle_url: str,
    datum: str,
    wappen_url: str,
) -> str:
    badge_label, badge_bg, badge_fg = badge_fuer_kategorie(kategorie)
    absaetze = "".join(f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip())
    wappen_html = (
        f'<img src="{wappen_url}" class="artikel-wappen" alt="Wappen" />'
        if wappen_url else
        '<div class="artikel-wappen-placeholder">BL</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{titel} – Ligaoutsider.de</title>
  <link rel="stylesheet" href="../style.css"/>
  <link rel="stylesheet" href="../artikel.css"/>
</head>
<body>

  <div class="topbar">
    <div class="topbar-inner">
      <span>Saison 2025/26</span>
      <div class="topbar-right"><a href="#">Anmelden</a><a href="#">Registrieren</a></div>
    </div>
  </div>

  <header class="site-header">
    <div class="header-inner">
      <a href="../index.html" class="logo">
        <span class="logo-liga">Liga</span><span class="logo-outsider">outsider</span><span class="logo-de">.de</span>
      </a>
    </div>
  </header>

  <div class="artikel-wrap">
    <article class="artikel">

      <div class="artikel-header">
        {wappen_html}
        <div>
          <span class="feed-badge" style="background:{badge_bg};color:{badge_fg}">{badge_label}</span>
          <h1 class="artikel-titel">{titel}</h1>
          <p class="artikel-meta">{datum} &nbsp;·&nbsp; Quelle: <a href="{quelle_url}" target="_blank" rel="noopener">{quelle_name}</a></p>
        </div>
      </div>

      <div class="artikel-text">
        {absaetze}
      </div>

      <div class="artikel-quelle">
        Originalquelle: <a href="{quelle_url}" target="_blank" rel="noopener">{quelle_name}</a>
      </div>

    </article>

    <!-- Kommentare -->
    <section class="kommentare">
      <h2>Kommentare</h2>

      <div id="kommentar-liste"><p class="kommentar-laden">Lade Kommentare…</p></div>

      <form id="kommentar-form">
        <div class="kommentar-felder">
          <input type="text" id="k-name" placeholder="Dein Name" maxlength="60" required />
          <input type="email" id="k-email" placeholder="E-Mail (optional, nicht sichtbar)" maxlength="120" />
        </div>
        <textarea id="k-text" placeholder="Dein Kommentar…" maxlength="1000" required></textarea>
        <button type="submit" class="kommentar-btn">Kommentar absenden</button>
        <p id="kommentar-status"></p>
      </form>

      <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
      <script>
        const SUPABASE_URL  = 'https://rsodjlglzwlscamdlwev.supabase.co';
        const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJzb2RqbGdsendsc2NhbWRsd2V2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEzNjk1MzIsImV4cCI6MjA5Njk0NTUzMn0.ETR6sL-b-ZmjuqWFmj3jgP2vzq70J0Yb4JgATOCekns';
        const ARTIKEL_ID    = '{datei_id}';

        const sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON);

        async function ladeKommentare() {{
          const liste = document.getElementById('kommentar-liste');
          const {{ data, error }} = await sb
            .from('kommentare')
            .select('name, inhalt, erstellt_am')
            .eq('artikel_id', ARTIKEL_ID)
            .order('erstellt_am', {{ ascending: true }});

          if (error || !data?.length) {{
            liste.innerHTML = '<p class="kommentar-leer">Noch keine Kommentare. Sei der Erste!</p>';
            return;
          }}

          liste.innerHTML = data.map(k => {{
            const datum = new Date(k.erstellt_am).toLocaleDateString('de-DE', {{
              day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
            }});
            return `<div class="kommentar-item">
              <div class="kommentar-kopf">
                <span class="kommentar-name">${{k.name}}</span>
                <span class="kommentar-datum">${{datum}}</span>
              </div>
              <p class="kommentar-text">${{k.inhalt.replace(/</g,'&lt;')}}</p>
            </div>`;
          }}).join('');
        }}

        document.getElementById('kommentar-form').addEventListener('submit', async e => {{
          e.preventDefault();
          const status = document.getElementById('kommentar-status');
          const name   = document.getElementById('k-name').value.trim();
          const email  = document.getElementById('k-email').value.trim();
          const inhalt = document.getElementById('k-text').value.trim();

          if (!name || !inhalt) return;

          status.textContent = 'Wird gesendet…';
          const {{ error }} = await sb.from('kommentare').insert({{
            artikel_id: ARTIKEL_ID, name, email, inhalt
          }});

          if (error) {{
            status.textContent = 'Fehler: ' + error.message;
          }} else {{
            status.textContent = '✓ Kommentar wurde gespeichert!';
            document.getElementById('k-name').value  = '';
            document.getElementById('k-email').value = '';
            document.getElementById('k-text').value  = '';
            setTimeout(() => {{ status.textContent = ''; }}, 3000);
            ladeKommentare();
          }}
        }});

        ladeKommentare();
      </script>
    </section>

  </div>

  <footer class="site-footer">
    <div class="footer-inner">
      <p class="footer-copy">© Ligaoutsider.de, 2026</p>
      <nav class="footer-nav">
        <a href="#">Impressum</a>
        <a href="#">Datenschutzerklärung</a>
      </nav>
    </div>
  </footer>

</body>
</html>"""


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
    ARTIKEL_ORDNER.mkdir(exist_ok=True)
    bestehende = feed_laden()
    neu_generiert = 0

    print(f"Ligaoutsider Generator startet – max. {MAX_ARTIKEL_PRO_LAUF} neue Artikel")
    print("─" * 60)

    for feed_url in RSS_FEEDS:
        if neu_generiert >= MAX_ARTIKEL_PRO_LAUF:
            break

        print(f"\nLese Feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        quelle_name = feed.feed.get("title", feed_url)

        for eintrag in feed.entries:
            if neu_generiert >= MAX_ARTIKEL_PRO_LAUF:
                break

            url   = eintrag.get("link", "")
            titel = eintrag.get("title", "")
            beschr = eintrag.get("summary", eintrag.get("description", ""))

            # Bei Reddit: echte Quell-URL aus dem Post holen
            ist_reddit = "reddit.com" in feed_url
            if ist_reddit:
                echte_url = eintrag.get("url", "") or eintrag.get("source", {}).get("href", "")
                # Reddit-Posts haben die verlinkte URL oft im "url"-Feld
                if not echte_url:
                    # Aus der Beschreibung extrahieren
                    import re as _re
                    m = _re.search(r'href="(https?://(?!www\.reddit)[^"]+)"', beschr)
                    echte_url = m.group(1) if m else ""
                if echte_url and "reddit.com" not in echte_url:
                    from urllib.parse import urlparse as _up
                    quelle_name = _up(echte_url).netloc.replace("www.", "")
                    url = echte_url

            if not url or not titel:
                continue
            if schon_verarbeitet(url):
                print(f"  ↩  Übersprungen (schon vorhanden): {titel[:60]}")
                continue

            # Alters-Check: Einträge älter als MAX_ALTER_TAGE überspringen
            veroeffentlicht = eintrag.get("published_parsed") or eintrag.get("updated_parsed")
            if veroeffentlicht:
                alter = (datetime.datetime.now() - datetime.datetime(*veroeffentlicht[:6]))
                if alter.days > MAX_ALTER_TAGE:
                    aid = artikel_id(url)
                    (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                    continue

            print(f"  ✦  Prüfe: {titel[:60]}")

            if not ist_relevant(titel, beschr):
                print(f"  ✗  KI: nicht relevant")
                aid = artikel_id(url)
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                continue

            # Duplikat-Check gegen bestehende Artikel-Titel
            bestehende_titel = [a["titel"] for a in bestehende]
            if ist_duplikat(titel, bestehende_titel):
                print(f"  ⊘  KI: Duplikat – Thema bereits vorhanden")
                aid = artikel_id(url)
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                continue

            print(f"  ✓  KI: relevant & neu – schreibe Artikel …")

            try:
                ergebnis = artikel_generieren(titel, beschr, quelle_name, url)
            except Exception as e:
                print(f"  ⚠  Fehler beim Generieren: {e}")
                continue

            aid        = artikel_id(url)
            datum      = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            wappen_url = verein_wappen_url(ergebnis["titel"] + " " + beschr)
            html       = artikel_html(
                datei_id   = aid,
                titel      = ergebnis["titel"],
                text       = ergebnis["text"],
                kategorie  = ergebnis["kategorie"],
                quelle_name= quelle_name,
                quelle_url = url,
                datum      = datum,
                wappen_url = wappen_url,
            )

            datei_pfad = ARTIKEL_ORDNER / f"{aid}.html"
            datei_pfad.write_text(html, encoding="utf-8")

            badge_label, badge_bg, badge_fg = badge_fuer_kategorie(ergebnis["kategorie"])
            bestehende.append({
                "id":         aid,
                "titel":      ergebnis["titel"],
                "kategorie":  ergebnis["kategorie"],
                "badge":      badge_label,
                "badge_bg":   badge_bg,
                "badge_fg":   badge_fg,
                "datum":      datum,
                "wappen_url": wappen_url,
                "pfad":       f"artikel/{aid}.html",
            })

            feed_speichern(bestehende)
            neu_generiert += 1
            print(f"  ✅ Gespeichert: {ergebnis['titel'][:60]}")

    print(f"\n─" * 60)
    print(f"Fertig. {neu_generiert} neue Artikel generiert.")
    print(f"feed.json enthält jetzt {len(bestehende)} Artikel.")


if __name__ == "__main__":
    main()
