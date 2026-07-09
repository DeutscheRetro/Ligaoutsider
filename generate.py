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
import logging
from pathlib import Path
from dotenv import load_dotenv
import feedparser
import anthropic
from slugify import slugify
from url_cache import URLCache

load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────────

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
_run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"run_{_run_ts}.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ligaoutsider")

# Skips als JSONL
_skips_path = LOG_DIR / f"skips_{_run_ts[:8]}.jsonl"

def _log_skip(item_id: str, title: str, stage: str, reason: str):
    entry = {"ts": datetime.datetime.now().isoformat(), "id": item_id,
             "title": title[:80], "stage": stage, "reason": reason}
    with _skips_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ─── Konfiguration ────────────────────────────────────────────────────────────

RSS_FEEDS = [
    # Deutsche Quellen
    "https://newsfeed.kicker.de/news/bundesliga",
    "https://www.sportschau.de/fussball/bundesliga/index~rss2.xml",
    "https://sportbild.bild.de/feed/sportbild-home.xml",
    "https://www.bild.de/rss-feeds/rss-16725492,feed=fussball-mix.bild.html",
    "https://www.11freunde.de/feed",
    "https://www.bundesliga.com/de/bundesliga/news.rss",
    # Google News – Bundesliga Topic Feed (kuratiert)
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtUmxHZ0pFUlNnQVAB?hl=de&gl=DE&ceid=DE:de",
    # Google News – gezielte Bundesliga-Suchen
    "https://news.google.com/rss/search?q=Bundesliga+Testspiel+Ergebnis&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Bundesliga+Vorbereitung+Sommertour&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Bundesliga+Verletzung+Ausfall+gesperrt&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Bundesliga+Transfer+Wechsel+verpflichtet&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Bundesliga+Gerücht+Interesse+Angebot&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Bundesliga+Vertrag+verlängert+ablösefrei&hl=de&gl=DE&ceid=DE:de",
    # Google News – alle 18 Teams
    "https://news.google.com/rss/search?q=FC+Bayern+München+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Borussia+Dortmund+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Bayer+04+Leverkusen+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=RB+Leipzig+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=VfB+Stuttgart+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Eintracht+Frankfurt+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Borussia+Mönchengladbach+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=SC+Freiburg+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=TSG+Hoffenheim+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=FSV+Mainz+05+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=FC+Augsburg+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=1.+FC+Union+Berlin+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=SV+Werder+Bremen+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Hamburger+SV+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=1.+FC+Köln+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=FC+Schalke+04+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=SV+Elversberg+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=SC+Paderborn+Transfer+News&hl=de&gl=DE&ceid=DE:de",
    "https://www.transfermarkt.de/rss/news",
    "https://www.transfermarkt.de/bundesliga/news/wettbewerb/L1?rss=1",
    "https://rss.dw.com/xml/sport-de",
    "https://www.waz.de/sport/fussball/rss",
    "https://www.faz.net/rss/aktuell/sport/fussball/bundesliga/",

    # Englische Quellen
    "https://bulinews.com/rss.xml",
    "https://www.eyefootball.com/rss_news_main.xml",
    "https://www.ligaportal.at/international/deutsche-bundesliga?format=feed&type=rss",

    # Reddit (100 Einträge)
    "https://www.reddit.com/r/bundesliga/new.rss?limit=100",
    "https://www.reddit.com/r/soccer/new.rss?limit=100",

    # kicker Team-Feeds – 18 Erstligisten 2026/27
    "https://rss.kicker.de/news/fc-bayern-muenchen",
    "https://rss.kicker.de/news/borussia-dortmund",
    "https://rss.kicker.de/news/rb-leipzig",
    "https://rss.kicker.de/news/bayer-leverkusen",
    "https://rss.kicker.de/news/vfb-stuttgart",
    "https://rss.kicker.de/news/eintracht-frankfurt",
    "https://rss.kicker.de/news/borussia-moenchengladbach",
    "https://rss.kicker.de/news/sc-freiburg",
    "https://rss.kicker.de/news/tsg-hoffenheim",
    "https://rss.kicker.de/news/fsv-mainz-05",
    "https://rss.kicker.de/news/fc-augsburg",
    "https://rss.kicker.de/news/1-fc-union-berlin",
    "https://rss.kicker.de/news/sv-werder-bremen",
    "https://rss.kicker.de/news/hamburger-sv",
    "https://rss.kicker.de/news/1-fc-koeln",
    "https://rss.kicker.de/news/fc-schalke-04",
    "https://rss.kicker.de/news/sv-elversberg",
    "https://rss.kicker.de/news/sc-paderborn-07",
]

# Artikel bis zu X Tage alt akzeptieren
MAX_ALTER_TAGE = 3

# Wie viele neue Artikel maximal pro Durchlauf generieren
MAX_ARTIKEL_PRO_LAUF = 50

# Wo Artikel gespeichert werden
ARTIKEL_ORDNER = Path("artikel")
FEED_JSON      = Path("feed.json")

DISQUS_SHORTNAME = "ligaoutsider"  # <-- später auf disqus.com eintragen

# ─── 1. Bundesliga Klubs 2026/27 ──────────────────────────────────────────────

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
    "allianz arena":     "../logos/bayern.png",
    # Dortmund
    "borussia dortmund": "../logos/dortmund.png",
    "dortmund":          "../logos/dortmund.png",
    "bvb":               "../logos/dortmund.png",
    "signal iduna":      "../logos/dortmund.png",
    # Leipzig
    "rb leipzig":          "../logos/leipzig.png",
    "leipzig":             "../logos/leipzig.png",
    "red bull arena":      "../logos/leipzig.png",
    # Leverkusen
    "bayer 04":            "../logos/leverkusen.png",
    "leverkusen":          "../logos/leverkusen.png",
    "bayarena":            "../logos/leverkusen.png",
    # Frankfurt
    "eintracht frankfurt": "../logos/frankfurt.png",
    "eintracht":           "../logos/frankfurt.png",
    "frankfurt":           "../logos/frankfurt.png",
    "sge":                 "../logos/frankfurt.png",
    "deutsche bank park":  "../logos/frankfurt.png",
    # Stuttgart
    "vfb stuttgart":    "../logos/stuttgart.png",
    "stuttgart":        "../logos/stuttgart.png",
    "mhp arena":        "../logos/stuttgart.png",
    # Gladbach
    "mönchengladbach":  "../logos/gladbach.png",
    "gladbach":         "../logos/gladbach.png",
    "borussia m":       "../logos/gladbach.png",
    "borussia-park":    "../logos/gladbach.png",
    # Freiburg
    "sc freiburg":      "../logos/freiburg.png",
    "freiburg":         "../logos/freiburg.png",
    "europa-park stadion": "../logos/freiburg.png",
    # Union Berlin
    "union berlin":     "../logos/union.png",
    "1. fc union":      "../logos/union.png",
    "an der alten försterei": "../logos/union.png",
    # Mainz
    "fsv mainz":        "../logos/mainz.png",
    "mainz":            "../logos/mainz.png",
    "mewa arena":       "../logos/mainz.png",
    # Augsburg
    "fc augsburg":      "../logos/augsburg.png",
    "augsburg":         "../logos/augsburg.png",
    "www arena":        "../logos/augsburg.png",
    # Werder
    "sv werder":        "../logos/werder.png",
    "werder":           "../logos/werder.png",
    "weserstadion":     "../logos/werder.png",
    "wohninvest weserstadion": "../logos/werder.png",
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

