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
                f"- Es direkt um mindestens einen dieser 18 Klubs geht (Transfer, Spiel, Trainer, Verletzung, Vertrag)\n"
                f"- Es eine echte redaktionelle News ist (kein Reddit-Userpost, kein Werbeartikel, kein Quiz)\n"
                f"- Es KEIN WM-, EM- oder Nationalmannschafts-Thema ist (auch kein Interview mit Nationaltrainern wie Nagelsmann)\n"
                f"- Es KEINE 2. Liga, Champions League ohne BL-Bezug oder andere Liga ist\n"
                f"- Der Hauptfokus auf der 1. Bundesliga liegt, nicht nur eine Randerwähnung\n\n"
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
    rss_titel_dieser_lauf: list[str] = []  # raw RSS titles processed this run
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

            # Duplikat-Check gegen bestehende Artikel-Titel + raw RSS-Titel dieses Laufs
            bestehende_titel = rss_titel_dieser_lauf + [a["titel"] for a in bestehende]
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

            rss_titel_dieser_lauf.append(titel)
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

    CDN = "https://kickbase.b-cdn.net/"
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "User-Agent": "Kickbase GmbH/5.5.2 CFNetwork/1568.200.51 Darwin/24.1.0",
    })

    # Login (v4: em/pass → tkn)
    try:
        r = session.post("https://api.kickbase.com/v4/user/login",
                         json={"em": email, "pass": password, "loy": False, "rep": {}}, timeout=15)
        r.raise_for_status()
        token = r.json().get("tkn")
        if not token:
            raise ValueError(f"Kein tkn in Response: {list(r.json().keys())}")
        session.headers["Authorization"] = f"Bearer {token}"
        print("✅ Kickbase Login erfolgreich")
    except Exception as e:
        print(f"❌ Kickbase Login fehlgeschlagen: {e}")
        return

    # Spieler-IDs aus Top-Liste holen, dann Einzeldetails abrufen (echte mv/tp)
    try:
        r = session.get("https://api.kickbase.com/v4/competitions/1/players", timeout=20)
        r.raise_for_status()
        id_list = [(p["pi"], p.get("tid", "")) for p in r.json().get("it", [])]
        print(f"  → {len(id_list)} Spieler-IDs geladen")
    except Exception as e:
        print(f"❌ Kickbase Spieler-Liste fehlgeschlagen: {e}")
        return

    import time as _time
    players = []
    for pid, _ in id_list:
        try:
            r2 = session.get(f"https://api.kickbase.com/v4/competitions/1/players/{pid}", timeout=10)
            r2.raise_for_status()
            d  = r2.json()
            tid = d.get("tid", "")
            # Team-Icon aus Spieltagsdaten extrahieren
            team_img = ""
            for md in d.get("mdsum", []):
                if md.get("t1") == tid:
                    team_img = md.get("t1im", "")
                    break
                elif md.get("t2") == tid:
                    team_img = md.get("t2im", "")
                    break
            logo = CDN + team_img if team_img else ""
            players.append({
                "name":    (d.get("fn", "") + " " + d.get("ln", "")).strip(),
                "logo":    logo,
                "mw":      d.get("mv", 0) or 0,
                "pts":     d.get("tp", 0) or 0,
                "ap":      d.get("ap", 0) or 0,
                "goals":   d.get("g",  0) or 0,
                "assists": d.get("a",  0) or 0,
                "sp_pts":  d.get("pes", 0) or 0,
                "mvt":     d.get("tfhmvt", 0) or 0,
            })
            _time.sleep(0.2)
        except Exception as e:
            print(f"  ⚠️ Spieler {pid}: {e}")

    print(f"  → {len(players)} Spieler-Details geladen")

    # Effizienz: Punkte pro Million Marktwert
    for p in players:
        p["eff"] = round(p["pts"] / (p["mw"] / 1e6), 2) if p["mw"] > 500000 else 0

    def top(lst, key, n=10, reverse=True):
        return sorted([x for x in lst if x[key]], key=lambda x: x[key], reverse=reverse)[:n]

    teuerste  = [{"name":p["name"],"logo":p["logo"],"mw":p["mw"]}        for p in top(players,"mw")]
    punkte    = [{"name":p["name"],"logo":p["logo"],"pts":p["pts"]}       for p in top(players,"pts")]
    effizienz = [{"name":p["name"],"logo":p["logo"],"eff":p["eff"]}       for p in top(players,"eff")]
    tore      = [{"name":p["name"],"logo":p["logo"],"goals":p["goals"]}   for p in top(players,"goals")]
    spieltag  = [{"name":p["name"],"logo":p["logo"],"pts":p["sp_pts"]}    for p in top(players,"sp_pts")]
    raketen   = [{"name":p["name"],"logo":p["logo"],"diff":p["mvt"]}      for p in top(players,"mvt")]
    crash     = [{"name":p["name"],"logo":p["logo"],"diff":p["mvt"]}      for p in top(players,"mvt",reverse=False) if p["mvt"] < 0]

    result = {
        "updated":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "teuerste":  teuerste,
        "punkte":    punkte,
        "effizienz": effizienz,
        "tore":      tore,
        "spieltag":  spieltag,
        "raketen":   raketen,
        "crash":     crash,
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

        # 2. TM-ID + Profildaten
        tm_id = None
        tm_mw = None
        tm_alter = None
        tm_groesse = None
        tm_nation = None
        tm_position = None
        tm_vollname = None
        try:
            # TM-Suche: "H. Kane" → "Kane", "Luis Díaz" → "Luis Díaz"
            m_abbr = re.match(r'^[A-Z]\.\s+(.+)$', name)
            tm_suchname = m_abbr.group(1) if m_abbr else name
            search_html = get_html(
                f"https://www.transfermarkt.de/schnellsuche/ergebnis/schnellsuche?query={urllib.parse.quote(tm_suchname)}&Spieler_page=0"
            )
            m_id = re.search(r'href="/([^/]+)/profil/spieler/(\d+)"', search_html)
            if m_id:
                tm_slug = m_id.group(1)
                tm_id = m_id.group(2)
                # Slug → vollständiger Name (z.B. "patrik-schick" → "Patrik Schick")
                tm_vollname = tm_slug.replace("-", " ").title()

                # Profilseite
                profil_html = get_html(f"https://www.transfermarkt.de/{tm_slug}/profil/spieler/{tm_id}")

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
                    m_pos = re.search(r'<dt[^>]*>Hauptposition:</dt>\s*<dd[^>]*>([^<]+)<', profil_html)
                    if m_pos:
                        tm_position = m_pos.group(1).strip()
        except Exception as e:
            print(f"(TM Fehler: {e})", end=" ")

        # 4. TM Performance + Transfer-History → BL-Karriere
        karriere = []
        if tm_id:
            try:
                from collections import defaultdict
                import datetime as dt

                perf, transfers_resp = None, None
                try:
                    perf = get_json(
                        f"https://www.transfermarkt.de/ceapi/performance-game/{tm_id}",
                        headers={"x-tmapi-version": "1"}
                    )
                except Exception:
                    pass
                try:
                    transfers_resp = get_json(
                        f"https://www.transfermarkt.de/ceapi/transferHistory/list/{tm_id}",
                        headers={"x-tmapi-version": "1"}
                    )
                except Exception:
                    pass

                # Transfer-History → Saison → Vereinsname
                # Saison "24/25" startet ~01.08.2024, endet ~31.05.2025
                def verein_fuer_saison(transfers_data, saison_str):
                    """Bestimmt Vereinsname + Wappen-URL für eine Saison aus Transfer-History."""
                    if not transfers_data:
                        return None, None
                    year_start = 2000 + int(saison_str[:2])
                    season_end = dt.date(year_start + 1, 6, 30)

                    tlist = sorted(
                        [t for t in transfers_data.get("transfers", []) if t.get("dateUnformatted")],
                        key=lambda t: t["dateUnformatted"]
                    )
                    current_name = None
                    current_icon = None
                    for t in tlist:
                        try:
                            d = dt.date.fromisoformat(t["dateUnformatted"])
                        except Exception:
                            continue
                        if d >= season_end:
                            break
                        to = t.get("to", {})
                        to_club = to.get("clubName", "")
                        if to_club and to_club not in ("Vereinslos", "Without Club"):
                            current_name = to_club
                            current_icon = to.get("clubEmblem-2x", "")
                    return current_name, current_icon

                games = (perf or {}).get("data", {}).get("performance", [])

                # Aggregiere BL-Spiele nach Saison
                bl_stats = defaultdict(lambda: {"spiele": 0, "tore": 0, "assists": 0})
                bl_season_id = {}

                for g in games:
                    info = g.get("gameInformation", {})
                    if info.get("competitionId") != "L1" or info.get("isNationalGame"):
                        continue
                    season_display = info.get("season", {}).get("display", "")
                    season_id = info.get("season", {}).get("id", 0)
                    if not season_display:
                        continue
                    gs = g.get("statistics", {}).get("goalStatistics", {})
                    bl_stats[season_display]["spiele"] += 1
                    bl_stats[season_display]["tore"]   += gs.get("goalsScoredTotal") or 0
                    bl_stats[season_display]["assists"] += gs.get("assists") or 0
                    bl_season_id[season_display] = season_id

                # Vereinsname + Wappen aus Transfer-History
                for saison in sorted(bl_stats.keys(),
                                     key=lambda s: bl_season_id.get(s, 0), reverse=True):
                    st = bl_stats[saison]
                    verein_name, verein_icon = verein_fuer_saison(transfers_resp, saison)
                    karriere.append({
                        "saison":      saison,
                        "verein":      verein_name or "",
                        "verein_icon": verein_icon or "",
                        "spiele":      st["spiele"],
                        "tore":        st["tore"],
                        "assists":     st["assists"],
                    })
            except Exception as e:
                print(f"(Perf Fehler: {e})", end=" ")

        # Vereinshistorie aus Transfer-History (nur Profivereine, keine Leih-Enden)
        vereinshistorie = []
        if transfers_resp:
            JUGEND_KEYWORDS = ("U17", "U18", "U19", "U21", "U23", "Jgd", "B-Junioren", "A-Junioren")
            for t in transfers_resp.get("transfers", []):
                fee = t.get("fee", "")
                if fee in ("Leih-Ende", "-", "?"):
                    continue
                to = t.get("to", {})
                club = to.get("clubName", "")
                if not club or club in ("Vereinslos", "Without Club"):
                    continue
                if any(k in club for k in JUGEND_KEYWORDS):
                    continue
                year = (t.get("dateUnformatted") or "")[:4]
                vereinshistorie.append({
                    "jahr": year,
                    "verein": club,
                    "verein_icon": to.get("clubEmblem-2x", ""),
                    "leihe": fee == "Leihe",
                })

        # 5. Verein aus OpenLigaDB
        team_id = player_team.get(gid)
        verein = team_names.get(team_id, "") if team_id else ""

        result = {
            "goalGetterId": gid,
            "name": tm_vollname or name,
            "verein": verein,
            "alter": tm_alter,
            "groesse": tm_groesse,
            "nation": tm_nation,
            "position": tm_position,
            "marktwert": tm_mw,
            "karriere": karriere,
            "vereinshistorie": vereinshistorie,
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
