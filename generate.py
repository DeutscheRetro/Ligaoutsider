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
    "https://www.transfermarkt.de/bundesliga/news/wettbewerb/L1?rss=1",
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
    # Bayern
    "fc bayern münchen": "../logos/bayern.png",
    "fc bayern":         "../logos/bayern.png",
    "bayern":            "../logos/bayern.png",
    "fcb":               "../logos/bayern.png",
    # Dortmund
    "borussia dortmund": "../logos/dortmund.png",
    "dortmund":          "../logos/dortmund.png",
    "bvb":               "../logos/dortmund.png",
    # Leipzig
    "rb leipzig":          "../logos/leipzig.png",
    "leipzig":             "../logos/leipzig.png",
    # Leverkusen
    "bayer 04":            "../logos/leverkusen.png",
    "leverkusen":          "../logos/leverkusen.png",
    # Frankfurt
    "eintracht frankfurt": "../logos/frankfurt.png",
    "eintracht":           "../logos/frankfurt.png",
    "frankfurt":           "../logos/frankfurt.png",
    "sge":                 "../logos/frankfurt.png",
    # Stuttgart
    "vfb stuttgart":    "../logos/stuttgart.png",
    "stuttgart":        "../logos/stuttgart.png",
    # Gladbach
    "mönchengladbach":  "../logos/gladbach.png",
    "gladbach":         "../logos/gladbach.png",
    "borussia m":       "../logos/gladbach.png",
    # Freiburg
    "sc freiburg":      "../logos/freiburg.png",
    "freiburg":         "../logos/freiburg.png",
    # Union Berlin
    "union berlin":     "../logos/union.png",
    "1. fc union":      "../logos/union.png",
    # Mainz
    "fsv mainz":        "../logos/mainz.png",
    "mainz":            "../logos/mainz.png",
    # Augsburg
    "fc augsburg":      "../logos/augsburg.png",
    "augsburg":         "../logos/augsburg.png",
    # Werder
    "sv werder":        "../logos/werder.png",
    "werder":           "../logos/werder.png",
    # Hoffenheim
    "tsg hoffenheim":   "../logos/hoffenheim.png",
    "hoffenheim":       "../logos/hoffenheim.png",
    "tsg 1899":         "../logos/hoffenheim.png",
    # HSV
    "hamburger sv":     "../logos/hsv.png",
    "hamburger":        "../logos/hsv.png",
    "hsv":              "../logos/hsv.png",
    # Köln
    "1. fc köln":       "../logos/koeln.png",
    "köln":             "../logos/koeln.png",
    "effzeh":           "../logos/koeln.png",
    # Schalke
    "fc schalke":       "../logos/schalke.png",
    "schalke":          "../logos/schalke.png",
    # Paderborn
    "sc paderborn":     "../logos/paderborn.png",
    "paderborn":        "../logos/paderborn.png",
    # Elversberg
    "sv elversberg":    "../logos/elversberg.png",
    "elversberg":       "../logos/elversberg.png",
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
    from datetime import datetime
    artikel_liste.sort(key=lambda x: datetime.strptime(x["datum"], "%d.%m.%Y %H:%M"), reverse=True)
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
                f"Ist das eine relevante News über die 1. Bundesliga (Saison 2026/27)?\n"
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
    prompt = f"""Du bist Sportredakteur bei Ligaoutsider.de. Dein Stil orientiert sich an kicker.de: sachlich, präzise, informativ. Fachkundige Sprache ohne Reißerisches. Keine KI-Floskeln, kein aufgeblasener Stil.

Strikte Regeln:
- Seriöser Sportzeitungsstil wie kicker.de oder Sportschau
- KEINE Gedankenstriche oder Bindestriche als Satzzeichen mitten im Satz
- Klare, vollständige Sätze. Maximal 25 Wörter pro Satz.
- Fakten zuerst. Hintergründe und Einordnung danach.
- Keine Ausrufezeichen, keine Reißer-Formulierungen
- Keine Aufzählungen, keine Bullet Points
- Schreib wie ein erfahrener Fußballjournalist

Basierend auf dieser Meldung:
TITEL: {titel}
BESCHREIBUNG: {beschreibung}
QUELLE: {quelle_name} ({quelle_url})

Erstelle:
1. Einen präzisen, informativen Titel im Kicker-Stil (max. 80 Zeichen, keine Bindestriche als Satzzeichen)
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
        f'<img src="{wappen_url}" class="artikel-wappen" alt="Wappen" onerror="this.style.display=\'none\'"/>'
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
  <script>if(localStorage.getItem('theme')==='light')document.body.classList.add('light');</script>
</head>
<body>

  <script src="https://identity.netlify.com/v1/netlify-identity-widget.js"></script>

  <header class="site-header">
    <div class="header-inner">
      <a href="../index.html" class="logo">
        <span class="logo-liga">Liga</span><span class="logo-outsider">outsider</span><span class="logo-de">.de</span>
      </a>
      <div class="header-right">
        <button class="theme-toggle" id="theme-toggle" title="Hell/Dunkel wechseln">
          <span id="theme-icon">☀️</span>
          <span id="theme-label">Hell</span>
        </button>
        <div class="auth-buttons">
          <a href="#" class="auth-btn" id="login-btn">Anmelden</a>
          <span id="user-info" style="display:none">
            <span id="user-name" class="auth-username"></span>
            <a href="#" class="auth-btn" id="logout-btn">Abmelden</a>
          </span>
        </div>
      </div>
    </div>
  </header>

  <nav class="section-nav">
    <div class="section-nav-inner">
      <a href="../index.html" class="section-nav-link">Aktuelle News</a>
      <a href="../archiv.html" class="section-nav-link">Newsarchiv</a>
      <a href="../kickbase.html" class="section-nav-link">Kickbase-Stats</a>
      <a href="../forum.html" class="section-nav-link">💬 Forum</a>
    </div>
  </nav>

  <div class="artikel-wrap">
    <a href="javascript:history.back()" class="artikel-back">← Zurück</a>
    <article class="artikel">

      <div class="artikel-header">
        {wappen_html}
        <div>
          <span class="feed-badge" style="background:{badge_bg};color:{badge_fg}">{badge_label}</span>
          <h1 class="artikel-titel">{titel}</h1>
          <p class="artikel-meta">{datum}</p>
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
      <p id="k-gasthinweis" style="font-size:13px;color:var(--text4);margin-top:16px">
        Bitte <a href="#" onclick="netlifyIdentity.open('login');return false;" style="color:var(--accent)">anmelden</a>, um Kommentare zu schreiben.
      </p>
      <form id="kommentar-form" style="display:none">
        <p id="k-eingeloggt" style="font-size:12px;color:var(--text4);margin-bottom:8px">Kommentieren als <strong id="k-username" style="color:var(--accent)"></strong></p>
        <textarea id="k-text" placeholder="Dein Kommentar…" maxlength="1000" required></textarea>
        <button type="submit" class="kommentar-btn">Kommentar absenden</button>
        <p id="kommentar-status"></p>
      </form>
    </section>

  </div>

  <script>
    const SUPABASE_URL  = 'https://rsodjlglzwlscamdlwev.supabase.co';
    const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJzb2RqbGdsendsc2NhbWRsd2V2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEzNjk1MzIsImV4cCI6MjA5Njk0NTUzMn0.ETR6sL-b-ZmjuqWFmj3jgP2vzq70J0Yb4JgATOCekns';
    const ARTIKEL_ID    = '{datei_id}';
    const ADMIN_EMAIL   = 'twitchpre@gmail.com';
  </script>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
  <script src="../kommentare.js"></script>

  <footer class="site-footer">
    <div class="footer-inner">
      <p class="footer-copy">© Ligaoutsider.de, 2026</p>
      <nav class="footer-nav">
        <a href="../impressum.html">Impressum</a>
        <a href="../datenschutz.html">Datenschutzerklärung</a>
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


def kickbase_fetch():
    """Kickbase-Daten holen und kickbase.json schreiben."""
    import requests

    email    = os.environ.get("KICKBASE_EMAIL", "")
    password = os.environ.get("KICKBASE_PASSWORD", "")
    if not email or not password:
        print("⚠️  KICKBASE_EMAIL/PASSWORD nicht gesetzt – überspringe Kickbase.")
        return

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})

    # Login
    try:
        r = session.post("https://api.kickbase.com/user/login",
                         json={"email": email, "password": password, "ext": True}, timeout=15)
        r.raise_for_status()
        token = r.json()["token"]
        session.headers["Authorization"] = f"Bearer {token}"
        print("✅ Kickbase Login erfolgreich")
    except Exception as e:
        print(f"❌ Kickbase Login fehlgeschlagen: {e}")
        return

    # Bundesliga = competition 1
    COMP = "1"
    LOGO_MAP = {
        "FC Bayern München": "bayern", "Borussia Dortmund": "dortmund", "RB Leipzig": "leipzig",
        "Bayer 04 Leverkusen": "leverkusen", "Eintracht Frankfurt": "frankfurt", "VfB Stuttgart": "stuttgart",
        "Borussia Mönchengladbach": "gladbach", "Sport-Club Freiburg": "freiburg", "1. FC Union Berlin": "union",
        "1. FSV Mainz 05": "mainz", "FC Augsburg": "augsburg", "SV Werder Bremen": "werder",
        "TSG Hoffenheim": "hoffenheim", "Hamburger SV": "hsv", "1. FC Köln": "koeln",
        "FC Schalke 04": "schalke", "SC Paderborn 07": "paderborn", "SV Elversberg": "elversberg",
    }

    try:
        r = session.get(f"https://api.kickbase.com/competition/{COMP}/players", timeout=20)
        r.raise_for_status()
        raw = r.json().get("players", r.json() if isinstance(r.json(), list) else [])
    except Exception as e:
        print(f"❌ Kickbase Spieler-Fetch fehlgeschlagen: {e}")
        return

    players = []
    for p in raw:
        mw   = p.get("marketValue", 0) or 0
        pts  = p.get("totalPoints", 0) or 0
        ap   = p.get("averagePoints", 0) or 0
        own  = p.get("teamData", {}).get("teamId") or p.get("teamId") or ""
        team = p.get("teamName", "")
        name = (p.get("firstName", "") + " " + p.get("lastName", "")).strip() or p.get("name", "")
        logo = LOGO_MAP.get(team, "")
        mw7  = p.get("marketValueTrend", 0) or 0  # einige APIs liefern absoluten 7-Tage-Diff
        own_pct = p.get("ownerPercentage", 0) or p.get("ownPercentage", 0) or 0
        # Letzte-Spieltag-Punkte
        sp_pts = p.get("lastMatchPoints", 0) or p.get("currentSeasonMatchDayPoints", 0) or 0
        players.append({
            "name": name, "logo": logo, "mw": mw, "pts": pts, "ap": ap,
            "mw7": mw7, "own": own_pct, "sp_pts": sp_pts,
        })

    # Effizienz: Punkte pro Million MW
    for p in players:
        p["eff"] = round(p["pts"] / (p["mw"] / 1e6), 2) if p["mw"] > 500000 else 0

    def top(lst, key, n=10, reverse=True):
        return sorted([x for x in lst if x[key]], key=lambda x: x[key], reverse=reverse)[:n]

    def fmt(lst, val_key, extra_key=None):
        out = []
        for p in lst:
            d = {"name": p["name"], "logo": p["logo"]}
            d[val_key] = p[val_key]
            if extra_key:
                d[extra_key] = p[extra_key]
            out.append(d)
        return out

    teuerste  = [{"name":p["name"],"logo":p["logo"],"mw":p["mw"]}    for p in top(players,"mw")]
    punkte    = [{"name":p["name"],"logo":p["logo"],"pts":p["pts"]}   for p in top(players,"pts")]
    effizienz = [{"name":p["name"],"logo":p["logo"],"eff":p["eff"]}   for p in top(players,"eff")]
    raketen   = [{"name":p["name"],"logo":p["logo"],"diff":p["mw7"]}  for p in top(players,"mw7")]
    crash     = [{"name":p["name"],"logo":p["logo"],"diff":p["mw7"]}  for p in top(players,"mw7",reverse=False)]
    beliebt   = [{"name":p["name"],"logo":p["logo"],"ownership":p["own"]} for p in top(players,"own")]
    spieltag  = [{"name":p["name"],"logo":p["logo"],"pts":p["sp_pts"]} for p in top(players,"sp_pts")]
    form_top  = [{"name":p["name"],"logo":p["logo"],"avg":p["ap"]}    for p in top(players,"ap")]
    # Hidden Gems: hohe Effizienz aber geringe Ownership (unter 30%)
    gems_raw  = [p for p in players if p["own"] < 30 and p["eff"] > 0]
    gems      = [{"name":p["name"],"logo":p["logo"],"eff":p["eff"]}   for p in top(gems_raw,"eff")]

    result = {
        "updated":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "teuerste":  teuerste,
        "punkte":    punkte,
        "effizienz": effizienz,
        "raketen":   raketen,
        "crash":     crash,
        "beliebt":   beliebt,
        "spieltag":  spieltag,
        "form":      form_top,
        "gems":      gems,
    }
    Path("kickbase.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ kickbase.json geschrieben ({len(players)} Spieler verarbeitet)")


def spieler_fetch():
    """Top-Scorer aus OpenLigaDB holen, Profildaten scrapen, spieler/*.json speichern."""
    import urllib.request

    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def get_json(url, headers=None):
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def get_html(url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")

    SPIELER_ORDNER = Path("spieler")
    SPIELER_ORDNER.mkdir(exist_ok=True)

    # 1. Top-Scorer aus OpenLigaDB
    print("📊 Lade Torjäger von OpenLigaDB …")
    try:
        scorer_data = get_json("https://api.openligadb.de/getgoalgetters/bl1/2025")
    except Exception as e:
        print(f"❌ OpenLigaDB Fehler: {e}")
        return

    top_scorer = sorted(scorer_data, key=lambda x: x["goalCount"], reverse=True)[:15]

    # goalGetterId → teamId via Spieldaten (letzter Spieltag reicht)
    player_team = {}
    try:
        matches = get_json("https://api.openligadb.de/getmatchdata/bl1/2025")
        for m in matches:
            for g in (m.get("goals") or []):
                if g.get("goalGetterID") and g.get("scoringTeamId") and not g.get("isOwnGoal"):
                    player_team[g["goalGetterID"]] = g["scoringTeamId"]
    except Exception as e:
        print(f"⚠️  Spieldaten Fehler: {e}")

    # teamId → Name
    team_names = {}
    try:
        teams = get_json("https://api.openligadb.de/getavailableteams/bl1/2025")
        for t in teams:
            team_names[t["teamId"]] = t["teamName"]
    except Exception:
        pass

    for scorer in top_scorer:
        gid = scorer["goalGetterId"]
        name = scorer["goalGetterName"]
        print(f"  → {name} …", end=" ", flush=True)

        out_path = SPIELER_ORDNER / f"{gid}.json"

        # 2. Wikipedia-Foto + Seitenlink
        wiki_foto = None
        wiki_seite = None
        wiki_autor = None
        try:
            # Vollständigen Namen für Wikipedia brauchen wir — probiere zuerst mit Abkürzung
            # OpenLigaDB gibt "H. Kane" → wir suchen via Wikipedia-Suche
            wiki_search = get_json(
                f"https://de.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={urllib.parse.quote(name + ' Fußballer')}&srlimit=1&format=json"
            )
            hits = wiki_search.get("query", {}).get("search", [])
            if hits:
                page_title = hits[0]["title"]
                summary = get_json(
                    f"https://de.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title)}"
                )
                wiki_foto = summary.get("thumbnail", {}).get("source")
                wiki_seite = summary.get("content_urls", {}).get("desktop", {}).get("page")
                # Bildautor via Commons API (best-effort)
                img_file = summary.get("originalimage", {}).get("source", "")
                m_file = re.search(r'/commons/[^/]+/[^/]+/([^/]+\.(?:jpg|jpeg|png|svg))', img_file, re.I)
                if m_file:
                    file_name = urllib.parse.unquote(m_file.group(1))
                    img_info = get_json(
                        f"https://commons.wikimedia.org/w/api.php?action=query&titles=File:{urllib.parse.quote(file_name)}"
                        f"&prop=imageinfo&iiprop=extmetadata&format=json"
                    )
                    pages = img_info.get("query", {}).get("pages", {})
                    for p in pages.values():
                        meta = (p.get("imageinfo") or [{}])[0].get("extmetadata", {})
                        artist = meta.get("Artist", {}).get("value", "")
                        # Strip HTML tags
                        artist = re.sub(r'<[^>]+>', '', artist).strip()
                        if artist:
                            wiki_autor = artist[:80]
        except Exception:
            pass

        # 3. TM-ID via Namenssuche
        tm_id = None
        tm_mw = None
        tm_alter = None
        tm_groesse = None
        tm_nation = None
        tm_position = None
        try:
            # Suche nach vollem Namen (ohne Abkürzung) — nutze Wikipedia-Titel wenn verfügbar
            vollname = page_title if 'page_title' in dir() and page_title else name
            search_html = get_html(
                f"https://www.transfermarkt.de/schnellsuche/ergebnis/schnellsuche?query={urllib.parse.quote(vollname)}&Spieler_page=0"
            )
            m_id = re.search(r'href="/[^/]+/profil/spieler/(\d+)"', search_html)
            if m_id:
                tm_id = m_id.group(1)

                # Profilseite
                profil_html = get_html(f"https://www.transfermarkt.de/x/profil/spieler/{tm_id}")

                # Marktwert
                m_mw = re.search(r'(\d+[,\.]\d+)\s*(Mio|Tsd)\.?\s*€', profil_html)
                if m_mw:
                    betrag = m_mw.group(1).replace(",", ".")
                    einheit = m_mw.group(2)
                    tm_mw = f"{m_mw.group(1)} {einheit}. €"

                # Info-Tabelle parsen
                info_block = re.search(r'class="info-table[^"]*">(.*?)class="box"', profil_html, re.DOTALL)
                if info_block:
                    block = info_block.group(1)
                    # Alter
                    m_age = re.search(r'\d{2}\.\d{2}\.\d{4}\s*\((\d+)\)', block)
                    if m_age:
                        tm_alter = int(m_age.group(1))
                    # Größe
                    m_gr = re.search(r'(\d,\d{2})\s*m', block)
                    if m_gr:
                        tm_groesse = m_gr.group(1) + " m"
                    # Nationalität (text hinter Flagge)
                    nations = re.findall(r'title="([A-ZÄÖÜ][a-zäöüA-ZÄÖÜ\s\-]+)"\s+alt="\1"[^>]+class="flaggenrahmen"', block)
                    if nations:
                        tm_nation = nations[0]
                    # Position
                    m_pos = re.search(r'Hauptposition.*?detail-position__position">([^<]+)<', profil_html, re.DOTALL)
                    if m_pos:
                        tm_position = m_pos.group(1).strip()
        except Exception as e:
            print(f"(TM Fehler: {e})", end=" ")

        # 4. TM Performance-Daten (Saison-Aggregat)
        karriere = []
        if tm_id:
            try:
                perf = get_json(
                    f"https://www.transfermarkt.de/ceapi/performance-game/{tm_id}",
                    headers={"x-tmapi-version": "1"}
                )
                games = perf.get("data", {}).get("performance", [])

                # Aggregieren nach Saison + Liga
                from collections import defaultdict
                saison_stats = defaultdict(lambda: {"spiele": 0, "tore": 0, "assists": 0, "minuten": 0})
                saison_meta = {}  # saison_key → (display, liga)

                LIGA_NAMEN = {
                    "L1": "Bundesliga", "GB1": "Premier League", "ES1": "La Liga",
                    "IT1": "Serie A", "FR1": "Ligue 1", "NL1": "Eredivisie",
                    "PO1": "Primeira Liga", "TR1": "Süper Lig", "DFB": "DFB-Pokal",
                    "CL": "Champions League", "EL": "Europa League", "FIWC": "WM",
                    "EM": "EM",
                }

                for g in games:
                    info = g.get("gameInformation", {})
                    comp = info.get("competitionId", "")
                    # Nur Ligaspiele (keine Pokal/Int für Karriere)
                    if info.get("isNationalGame"):
                        continue
                    season_display = info.get("season", {}).get("display", "")
                    if not season_display:
                        continue
                    key = f"{season_display}_{comp}"
                    stats = g.get("statistics", {})
                    goal_stats = stats.get("goalStatistics", {})
                    time_stats = stats.get("playingTimeStatistics", {})

                    if time_stats.get("participationState") == "not_in_squad":
                        continue

                    saison_stats[key]["spiele"] += 1
                    saison_stats[key]["tore"] += goal_stats.get("goalsScoredTotal") or 0
                    saison_stats[key]["assists"] += goal_stats.get("assists") or 0
                    saison_stats[key]["minuten"] += time_stats.get("playedMinutes") or 0
                    if key not in saison_meta:
                        saison_meta[key] = {
                            "saison": season_display,
                            "liga": LIGA_NAMEN.get(comp, comp),
                            "season_id": info.get("season", {}).get("id", 0)
                        }

                # Sortiert neueste Saison zuerst
                for key in sorted(saison_stats.keys(),
                                   key=lambda k: saison_meta[k]["season_id"], reverse=True):
                    meta = saison_meta[key]
                    st = saison_stats[key]
                    karriere.append({
                        "saison": meta["saison"],
                        "liga": meta["liga"],
                        "spiele": st["spiele"],
                        "tore": st["tore"],
                        "assists": st["assists"],
                    })
            except Exception as e:
                print(f"(Perf Fehler: {e})", end=" ")

        # 5. Verein aus OpenLigaDB
        team_id = player_team.get(gid)
        verein = team_names.get(team_id, "") if team_id else ""

        result = {
            "goalGetterId": gid,
            "name": name,
            "verein": verein,
            "foto": wiki_foto,
            "wiki_seite": wiki_seite,
            "wiki_autor": wiki_autor,
            "alter": tm_alter,
            "groesse": tm_groesse,
            "nation": tm_nation,
            "position": tm_position,
            "marktwert": tm_mw,
            "karriere": karriere,
            "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("✅")
        time.sleep(1.5)  # TM nicht überlasten

    print(f"✅ spieler/ aktualisiert ({len(top_scorer)} Spieler)")


if __name__ == "__main__":
    import urllib.parse
    try:
        kickbase_fetch()
    except Exception as e:
        print(f"❌ kickbase_fetch Fehler: {e}")
    try:
        spieler_fetch()
    except Exception as e:
        print(f"❌ spieler_fetch Fehler: {e}")
    main()