# Mapping: Texttreffer → data-filter-Schlüssel (wie in index.html)
VEREIN_FILTER = {
    # Bayern – eindeutig genug als Eigenname
    "fc bayern münchen": "Bayern", "fc bayern": "Bayern", "bayern münchen": "Bayern",
    "fc-bayern": "Bayern",
    # Dortmund
    "borussia dortmund": "Dortmund", "bvb": "Dortmund", "dortmund": "Dortmund",
    # Leipzig – "leipzig" allein ist ok (keine große andere Fußball-Relevanz)
    "rb leipzig": "Leipzig", "rasenballsport": "Leipzig", "leipzig": "Leipzig",
    # Leverkusen – "leverkusen" eindeutig
    "bayer 04 leverkusen": "Leverkusen", "bayer leverkusen": "Leverkusen",
    "bayer 04": "Leverkusen", "leverkusen": "Leverkusen",
    # Frankfurt – nur compound; alle kürzeren Keywords zu generisch
    "eintracht frankfurt": "Frankfurt",
    # Stuttgart – "stuttgart" oft Stadtname in Bundesliga-Kontext, compound bevorzugen
    "vfb stuttgart": "Stuttgart", "vfb": "Stuttgart",
    # Gladbach
    "borussia mönchengladbach": "Gladbach", "mönchengladbach": "Gladbach",
    "gladbach": "Gladbach", "bmg": "Gladbach", "die fohlen": "Gladbach",
    # Freiburg – "freiburg" allein ok
    "sc freiburg": "Freiburg", "freiburg": "Freiburg",
    # Union – "union" allein viel zu generisch
    "1. fc union berlin": "Union", "union berlin": "Union", "fc union": "Union",
    # Mainz – "mainz" allein ok (keine andere Bundesliga-Relevanz)
    "1. fsv mainz": "Mainz", "fsv mainz": "Mainz", "mainz 05": "Mainz", "mainz": "Mainz",
    # Augsburg – ok
    "fc augsburg": "Augsburg", "augsburg": "Augsburg",
    # Werder – eindeutig
    "sv werder bremen": "Werder", "werder bremen": "Werder", "werder": "Werder",
    # Hoffenheim – ok
    "tsg hoffenheim": "Hoffenheim", "tsg 1899": "Hoffenheim", "hoffenheim": "Hoffenheim",
    # HSV – "hamburger" allein zu generisch
    "hamburger sv": "Hamburger", "hsv": "Hamburger",
    # Köln – "köln" oft Stadtname, compound bevorzugen
    "1. fc köln": "Köln", "fc köln": "Köln", "effzeh": "Köln",
    # Schalke
    "fc schalke 04": "Schalke", "fc schalke": "Schalke", "schalke 04": "Schalke",
    "schalke": "Schalke", "s04": "Schalke",
    # Paderborn
    "sc paderborn": "Paderborn", "paderborn": "Paderborn",
    # Elversberg
    "sv elversberg": "Elversberg", "elversberg": "Elversberg",
}

def _count_key(key: str, text: str) -> int:
    """Zählt Vorkommen von key in text mit Wortgrenzen (verhindert Substring-false-positives)."""
    return len(re.findall(r'(?<!\w)' + re.escape(key) + r'(?!\w)', text))


def vereine_im_text(titel: str, text: str) -> list[str]:
    """Taggt Club nur wenn er im Titel steht ODER ≥2x im Artikeltext vorkommt.
    Nutzt Wortgrenzen um Substrings wie 'anspruchsvollem' → 'hsv' zu verhindern."""
    t_lower = titel.lower()
    body_lower = text.lower()
    gefunden = set()
    bereits_gefunden: set[str] = set()
    for key in sorted(VEREIN_FILTER, key=len, reverse=True):
        club = VEREIN_FILTER[key]
        if club in bereits_gefunden:
            continue
        in_titel = _count_key(key, t_lower) > 0
        count_body = _count_key(key, body_lower)
        if in_titel or count_body >= 2:
            gefunden.add(club)
            bereits_gefunden.add(club)
    return sorted(gefunden)

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


def lade_deleted_ids() -> set:
    p = Path("deleted_ids.json")
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except Exception:
        return set()

DELETED_IDS: set = set()  # wird in main() befüllt

def schon_verarbeitet(url: str) -> bool:
    aid = artikel_id(url)
    if aid in DELETED_IDS:
        return True
    return (ARTIKEL_ORDNER / f"{aid}.html").exists() or (ARTIKEL_ORDNER / f"{aid}.skip").exists()


def verein_wappen_url(text: str, title: str = "") -> str:
    """Findet das relevanteste Vereinslogo per Scoring aggregiert pro Logo-URL."""
    _context_kw = ("wechselt", "transfer", "verletzung", "verpflichtet", "spielt",
                   "trainer", "vertrag", "ablöse", "gegen", "siegt", "verliert")
    full_lower = (title + " " + text).lower()
    title_lower = title.lower()
    text_len = len(full_lower) or 1
    logo_scores: dict[str, int] = {}
    for key, logo_url in VEREIN_WAPPEN.items():
        count = full_lower.count(key)
        if count == 0:
            continue
        score = count * 10
        if key in title_lower:
            score += 100  # Titel stark bevorzugen
        pos = full_lower.find(key)
        if pos != -1:
            if pos < text_len * 0.25:
                score += 15
            elif pos < text_len * 0.5:
                score += 8
        # Kontext-Bonus: Club nahe an Kontext-Keywords
        for kw in _context_kw:
            if f"{key} {kw}" in full_lower or f"{kw} {key}" in full_lower:
                score += 20
                break
        logo_scores[logo_url] = logo_scores.get(logo_url, 0) + score
    if not logo_scores:
        return BL_LOGO
    return max(logo_scores, key=logo_scores.get)  # type: ignore[arg-type]


def badge_fuer_kategorie(kategorie: str) -> tuple:
    return BADGE_KATEGORIEN.get(kategorie.lower(), ("News", "#e8c000", "#000"))


def feed_laden() -> list:
    """Lädt feed.json – merged lokale Datei mit live Version von ligaoutsider.de."""
    lokal = []
    if FEED_JSON.exists():
        try:
            lokal = json.loads(FEED_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Live-Version holen um parallele GitHub-Actions-Runs abzusichern
    live = []
    try:
        import urllib.request as _ureq
        r = _ureq.urlopen("https://ligaoutsider.de/feed.json", timeout=8)
        live = json.loads(r.read().decode("utf-8"))
        print(f"  Live feed.json geladen: {len(live)} Artikel")
    except Exception as e:
        print(f"  Live feed.json nicht erreichbar ({e}) – nur lokale Version")

    # Merge: live + lokal, Duplikate per ID entfernen
    merged = {a["id"]: a for a in live}
    for a in lokal:
        merged.setdefault(a["id"], a)
    return list(merged.values())


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


def _schluesselwoerter(t: str) -> set:
    stopwords = {"der", "die", "das", "ein", "eine", "und", "mit", "bei", "vor",
                 "nach", "von", "an", "im", "am", "auf", "für", "zu", "in", "ist",
                 "aus", "fc", "sv", "rb", "vfb", "sc", "bsc", "tsg"}
    return {w.lower() for w in re.split(r'\W+', t) if len(w) > 3 and w.lower() not in stopwords}


def _artikel_text_laden(artikel_id_str: str) -> str:
    """Lädt Plaintext eines bestehenden Artikels aus dem HTML (max 800 Zeichen)."""
    pfad = ARTIKEL_ORDNER / f"{artikel_id_str}.html"
    if not pfad.exists():
        return ""
    try:
        html = pfad.read_text(encoding="utf-8")
        # Nur artikel-text div
        m = re.search(r'<div class="artikel-text">(.*?)</div>', html, re.DOTALL)
        block = m.group(1) if m else html
        text = re.sub(r'<[^>]+>', ' ', block)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:800]
    except Exception:
        return ""


def _eigennamen(t: str) -> set:
    """Extrahiert großgeschriebene Wörter (Spieler-/Clubnamen) aus einem Titel."""
    return {w for w in re.split(r'\W+', t) if len(w) > 3 and w[0].isupper()}


# ─── Published Stories (persistenter State) ───────────────────────────────────

PUBLISHED_JSON = Path("data/published_stories.json")

def lade_published_stories() -> list[dict]:
    PUBLISHED_JSON.parent.mkdir(exist_ok=True)
    if not PUBLISHED_JSON.exists():
        return []
    try:
        return json.loads(PUBLISHED_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []

def speichere_published_stories(stories: list[dict]):
    PUBLISHED_JSON.parent.mkdir(exist_ok=True)
    PUBLISHED_JSON.write_text(
        json.dumps(stories[-1000:], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ─── Content Fingerprint (Stage 4) ────────────────────────────────────────────

def fingerprint_generieren(titel: str, summary: str) -> dict | None:
    """Haiku extrahiert strukturierten Story-Fingerprint als JSON."""
    try:
        antwort = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f'Extrahiere einen Story-Fingerprint als reines JSON (kein Markdown):\n'
                f'{{"event_type":"transfer|verletzung|trainerwechsel|spielergebnis|testspiel|geruecht|vereinsnews|analyse|sonstiges",'
                f'"main_teams":["max 3 Teams"],'
                f'"main_players":["max 3 Spieler"],'
                f'"one_sentence_summary":"1 Satz Kern-Ereignis"}}\n\n'
                f'Titel: {titel}\nZusammenfassung: {summary[:500]}'
            )}]
        )
        roh = antwort.content[0].text.strip()
        m = re.search(r'\{.*\}', roh, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return None


def _fingerprint_similarity(fp1: dict, fp2: dict) -> float:
    """Jaccard-Similarity zweier Fingerprints: Teams (60%) + Spieler (40%)."""
    t1 = {t.lower() for t in fp1.get("main_teams", [])}
    t2 = {t.lower() for t in fp2.get("main_teams", [])}
    p1 = {p.lower() for p in fp1.get("main_players", [])}
    p2 = {p.lower() for p in fp2.get("main_players", [])}
    team_score = len(t1 & t2) / len(t1 | t2) if (t1 | t2) else 0.0
    player_score = len(p1 & p2) / len(p1 | p2) if (p1 | p2) else 0.0
    return round(team_score * 0.6 + player_score * 0.4, 3)


def _is_update_artikel(title: str, text: str) -> bool:
    """Erkennt ob Artikel eine offizielle Bestätigung/Update ist (kein Gerücht)."""
    combined = (title + " " + text).lower()
    update_signals = [
        "offiziell", "bestätigt", "unterschrieben", "vollzogen",
        "wechselt zu", "ablöse", "fix", "perfekt", "beschlossene sache",
        "offiziell bestätigt", "transfer ist perfekt",
    ]
    return any(signal in combined for signal in update_signals)


def _fingerprints_aehnlich(fp1: dict, fp2: dict) -> bool:
    """True wenn zwei Fingerprints dieselbe Story beschreiben."""
    from rapidfuzz import fuzz
    # Jaccard-Similarity ≥ 0.85 auf Teams + Spieler
    if _fingerprint_similarity(fp1, fp2) >= 0.85:
        return True
    # Gleicher Event-Typ + mind. 2 gemeinsame Entitäten (Fallback)
    if fp1.get("event_type") == fp2.get("event_type"):
        e1 = set(fp1.get("main_teams", []) + fp1.get("main_players", []))
        e2 = set(fp2.get("main_teams", []) + fp2.get("main_players", []))
        if len(e1 & e2) >= 2:
            return True
    # Fuzzy auf one_sentence_summary
    s1 = fp1.get("one_sentence_summary", "")
    s2 = fp2.get("one_sentence_summary", "")
    if s1 and s2 and fuzz.ratio(s1, s2) >= 85:
        return True
    return False


def _ist_innerhalb_tage(published_at_str: str, days: int = 14) -> bool:
    """True wenn published_at innerhalb der letzten N Tage."""
    if not published_at_str:
        return False
    try:
        ts = datetime.datetime.fromisoformat(published_at_str)
        return (datetime.datetime.now() - ts).days <= days
    except Exception:
        return False


def ist_duplikat(neuer_titel: str, beschreibung: str, bestehende: list) -> bool:
    """Prüft ob Meldung inhaltlich schon vorhanden oder echte neue Entwicklung.
    bestehende: Liste von Artikel-Dicts (mit 'id' und 'titel').
    """
    if not bestehende:
        return False

    bestehende_titel = [a["titel"] if isinstance(a, dict) else a for a in bestehende]

    neu_woerter = _schluesselwoerter(neuer_titel + " " + beschreibung)
    neu_namen = _eigennamen(neuer_titel)

    # Ähnliche Artikel finden
    aehnliche = []
    for a in bestehende[-100:]:
        titel = a["titel"] if isinstance(a, dict) else a
        alt_woerter = _schluesselwoerter(titel)
        alt_namen = _eigennamen(titel)

        if neu_woerter and alt_woerter:
            overlap = len(neu_woerter & alt_woerter) / min(len(neu_woerter), len(alt_woerter))
            if overlap >= 0.6:
                return True  # Sehr hoher Keyword-Overlap → sofort Duplikat

        # Eigennamen-Check: ≥2 gleiche Eigennamen = sehr wahrscheinlich selbes Thema → KI-Check
        gemeinsame_namen = neu_namen & alt_namen
        if len(gemeinsame_namen) >= 2:
            aehnliche.append(a)
            continue

        if neu_woerter and alt_woerter and overlap >= 0.4:
            aehnliche.append(a)

    # KI-Check mit Volltexten ähnlicher Artikel
    titel_liste = "\n".join(f"- {t}" for t in bestehende_titel[-100:])
    beschr_kurz = beschreibung[:400] if beschreibung else "(keine Beschreibung)"

    verwandte_texte = ""
    for a in aehnliche[:3]:  # max 3 ähnliche Artikel vollständig laden
        if isinstance(a, dict) and "id" in a:
            txt = _artikel_text_laden(a["id"])
            if txt:
                verwandte_texte += f"\n---\nTitel: {a['titel']}\nText: {txt}\n"

    verwandte_section = (
        f"\nBESONDERS ÄHNLICHE BEREITS VERÖFFENTLICHTE ARTIKEL (Volltext):\n{verwandte_texte}"
        if verwandte_texte else ""
    )

    antwort = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                f"Du prüfst ob eine neue Fußball-Meldung ein Duplikat ist oder eine echte neue Entwicklung.\n\n"
                f"NEUE MELDUNG:\n"
                f"Titel: {neuer_titel}\n"
                f"Inhalt: {beschr_kurz}\n\n"
                f"BEREITS VERÖFFENTLICHTE ARTIKEL (Titel):\n{titel_liste}"
                f"{verwandte_section}\n\n"
                f"Antworte JA (Duplikat) wenn:\n"
                f"- Derselbe Spieler + derselbe Zielclub bereits vorhanden – EGAL ob andere Quelle, andere Ablösesumme oder andere Formulierung\n"
                f"- Derselbe Spieler + dieselbe Verletzung/Sperre bereits vorhanden\n"
                f"- Gleicher Sachverhalt aus anderer Perspektive (z.B. 'Rekordabgang für Club X' vs 'Spieler wechselt zu Club Y')\n\n"
                f"Antworte NEIN nur wenn:\n"
                f"- Komplett neue Entwicklung: Einigung nach Gerücht, Dementi, Platzen des Deals, medizinischer Check bestanden\n"
                f"- Komplett andere Personen oder Vereine\n\n"
                f"Im Zweifel: JA.\n"
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
                f"Ist das eine relevante Fußball-News über einen der folgenden Klubs?\n"
                f"Klubs: {klubs}.\n"
                f"Antworte NUR mit JA wenn:\n"
                f"- Es direkt um mindestens einen dieser Klubs geht (Transfer, Spiel, Trainer, Verletzung, Vertrag, Testspiel)\n"
                f"- Es eine echte redaktionelle News ist (kein Social-Media-Post, kein Werbeartikel, kein Quiz, keine Trauerbekundung)\n"
                f"- Es KEIN WM-, EM-, Nationalmannschafts-, Frauenfußball- oder 2.-Bundesliga-Thema ist\n"
                f"- Es KEINE reine Champions-League/Europa-League-News ohne Bezug zu diesen Klubs ist\n"
                f"- Der Fokus auf dem Klub liegt, nicht nur eine Randerwähnung\n\n"
                f"Titel: {titel}\nBeschreibung: {beschreibung}\n\n"
                f"Antworte nur mit JA oder NEIN."
            )
        }]
    )
    return "JA" in antwort.content[0].text.upper()


def fetch_fulltext(url: str) -> tuple[str | None, str]:
    """Lädt Volltext via trafilatura. Gibt (text, reason) zurück — reason='ok' oder Fehlergrund."""
    import trafilatura
    import requests as _req
    MIN_WORDS = 250
    PAYWALL_MARKERS = ["paywall", "abo", "abonnenten", "premium",
                       "login erforderlich", "nur für abonnenten", "artikelende"]
    try:
        # Redirect folgen (inkl. Google News)
        try:
            r = _req.get(url, allow_redirects=True, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            final_url = r.url
            if "google.com" in final_url:
                return None, "google_redirect_unresolved"
            html_content = r.content
        except Exception as e:
            return None, f"fetch_failed_{type(e).__name__}"

        text = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=False,
            output_format="txt",
            favor_precision=True,
        )
        if not text:
            return None, "trafilatura_returned_empty"

        words = text.split()
        word_count = len(words)
        MIN_WORDS = 160
        if word_count < MIN_WORDS:
            # Kurze Transfermeldungen erlauben wenn Key-Indicators vorhanden
            _KEY = ["wechselt", "transfer", "verpflichtet", "verletzt",
                    "verlängert", "ablöse", "testspiel", "trainiert", "abgang", "zugang"]
            if word_count >= 100 and any(k in text.lower() for k in _KEY):
                pass  # short but relevant
            else:
                return None, f"too_short_{word_count}_words"

        text_lower = text.lower()
        for marker in PAYWALL_MARKERS:
            if marker in text_lower:
                return None, "likely_paywall"

        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.4:
            return None, "low_unique_content_ratio"

        return text[:4000], "ok"

    except Exception as e:
        return None, f"exception_{type(e).__name__}"


# Legacy-Wrapper für Abwärtskompatibilität (intern nicht mehr genutzt)
def quellartikel_laden(url: str) -> str:
    text, reason = fetch_fulltext(url)
    return text or ""


def artikel_generieren(titel: str, volltext: str, quelle_name: str, quelle_url: str) -> dict:
    """Lässt Sonnet Artikel schreiben. Bekommt validierten Volltext (Stage 5 Survivor)."""
    prompt = f"""Du bist Sportredakteur bei Ligaoutsider.de. Stil: kicker.de – sachlich, präzise, konkret.

ABSOLUTE REGELN – KEINE HALLUZINATIONEN:
- Nur Fakten, Namen, Zahlen aus dem QUELLTEXT verwenden.
- Steht eine Information nicht im Quelltext → weglassen oder "laut Quelle nicht spezifiziert".
- KEINE Spekulationen, KEINE Ergänzungen aus Trainingswissen.
- VERBOTEN: „Die Entwicklung bleibt abzuwarten", „Transfers dieser Art sind komplex", alle Plattitüden.
- Spielernamen korrekt inkl. Akzente (João, Raphaël, Øyvind).
- Keine Gedankenstriche als Satzzeichen. Klare Sätze, max. 25 Wörter. Keine Ausrufezeichen.

QUELLTEXT (vollständig):
{volltext}

Originaltitel: {titel}
Quelle: {quelle_name} ({quelle_url})

Erstelle:
1. Präzisen Titel im Kicker-Stil (max. 80 Zeichen)
2. Zwei bis vier Absätze – so viele wie Quellinfos rechtfertigen, nicht mehr
3. Kategorie: transfer | verletzung | aufstellung | interview | analyse | news

Antworte ausschließlich im JSON-Format (kein Markdown drumherum):
{{
  "titel": "...",
  "text": "Absatz 1.\\n\\nAbsatz 2.\\n\\nAbsatz 3.",
  "kategorie": "..."
}}"""

    antwort = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )

    roh = antwort.content[0].text.strip()
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
    vereine: list = None,
) -> str:
    badge_label, badge_bg, badge_fg = badge_fuer_kategorie(kategorie)
    absaetze = "".join(f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip())
    wappen_html = (
        f'<img src="{wappen_url}" class="artikel-wappen" alt="Wappen" onerror="this.style.display=\'none\'"/>'
        if wappen_url else
        '<div class="artikel-wappen-placeholder">BL</div>'
    )
    vereine_tags_html = ""
    if vereine:
        tags = "".join(
            f'<a href="../index.html?filter={v}" class="verein-tag">{v}</a>'
            for v in vereine
        )
        vereine_tags_html = f'<div class="verein-tags">{tags}</div>'

    artikel_url = f"https://ligaoutsider.de/artikel/{datei_id}.html"
    ersten_absatz = text.split("\n\n")[0].strip() if text else titel

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{titel} – Ligaoutsider.de</title>
  <link rel="stylesheet" href="../style.css"/>
  <link rel="stylesheet" href="../artikel.css"/>
  <link rel="icon" href="../favicon.png" type="image/png"/>
  <script>if(localStorage.getItem('theme')==='light')document.body.classList.add('light');</script>
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-SP8DWFL2SE"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-SP8DWFL2SE');
  </script>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "{titel}",
    "datePublished": "{datum}",
    "dateModified": "{datum}",
    "author": {{
      "@type": "Organization",
      "name": "Ligaoutsider.de"
    }},
    "publisher": {{
      "@type": "Organization",
      "name": "Ligaoutsider.de",
      "url": "https://ligaoutsider.de"
    }},
    "url": "{artikel_url}",
    "description": "{ersten_absatz[:200].replace('"', '&quot;')}",
    "inLanguage": "de",
    "about": {{
      "@type": "SportsOrganization",
      "name": "1. Bundesliga"
    }}
  }}
  </script>
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

      {vereine_tags_html}

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

def qualitaets_check(kandidaten: list) -> list:
    """Sonnet prüft alle Kandidaten als Batch mit strukturiertem JSON-Output.
    Gibt nur approved Kandidaten zurück."""
    if not kandidaten:
        return []

    liste = ""
    for i, k in enumerate(kandidaten):
        text_preview = k["ergebnis"]["text"][:300].replace("\n", " ")
        liste += f"\n[{i}] Titel: {k['ergebnis']['titel']}\n    Text: {text_preview}\n"

    antwort = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": (
                f"Du bist leitender QS-Redakteur von ligaoutsider.de.\n"
                f"Reviewe {len(kandidaten)} Kandidaten. Für JEDEN prüfe:\n"
                f"1. Faktentreue: Kein Lückenfüller, keine Floskeln wie 'Details nicht bekannt'\n"
                f"2. Einzigartigkeit: Kein Duplikat eines anderen Kandidaten (gleicher Spieler + Situation)\n"
                f"3. Qualität: Substanz, lesbar, nicht leer/generisch\n\n"
                f"KANDIDATEN:\n{liste}\n\n"
                f"Output NUR als valides JSON-Array:\n"
                f'[{{"id":0,"decision":"APPROVE"|"REJECT","reason":"1 Satz"}},...]'
            )
        }]
    )

    roh = antwort.content[0].text.strip()
    m = re.search(r'\[.*\]', roh, re.DOTALL)
    if not m:
        log.warning(f"QA: Kein JSON-Array in Antwort: {roh[:200]}")
        # Fallback: alle ablehnen
        return []

    try:
        ergebnisse = json.loads(m.group())
    except json.JSONDecodeError:
        log.warning("QA: JSON-Parse-Fehler, alle abgelehnt")
        return []

    approved = []
    for item in ergebnisse:
        if isinstance(item, dict) and item.get("decision") == "APPROVE":
            idx = item.get("id")
            if isinstance(idx, int) and 0 <= idx < len(kandidaten):
                approved.append(kandidaten[idx])
                log.info(f"QA APPROVE [{idx}]: {kandidaten[idx]['ergebnis']['titel'][:60]}")
            else:
                log.warning(f"QA: ungültiger Index {idx}")
        elif isinstance(item, dict):
            idx = item.get("id", "?")
            reason = item.get("reason", "")
            log.info(f"QA REJECT [{idx}]: {reason}")
    return approved


def main():
    global DELETED_IDS
    DELETED_IDS = lade_deleted_ids()
    ARTIKEL_ORDNER.mkdir(exist_ok=True)
    bestehende = feed_laden()
    published_stories = lade_published_stories()

    # Fingerprints aus published_stories für Dedup (mit Timestamp für Zeitfenster-Check)
    pub_fingerprints: list[tuple[dict, str]] = [
        (s["fingerprint"], s.get("published_at", ""))
        for s in published_stories if s.get("fingerprint")
    ]
    pub_urls: set[str] = {s.get("original_url", "") for s in published_stories}

    # Run-Stats
    stats = {
        "ts": _run_ts, "ingested": 0,
        "s2_pre_filter": 0, "s3_relevance": 0, "s4_dedup_early": 0,
        "s5_fulltext_fail": 0, "s6_dedup_refined": 0,
        "s7_generated": 0, "s8_qa_rejected": 0, "published": 0,
    }

    neu_generiert = 0
    kandidaten: list[dict] = []
    batch_fingerprints: list[tuple[dict, str]] = []  # (fingerprint, published_at) für Intra-Batch-Dedup
    batch_titles: list[str] = []  # für Intra-Batch rapidfuzz Titel-Dedup (Stage 2)

    url_cache = URLCache("data/seen_urls.json", max_age_days=30)
    log.info(f"URL-Cache geladen: {url_cache.get_seen_count()} bekannte URLs (letzte 30 Tage)")

    _SKIP_KEYWORDS = (
        "nagelsmann", "nationalmannschaft", "dfb-team", "em 2026", "wm 2026",
        "nations league", "länderspiel", "u21-em", "olympia",
        "frauen", "frauenfußball", "frauenbundesliga", "-frauen",
        "2. bundesliga", "2. liga", "zweite bundesliga", "zweitliga",
    )

    log.info(f"=== Ligaoutsider Generator startet – max. {MAX_ARTIKEL_PRO_LAUF} Artikel ===")

    # Sky DE direkt scrapen → als synthetisches RSS in den Feed-Loop einreihen
    _sky_items = sky_de_items()
    if _sky_items:
        _sky_xml = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Sky Sport DE</title>' + "".join(
            f'<item><title>{it["title"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</title>'
            f'<link>{it["link"]}</link></item>'
            for it in _sky_items
        ) + "</channel></rss>"
        _SKY_SENTINEL = "__sky_de__"
        _sky_feed_cache = {_SKY_SENTINEL: feedparser.parse(_sky_xml)}
    else:
        _SKY_SENTINEL = None
        _sky_feed_cache = {}

    _all_feeds = RSS_FEEDS + ([_SKY_SENTINEL] if _SKY_SENTINEL else [])

    for feed_url in _all_feeds:
        if neu_generiert >= MAX_ARTIKEL_PRO_LAUF:
            break

        log.info(f"Feed: {feed_url}")
        try:
            feed = _sky_feed_cache[feed_url] if feed_url in _sky_feed_cache else feedparser.parse(feed_url)
        except Exception as e:
            log.error(f"Feed-Parse-Fehler: {e}")
            continue

        ist_google_news = "news.google.com" in feed_url
        feed_quelle = feed.feed.get("title", feed_url)

        for eintrag in feed.entries:
            if neu_generiert >= MAX_ARTIKEL_PRO_LAUF:
                break

            url    = eintrag.get("link", "")
            titel  = eintrag.get("title", "").strip()
            beschr = eintrag.get("summary", eintrag.get("description", ""))

            if not url or not titel:
                continue

            # URL-Cache: bereits gesehene Einträge sofort überspringen
            if url_cache.is_seen(url):
                continue

            # Quelle bei Google News aus entry.source
            quelle_name = feed_quelle
            if ist_google_news:
                src = eintrag.get("source", {})
                if isinstance(src, dict) and src.get("title"):
                    quelle_name = src["title"]
                elif hasattr(src, "title") and src.title:
                    quelle_name = src.title
                else:
                    from urllib.parse import urlparse as _up
                    _netloc = _up(url).netloc.replace("www.", "")
                    if _netloc and "google" not in _netloc:
                        quelle_name = _netloc

            # Reddit: echte URL extrahieren
            if "reddit.com" in feed_url:
                echte_url = eintrag.get("url", "")
                if not echte_url:
                    m = re.search(r'href="(https?://(?!www\.reddit)[^"]+)"', beschr)
                    echte_url = m.group(1) if m else ""
                if echte_url and "reddit.com" not in echte_url:
                    from urllib.parse import urlparse as _up
                    quelle_name = _up(echte_url).netloc.replace("www.", "")
                    url = echte_url

            # Ligainsider: Originalquelle extrahieren
            if "ligainsider.de" in url:
                try:
                    import urllib.request as _ureq
                    _rq = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    _html = _ureq.urlopen(_rq, timeout=8).read().decode("utf-8", errors="ignore")
                    _m = re.search(r'<strong>Quelle:</strong>\s*<a[^>]+href="([^"]+)"', _html)
                    if _m:
                        url = _m.group(1)
                        from urllib.parse import urlparse as _up
                        quelle_name = _up(url).netloc.replace("www.", "")
                    else:
                        continue
                except Exception:
                    continue

            aid = artikel_id(url)
            url_cache.mark_seen(url)
            stats["ingested"] += 1

            # ── Stage 2: Pre-Filter Gate ──────────────────────────────────────
            # Exact: schon verarbeitet (lokale .html/.skip oder published_stories)
            if schon_verarbeitet(url) or url in pub_urls:
                log.debug(f"S2 skip (already processed): {titel[:60]}")
                continue

            # Alters-Check
            veroeffentlicht = eintrag.get("published_parsed") or eintrag.get("updated_parsed")
            if veroeffentlicht:
                alter = datetime.datetime.now() - datetime.datetime(*veroeffentlicht[:6])
                if alter.days > MAX_ALTER_TAGE:
                    (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                    continue

            # Intra-Batch Titel-Dedup via rapidfuzz (Stage 2)
            if batch_titles:
                from rapidfuzz import process as _rfp
                match = _rfp.extractOne(titel, batch_titles, score_cutoff=88)
                if match:
                    log.debug(f"S2 batch title dup ({match[1]}%): {titel[:60]}")
                    _log_skip(aid, titel, "stage2", f"batch_title_dup_{match[1]:.0f}pct")
                    (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                    stats["s2_pre_filter"] += 1
                    continue

            # Blacklist-Keywords
            text_check = (titel + " " + beschr).lower()
            if any(kw in text_check for kw in _SKIP_KEYWORDS):
                log.info(f"S2 blacklist: {titel[:60]}")
                _log_skip(aid, titel, "stage2", "blacklist_keyword")
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                stats["s2_pre_filter"] += 1
                continue

            # ── Stage 3: Relevance Gate (Haiku) ──────────────────────────────
            _ist_kicker_team = "rss.kicker.de/news/" in feed_url
            if not _ist_kicker_team and not ist_relevant(titel, beschr):
                log.info(f"S3 not relevant: {titel[:60]}")
                _log_skip(aid, titel, "stage3", "not_relevant")
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                stats["s3_relevance"] += 1
                continue

            # ── Stage 4: Fingerprint + Early Dedup ───────────────────────────
            fp = fingerprint_generieren(titel, beschr)
            if fp:
                is_update = _is_update_artikel(titel, beschr)
                for existing_fp, existing_ts in pub_fingerprints + batch_fingerprints:
                    if not _fingerprints_aehnlich(fp, existing_fp):
                        continue
                    # Ähnlicher Fingerprint gefunden — Update-Bypass prüfen
                    if is_update and _ist_innerhalb_tage(existing_ts, days=14):
                        log.info(f"S4 update-bypass (Folgeartikel): {titel[:60]}")
                        break  # durchlassen
                    log.info(f"S4 fingerprint dup: {titel[:60]}")
                    _log_skip(aid, titel, "stage4", "fingerprint_duplicate")
                    (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                    stats["s4_dedup_early"] += 1
                    fp = None
                    break
            if fp is None and (ARTIKEL_ORDNER / f"{aid}.skip").exists():
                continue  # wurde als Dup markiert

            # Rapidfuzz-Titel-Check gegen published_stories (fängt null-Fingerprint-Einträge)
            if not (ARTIKEL_ORDNER / f"{aid}.skip").exists():
                from rapidfuzz import fuzz as _fuzz
                pub_titles = [s.get("generated_title") or s.get("title", "") for s in published_stories[-150:]]
                for pt in pub_titles:
                    if pt and _fuzz.ratio(titel.lower(), pt.lower()) >= 88:
                        log.info(f"S4 title-fuzz dup ({pt[:50]}): {titel[:50]}")
                        _log_skip(aid, titel, "stage4", "title_fuzzy_duplicate")
                        (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                        stats["s4_dedup_early"] += 1
                        break
            if (ARTIKEL_ORDNER / f"{aid}.skip").exists():
                continue

            # ── Stage 5: Fulltext Fetch & Validation (CRITICAL GATE) ─────────
            log.info(f"S5 fetch fulltext: {titel[:60]}")
            volltext, reason = fetch_fulltext(url)
            if reason != "ok":
                log.info(f"S5 fulltext fail ({reason}): {titel[:60]}")
                _log_skip(aid, titel, "stage5", f"fulltext_failed_{reason}")
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                stats["s5_fulltext_fail"] += 1
                continue

            # ── Stage 6: Refined Dedup mit Fulltext ──────────────────────────
            if fp:
                # Fingerprint mit Volltext updaten (besserer Kontext)
                fp_refined = fingerprint_generieren(titel, volltext[:600])
                if fp_refined:
                    fp = fp_refined
                is_update = _is_update_artikel(titel, volltext[:400])
                for existing_fp, existing_ts in pub_fingerprints + batch_fingerprints:
                    if not _fingerprints_aehnlich(fp, existing_fp):
                        continue
                    if is_update and _ist_innerhalb_tage(existing_ts, days=14):
                        log.info(f"S6 update-bypass (Folgeartikel): {titel[:60]}")
                        break
                    log.info(f"S6 refined dup: {titel[:60]}")
                    _log_skip(aid, titel, "stage6", "refined_fingerprint_duplicate")
                    (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                    stats["s6_dedup_refined"] += 1
                    fp = None
                    break
                if fp is None:
                    continue

            # ── Stage 7: Article Generation (Sonnet) ─────────────────────────
            log.info(f"S7 generate: {titel[:60]}")
            try:
                ergebnis = artikel_generieren(titel, volltext, quelle_name, url)
            except Exception as e:
                log.warning(f"S7 generation error: {e}")
                continue

            datum      = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            vereine    = vereine_im_text(ergebnis["titel"], ergebnis["text"])
            wappen_url = verein_wappen_url(ergebnis["text"][:1200], title=ergebnis["titel"])

            if fp:
                batch_fingerprints.append((fp, datetime.datetime.now().isoformat()))
            batch_titles.append(titel)

            kandidaten.append({
                "aid":         aid,
                "datum":       datum,
                "ergebnis":    ergebnis,
                "quelle_name": quelle_name,
                "url":         url,
                "wappen_url":  wappen_url,
                "vereine":     vereine,
                "fingerprint": fp,
            })
            stats["s7_generated"] += 1
            log.info(f"  Kandidat: {ergebnis['titel'][:60]}")

    # ── Stage 8: Batch Quality Gate (Sonnet) ─────────────────────────────────
    if kandidaten:
        log.info(f"S8 QA: {len(kandidaten)} Kandidaten …")
        approved = qualitaets_check(kandidaten)
        stats["s8_qa_rejected"] = len(kandidaten) - len(approved)
        log.info(f"S8 approved: {len(approved)} / {len(kandidaten)}")
    else:
        approved = []

    # ── Stage 9/10: Publish & Persist ────────────────────────────────────────
    for k in approved:
        ergebnis = k["ergebnis"]
        aid = k["aid"]
        html = artikel_html(
            datei_id    = aid,
            titel       = ergebnis["titel"],
            text        = ergebnis["text"],
            kategorie   = ergebnis["kategorie"],
            quelle_name = k["quelle_name"],
            quelle_url  = k["url"],
            datum       = k["datum"],
            wappen_url  = k["wappen_url"],
            vereine     = k["vereine"],
        )
        (ARTIKEL_ORDNER / f"{aid}.html").write_text(html, encoding="utf-8")
        badge_label, badge_bg, badge_fg = badge_fuer_kategorie(ergebnis["kategorie"])
        feed_entry = {
            "id":         aid,
            "titel":      ergebnis["titel"],
            "kategorie":  ergebnis["kategorie"],
            "badge":      badge_label,
            "badge_bg":   badge_bg,
            "badge_fg":   badge_fg,
            "datum":      k["datum"],
            "wappen_url": k["wappen_url"],
            "vereine":    k["vereine"],
            "pfad":       f"artikel/{aid}.html",
        }
        bestehende.append(feed_entry)
        feed_speichern(bestehende)

        # Persistenter State updaten
        published_stories.append({
            "id":             aid,
            "generated_title": ergebnis["titel"],
            "original_url":   k["url"],
            "fingerprint":    k.get("fingerprint"),
            "published_at":   datetime.datetime.now().isoformat(),
            "source":         k["quelle_name"],
        })
        speichere_published_stories(published_stories)
        neu_generiert += 1
        stats["published"] += 1
        log.info(f"Veröffentlicht: {ergebnis['titel'][:60]}")

    sitemap_generieren(bestehende)

    # Stage 9: Facebook-Posts & Reddit nach finalem Publish
    for k in approved:
        ergebnis = k["ergebnis"]
        aid = k["aid"]
        artikel_url = f"https://ligaoutsider.de/artikel/{aid}.html"
        facebook_post(ergebnis["titel"], artikel_url)
        reddit_post(ergebnis["titel"], ergebnis["text"], artikel_url)

    # Run-Stats speichern
    stats_path = LOG_DIR / f"run_{_run_ts}.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    url_cache.cleanup_and_save()
    log.info(f"URL-Cache gespeichert: {url_cache.get_seen_count()} URLs")

    log.info(f"=== Fertig. {neu_generiert} neue Artikel. feed.json: {len(bestehende)} ===")
    log.info(f"Stats: {json.dumps(stats)}")


def sky_de_items() -> list[dict]:
    """Scrapt sport.sky.de/fussball direkt und gibt Feed-kompatible Dicts zurück."""
    import re as _re
    sky_url = "https://sport.sky.de/fussball"
    try:
        resp = requests.get(sky_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"Sky DE Scraper: Fetch fehlgeschlagen: {e}")
        return []
    # Artikel-Links: /fussball/artikel/{slug}/{id}/{cat}
    pattern = _re.compile(r'href="(/fussball/artikel/([^/"]+)/\d+/\d+)"')
    seen = set()
    items = []
    for m in pattern.finditer(resp.text):
        path, slug = m.group(1), m.group(2)
        url = f"https://sport.sky.de{path}"
        if url in seen:
            continue
        seen.add(url)
        titel = slug.replace("-", " ").title()
        items.append({"link": url, "title": titel, "summary": "", "_sky_de": True})
    log.info(f"Sky DE Scraper: {len(items)} Artikel gefunden")
    return items


def reddit_post(titel: str, text: str, artikel_url: str):
    """Postet Artikel als Text-Post auf r/ligaoutsider (benötigt REDDIT_* Secrets)."""
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    username      = os.environ.get("REDDIT_USERNAME", "")
    password      = os.environ.get("REDDIT_PASSWORD", "")
    if not all([client_id, client_secret, username, password]):
        log.info("Reddit: Keine Credentials – übersprungen")
        return
    try:
        import praw
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent="ligaoutsider-bot/1.0",
        )
        body = f"{text}\n\n---\n[➡️ Vollständiger Artikel auf Ligaoutsider.de]({artikel_url})"
        reddit.subreddit("ligaoutsider").submit(titel, selftext=body)
        log.info(f"Reddit: Gepostet – {titel[:60]}")
    except Exception as e:
        log.warning(f"Reddit-Post fehlgeschlagen: {e}")


def facebook_post(titel: str, artikel_url: str):
    """Postet neuen Artikel auf Facebook-Seite (benötigt FACEBOOK_PAGE_TOKEN + FACEBOOK_PAGE_ID)."""
    page_token = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
    page_id    = os.environ.get("FACEBOOK_PAGE_ID", "")
    if not page_token or not page_id:
        return
    import urllib.request as _req
    import urllib.parse as _parse
    data = _parse.urlencode({
        "message":      f"⚽ {titel}\n\n{artikel_url}",
        "link":         artikel_url,
        "access_token": page_token,
    }).encode()
    try:
        _req.urlopen(
            _req.Request(f"https://graph.facebook.com/v19.0/{page_id}/feed", data=data),
            timeout=10
        )
        print(f"  📘 Facebook-Post erstellt")
    except Exception as e:
        print(f"  ⚠️  Facebook-Post fehlgeschlagen: {e}")


def sitemap_generieren(artikel_liste: list):
    base = "https://ligaoutsider.de"
    heute = datetime.date.today().isoformat()
    urls = [
        (f"{base}/", "1.0", "daily"),
        (f"{base}/archiv.html", "0.8", "daily"),
        (f"{base}/kickbase.html", "0.6", "weekly"),
        (f"{base}/forum.html", "0.6", "weekly"),
    ]
    for a in artikel_liste:
        urls.append((f"{base}/{a['pfad']}", "0.9", "monthly"))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, prio, freq in urls:
        lines += [
            "  <url>",
            f"    <loc>{loc}</loc>",
            f"    <lastmod>{heute}</lastmod>",
            f"    <changefreq>{freq}</changefreq>",
            f"    <priority>{prio}</priority>",
            "  </url>",
        ]
    lines.append("</urlset>")
    Path("sitemap.xml").write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ sitemap.xml generiert ({len(urls)} URLs)")


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
        r = session.get("https://api.kickbase.com/v4/competitions/1/players?limit=200", timeout=20)
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

    # Wenn API < 50 Spieler liefert (Saison noch nicht gestartet / unvollständig),
    # bestehende punkte-Liste aus kickbase.json beibehalten statt mit falschen Top-10 überschreiben
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
        transfers_resp = None
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
