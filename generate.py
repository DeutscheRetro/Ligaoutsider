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
    # Pro Verein alles aus den letzten 24 Stunden (nicht nur Transfers):
    # Training, Verletzungen, Pressekonferenzen, Aufstellungsfragen
    "https://news.google.com/rss/search?q=%22FC+Bayern%22+OR+%22Bayern+M%C3%BCnchen%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=BVB+OR+%22Borussia+Dortmund%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22Bayer+Leverkusen%22+OR+%22Bayer+04%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22RB+Leipzig%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22VfB+Stuttgart%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22Eintracht+Frankfurt%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Gladbach+OR+%22Borussia+M%C3%B6nchengladbach%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22SC+Freiburg%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Hoffenheim+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22Mainz+05%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22FC+Augsburg%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22Union+Berlin%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22Werder+Bremen%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=HSV+OR+%22Hamburger+SV%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%221.+FC+K%C3%B6ln%22+OR+%22FC+K%C3%B6ln%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Schalke+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=Elversberg+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=%22SC+Paderborn%22+when%3A1d&hl=de&gl=DE&ceid=DE:de",
    "https://www.transfermarkt.de/rss/news",
    "https://www.waz.de/sport/fussball/rss",
    "https://www.faz.net/rss/aktuell/sport/fussball/bundesliga/",

    # Englische Quellen
    "https://bulinews.com/rss.xml",
    "https://www.abendblatt.de/sport/rss",
    "https://www.merkur.de/sport/fc-bayern/rssfeed.rdf",
    "https://www.eyefootball.com/rss_news_main.xml",
    "https://www.ligaportal.at/international/deutsche-bundesliga?format=feed&type=rss",

    # Reddit (100 Einträge)
    "https://www.reddit.com/r/soccer/new.rss?limit=100",

    # kicker Team-Feeds – 18 Erstligisten 2026/27
    # Host rss.kicker.de existiert nicht mehr; newsfeed.kicker.de/team/<slug>
    # ist der aktuelle Pfad. Diese Feeds umgehen den Keyword-Vorfilter.
    "https://newsfeed.kicker.de/team/fc-bayern-muenchen",
    "https://newsfeed.kicker.de/team/borussia-dortmund",
    "https://newsfeed.kicker.de/team/rb-leipzig",
    "https://newsfeed.kicker.de/team/bayer-04-leverkusen",
    "https://newsfeed.kicker.de/team/vfb-stuttgart",
    "https://newsfeed.kicker.de/team/eintracht-frankfurt",
    "https://newsfeed.kicker.de/team/bor-moenchengladbach",
    "https://newsfeed.kicker.de/team/sc-freiburg",
    "https://newsfeed.kicker.de/team/tsg-hoffenheim",
    "https://newsfeed.kicker.de/team/1-fsv-mainz-05",
    "https://newsfeed.kicker.de/team/fc-augsburg",
    "https://newsfeed.kicker.de/team/1-fc-union-berlin",
    "https://newsfeed.kicker.de/team/werder-bremen",
    "https://newsfeed.kicker.de/team/hamburger-sv",
    "https://newsfeed.kicker.de/team/1-fc-koeln",
    "https://newsfeed.kicker.de/team/fc-schalke-04",
    "https://newsfeed.kicker.de/team/sv-elversberg",
    "https://newsfeed.kicker.de/team/sc-paderborn-07",
    "https://newsfeed.kicker.de/news/champions-league",
    # LigaInsider nur als Themenfinder – Quelle ist immer der dort verlinkte Originalartikel
    "ligainsider:themen",
]

# Artikel bis zu X Tage alt akzeptieren
MAX_ALTER_TAGE = 3

# Wie viele neue Artikel maximal pro Durchlauf generieren
MAX_ARTIKEL_PRO_LAUF = 50

# Wo Artikel gespeichert werden
ARTIKEL_ORDNER = Path("artikel")
FEED_JSON      = Path("feed.json")
OG_ORDNER      = Path("og")
FONT_ORDNER    = Path(__file__).parent / "fonts"

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
    # Kurz- und Spitznamen, wie sie in Überschriften stehen ("Eintrachts neues Schnäppchen")
    "Eintracht", "Bayer 04", "Werkself", "Fohlen", "Borussia", "Königsblau", "Knappen", "S04",
    "Geißböcke", "Eisernen", "Rothosen", "Nullfünfer", "Kraichgauer", "Breisgauer",
    "Fuggerstädter", "Roten Bullen", "Hanseaten",
]

# ─── Wappen-URLs für die Feed-Anzeige ─────────────────────────────────────────

BL_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/d/df/Bundesliga_logo_%282017%29.svg/120px-Bundesliga_logo_%282017%29.svg.png"

W = "https://upload.wikimedia.org/wikipedia"  # Abkürzung

VEREIN_WAPPEN = {
    # Bayern
    "fc bayern münchen": "logos/bayern.png",
    "fc bayern":         "logos/bayern.png",
    "bayern":            "logos/bayern.png",
    "fcb":               "logos/bayern.png",
    "allianz arena":     "logos/bayern.png",
    # Dortmund
    "borussia dortmund": "logos/dortmund.png",
    "dortmund":          "logos/dortmund.png",
    "bvb":               "logos/dortmund.png",
    "signal iduna":      "logos/dortmund.png",
    # Leipzig
    "rb leipzig":          "logos/leipzig.png",
    "leipzig":             "logos/leipzig.png",
    "red bull arena":      "logos/leipzig.png",
    # Leverkusen
    "bayer 04":            "logos/leverkusen.png",
    "leverkusen":          "logos/leverkusen.png",
    "bayarena":            "logos/leverkusen.png",
    # Frankfurt
    "eintracht frankfurt": "logos/frankfurt.png",
    "eintracht":           "logos/frankfurt.png",
    "frankfurt":           "logos/frankfurt.png",
    "sge":                 "logos/frankfurt.png",
    "deutsche bank park":  "logos/frankfurt.png",
    # Stuttgart
    "vfb stuttgart":    "logos/stuttgart.png",
    "stuttgart":        "logos/stuttgart.png",
    "mhp arena":        "logos/stuttgart.png",
    # Gladbach
    "mönchengladbach":  "logos/gladbach.png",
    "gladbach":         "logos/gladbach.png",
    "borussia m":       "logos/gladbach.png",
    "borussia-park":    "logos/gladbach.png",
    # Freiburg
    "sc freiburg":      "logos/freiburg.png",
    "freiburg":         "logos/freiburg.png",
    "europa-park stadion": "logos/freiburg.png",
    # Union Berlin
    "union berlin":     "logos/union.png",
    "1. fc union":      "logos/union.png",
    "union":            "logos/union.png",
    "an der alten försterei": "logos/union.png",
    "köpenick":         "logos/union.png",
    # Mainz
    "fsv mainz":        "logos/mainz.png",
    "mainz":            "logos/mainz.png",
    "mewa arena":       "logos/mainz.png",
    # Augsburg
    "fc augsburg":      "logos/augsburg.png",
    "augsburg":         "logos/augsburg.png",
    "www arena":        "logos/augsburg.png",
    # Werder
    "sv werder":        "logos/werder.png",
    "werder":           "logos/werder.png",
    "weserstadion":     "logos/werder.png",
    "wohninvest weserstadion": "logos/werder.png",
    # Hoffenheim
    "tsg hoffenheim":   "logos/hoffenheim.png",
    "hoffenheim":       "logos/hoffenheim.png",
    "tsg 1899":         "logos/hoffenheim.png",
    # HSV
    "hamburger sv":     "logos/hsv.png",
    "hamburger":        "logos/hsv.png",
    "hsv":              "logos/hsv.png",
    # Köln
    "1. fc köln":       "logos/koeln.png",
    "köln":             "logos/koeln.png",
    "effzeh":           "logos/koeln.png",
    # Schalke
    "fc schalke":       "logos/schalke.png",
    "schalke":          "logos/schalke.png",
    # Paderborn
    "sc paderborn":     "logos/paderborn.png",
    "paderborn":        "logos/paderborn.png",
    # Elversberg
    "sv elversberg":    "logos/elversberg.png",
    "sve":              "logos/elversberg.png",
    "elversberg":       "logos/elversberg.png",
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

# Kanonische Klubnamen, die das Modell in "hauptklub" zurueckgeben darf,
# plus das zugehoerige Wappen. Reihenfolge = Reihenfolge im Prompt.
KLUB_LOGO = {
    "Bayern":      "logos/bayern.png",
    "Dortmund":    "logos/dortmund.png",
    "Leipzig":     "logos/leipzig.png",
    "Leverkusen":  "logos/leverkusen.png",
    "Frankfurt":   "logos/frankfurt.png",
    "Stuttgart":   "logos/stuttgart.png",
    "Gladbach":    "logos/gladbach.png",
    "Freiburg":    "logos/freiburg.png",
    "Union":       "logos/union.png",
    "Mainz":       "logos/mainz.png",
    "Augsburg":    "logos/augsburg.png",
    "Werder":      "logos/werder.png",
    "Hoffenheim":  "logos/hoffenheim.png",
    "HSV":         "logos/hsv.png",
    "Köln":        "logos/koeln.png",
    "Schalke":     "logos/schalke.png",
    "Paderborn":   "logos/paderborn.png",
    "Elversberg":  "logos/elversberg.png",
}

# "HSV" liest sich im Prompt natuerlicher, der Filter-Chip auf der Seite
# heisst aber "Hamburger" – wie vereine_im_text() den Klub benennt.
KLUB_FILTERNAME = {"HSV": "Hamburger"}


def _count_key(key: str, text: str) -> int:
    """Zählt Vorkommen von key in text am Wortanfang.

    Rechts bewusst offen: deutsche Beugungen wie 'Frankfurter', 'Kölner',
    'Schalker' oder 'Bayerns' sind echte Treffer. Die Grenze links verhindert
    Substring-Unfug wie 'anspruchsvollem' → hsv oder 'ausgezeichnet' → sge.

    Kurze Kürzel (BVB, SGE, SVE) sind Akronyme statt Wortstämme und brauchen
    auch rechts eine Grenze, sonst schlägt 'SVE' auf 'Sven' und 'Svensson' an.
    """
    rechts = r'(?!\w)' if len(key) <= 3 else ''
    return len(re.findall(r'(?<!\w)' + re.escape(key) + rechts, text))


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
    html_file = ARTIKEL_ORDNER / f"{aid}.html"
    if html_file.exists():
        # Regenerate if SEO tags missing
        if 'rel="canonical"' not in html_file.read_text(encoding='utf-8', errors='ignore'):
            return False
        return True
    return (ARTIKEL_ORDNER / f"{aid}.skip").exists()


def verein_wappen_url(text: str, title: str = "") -> str:
    """Findet das relevanteste Vereinslogo per Scoring aggregiert pro Logo-URL."""
    _context_kw = ("wechselt", "transfer", "verletzung", "verpflichtet", "spielt",
                   "trainer", "vertrag", "ablöse", "siegt", "verliert")
    # "gegen X" / "bei X" markiert den Gegner, nicht das Thema des Artikels
    _gegner_kw = ("gegen", "bei", "auswärts bei", "zu gast bei", "empfängt")
    full_lower = (title + " " + text).lower()
    title_lower = title.lower()
    # Gleichnamige Klubs ausserhalb der Liga ausblenden, bevor gezaehlt wird
    for fremd in ("philadelphia union", "union saint-gilloise", "union berlin ii"):
        full_lower = full_lower.replace(fremd, " ")
        title_lower = title_lower.replace(fremd, " ")
    text_len = len(full_lower) or 1

    # Erst pro Logo aggregieren. Mehrere Keys zeigen auf denselben Klub
    # ("stuttgart", "vfb stuttgart"); ohne Aggregation kassiert der Klub
    # jeden Bonus mehrfach und ueberholt den eigentlich gemeinten.
    agg: dict[str, dict] = {}
    for key, logo_url in VEREIN_WAPPEN.items():
        count = _count_key(key, full_lower)
        if count == 0:
            continue
        m_full = re.search(r'(?<!\w)' + re.escape(key), full_lower)
        m_titel = re.search(r'(?<!\w)' + re.escape(key), title_lower)
        a = agg.setdefault(logo_url, {"count": 0, "pos": text_len, "titel_pos": None,
                                      "kontext": False, "gegner": False})
        # max statt sum: der kuerzere Key zaehlt die Treffer des laengeren mit
        a["count"] = max(a["count"], count)
        if m_full:
            a["pos"] = min(a["pos"], m_full.start())
        if m_titel:
            a["titel_pos"] = (m_titel.start() if a["titel_pos"] is None
                              else min(a["titel_pos"], m_titel.start()))
        if any(f"{key} {kw}" in full_lower or f"{kw} {key}" in full_lower
               for kw in _context_kw):
            a["kontext"] = True
        if any(f"{kw} {key}" in title_lower for kw in _gegner_kw):
            a["gegner"] = True

    if not agg:
        return BL_LOGO

    # Wer im Titel zuerst steht, ist fast immer das Thema – Bonus nur einmal
    im_titel = [(v["titel_pos"], k) for k, v in agg.items() if v["titel_pos"] is not None]
    erster_im_titel = min(im_titel)[1] if im_titel else None

    logo_scores: dict[str, int] = {}
    for logo_url, a in agg.items():
        score = a["count"] * 10
        if a["titel_pos"] is not None:
            score += 100
        if logo_url == erster_im_titel:
            score += 45
        if a["pos"] < text_len * 0.25:
            score += 15
        elif a["pos"] < text_len * 0.5:
            score += 8
        if a["kontext"]:
            score += 20
        if a["gegner"]:
            score -= 60
        logo_scores[logo_url] = score

    bestes = max(logo_scores, key=logo_scores.get)  # type: ignore[arg-type]
    # Ligaweite Artikel (Spielplan, Testspiel-Uebersichten) nennen viele Klubs,
    # keinen im Titel und haben keinen klaren Schwerpunkt – da ist das neutrale
    # Bundesliga-Logo ehrlicher als ein willkuerlich gewaehltes Wappen.
    if not im_titel and len(agg) >= 5:
        rest = sorted((s for k, s in logo_scores.items() if k != bestes), reverse=True)
        if rest and logo_scores[bestes] < rest[0] * 1.5:
            return BL_LOGO
    return bestes


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
    # Neueste zuerst
    from datetime import datetime
    artikel_liste.sort(key=lambda x: datetime.strptime(x["datum"], "%d.%m.%Y %H:%M"), reverse=True)
    FEED_JSON.write_text(
        json.dumps(artikel_liste[:100_000], ensure_ascii=False, indent=2),
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

NEWS_ARCHIVE_JSON = Path("data/news_archive.json")

def lade_news_archive() -> list[dict]:
    if NEWS_ARCHIVE_JSON.exists():
        try:
            return json.loads(NEWS_ARCHIVE_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def speichere_news_archive(archive: list[dict]):
    NEWS_ARCHIVE_JSON.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")

def final_pre_publish_check(titel: str, fp: dict, archive: list[dict]) -> bool:
    """True = Duplikat (skip), False = neu publizieren.
    Gleicher main_club + gleiche main_players + gleiche event_stage innerhalb 7 Tage → Duplikat.
    Andere event_stage → neue Entwicklung → publizieren."""
    if not fp:
        return False
    new_club = (fp.get("main_club") or "").lower().strip()
    new_stage = fp.get("event_stage", "sonstiges")
    new_players = {p.lower() for p in fp.get("main_players", [])}

    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    for entry in archive:
        try:
            entry_ts = datetime.datetime.fromisoformat(entry.get("published_at", ""))
        except Exception:
            continue
        if entry_ts < cutoff:
            continue

        old_club = (entry.get("main_club") or "").lower().strip()
        old_stage = entry.get("event_stage", "sonstiges")
        old_players = {p.lower() for p in entry.get("main_players", [])}

        # Gleicher Verein?
        if new_club and old_club and new_club != old_club:
            continue

        # Spieler-Überschneidung?
        if new_players and old_players and not (new_players & old_players):
            continue

        # Gleiche event_stage → echtes Duplikat
        if new_stage == old_stage and new_stage not in ("sonstiges", ""):
            log.info(f"FinalCheck SKIP: {new_club}/{new_players} stage={new_stage} bereits in Archiv")
            return True

        # Andere event_stage → neue Entwicklung → durchlassen
        # (z.B. geruecht → vollzogen)

    return False

def speichere_published_stories(stories: list[dict]):
    PUBLISHED_JSON.parent.mkdir(exist_ok=True)
    PUBLISHED_JSON.write_text(
        json.dumps(stories[-1000:], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ─── Content Fingerprint (Stage 4) ────────────────────────────────────────────

def fingerprint_generieren(titel: str, summary: str) -> dict | None:
    """Haiku extrahiert strukturierten Story-Fingerprint als JSON.
    Enthält jetzt auch main_club, event_stage, summary für news_archive."""
    try:
        antwort = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": (
                f'Extrahiere einen Story-Fingerprint als reines JSON (kein Markdown):\n'
                f'{{"event_type":"transfer|verletzung|trainerwechsel|spielergebnis|testspiel|geruecht|vereinsnews|analyse|sonstiges",'
                f'"main_club":"der primäre Bundesliga-Verein des Artikels (vollständiger Name)",'
                f'"event_stage":"geruecht|angebot|einigung|vollzogen|verletzung|kader|vertrag|trainer|sonstiges",'
                f'"main_teams":["max 3 Teams"],'
                f'"main_players":["max 3 Spieler"],'
                f'"summary":"2-3 Sätze faktische Zusammenfassung (max 60 Wörter)",'
                f'"one_sentence_summary":"1 Satz Kern-Ereignis"}}\n\n'
                f'Regeln:\n'
                f'- event_stage=geruecht: nur Interesse/Spekulationen\n'
                f'- event_stage=angebot: konkretes Angebot liegt vor\n'
                f'- event_stage=einigung: Einigung erzielt, Transfer noch nicht vollzogen\n'
                f'- event_stage=vollzogen: Transfer/Vertrag offiziell bestätigt/unterschrieben\n\n'
                f'Titel: {titel}\nZusammenfassung: {summary[:800]}'
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


def schon_berichtet(titel: str, kern: str, vorhandene: list[str]) -> str | None:
    """Stage 6.5: Haiku prüft vor dem Schreiben, ob dasselbe Ereignis schon berichtet
    wurde (letzte Tage oder in diesem Lauf). Gibt den passenden Titel zurück oder None.
    Fängt, was Fingerprints übersehen: dieselbe Nachricht aus anderer Quelle oder als
    Einordnung/Kommentar ("Warum X trotz Y der richtige Trainer bleibt")."""
    if not vorhandene:
        return None
    liste = "\n".join(f"[{i}] {t}" for i, t in enumerate(vorhandene[-250:]))
    try:
        antwort = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{"role": "user", "content": (
                "Ist die NEUE Meldung dieselbe Nachricht wie eine der VORHANDENEN?\n"
                "Dieselbe Nachricht heißt: dieselben Personen/derselbe Verein und dasselbe Ereignis "
                "(z. B. dieselbe Vertragsverlängerung, derselbe Ausfall, dieselbe Rückkehr, dasselbe Spiel), "
                "auch wenn Quelle, Formulierung, Zahlen oder Blickwinkel (Analyse, Kommentar, Reaktion) anders sind.\n"
                "KEINE Doppelmeldung ist nur eine echte neue Entwicklung: z. B. Gerücht → offiziell, "
                "fraglich → fällt definitiv aus, Verletzung → Rückkehr ins Training, oder ein anderes Spiel.\n\n"
                f"NEUE Meldung: {titel}\nKern: {kern[:400]}\n\n"
                f"VORHANDENE:\n{liste}\n\n"
                "Antworte nur mit der Nummer der passenden vorhandenen Meldung oder mit NEIN."
            )}],
        )
        roh = antwort.content[0].text.strip()
        m = re.match(r"\[?(\d+)\]?", roh)
        if not (m and int(m.group(1)) < len(vorhandene[-250:])):
            return None
        kandidat = vorhandene[-250:][int(m.group(1))]
        # Gegenprobe nur für dieses Paar: die Listenauswahl greift gelegentlich daneben
        # (zwei verschiedene HSV-Meldungen am selben Tag)
        pruef = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": (
                "Berichten diese zwei Meldungen über dasselbe Ereignis mit denselben Personen? "
                "Andere Person oder anderes Ereignis = NEIN.\n\n"
                f"A: {titel}\nKern A: {kern[:300]}\n\nB: {kandidat}\n\nAntworte nur JA oder NEIN."
            )}],
        )
        return kandidat if "JA" in pruef.content[0].text.upper() else None
    except Exception as e:
        log.warning(f"S6.5 Duplikatprüfung fehlgeschlagen: {e}")
    return None


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


_BL_SPIELER_CACHE: list[str] = []
_BL_SPIELER_LOADED = False

def _lade_bl_spieler() -> list[str]:
    """Namen aller Bundesliga-Spieler für den Vorfilter (gecacht pro Lauf).

    Quelle ist spieler_db.json (Transfermarkt-Kader). OpenLigaDB liefert für
    2026 keine Spielerliste mehr – dadurch fielen Überschriften ohne Vereinsnamen
    ("Kane findet Ballon-d'Or-Debatte kompliziert") früher komplett durch.
    """
    global _BL_SPIELER_CACHE, _BL_SPIELER_LOADED
    if _BL_SPIELER_LOADED:
        return _BL_SPIELER_CACHE
    _BL_SPIELER_LOADED = True
    namen = set()
    try:
        db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
        for team in db["teams"].values():
            for sp in team["spieler"]:
                for n in (sp.get("name"), (sp.get("kickbase") or {}).get("name")):
                    if not n:
                        continue
                    namen.add(n)
                    teile = n.split()
                    # Nachname allein nur, wenn er lang genug ist, um nicht ständig zu treffen
                    if len(teile) > 1 and len(teile[-1]) >= 5:
                        namen.add(teile[-1])
    except Exception as e:
        log.warning(f"Spielerliste nicht verfügbar: {e}")
    _BL_SPIELER_CACHE = sorted(namen)
    log.info(f"BL-Spielerliste geladen: {len(_BL_SPIELER_CACHE)} Namen")
    return _BL_SPIELER_CACHE


# Klubs ausserhalb der 1. Bundesliga. Mehrwortig, wo der Stadtname sonst mit
# einem Erstligisten kollidiert (Koeln, Leipzig, Muenchen).
NICHT_BL_KLUBS = (
    "dynamo dresden", "hannover 96", "rot-weiss essen", "rot-weiß essen",
    "lok leipzig", "chemie leipzig", "karlsruher sc", "fortuna düsseldorf",
    "hertha bsc", "1. fc nürnberg", "greuther fürth", "sv darmstadt",
    "holstein kiel", "vfl bochum", "arminia bielefeld", "preußen münster",
    "ssv ulm", "eintracht braunschweig", "hansa rostock", "msv duisburg",
    "sv sandhausen", "jahn regensburg", "sc verl", "waldhof mannheim",
    "energie cottbus", "viktoria köln", "tsv 1860", "1860 münchen",
    "1. fc saarbrücken", "erzgebirge aue", "vfl osnabrück", "wehen wiesbaden",
    "1. fc magdeburg", "kaiserslautern", "alemannia aachen", "stuttgarter kickers",
    "fc ingolstadt", "vfb oldenburg",
)


def nur_fremdklub(titel: str) -> bool:
    """Titel dreht sich um einen Nicht-Erstligisten und nennt keinen BL-Klub.

    Bewusst eng gefasst: sobald auch ein Bundesligist im Titel steht, bleibt
    der Artikel drin. "Hansa Rostock verliert Test gegen Gladbach" ist echte
    Gladbach-News, auch wenn Rostock vorne steht.
    """
    t = titel.lower()
    if not any(k in t for k in NICHT_BL_KLUBS):
        return False
    return not any(_count_key(k, t) for k in VEREIN_WAPPEN)


def keyword_pre_filter(titel: str, beschreibung: str) -> bool:
    """Stage 3: Billiger Keyword-Check — kein Haiku-Call.
    Lässt durch wenn BL-Klub ODER BL-Spieler im Titel/Beschreibung vorkommt."""
    combined = (titel + " " + beschreibung).lower()
    if any(_count_key(k.lower(), combined) for k in BL1_KLUBS):
        return True
    spieler = _lade_bl_spieler()
    return any(_count_key(s.lower(), combined) for s in spieler if len(s) > 4)


def ist_relevant(titel: str, volltext: str) -> bool:
    """Stage 5.5: Haiku beurteilt Relevanz anhand des ECHTEN Artikeltexts (nicht RSS-Snippet).
    Volltext wird auf 1500 Zeichen gekürzt — enthält Kern-Infos."""
    klubs = ", ".join(BL1_KLUBS)
    antwort = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                f"Ist das eine relevante Fußball-News über einen der folgenden Klubs oder deren Spieler?\n"
                f"Klubs: {klubs}.\n"
                f"Antworte NUR mit JA wenn:\n"
                f"- Es direkt um mindestens einen dieser Klubs oder einen ihrer Spieler geht (Transfer, Spiel, Trainer, Verletzung, Vertrag, Testspiel, "
                f"Training, Pressekonferenz, Aufstellung, Startelf-Chancen, Rückkehr nach Verletzung, Aussagen von Spielern oder Trainern)\n"
                f"- Es eine echte redaktionelle News ist (kein Social-Media-Post, kein Werbeartikel, kein Quiz, keine Trauerbekundung)\n"
                f"- Es KEIN WM-, EM-, Nationalmannschafts-, Frauenfußball- oder 2.-Bundesliga-Thema ist\n"
                f"- Es KEINE reine Champions-League/Europa-League-News ohne Bezug zu diesen Klubs ist\n"
                f"- Der Fokus auf dem Klub/Spieler liegt, nicht nur eine Randerwähnung\n"
                f"- Es KEIN Ranking, keine Liste und keine Statistik-Übersicht ist, in der einer dieser Klubs lediglich als ein Eintrag unter vielen auftaucht (z. B. Markenwert-Rankings, Follower-Zahlen, Europa-Tabellen). Geht es zentral um einen Klub außerhalb der Liste: NEIN.\n"
                f"- Es um ein AKTUELLES Geschehen geht. Historische Rückblicke auf vergangene Spielzeiten, Jubiläums- und Archivstücke sind NEIN, auch wenn der Klub stimmt. Nenne der Artikel eine zurückliegende Saison als Schauplatz (etwa 2009/10), ist das ein klares NEIN.\n"
                f"- Wenn ein Spieler eines dieser Klubs im Ausland spielt (Leihe, Auslandsklub): NUR JA wenn Transfer zurück, Vertragsende, oder direkter Bezug zu diesen Klubs. Ein Tor in der Ligue 1/Premier League/Serie A ist KEIN Grund für JA.\n\n"
                f"Titel: {titel}\nArtikeltext: {volltext[:1500]}\n\n"
                f"Geht es um einen Spieler oder Trainer eines dieser Klubs und das aktuelle Geschehen dort, ist die Antwort JA. "
                f"Im Zweifel JA.\n"
                f"Antworte nur mit JA oder NEIN."
            )
        }]
    )
    return "JA" in antwort.content[0].text.upper()


_GN_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


def _decode_google_news_url(google_url: str) -> str | None:
    """Loest einen Google-News-Link zur echten Artikel-URL auf.

    Frueher steckte die Ziel-URL base64-kodiert im Pfad. Seit Google auf
    undurchsichtige Artikel-IDs (AU_yqL...) umgestellt hat, greift der alte
    Weg nicht mehr - er wird nur noch fuer Altbestaende versucht. Danach
    fragen wir denselben Endpunkt ab, den die Google-News-Oberflaeche nutzt.

    Schlaegt alles fehl, gibt die Funktion None zurueck und der Artikel wird
    uebersprungen; die Pipeline darf daran nie haengen bleiben.
    """
    import base64
    import requests as _req

    m = re.search(r'articles/([A-Za-z0-9_=-]+)', google_url)
    if not m:
        return None
    artikel_id = m.group(1)

    # Altes Format: Ziel-URL steckt direkt im base64-Teil
    if artikel_id.startswith("CBMi"):
        try:
            b64 = artikel_id[4:]
            b64 += "=" * (-len(b64) % 4)
            roh = base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
            treffer = re.search(r'https?://[^\x00-\x1f\s]+', roh)
            if treffer:
                ziel = treffer.group(0).rstrip("\x00").rstrip("=")
                if "google.com" not in ziel:
                    return ziel
        except Exception:
            pass

    # Aktuelles Format: Signatur von der Artikelseite holen, dann aufloesen
    try:
        s = _req.Session()
        s.headers.update({"User-Agent": _GN_UA})
        # Ohne Einwilligungs-Cookie leitet Google (EU) auf consent.google.com um.
        # "CONSENT=YES+cb" wird nicht mehr akzeptiert, maßgeblich ist heute SOCS.
        s.cookies.set("SOCS", "CAESEwgDEgk0ODE3Nzk3MjQaAmRlIAEaBgiA_LyaBg", domain=".google.com")
        s.cookies.set("CONSENT", "PENDING+987", domain=".google.com")
        seite = s.get(f"https://news.google.com/rss/articles/{artikel_id}", timeout=10)
        sig = re.search(r'data-n-a-sg="([^"]+)"', seite.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', seite.text)
        if not (sig and ts):
            return None

        nutzlast = json.dumps([
            "Fbv4je",
            json.dumps(["garturlreq", [["de", "DE", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"],
                                        None, None, 1, 1, "DE:de", None, 180, None, None, None,
                                        None, None, 0, None, None, [1608992194]],
                                       "de", "DE", 1, [2, 4, 8], 1, 1, None, 0, 0, None, 0],
                        artikel_id, int(ts.group(1)), sig.group(1)]),
        ])
        antwort = s.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data={"f.req": json.dumps([[nutzlast and json.loads(nutzlast)]])},
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=10,
        )
        # Die Ziel-URL steht als escaptes JSON in der Antwort: ...["garturlres","https://…"]
        ziel = re.search(r'garturlres\\?",\\?"(https?://[^"\\]+)', antwort.text)
        if not ziel:
            log.debug(f"Google-News-Antwort ohne URL: {antwort.status_code} {antwort.text[:120]}")
        return ziel.group(1) if ziel else None
    except Exception as e:
        log.debug(f"Google-News-Aufloesung fehlgeschlagen: {e}")
        return None


def _ligainsider_eintraege() -> list[dict]:
    """Themenfinder: News der letzten Tage von den 18 LigaInsider-Vereinsseiten im
    Format eines RSS-Eintrags. LigaInsider selbst wird nie Quelle – die Pipeline
    folgt nur dem dort verlinkten Originalartikel (siehe main)."""
    import requests as _req
    import html as _html
    s = _req.Session()
    s.headers.update({"User-Agent": _GN_UA, "Accept-Language": "de-DE,de;q=0.9"})
    try:
        start = s.get("https://www.ligainsider.de/bundesliga/spieltage/", timeout=15).text
    except Exception as e:
        log.warning(f"LigaInsider nicht erreichbar: {e}")
        return []
    teams = sorted(set(re.findall(r'href="/(?!bundesliga)([a-z0-9-]+)/(\d+)/verein/news/"', start)))
    jetzt = datetime.datetime.now()
    eintraege, gesehen = [], set()
    for slug, tid in teams:
        try:
            h = s.get(f"https://www.ligainsider.de/{slug}/{tid}/verein/news/", timeout=15).text
        except Exception:
            continue
        for m in re.finditer(r'<h3>(.*?)</h3>', h, re.S):
            titel = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).replace("\xad", "").strip()
            link = re.search(r'href="(/[^"]+-\d+/)"[^>]*>\s*$', h[max(0, m.start() - 300):m.start()])
            zeit = re.search(r'<small class="float-start">([^<]+)</small>', h[m.end():m.end() + 2500])
            if not (titel and link and zeit):
                continue
            url = "https://www.ligainsider.de" + link.group(1)
            if url in gesehen:
                continue
            gesehen.add(url)
            z = zeit.group(1).strip()
            if (mm := re.match(r"Vor (\d+) (Min|Std)", z)):
                dt = jetzt - datetime.timedelta(minutes=int(mm.group(1)) * (1 if mm.group(2) == "Min" else 60))
            elif z == "Gestern":
                dt = jetzt - datetime.timedelta(days=1)
            elif (mm := re.match(r"Vor (\d+) Tagen", z)):
                dt = jetzt - datetime.timedelta(days=int(mm.group(1)))
            elif (mm := re.match(r"(\d\d)\.(\d\d)\.(\d{4})", z)):
                dt = datetime.datetime(int(mm.group(3)), int(mm.group(2)), int(mm.group(1)))
            else:
                continue
            eintraege.append({"link": url, "title": titel, "summary": titel,
                              "published_parsed": dt.timetuple()})
        time.sleep(1)
    log.info(f"LigaInsider (Themenfinder): {len(eintraege)} Meldungen von {len(teams)} Vereinsseiten")
    return eintraege


def fetch_fulltext(url: str) -> tuple[str | None, str]:
    """Lädt Volltext via trafilatura. Gibt (text, reason) zurück — reason='ok' oder Fehlergrund."""
    import trafilatura
    import requests as _req
    MIN_WORDS = 250
    PAYWALL_MARKERS = ["paywall", "abo", "abonnenten", "premium",
                       "login erforderlich", "nur für abonnenten", "artikelende"]
    try:
        # Google News Redirect vorab dekodieren
        fetch_url = url
        if "news.google.com" in url:
            decoded = _decode_google_news_url(url)
            if decoded:
                fetch_url = decoded
                log.debug(f"Google News dekodiert: {decoded[:80]}")

        # Redirect folgen
        try:
            r = _req.get(fetch_url, allow_redirects=True, timeout=12,
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
        MIN_WORDS = 60
        if word_count < MIN_WORDS:
            # Kurze Transfermeldungen erlauben wenn Key-Indicators vorhanden
            _KEY = ["wechselt", "transfer", "verpflichtet", "verletzt",
                    "verlängert", "ablöse", "testspiel", "trainiert", "abgang", "zugang"]
            if word_count >= 40 and any(k in text.lower() for k in _KEY):
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
    klub_liste = " | ".join(KLUB_LOGO) + " | keiner"
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
4. Hauptklub: Der EINE Klub, um den es im Artikel zentral geht.
   Erlaubt ist ausschließlich einer dieser Werte:
   {klub_liste}
   Regeln dafür:
   - Der Klub, dessen Perspektive der Artikel einnimmt – nicht der Gegner.
     "Schalke gewinnt bei Union" → Schalke. "Bayern verpflichtet Brown von Frankfurt" → Bayern.
   - Wird ein Klub nur als Gegner, in einer Rangliste, Tabelle oder Aufzählung
     erwähnt, ist er NICHT der Hauptklub.
   - Geht es zentral um einen Klub außerhalb dieser Liste (z. B. Real Madrid,
     Nationalmannschaft, 2. Liga) oder um keinen Klub: "keiner".
5. Spielerstatus: Nur wenn der Quelltext ausdrücklich sagt, ob ein Bundesliga-Spieler
   am nächsten BUNDESLIGA-Spiel teilnehmen kann (Europapokal, DFB-Pokal und
   Länderspiele zählen nicht). Pro Spieler ein Eintrag:
   - "spieler": Nachname wie im Text, "klub": einer der Werte aus Punkt 4
   - "status": "faellt_aus" | "fraglich" | "spielt" | "startelf"
     ("spielt" = wieder fit/einsatzbereit, "startelf" = Startelfeinsatz angekündigt)
   - "grund": max. 8 Wörter, z. B. "Muskelfaserriss" oder "Rückkehr ins Mannschaftstraining"
   Keine Transfers, keine Gerüchte, keine Vermutungen. Sonst leere Liste.
6. Formation: Nur wenn der Quelltext die Grundordnung für das nächste Spiel des Hauptklubs
   nennt (z. B. "4-2-3-1", "Dreierkette" → "3-4-3" nur wenn die Zahlen genannt sind). Sonst "".

Antworte ausschließlich im JSON-Format (kein Markdown drumherum):
{{
  "titel": "...",
  "text": "Absatz 1.\\n\\nAbsatz 2.\\n\\nAbsatz 3.",
  "kategorie": "...",
  "hauptklub": "...",
  "spielerstatus": [{{"spieler": "...", "klub": "...", "status": "...", "grund": "..."}}],
  "formation": ""
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


# ─── og:image-Karten ──────────────────────────────────────────────────────────

def _og_wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = f"{cur} {w}".strip()
        if draw.textlength(probe, font=font) <= max_w:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def og_karte(datei_id: str, titel: str, kategorie: str, wappen_url: str):
    """1200x630-Karte für Social-Previews. Gibt die oeffentliche URL zurueck
    oder None, wenn die Karte nicht erzeugt werden konnte."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.warning("Pillow fehlt – keine og:image-Karten")
        return None

    try:
        OG_ORDNER.mkdir(parents=True, exist_ok=True)
        W, H = 1200, 630
        img = Image.new("RGB", (W, H), "#0d0d0d")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 10], fill="#e8c000")

        fett = str(FONT_ORDNER / "InterDisplay-ExtraBold.ttf")
        tile, tile_x = 220, 80
        text_x = tile_x + tile + 56
        text_w = W - text_x - 70
        badge_h, badge_gap = 46, 30

        label, badge_bg, badge_fg = badge_fuer_kategorie(kategorie)

        for size in (62, 56, 50, 45, 41):
            f_titel = ImageFont.truetype(fett, size)
            lines = _og_wrap(d, titel, f_titel, text_w)
            if len(lines) <= 4:
                break
        lines = lines[:4]
        lh = int(size * 1.16)

        block_h = badge_h + badge_gap + lh * len(lines)
        top = max(90, (H - 70 - block_h) // 2)

        ty = max(60, min(top + (block_h - tile) // 2, H - 150 - tile))
        d.rounded_rectangle([tile_x, ty, tile_x + tile, ty + tile], radius=20, fill="#17171a")

        logo_datei = None
        if wappen_url:
            logo_datei = Path(wappen_url.lstrip("./"))
        if logo_datei and logo_datei.exists():
            logo = Image.open(logo_datei).convert("RGBA")
            scale = min(150 / logo.width, 150 / logo.height)
            logo = logo.resize((max(1, round(logo.width * scale)),
                                max(1, round(logo.height * scale))), Image.LANCZOS)
            img.paste(logo, (tile_x + (tile - logo.width) // 2,
                             ty + (tile - logo.height) // 2), logo)

        f_badge = ImageFont.truetype(fett, 26)
        bw = d.textlength(label.upper(), font=f_badge)
        d.rounded_rectangle([text_x, top, text_x + bw + 34, top + badge_h], radius=6, fill=badge_bg)
        d.text((text_x + 17, top + 9), label.upper(), font=f_badge, fill=badge_fg)

        y = top + badge_h + badge_gap
        for ln in lines:
            d.text((text_x, y), ln, font=f_titel, fill="#ffffff")
            y += lh

        f_mark = ImageFont.truetype(fett, 32)
        x, my = 80, H - 68
        for teil, farbe in (("Liga", "#e8c000"), ("outsider", "#ffffff"), (".de", "#777777")):
            d.text((x, my), teil, font=f_mark, fill=farbe)
            x += d.textlength(teil, font=f_mark)

        img.save(OG_ORDNER / f"{datei_id}.jpg", "JPEG",
                 quality=82, optimize=True, progressive=True)
        return f"https://ligaoutsider.de/og/{datei_id}.jpg"
    except Exception as e:
        log.warning(f"og:image fuer {datei_id} fehlgeschlagen: {e}")
        return None


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
    og_image_url: str = None,
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
    meta_desc = ersten_absatz[:155].replace('"', '&quot;').replace('\n', ' ')
    titel_attr = titel.replace('"', '&quot;')
    # schema.org verlangt ISO 8601, sonst ignoriert Google das Datum
    _dm = re.match(r"(\d{2})\.(\d{2})\.(\d{4})[ T](\d{2}):(\d{2})", datum or "")
    datum_iso = (f"{_dm.group(3)}-{_dm.group(2)}-{_dm.group(1)}"
                 f"T{_dm.group(4)}:{_dm.group(5)}:00+02:00") if _dm else datum
    # JSON-LD-Werte muessen JSON-escaped sein, sonst zerlegen Anfuehrungszeichen den Block
    titel_json = json.dumps(titel, ensure_ascii=False)
    desc_json = json.dumps(ersten_absatz[:200], ensure_ascii=False)
    if og_image_url:
        og_image = og_image_url
        # Masse nur angeben, wenn es wirklich die 1200x630-Karte ist
        og_masse = ('  <meta property="og:image:width" content="1200"/>\n'
                    '  <meta property="og:image:height" content="630"/>\n')
        twitter_card = "summary_large_image"
    elif wappen_url and not wappen_url.startswith('http'):
        og_image = f"https://ligaoutsider.de/{wappen_url.lstrip('./')}"
        og_masse = ""
        twitter_card = "summary"
    else:
        og_image = wappen_url or "https://ligaoutsider.de/logos/bundesliga.png"
        og_masse = ""
        twitter_card = "summary"

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{titel} – Ligaoutsider.de</title>
  <link rel="canonical" href="{artikel_url}"/>
  <meta name="description" content="{meta_desc}"/>
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="{titel_attr}"/>
  <meta property="og:description" content="{meta_desc}"/>
  <meta property="og:url" content="{artikel_url}"/>
  <meta property="og:image" content="{og_image}"/>
{og_masse}  <meta property="og:image:alt" content="{titel_attr}"/>
  <meta property="og:site_name" content="Ligaoutsider.de"/>
  <meta property="og:locale" content="de_DE"/>
  <meta name="twitter:card" content="{twitter_card}"/>
  <meta name="twitter:title" content="{titel_attr}"/>
  <meta name="twitter:description" content="{meta_desc}"/>
  <meta name="twitter:image" content="{og_image}"/>
  <link rel="stylesheet" href="../style.css"/>
  <link rel="stylesheet" href="../artikel.css"/>
  <link rel="icon" href="../favicon.png" type="image/png"/>
  <script>if(localStorage.getItem('theme')==='light')document.documentElement.classList.add('light');</script>
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
    "headline": {titel_json},
    "datePublished": "{datum_iso}",
    "dateModified": "{datum_iso}",
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
    "description": {desc_json},
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
            <a href="../nachrichten.html" id="nachrichten-icon" class="post-icon" title="Nachrichten" aria-label="Nachrichten">✉️<span class="post-zahl" id="nachrichten-zahl" hidden></span></a>
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
      <a href="../comunio.html" class="section-nav-link">Comunio-Stats</a>
      <a href="../aufstellung.html" class="section-nav-link">Aufstellungen</a>
      <a href="../elf.html" class="section-nav-link">Meine Elf</a>
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
        <a href="{quelle_url}" target="_blank" rel="noopener noreferrer">Quelle</a>
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

    # Vollständiger Text: mit nur 300 Zeichen hielt die Prüfung fast jeden Artikel
    # für "mitten im Satz abgebrochen" und lehnte zwei Drittel ab.
    liste = ""
    for i, k in enumerate(kandidaten):
        text_voll = k["ergebnis"]["text"][:2500].replace("\n", " ")
        liste += f"\n[{i}] Titel: {k['ergebnis']['titel']}\n    Text: {text_voll}\n"

    antwort = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200 + 80 * len(kandidaten),
        messages=[{
            "role": "user",
            "content": (
                f"Du bist leitender QS-Redakteur von ligaoutsider.de.\n"
                f"Reviewe {len(kandidaten)} Kandidaten. Die Texte sind vollständig abgedruckt. Für JEDEN prüfe:\n"
                f"1. Faktentreue: Kein Lückenfüller, keine Floskeln wie 'Details nicht bekannt', kein Verweis auf eine Bezahlschranke\n"
                f"2. Einzigartigkeit: Kein Duplikat eines anderen Kandidaten (gleicher Spieler + Situation)\n"
                f"3. Qualität: Substanz, lesbar, nicht leer/generisch\n\n"
                f"Kurze Meldungen sind ausdrücklich erwünscht, wenn sie eine konkrete Information enthalten "
                f"(Ausfall, Rückkehr ins Training, Startelf-Chance, Aussage eines Trainers). Kürze allein ist KEIN Ablehnungsgrund.\n\n"
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
    # Zähler für erneute Abrufversuche bei vorübergehenden Fehlern
    _versuche_datei = Path("data/abruf_versuche.json")
    try:
        _abruf_versuche = json.loads(_versuche_datei.read_text(encoding="utf-8"))
    except Exception:
        _abruf_versuche = {}
    log.info(f"URL-Cache geladen: {url_cache.get_seen_count()} bekannte URLs (letzte 30 Tage)")

    _SKIP_KEYWORDS = (
        "nagelsmann", "nationalmannschaft", "dfb-team", "em 2026", "wm 2026",
        "nations league", "länderspiel", "u21-em", "olympia",
        "frauen", "frauenfußball", "frauenbundesliga", "-frauen",
        "2. bundesliga", "2. liga", "zweite bundesliga", "zweitliga",
        # Rueckblicke: kicker spielt Archivmaterial in die Team-Feeds.
        # Bewusst eng: "retro" oder "legendär" allein wirft auch aktuelle News
        # raus, etwa das Retro-Trikot, das Frankfurts Vereinswebsite lahmlegte.
        "heute vor", "vor x jahren", "rückblick auf die saison",
        "in den 70ern", "in den 80ern", "in den 90ern", "jahrestag",
    )

    log.info(f"=== Ligaoutsider Generator startet – max. {MAX_ARTIKEL_PRO_LAUF} Artikel ===")

    # Eingereichte URLs aus Supabase laden
    _submitted_urls = []
    try:
        import urllib.request as _ur2, json as _json2
        _supa_url = "https://rsodjlglzwlscamdlwev.supabase.co/rest/v1/submitted_urls?status=eq.pending&select=id,url"
        _supa_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if _supa_key:
            _req2 = _ur2.Request(_supa_url, headers={
                "apikey": _supa_key, "Authorization": f"Bearer {_supa_key}"
            })
            with _ur2.urlopen(_req2, timeout=10) as _r2:
                _rows = _json2.loads(_r2.read())
            _submitted_urls = [r["url"] for r in _rows if r.get("url")]
            _submitted_ids  = [r["id"]  for r in _rows if r.get("id")]
            if _submitted_urls:
                log.info(f"📥 {len(_submitted_urls)} eingereichte URLs aus Supabase")
                # Als 'processed' markieren
                for _sid in _submitted_ids:
                    try:
                        _upd = _ur2.Request(
                            f"https://rsodjlglzwlscamdlwev.supabase.co/rest/v1/submitted_urls?id=eq.{_sid}",
                            data=b'{"status":"processed"}',
                            headers={"apikey": _supa_key, "Authorization": f"Bearer {_supa_key}",
                                     "Content-Type": "application/json", "Prefer": "return=minimal"},
                            method="PATCH"
                        )
                        _ur2.urlopen(_upd, timeout=5)
                    except Exception:
                        pass
    except Exception as _e2:
        log.warning(f"Supabase submitted_urls Fehler: {_e2}")

    _all_feeds = RSS_FEEDS + _submitted_urls
    # Zeitbudget: GitHub bricht den Lauf nach 20 Minuten ab. Was bis dahin nicht
    # verarbeitet ist, bleibt ungesehen und kommt im nächsten Lauf dran.
    _start = time.time()
    ZEITBUDGET_SEK = 13 * 60

    for feed_url in _all_feeds:
        # Limit zählt geschriebene Kandidaten – veröffentlicht wird erst nach der QA,
        # sonst schreibt der Lauf bis zum Zeitbudget immer weiter
        if len(kandidaten) >= MAX_ARTIKEL_PRO_LAUF:
            break
        if time.time() - _start > ZEITBUDGET_SEK:
            log.warning("Zeitbudget erreicht – restliche Feeds im nächsten Lauf")
            break

        log.info(f"Feed: {feed_url}")
        try:
            if feed_url == "ligainsider:themen":
                from types import SimpleNamespace
                feed = SimpleNamespace(entries=_ligainsider_eintraege(), feed={"title": "LigaInsider"})
            else:
                feed = feedparser.parse(feed_url)
        except Exception as e:
            log.error(f"Feed-Parse-Fehler: {e}")
            continue

        ist_google_news = "news.google.com" in feed_url
        feed_quelle = feed.feed.get("title", feed_url)

        for eintrag in feed.entries:
            if len(kandidaten) >= MAX_ARTIKEL_PRO_LAUF or time.time() - _start > ZEITBUDGET_SEK:
                break

            url    = eintrag.get("link", "")
            titel  = eintrag.get("title", "").strip()
            beschr = eintrag.get("summary", eintrag.get("description", ""))

            if not url or not titel:
                continue

            # URL-Cache: bereits gesehene Einträge sofort überspringen
            if url_cache.is_seen(url):
                continue

            # Video- und Galerieseiten haben keinen Artikeltext. Was daraus
            # entsteht, ist duenn und oft ein historischer Rueckblick - so kam
            # ein Bericht ueber die Champions League 2009/10 als aktuelle News
            # auf die Seite. Bei kicker ist knapp ein Drittel des Team-Feeds Video.
            if re.search(r'/(video|videos|galerie|bildergalerie|podcast|audio)([/\-]|$|#|\?)', url.lower()):
                log.info(f"S1 Medienseite ohne Artikeltext: {titel[:60]}")
                _log_skip(artikel_id(url), titel, "stage1", "medienseite")
                url_cache.mark_seen(url)
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

            # LigaInsider dient nur zum Finden von Themen. Verarbeitet und als Quelle
            # genannt wird ausschließlich der dort verlinkte Originalartikel.
            # Ohne echten Link (z. B. nur "Pressekonferenz") wird die Meldung übersprungen.
            if "ligainsider.de" in url:
                url_cache.mark_seen(url)
                try:
                    import urllib.request as _ureq
                    from urllib.parse import urlparse as _up
                    _rq = _ureq.Request(url, headers={"User-Agent": _GN_UA})
                    _html = _ureq.urlopen(_rq, timeout=8).read().decode("utf-8", errors="ignore")
                    _m = re.search(r'<strong>Quelle:</strong>\s*<a[^>]+href="(https?://[^"]+)"', _html)
                    _ziel = _m.group(1) if _m else ""
                    _host = _up(_ziel).netloc.lower() if _ziel else ""
                    if not (_ziel and "." in _host and "ligainsider" not in _host) or any(
                            x in _host for x in ("instagram.", "x.com", "twitter.", "facebook.", "tiktok.", "youtube.")):
                        continue
                    url = _ziel
                    quelle_name = _up(url).netloc.replace("www.", "")
                    if url_cache.is_seen(url):
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

            # Reine Unterhaus-Meldung: spart Volltext-Abruf und Haiku-Call
            if nur_fremdklub(titel):
                log.info(f"S2 kein BL-Klub im Titel: {titel[:60]}")
                _log_skip(aid, titel, "stage2", "nur_fremdklub")
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                stats["s2_pre_filter"] += 1
                continue

            # ── Stage 3: Keyword Pre-Filter (kein Haiku-Call) ────────────────
            _ist_kicker_team = "rss.kicker.de/news/" in feed_url
            if not _ist_kicker_team and not keyword_pre_filter(titel, beschr):
                log.info(f"S3 keyword miss: {titel[:60]}")
                _log_skip(aid, titel, "stage3", "keyword_pre_filter")
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
                stats["s5_fulltext_fail"] += 1
                # Dauerhafte Fehler: .skip setzen (paywall, google-Redirect, Exception)
                _PERMANENT_SKIP = {"likely_paywall", "google_redirect_unresolved", "low_unique_content_ratio"}
                if reason in _PERMANENT_SKIP or reason.startswith("exception_"):
                    _log_skip(aid, titel, "stage5", f"fulltext_failed_{reason}")
                    (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                    continue
                # Temporärer Fehler (trafilatura_returned_empty, too_short, fetch_failed):
                # Fallback auf RSS-Beschreibung wenn ausreichend lang
                beschr_clean = re.sub(r'<[^>]+>', ' ', beschr).strip()
                if len(beschr_clean.split()) >= 30:
                    volltext = beschr_clean
                    log.info(f"S5 fulltext fallback auf RSS-Beschreibung ({len(beschr_clean.split())} Wörter): {titel[:50]}")
                else:
                    _log_skip(aid, titel, "stage5", f"fulltext_failed_{reason}_rss_too_short")
                    # Seite war evtl. nur kurz nicht erreichbar: bis zu drei Läufe erneut versuchen
                    versuche = _abruf_versuche.get(aid, 0) + 1
                    _abruf_versuche[aid] = versuche
                    if versuche < 3:
                        url_cache.forget(url)
                    continue

            # ── Stage 5.5: Relevanz-Check mit echtem Volltext (Haiku) ────────
            if not _ist_kicker_team and not ist_relevant(titel, volltext):
                log.info(f"S5.5 not relevant (fulltext): {titel[:60]}")
                _log_skip(aid, titel, "stage5.5", "not_relevant_fulltext")
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                stats["s3_relevance"] += 1
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
            # ── Stage 6.5: gleiche Nachricht schon berichtet? (vor dem teuren Schreiben) ──
            _grenze = datetime.datetime.now() - datetime.timedelta(days=4)
            _vorhanden = [e["titel"] for e in bestehende
                          if datetime.datetime.strptime(e["datum"], "%d.%m.%Y %H:%M") >= _grenze]
            _vorhanden += [k["ergebnis"]["titel"] for k in kandidaten]
            _kern = (fp or {}).get("one_sentence_summary") or re.sub(r"\s+", " ", volltext[:400])
            _treffer = schon_berichtet(titel, _kern, _vorhanden)
            if _treffer:
                log.info(f"S6.5 schon berichtet ({_treffer[:50]}): {titel[:50]}")
                _log_skip(aid, titel, "stage6.5", "schon_berichtet")
                (ARTIKEL_ORDNER / f"{aid}.skip").touch()
                stats["s6_dedup_refined"] += 1
                continue

            log.info(f"S7 generate: {titel[:60]}")
            try:
                ergebnis = artikel_generieren(titel, volltext, quelle_name, url)
            except Exception as e:
                log.warning(f"S7 generation error: {e}")
                continue

            # Sonnet hat den Volltext gelesen und nennt den Hauptklub. Sagt es
            # "keiner", geht es zentral um einen Klub ausserhalb der Liga.
            hauptklub = str(ergebnis.get("hauptklub", "")).strip()
            if hauptklub.lower() in ("keiner", "keine", "none", ""):
                _log_skip(aid, titel, "S7.5", "kein_bl_hauptklub")
                stats["s7_5_kein_hauptklub"] = stats.get("s7_5_kein_hauptklub", 0) + 1
                log.info(f"S7.5 kein BL-Hauptklub: {ergebnis['titel'][:60]}")
                continue

            datum      = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            vereine    = vereine_im_text(ergebnis["titel"], ergebnis["text"])
            if hauptklub in KLUB_LOGO:
                wappen_url = KLUB_LOGO[hauptklub]
                vereine = sorted(set(vereine) | {KLUB_FILTERNAME.get(hauptklub, hauptklub)})
            else:
                log.warning(f"S7.5 unbekannter Hauptklub {hauptklub!r} – Fallback auf Scoring")
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

    # ── Stage 9.5: Final Pre-Publish Check ────────────────────────────────────
    news_archive = lade_news_archive()
    from rapidfuzz import fuzz as _fuzz2

    # Archiv-Summaries + Titel für Content-Vergleich (letzte 7 Tage)
    cutoff_95 = datetime.datetime.now() - datetime.timedelta(days=7)
    archive_recent = [
        e for e in news_archive
        if _ist_innerhalb_tage(e.get("published_at", ""), days=7)
    ]
    archive_summaries = [(e.get("summary", ""), e.get("title", "")) for e in archive_recent]

    final_approved = []
    for k in approved:
        fp = k.get("fingerprint") or {}
        titel_k = k["ergebnis"]["titel"]
        new_summary = fp.get("summary") or fp.get("one_sentence_summary", "")

        # 1) Summary-Vergleich gegen news_archive (letzten 7 Tage) — Inhalt statt Titel
        dup = False
        if new_summary:
            for arch_summary, arch_title in archive_summaries:
                if not arch_summary:
                    continue
                sim = _fuzz2.token_set_ratio(new_summary.lower(), arch_summary.lower())
                if sim >= 82:
                    log.info(f"S9.5 summary-dup (sim={sim}, '{arch_title[:40]}'): {titel_k[:50]}")
                    _log_skip(k["aid"], titel_k, "s9.5", f"summary_duplicate_sim{sim}")
                    dup = True
                    break

        # 2) Titel-Fallback wenn kein Summary vorhanden
        if not dup and not new_summary:
            all_pub_titles = (
                [s.get("generated_title") or s.get("title", "") for s in published_stories[-200:]]
                + [e.get("titel", "") for e in bestehende]
            )
            for pt in all_pub_titles:
                if pt and _fuzz2.ratio(titel_k.lower(), pt.lower()) >= 88:
                    log.info(f"S9.5 title-dup ({pt[:40]}): {titel_k[:50]}")
                    _log_skip(k["aid"], titel_k, "s9.5", "title_duplicate_fallback")
                    dup = True
                    break

        if dup:
            stats["s8_qa_rejected"] = stats.get("s8_qa_rejected", 0) + 1
            continue

        # 3) event_stage Check (gleiche Stage = echtes Dup, andere Stage = neue Entwicklung)
        if final_pre_publish_check(titel_k, fp, news_archive):
            _log_skip(k["aid"], titel_k, "s9.5", "final_pre_publish_duplicate")
            stats["s8_qa_rejected"] = stats.get("s8_qa_rejected", 0) + 1
        else:
            final_approved.append(k)
    log.info(f"S9.5 FinalCheck: {len(final_approved)}/{len(approved)} durch")
    approved = final_approved

    # ── Stage 9/10: Publish & Persist ────────────────────────────────────────
    for k in approved:
        ergebnis = k["ergebnis"]
        aid = k["aid"]
        _wu = k["wappen_url"]
        _artikel_wu = ("../" + _wu) if _wu and _wu.startswith("logos/") else _wu
        _og_url = og_karte(aid, ergebnis["titel"], ergebnis["kategorie"], _wu)
        html = artikel_html(
            datei_id    = aid,
            titel       = ergebnis["titel"],
            text        = ergebnis["text"],
            kategorie   = ergebnis["kategorie"],
            quelle_name = k["quelle_name"],
            quelle_url  = k["url"],
            datum       = k["datum"],
            wappen_url  = _artikel_wu,
            vereine     = k["vereine"],
            og_image_url = _og_url,
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
            "anriss":     " ".join(ergebnis["text"].split()[:30]),
            "spielerstatus": [x for x in (ergebnis.get("spielerstatus") or [])
                              if isinstance(x, dict) and x.get("spieler") and x.get("status")],
            "formation":  (ergebnis.get("formation") or "").strip(),
            "hauptklub":  ergebnis.get("hauptklub", ""),
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

        # news_archive.json Eintrag
        fp = k.get("fingerprint") or {}
        archive_entry = {
            "id":           aid,
            "title":        ergebnis["titel"],
            "published_at": datetime.datetime.now().isoformat(),
            "main_club":    fp.get("main_club", ""),
            "event_stage":  fp.get("event_stage", "sonstiges"),
            "summary":      fp.get("summary") or fp.get("one_sentence_summary", ""),
            "main_players": fp.get("main_players", []),
            "source_url":   k["url"],
        }
        news_archive.append(archive_entry)
        speichere_news_archive(news_archive)

        neu_generiert += 1
        stats["published"] += 1
        log.info(f"Veröffentlicht: {ergebnis['titel'][:60]}")

    sitemap_generieren(bestehende)
    rss_generieren(bestehende)

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
    # nur Zähler von URLs behalten, die noch im Cache-Zeitraum liegen
    _versuche_datei.write_text(json.dumps(dict(list(_abruf_versuche.items())[-2000:])), encoding="utf-8")
    log.info(f"URL-Cache gespeichert: {url_cache.get_seen_count()} URLs")

    log.info(f"=== Fertig. {neu_generiert} neue Artikel. feed.json: {len(bestehende)} ===")
    log.info(f"Stats: {json.dumps(stats)}")


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
        (f"{base}/comunio.html", "0.6", "weekly"),
        (f"{base}/aufstellung.html", "0.7", "daily"),
        (f"{base}/elf.html", "0.6", "weekly"),
        (f"{base}/forum.html", "0.6", "weekly"),
    ]
    for a in artikel_liste:
        urls.append((f"{base}/{a['pfad']}", "0.9", "monthly"))
    try:
        _db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
        urls.append((f"{base}/spieler/index.html", "0.7", "weekly"))
        for _slug in spieler_slugs(_db).values():
            urls.append((f"{base}/spieler/{_slug}.html", "0.7", "weekly"))
    except Exception:
        pass

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
    try:
        import urllib.request as _ur
        _ur.urlopen("https://www.google.com/ping?sitemap=https://ligaoutsider.de/sitemap.xml", timeout=5)
        print("✅ Google Sitemap-Ping gesendet")
    except Exception as _e:
        print(f"⚠️ Google Sitemap-Ping fehlgeschlagen: {_e}")




def rss_generieren(artikel_liste: list):
    from email.utils import formatdate
    import time

    base = "https://ligaoutsider.de"
    items = []
    for a in artikel_liste[:50]:  # Max 50 Einträge im Feed
        titel = a.get("titel", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        link = f"{base}/{a['pfad']}"
        desc = a.get("kategorie", "").replace("&", "&amp;")
        badge = a.get("badge", "")
        if badge:
            desc = f"[{badge}] {desc}"
        # Datum parsen für RFC-2822
        try:
            from datetime import datetime as _dt
            dt = _dt.strptime(a["datum"], "%d.%m.%Y %H:%M")
            pub_date = formatdate(timeval=time.mktime(dt.timetuple()), localtime=True)
        except Exception:
            pub_date = formatdate()
        vereine = a.get("vereine", [])
        verein_str = ", ".join(vereine) if isinstance(vereine, list) else str(vereine)
        items.append(f"""  <item>
    <title>{titel}</title>
    <link>{link}</link>
    <guid isPermaLink="true">{link}</guid>
    <description>{desc}</description>
    <category>{verein_str}</category>
    <pubDate>{pub_date}</pubDate>
  </item>""")

    rss = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\">
  <channel>
    <title>Ligaoutsider – Bundesliga News</title>
    <link>{base}/</link>
    <description>Aktuelle Bundesliga-News, Transfers und Gerüchte</description>
    <language>de-de</language>
    <atom:link href="{base}/rss.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""
    Path("rss.xml").write_text(rss, encoding="utf-8")
    print(f"✅ rss.xml generiert ({len(items)} Einträge)")

COMUNIO_BASE = "https://stats.comunio.de"
COMUNIO_KLUB = [  # Teilstring im Comstats-Klubnamen -> Logo
    ("Bayern", "bayern"), ("Dortmund", "dortmund"), ("Leipzig", "leipzig"),
    ("Leverkusen", "leverkusen"), ("Frankfurt", "frankfurt"), ("Stuttgart", "stuttgart"),
    ("gladbach", "gladbach"), ("Freiburg", "freiburg"), ("Union", "union"),
    ("Mainz", "mainz"), ("Augsburg", "augsburg"), ("Werder", "werder"),
    ("Hoffenheim", "hoffenheim"), ("Hamburg", "hsv"), ("Köln", "koeln"),
    ("Schalke", "schalke"), ("Paderborn", "paderborn"), ("Elversberg", "elversberg"),
    ("Munich", "bayern"), ("Cologne", "koeln"), ("Koln", "koeln"), ("Bremen", "werder"),
]


def _comunio_logo(klub):
    for teil, datei in COMUNIO_KLUB:
        if klub and teil.lower() in klub.lower():
            return f"logos/{datei}.png"
    return ""


def _comunio_tabellen(pfad, session):
    """Alle Spielertabellen einer Comstats-Seite als Zeilen-Dicts."""
    import html as _html
    r = session.get(COMUNIO_BASE + pfad, timeout=20)
    r.raise_for_status()
    tabellen = []
    bloecke = re.findall(r"<table class='(?:playersTable|rangliste)[^']*'>(.*?)</table>", r.text, re.S)
    # Kaderseiten haben keine eigene Tabellenklasse → ganze Seite als eine Tabelle lesen
    for tb in bloecke or [r.text]:
        zeilen = []
        for tr in re.findall(r"<tr>(.*?)</tr>", tb, re.S):
            name = re.search(r"<a class='playerName[^>]*>(.*?)</a>", tr)
            if not name:
                continue
            nach_name = tr[name.end():]
            werte = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", td))).replace(" ", "").strip()
                     for td in re.findall(r"<td[^>]*>(.*?)</td>", nach_name, re.S)]
            pos = re.search(r"class='vectoricon pos[^']*' alt='([^']+)'", tr)
            zeilen.append({
                "name": _html.unescape(name.group(1)),
                "klubs": [_html.unescape(k) for k in re.findall(r'title="([^"]+)" class=\'clubicon', tr)],
                "pos": pos.group(1) if pos else "",
                "werte": [w for w in werte if w],
            })
        tabellen.append(zeilen)
    return tabellen


def _zahl(txt):
    txt = (txt or "").replace(".", "").replace(",", ".").replace("+", "").replace("%", "").replace(" ", "")
    try:
        return float(txt)
    except ValueError:
        return 0.0


def comunio_fetch():
    """Comunio-Statistiken von Comstats (stats.comunio.de) holen — Quelle wird auf der Seite genannt."""
    import requests as _req
    session = _req.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Ligaoutsider.de)"})

    def spieler(z, **extra):
        klub = z["klubs"][0] if z["klubs"] else ""
        return {"name": z["name"], "klub": klub, "logo": _comunio_logo(klub), "pos": z["pos"], **extra}

    # Spalten nach dem Namen: Klub(leer), Marktwert, Einsätze "3 (3)", Tore, Punkte, Punkte/Spiel
    def punkte_zeile(z):
        w = z["werte"]
        einsaetze = int(_zahl(w[1].split("(")[0])) if len(w) > 1 else 0
        return spieler(z, mw=int(_zahl(w[0])), spiele=einsaetze, tore=int(_zahl(w[2])),
                       pts=int(_zahl(w[3])), ap=round(_zahl(w[4]), 2))

    result = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat()}

    # Marktwert
    mw = _comunio_tabellen("/toplist/mv_ovr_25-Top25_Marktwerte", session)[0]
    result["teuerste"] = [spieler(z, mw=int(_zahl(z["werte"][0]))) for z in mw[:10]]

    # Punkte – Basis für Schnitt und Effizienz
    alle = [punkte_zeile(z) for z in _comunio_tabellen("/toplist/pts_ovr_100-Top100_Punkte_Spieler", session)[0]]
    result["punkte"] = alle[:10]
    max_spiele = max((p["spiele"] for p in alle), default=0)
    min_spiele = max(1, round(max_spiele * 0.75))
    stamm = [p for p in alle if p["spiele"] >= min_spiele]
    result["schnitt"] = sorted(stamm, key=lambda p: -p["ap"])[:10]
    for p in stamm:
        p["eff"] = round(p["pts"] / (p["mw"] / 1e6), 1) if p["mw"] else 0
    result["effizienz"] = sorted(stamm, key=lambda p: -p["eff"])[:10]
    result["torjaeger"] = sorted([p for p in alle if p["tore"] > 0], key=lambda p: (-p["tore"], -p["pts"]))[:10]

    # Beste je Position (Punkte pro Spiel, nur Stammkräfte)
    for key, pfad in [("torwart", "ppm_gk_25-Top25_Punkte_pro_Spiel_Torhueter"),
                      ("abwehr", "ppm_def_25-Top25_Punkte_pro_Spiel_Abwehr"),
                      ("mittelfeld", "ppm_mf_25-Top25_Punkte_pro_Spiel_Mittelfeld"),
                      ("sturm", "ppm_off_25-Top25_Punkte_pro_Spiel_Sturm")]:
        liste = [punkte_zeile(z) for z in _comunio_tabellen("/toplist/" + pfad, session)[0]]
        result[key] = [p for p in liste if p["spiele"] >= min_spiele][:8]
        time.sleep(1)

    # Marktwert-Gewinner/-Verlierer: Tabellen Tag+, Tag-, Woche+, Woche-, Monat+, Monat-
    pt = _comunio_tabellen("/toplist/pt-Gewinner_Verlierer", session)
    def trend(z):
        w = z["werte"]
        return spieler(z, mw=int(_zahl(w[0])), diff=int(_zahl(w[1])), proz=_zahl(w[2]))
    for key, idx in [("raketen", 0), ("crash", 1), ("woche", 2), ("wocheminus", 3)]:
        result[key] = [trend(z) for z in pt[idx][:10]] if len(pt) > idx else []

    # Nachfrage durch Manager: Tabelle 0 = trendend, 1 = aufsteigend
    tr = _comunio_tabellen("/trending", session)
    def gefragt(z):
        return spieler(z, pts=int(_zahl(z["werte"][0])), mw=int(_zahl(z["werte"][1])))
    result["trend"] = [gefragt(z) for z in tr[0][:10]] if tr else []
    result["aufsteigend"] = [gefragt(z) for z in tr[1][:10]] if len(tr) > 1 else []

    # Punkterekorde an einem Spieltag, aktuelle Saison: Punkte, Tore "3 (0)" (davon Elfmeter), Saison, Gegner
    rek = _comunio_tabellen("/toplist/mptsreccurseason_ovr_100-Top100_Punkterekorde_Spieler_Spieltag_Aktuelle_Saison", session)
    result["rekorde"] = [spieler(z, pts=int(_zahl(z["werte"][0])),
                                 tore=int(_zahl(z["werte"][1].split("(")[0])),
                                 gegner=z["klubs"][1] if len(z["klubs"]) > 1 else "")
                         for z in (rek[0][:10] if rek else [])]

    Path("comunio.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ comunio.json geschrieben ({len(alle)} Spieler, via Comstats)")


# ─── Spieler-Datenbank (Transfermarkt-Kader, abgeglichen mit Kickbase) ────────
TM_SAISON = 2026
TM_POS_GRUPPE = {
    "Torwart": "Torwart",
    "Innenverteidiger": "Abwehr", "Linker Verteidiger": "Abwehr", "Rechter Verteidiger": "Abwehr",
    "Defensives Mittelfeld": "Mittelfeld", "Zentrales Mittelfeld": "Mittelfeld",
    "Offensives Mittelfeld": "Mittelfeld", "Linkes Mittelfeld": "Mittelfeld", "Rechtes Mittelfeld": "Mittelfeld",
    "Linksaußen": "Sturm", "Rechtsaußen": "Sturm", "Hängende Spitze": "Sturm", "Mittelstürmer": "Sturm",
}


def _namens_schluessel(name):
    import unicodedata
    n = unicodedata.normalize("NFKD", (name or "").lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.replace("ø", "o").replace("æ", "ae").replace("ß", "ss").replace("ł", "l").replace("đ", "d")
    # Umschrift angleichen: "schwaebe" (URL) == "schwäbe" (nach NFKD "schwabe")
    n = n.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return re.sub(r"[^a-z ]", " ", n).split()


def _tm_kader(pfad, session):
    import html as _html
    r = session.get(f"https://www.transfermarkt.de{pfad}", timeout=25)
    r.raise_for_status()
    kader = []
    for zeile in re.findall(r'<tr class="(?:odd|even)">(.*?)</tr>\s*(?=<tr class="(?:odd|even)"|</tbody>)', r.text, re.S):
        link = re.search(r'<td class="hauptlink">\s*<a href="/([^"]+)/profil/spieler/(\d+)">\s*(.*?)\s*</a>', zeile, re.S)
        if not link:
            continue
        # Hinter dem Namen hängen Symbole mit title: Kapitän, Verletzung, Sperre
        symbole = [_html.unescape(t) for t in re.findall(r'<span title="([^"]+)"', link.group(3))]
        name = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<span.*", "", link.group(3), flags=re.S))).strip()
        pos = re.search(r"<tr>\s*<td>\s*([^<]+?)\s*</td>\s*</tr>\s*</table>", zeile, re.S)
        nr = re.search(r"<div class=rn_nummer>([^<]*)</div>", zeile)
        zellen = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", z))).strip()
                  for z in re.findall(r'<td class="zentriert">(.*?)</td>', zeile, re.S)]
        nation = re.findall(r'class="flaggenrahmen"[^>]*|title="([^"]+)" alt="[^"]+" class="flaggenrahmen"', zeile)
        mw = re.search(r'marktwertverlauf/spieler/\d+">([^<]+)</a>', zeile)
        geb = next((z for z in zellen if re.match(r"\d\d\.\d\d\.\d{4}", z)), "")
        kader.append({
            "name": name,
            "tm_id": int(link.group(2)),
            "kapitaen": "Mannschaftskapitän" in symbole,
            "tm_hinweise": [t for t in symbole if t != "Mannschaftskapitän"],
            "nr": (nr.group(1).strip() if nr else "").replace("-", "") or None,
            "position": _html.unescape(pos.group(1)).strip() if pos else "",
            "geboren": geb[:10],
            "nation": [n for n in nation if n],
            "fuss": next((z for z in zellen if z in ("links", "rechts", "beidfüßig")), ""),
            "vertrag_bis": zellen[-1] if zellen and re.match(r"\d\d\.\d\d\.\d{4}", zellen[-1]) else "",
            "tm_marktwert": _html.unescape(mw.group(1)).strip() if mw else "",
        })
    return kader


def spieler_db_fetch():
    """Alle Bundesliga-Kader von Transfermarkt, je Spieler mit Kickbase-Daten verknüpft → spieler_db.json."""
    import difflib
    import requests as _req
    tm = _req.Session()
    tm.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
    liga = tm.get(f"https://www.transfermarkt.de/1-bundesliga/startseite/wettbewerb/L1/saison_id/{TM_SAISON}", timeout=25).text
    vereine = sorted(set(re.findall(rf'href="/([^"/]+)/startseite/verein/(\d+)/saison_id/{TM_SAISON}"', liga)))
    if len(vereine) < 18:
        raise RuntimeError(f"Transfermarkt liefert nur {len(vereine)} Vereine")

    kb = _req.Session()
    kb.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.base-xi.de/players"})
    kb.get("https://www.base-xi.de/players", timeout=10)
    kb_spieler = kb.get("https://www.base-xi.de/api/players?comp=bl1&t=1", timeout=20).json()
    kb_nach_logo = {}
    for p in kb_spieler:
        kb_nach_logo.setdefault(_comunio_logo(p.get("teamName") or ""), []).append(p)

    teams = {}
    for slug, vid in vereine:
        kader = _tm_kader(f"/{slug}/kader/verein/{vid}/saison_id/{TM_SAISON}/plus/1", tm)
        time.sleep(2)
        # Vereinsname aus dem Slug ist ungenau → über Logo-Zuordnung auf den Kickbase-Namen
        logo = _comunio_logo(slug.replace("-", " ").replace("monchengladbach", "gladbach")
                             .replace("rasenballsport", "leipzig").replace("koln", "köln"))
        kb_team = kb_nach_logo.get(logo, [])
        team_name = kb_team[0]["teamName"] if kb_team else slug
        frei = list(kb_team)
        for s_ in kader:
            s_["gruppe"] = TM_POS_GRUPPE.get(s_["position"], "")
            ks = _namens_schluessel(s_["name"])
            treffer = None
            # 1. exakter Name, 2. gleicher Nachname + Rückennummer, 3. gleicher Nachname, 4. ähnlich
            for pruef in (
                lambda k: _namens_schluessel(k["name"]) == ks,
                lambda k: _namens_schluessel(k["name"])[-1:] == ks[-1:] and str(k.get("shirtNumber")) == str(s_["nr"]),
                lambda k: _namens_schluessel(k["name"])[-1:] == ks[-1:],
                # vertauschte/zusammengezogene Namen ("Min-jae Kim" / "Kim Minjae")
                lambda k: sorted("".join(_namens_schluessel(k["name"]))) == sorted("".join(ks)),
                # Namenszusätze ("Lukeba Castello Jr.", Doppelnamen)
                lambda k: len(set(_namens_schluessel(k["name"])) & set(ks)) >= 2,
            ):
                kandidaten = [k for k in frei if pruef(k)]
                if len(kandidaten) == 1:
                    treffer = kandidaten[0]
                    break
            if not treffer:
                namen = {" ".join(_namens_schluessel(k["name"])): k for k in frei}
                nah = difflib.get_close_matches(" ".join(ks), list(namen), n=1, cutoff=0.8)
                treffer = namen[nah[0]] if nah else None
            if treffer:
                frei.remove(treffer)
                s_["kickbase"] = {"id": treffer.get("id"), "name": treffer.get("name"),
                                  "position": treffer.get("position"), "nr": treffer.get("shirtNumber"),
                                  "mw": treffer.get("marketValue") or 0}
            else:
                s_["kickbase"] = None
        teams[team_name] = {
            "logo": logo, "tm_id": int(vid), "spieler": kader,
            "nur_kickbase": [{"id": k.get("id"), "name": k.get("name"), "position": k.get("position"),
                              "nr": k.get("shirtNumber")} for k in frei],
        }

    # Comunio: Marktwert und Position je Spieler von den Comstats-Kaderseiten
    import urllib.parse
    try:
        cs = _req.Session()
        cs.headers.update({"User-Agent": "Mozilla/5.0 (Ligaoutsider.de)"})
        start = cs.get(f"{COMUNIO_BASE}/squad/1-FC+Bayern+M%C3%BCnchen", timeout=20).text
        kader_links = sorted(set(re.findall(r'href="(/squad/\d+-[^"]+)"', start)))
        cs_treffer = 0
        for link in kader_links:
            logo = _comunio_logo(urllib.parse.unquote_plus(link.split("-", 1)[1]))
            team = next((t for t in teams.values() if t["logo"] == logo), None) if logo else None
            if not team:
                continue
            for tb in _comunio_tabellen(link, cs):
                for z in tb:
                    zahlen = [w for w in z["werte"] if re.fullmatch(r"\d{1,3}(\.\d{3})+", w)]
                    eintrag = _finde_spieler(z["name"], team["spieler"])
                    if eintrag is not None and zahlen:
                        eintrag["comunio"] = {"mw": int(zahlen[-1].replace(".", "")), "position": z["pos"]}
                        cs_treffer += 1
            time.sleep(1)
        print(f"  → Comunio-Marktwerte für {cs_treffer} Spieler")
    except Exception as ex:
        print(f"  ⚠️ Comunio-Kader nicht verfügbar: {ex}")

    Path("spieler_db.json").write_text(json.dumps({
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "saison": TM_SAISON, "teams": teams,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(t["spieler"]) for t in teams.values())
    ok = sum(1 for t in teams.values() for s_ in t["spieler"] if s_["kickbase"])
    print(f"✅ spieler_db.json geschrieben ({n} Spieler, {ok} mit Kickbase verknüpft)")


# ─── Fremde Aufstellungsprognosen (LigaInsider, RotoWire) ─────────────────────
QUELLEN_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def _ligainsider_prognosen(session):
    """Voraussichtliche Elf je Team: {logo: {"start": [...], "wackel": [...], "alt": [...]}} – Namen als Slug-Vollnamen."""
    uebersicht = session.get("https://www.ligainsider.de/bundesliga/spieltage/", timeout=20).text
    teams = sorted(set(re.findall(r'href="/bundesliga/team/([a-z0-9-]+)/(\d+)/saison-', uebersicht)))
    ergebnis = {}
    for slug, tid in teams:
        try:
            t = session.get(f"https://www.ligainsider.de/{slug}/{tid}/", timeout=20).text
            a = t.find('<div class="player_position_row')
            b = t.find('league_name_holder', a)
            if a < 0 or b < 0:
                continue
            block = t[a:b]
            start, wackel, alt = [], [], []
            for spalte in block.split('<div class="player_position_column')[1:]:
                namen = re.findall(r'<div class="player_name"><a href="/([a-z0-9-]+)_\d+/"', spalte)
                if not namen:
                    continue
                if "sub_child" in spalte and len(namen) > 1:
                    wackel.append(namen[0].replace("-", " "))
                    alt.extend(n.replace("-", " ") for n in namen[1:])
                else:
                    start.append(namen[0].replace("-", " "))
            stand = re.search(r"Letzte Aktualisierung:[^|]*\|\s*([\d.]+ [\d:]+)", t)
            if len(start) + len(wackel) >= 10:
                ergebnis[_comunio_logo(slug.replace("-", " ").replace("koeln", "köln").replace("moenchengladbach", "gladbach"))] = {
                    "start": start, "wackel": wackel, "alt": alt, "stand": stand.group(1) if stand else ""}
        except Exception as ex:
            print(f"  ⚠️ LigaInsider {slug}: {ex}")
        time.sleep(1.5)
    return ergebnis


def _rotowire_prognosen(session):
    """{logo: {"start": [...], "bestaetigt": bool}} von RotoWire (Vollnamen aus dem title-Attribut)."""
    import html as _html
    t = session.get("https://www.rotowire.com/soccer/lineups.php?league=BUND", timeout=25).text
    ergebnis = {}
    for spiel in t.split('class="lineup is-soccer"')[1:]:
        namen = [re.sub(r"\s+", " ", _html.unescape(n)).strip()
                 for n in re.findall(r'class="lineup__mteam is-(?:home|visit)">\s*([^<]+)', spiel)]
        listen = re.findall(r'<ul class="lineup__list is-(home|visit)">(.*?)</ul>', spiel, re.S)
        for (seite, inhalt), team in zip(listen, namen):
            vor_verletzt = re.split(r'lineup__title', inhalt)[0]
            spieler = [_html.unescape(n) for n in re.findall(r'<li class="lineup__player">.*?<a title="([^"]+)"', vor_verletzt, re.S)]
            if len(spieler) >= 10:
                ergebnis[_comunio_logo(team)] = {"start": spieler[:11], "bestaetigt": "is-confirmed" in vor_verletzt}
    return ergebnis


def _finde_spieler(name, kader):
    """Ordnet einen fremden Spielernamen einem Kaderspieler zu (oder None)."""
    ks = _namens_schluessel(name)
    if not ks:
        return None
    for pruef in (
        lambda k: _namens_schluessel(k["name"]) == ks,
        lambda k: sorted("".join(_namens_schluessel(k["name"]))) == sorted("".join(ks)),
        lambda k: len(set(_namens_schluessel(k["name"])) & set(ks)) >= 2,
        lambda k: _namens_schluessel(k["name"])[-1:] == ks[-1:],
    ):
        treffer = [k for k in kader if pruef(k)]
        if len(treffer) == 1:
            return treffer[0]
    return None



# ─── Spieler → Artikel (für die News-Liste im Spielerprofil) ──────────────────
def spieler_news_index(max_je_spieler=8):
    """spieler_news.json: je Transfermarkt-ID die neuesten Artikel, in denen der Spieler vorkommt.
    Gleiche Regeln wie die Verlinkung in spieler.js: voller Name immer, Nachname nur beim
    Verein des Artikels (akzentunabhängig, Groß-/Kleinschreibung zählt)."""
    import unicodedata
    import html as _html

    def falte(t):
        t = unicodedata.normalize("NFD", t)
        t = "".join(c for c in t if not unicodedata.combining(c))
        return t.replace("ø", "o").replace("Ø", "O").replace("ł", "l").replace("đ", "d")

    try:
        db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
        feed = json.loads(FEED_JSON.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"⚠️  spieler_news_index: {ex}")
        return

    spieler = []
    for team in db["teams"].values():
        for sp in team["spieler"]:
            teile = sp["name"].split()
            nach = " ".join(teile[1:]) if len(teile) > 1 else sp["name"]
            grenze = r"(?<![\w-]){}(?![\w-])"
            spieler.append({
                "id": sp["tm_id"], "logo": team["logo"],
                "voll": re.compile(grenze.format(re.escape(falte(sp["name"])))) if len(teile) > 1 else None,
                "nach": re.compile(grenze.format(re.escape(falte(nach)))) if len(nach) >= 4 else None,
                "nach_txt": nach,
            })
    # Nachnamen, die innerhalb eines Vereins mehrfach vorkommen, sind nicht eindeutig
    doppelt = {}
    for sp in spieler:
        doppelt[(sp["logo"], sp["nach_txt"])] = doppelt.get((sp["logo"], sp["nach_txt"]), 0) + 1

    index = {}
    for e in feed:  # neueste zuerst
        pfad = Path(e.get("pfad", ""))
        if not pfad.exists():
            continue
        roh = pfad.read_text(encoding="utf-8")
        body = re.search(r'<div class="artikel-text">(.*?)</div>', roh, re.S)
        text = falte(e.get("titel", "") + " " + _html.unescape(re.sub(r"<[^>]+>", " ", body.group(1) if body else "")))
        vereine = {_comunio_logo(KLUB_FILTERNAME.get(v, v)) for v in (e.get("vereine") or [])}
        if e.get("hauptklub"):
            vereine.add(_comunio_logo(KLUB_FILTERNAME.get(e["hauptklub"], e["hauptklub"])))
        vereine.discard("")
        for sp in spieler:
            treffer = bool(sp["voll"] and sp["voll"].search(text))
            if not treffer and sp["nach"] and sp["logo"] in vereine and doppelt[(sp["logo"], sp["nach_txt"])] == 1:
                treffer = bool(sp["nach"].search(text))
            if treffer:
                liste = index.setdefault(str(sp["id"]), [])
                if len(liste) < max_je_spieler:
                    liste.append({"titel": e["titel"], "datum": e["datum"], "pfad": e["pfad"]})

    Path("spieler_news.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ spieler_news.json geschrieben ({len(index)} Spieler mit News)")


# ─── Spielerseiten (eine statische Seite je Spieler, für Google) ─────────────
SPIELER_SEITEN_ORDNER = Path("spieler")


def spieler_slugs(db):
    """tm_id → URL-Slug ("harry-kane"); bei gleichen Namen wird die ID angehängt."""
    import unicodedata

    def basis(name):
        n = unicodedata.normalize("NFKD", name.replace("ø", "o").replace("Ø", "O").replace("ß", "ss")
                                  .replace("ł", "l").replace("æ", "ae").replace("đ", "d"))
        n = "".join(c for c in n if not unicodedata.combining(c)).lower()
        return re.sub(r"[^a-z0-9]+", "-", n).strip("-") or "spieler"

    alle = [sp for t in db["teams"].values() for sp in t["spieler"]]
    zaehler = {}
    for sp in alle:
        zaehler[basis(sp["name"])] = zaehler.get(basis(sp["name"]), 0) + 1
    return {sp["tm_id"]: basis(sp["name"]) + (f"-{sp['tm_id']}" if zaehler[basis(sp["name"])] > 1 else "")
            for sp in alle}


def _mio(v):
    return f"{v / 1e6:.1f}".replace(".", ",") + " Mio. €" if v else ""


def _seite(titel, beschreibung, url, inhalt, head_extra="", tiefe="../", kommentar_id=None):
    """Gemeinsamer Seitenrahmen (Kopf, Menü, Fuß) für generierte Seiten."""
    e = _html_esc
    kommentare = ""
    if kommentar_id:
        kommentare = f"""
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
    </section>"""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{e(titel)}</title>
  <link rel="canonical" href="{url}"/>
  <meta name="description" content="{e(beschreibung)}"/>
  <meta property="og:type" content="profile"/>
  <meta property="og:title" content="{e(titel)}"/>
  <meta property="og:description" content="{e(beschreibung)}"/>
  <meta property="og:url" content="{url}"/>
  <meta property="og:site_name" content="Ligaoutsider.de"/>
  <meta property="og:locale" content="de_DE"/>
  <link rel="stylesheet" href="{tiefe}style.css"/>
  <link rel="icon" href="{tiefe}favicon.png" type="image/png"/>
  <script>if(localStorage.getItem('theme')==='light')document.documentElement.classList.add('light');</script>
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-SP8DWFL2SE"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-SP8DWFL2SE');
  </script>
{head_extra}</head>
<body>

  <script src="https://identity.netlify.com/v1/netlify-identity-widget.js"></script>

  <header class="site-header">
    <div class="header-inner">
      <a href="{tiefe}index.html" class="logo">
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
            <a href="{tiefe}nachrichten.html" id="nachrichten-icon" class="post-icon" title="Nachrichten" aria-label="Nachrichten">✉️<span class="post-zahl" id="nachrichten-zahl" hidden></span></a>
            <span id="user-name" class="auth-username"></span>
            <a href="#" class="auth-btn" id="logout-btn">Abmelden</a>
          </span>
        </div>
      </div>
    </div>
  </header>

  <nav class="section-nav">
    <div class="section-nav-inner">
      <a href="{tiefe}index.html" class="section-nav-link">Aktuelle News</a>
      <a href="{tiefe}archiv.html" class="section-nav-link">Newsarchiv</a>
      <a href="{tiefe}kickbase.html" class="section-nav-link">Kickbase-Stats</a>
      <a href="{tiefe}comunio.html" class="section-nav-link">Comunio-Stats</a>
      <a href="{tiefe}aufstellung.html" class="section-nav-link">Aufstellungen</a>
      <a href="{tiefe}elf.html" class="section-nav-link">Meine Elf</a>
      <a href="{tiefe}forum.html" class="section-nav-link">💬 Forum</a>
    </div>
  </nav>

  <div class="sp-wrap">
{inhalt}
{kommentare}
  </div>

  <script>
    const SUPABASE_URL  = 'https://rsodjlglzwlscamdlwev.supabase.co';
    const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJzb2RqbGdsendsc2NhbWRsd2V2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEzNjk1MzIsImV4cCI6MjA5Njk0NTUzMn0.ETR6sL-b-ZmjuqWFmj3jgP2vzq70J0Yb4JgATOCekns';
{f"    const ARTIKEL_ID    = '{kommentar_id}';" if kommentar_id else ""}
  </script>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
  <script src="{tiefe}kommentare.js"></script>

  <footer class="site-footer">
    <div class="footer-inner">
      <p class="footer-copy">© Ligaoutsider.de, 2026</p>
      <nav class="footer-nav">
        <a href="{tiefe}impressum.html">Impressum</a>
        <a href="{tiefe}datenschutz.html">Datenschutzerklärung</a>
      </nav>
    </div>
  </footer>

</body>
</html>"""


def _html_esc(t):
    import html as _h
    return _h.escape(str(t if t is not None else ""), quote=True)


def spieler_seiten():
    """spieler/<slug>.html für alle Kaderspieler plus spieler/index.html als Übersicht."""
    e = _html_esc
    try:
        db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"⚠️  spieler_seiten: {ex}")
        return
    try:
        news = json.loads(Path("spieler_news.json").read_text(encoding="utf-8"))
    except Exception:
        news = {}
    slugs = spieler_slugs(db)
    SPIELER_SEITEN_ORDNER.mkdir(exist_ok=True)
    base = "https://ligaoutsider.de"
    geschrieben = 0
    heute = datetime.date.today()

    def alter(geb):
        m = re.match(r"(\d\d)\.(\d\d)\.(\d{4})", geb or "")
        if not m:
            return None
        g = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return heute.year - g.year - ((heute.month, heute.day) < (g.month, g.day))

    for team_name, team in db["teams"].items():
        for sp in team["spieler"]:
            slug = slugs[sp["tm_id"]]
            url = f"{base}/spieler/{slug}.html"
            kb, cm = sp.get("kickbase") or {}, sp.get("comunio") or {}
            a = alter(sp.get("geboren"))
            nation = " / ".join(sp.get("nation") or [])
            pos = sp.get("position") or sp.get("gruppe") or "Spieler"

            beschreibung = (f"{sp['name']} ({team_name}): {pos}"
                            + (f", {a} Jahre" if a else "") + (f", {nation}" if nation else "")
                            + (f". Kickbase-Marktwert {_mio(kb.get('mw'))}" if kb.get("mw") else "")
                            + (f", Comunio {_mio(cm.get('mw'))}" if cm.get("mw") else "")
                            + ". Aktuelle News, Verletzungen und Aufstellungschancen.")
            zeilen = [
                ("Verein", team_name), ("Position", pos), ("Rückennummer", sp.get("nr")),
                ("Geboren", sp.get("geboren") + (f" ({a} Jahre)" if a else "") if sp.get("geboren") else ""),
                ("Nationalität", nation), ("Starker Fuß", sp.get("fuss")),
                ("Vertrag bis", sp.get("vertrag_bis")), ("Marktwert (Transfermarkt)", sp.get("tm_marktwert")),
                ("Kickbase", " · ".join(x for x in (kb.get("position"), _mio(kb.get("mw"))) if x)),
                ("Comunio", " · ".join(x for x in (cm.get("position"), _mio(cm.get("mw"))) if x)),
            ]
            tabelle = "".join(f"<div><span>{e(k)}</span><span>{e(v)}</span></div>" for k, v in zeilen if v)
            hinweise = "".join(f"<div>{e(h)}</div>" for h in sp.get("tm_hinweise") or [])
            news_html = "".join(
                f'<a href="../{e(n["pfad"])}"><span>{e(n["titel"])}</span><small>{e(n["datum"].split(" ")[0])}</small></a>'
                for n in news.get(str(sp["tm_id"]), []))
            mitspieler = "".join(
                f'<a href="{slugs[m["tm_id"]]}.html">{e(m["name"])}</a>'
                for m in team["spieler"] if m["tm_id"] != sp["tm_id"])

            person = {
                "@context": "https://schema.org", "@type": "Person", "name": sp["name"], "url": url,
                "jobTitle": "Fußballspieler", "memberOf": {"@type": "SportsTeam", "name": team_name, "sport": "Fußball"},
            }
            m = re.match(r"(\d\d)\.(\d\d)\.(\d{4})", sp.get("geboren") or "")
            if m:
                person["birthDate"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            if nation:
                person["nationality"] = [{"@type": "Country", "name": n} for n in sp.get("nation")]
            head = f'  <script type="application/ld+json">{json.dumps(person, ensure_ascii=False)}</script>\n'

            inhalt = f"""    <a href="index.html" class="artikel-back">← Alle Spieler</a>
    <div class="sp-kopf">
      <img src="../{e(team['logo'])}" alt="{e(team_name)}">
      <div>
        <h1>{e(sp['name'])}{' <span title="Kapitän">(C)</span>' if sp.get('kapitaen') else ''}</h1>
        <p>{e(pos)} · {e(team_name)}</p>
      </div>
    </div>
    {f'<div class="sp-hinweis">{hinweise}</div>' if hinweise else ''}
    <div class="sp-tabelle">{tabelle}</div>
    <h2 class="sp-h2">Aktuelle News zu {e(sp['name'])}</h2>
    <div class="lo-sp-news sp-news">{news_html or '<p class="sp-leer">Noch keine Artikel.</p>'}</div>
    <p class="sp-links"><a href="../aufstellung.html?team={e(team_name)}">Voraussichtliche Elf fürs nächste Bundesliga-Spiel →</a>
      <a href="../elf.html">In „Meine Elf“ aufstellen →</a></p>
    <h2 class="sp-h2">Kader {e(team_name)}</h2>
    <div class="sp-mitspieler">{mitspieler}</div>"""

            html_neu = _seite(f"{sp['name']} – {team_name}: Profil, Marktwert, News | Ligaoutsider.de",
                              beschreibung[:300], url, inhalt, head, kommentar_id=f"spieler-{sp['tm_id']}")
            datei = SPIELER_SEITEN_ORDNER / f"{slug}.html"
            if not datei.exists() or datei.read_text(encoding="utf-8") != html_neu:
                datei.write_text(html_neu, encoding="utf-8")
                geschrieben += 1

    # Übersicht aller Spieler nach Verein (interne Verlinkung für Google)
    bloecke = "".join(
        f'<section class="sp-team"><h2><img src="../{e(t["logo"])}" alt="">{e(tn)}</h2><div class="sp-mitspieler">'
        + "".join(f'<a href="{slugs[x["tm_id"]]}.html">{e(x["name"])}<small>{e(x.get("position") or "")}</small></a>'
                  for x in t["spieler"]) + "</div></section>"
        for tn, t in sorted(db["teams"].items()))
    uebersicht = _seite("Alle Bundesliga-Spieler 2026/27 – Profile, Marktwerte, News | Ligaoutsider.de",
                        "Alle Spieler der 18 Bundesliga-Kader mit Position, Marktwert bei Kickbase und Comunio, "
                        "Verletzungen und aktuellen News.",
                        f"{base}/spieler/index.html",
                        f'    <h1 class="sp-titel">Alle Bundesliga-Spieler</h1>\n{bloecke}')
    (SPIELER_SEITEN_ORDNER / "index.html").write_text(uebersicht, encoding="utf-8")
    print(f"✅ Spielerseiten: {len(slugs)} Spieler, {geschrieben} geändert")

# ─── Aufstellungs-Check ───────────────────────────────────────────────────────
# Kickbase-Statuscodes: 0 fit, 2 angeschlagen; alles andere
# (1 verletzt, 8/16/32 Sperren, 256 nicht im Kader …) heißt Ausfall.
AMPEL_GELB = {2}  # 4 = Aufbautraining: noch nicht im Teamtraining, also Ausfall
STATUS_TEXT = {1: "verletzt", 2: "angeschlagen", 4: "im Aufbautraining"}
POS_REIHE = {"Torwart": "tw", "Abwehr": "abw", "Mittelfeld": "mf", "Sturm": "st"}


def _nachname(name):
    import unicodedata
    teil = (name or "").split()[-1] if (name or "").split() else ""
    return "".join(c for c in unicodedata.normalize("NFKD", teil.lower()) if not unicodedata.combining(c))


def _news_hinweise(tage=6):
    """Spielerstatus aus den Artikeln der letzten Tage, neuester Hinweis zuerst."""
    try:
        feed = json.loads(FEED_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    grenze = datetime.datetime.now() - datetime.timedelta(days=tage)
    hinweise, formationen = {}, {}
    for e in feed:  # feed ist neueste zuerst sortiert
        try:
            dt = datetime.datetime.strptime(e["datum"], "%d.%m.%Y %H:%M")
        except Exception:
            continue
        if dt < grenze:
            continue
        for h in e.get("spielerstatus") or []:
            logo = _comunio_logo(KLUB_FILTERNAME.get(h.get("klub"), h.get("klub")) or "")
            key = (logo, _nachname(h["spieler"]))
            hinweise.setdefault(key, {**h, "pfad": e["pfad"], "datum": e["datum"]})
        f = (e.get("formation") or "").strip()
        if re.fullmatch(r"\d(-\d){2,3}", f) and e.get("hauptklub"):
            logo = _comunio_logo(KLUB_FILTERNAME.get(e["hauptklub"], e["hauptklub"]))
            formationen.setdefault(logo, {"formation": f, "pfad": e["pfad"]})
    return hinweise, formationen


def _formation_aus_statistik(kader):
    """Durchschnittliche Startelf-Besetzung je Positionsgruppe, auf 10 Feldspieler gerundet."""
    spiele = max((p["spiele_team"] for p in kader), default=0)
    anteile = {}
    for pos in ("abw", "mf", "st"):
        jetzt = sum(p["starts"] for p in kader if p["reihe"] == pos) / spiele if spiele else 0
        vor = sum(p["starts_vor"] for p in kader if p["reihe"] == pos) / 34
        anteile[pos] = 0.7 * jetzt + 0.3 * vor if spiele else vor
    # Kickbase führt offensive Außenverteidiger als Abwehr und Flügelspieler als Sturm –
    # daher eine Fünferkette bzw. drei Stürmer erst bei klarer Mehrheit
    abw = anteile["abw"]
    st = anteile["st"]
    anz = {"abw": 3 if abw < 3.4 else (5 if abw >= 4.85 else 4),
           "st": 1 if st < 1.45 else (3 if st >= 2.6 else 2)}
    anz["mf"] = 10 - anz["abw"] - anz["st"]
    return anz


def aufstellung_fetch():
    """Voraussichtliche Startelf je Team aus Kickbase-Daten (BaseXI) plus News-Hinweisen."""
    import requests as _req
    session = _req.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.base-xi.de/players"})
    session.get("https://www.base-xi.de/players", timeout=10)
    daten = session.get("https://www.base-xi.de/api/players?comp=bl1&t=1", timeout=20).json()
    hinweise, formationen = _news_hinweise()

    fremd = {}
    qs = _req.Session()
    qs.headers.update({"User-Agent": QUELLEN_UA, "Accept-Language": "de-DE,de;q=0.9"})
    for quelle, abruf in (("ligainsider", _ligainsider_prognosen), ("rotowire", _rotowire_prognosen)):
        try:
            daten_q = abruf(qs)
            print(f"  → {quelle}: {len(daten_q)} Teams")
            for logo, d in daten_q.items():
                fremd.setdefault(logo, {})[quelle] = d
        except Exception as ex:
            print(f"  ⚠️ {quelle} nicht verfügbar: {ex}")

    # Spieler-Datenbank: echte Kader, genaue Positionen, Transfermarkt-Hinweise
    db = {}
    try:
        for t in json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))["teams"].values():
            for e in t["spieler"]:
                if e.get("kickbase"):
                    db[str(e["kickbase"]["id"])] = e
    except Exception as ex:
        print(f"⚠️  spieler_db.json nicht nutzbar: {ex}")

    teams = {}
    for p in daten:
        team = p.get("teamName") or ""
        if not team or p.get("position") not in POS_REIHE:
            continue
        if db and str(p.get("id")) not in db:
            continue  # nur Kickbase kennt ihn – kein Profikader
        teams.setdefault(team, []).append(p)

    spiele, ergebnis_teams = {}, {}
    for team, roh in teams.items():
        logo = _comunio_logo(team)
        spiele_team = max((p.get("matchesPlayed") or 0) for p in roh)
        kader = []
        for p in roh:
            status = p.get("status") or 0
            ampel = "gruen" if status == 0 else ("gelb" if status in AMPEL_GELB else "rot")
            roh_text = p.get("statusText") or ""
            text = roh_text.lower()
            naechster = ((p.get("match_data") or {}).get("next_abbr") or "").upper()
            # "verpasst" zählt nur, wenn damit ausdrücklich das nächste Spiel gemeint ist
            # ("verpasst KOE (H)" bei nächstem Gegner KOE). Alles andere ist veraltet
            # oder betrifft spätere Spiele – dann entscheidet der Statuscode.
            genannt = re.findall(r"verpasst\b[^,;.]*?\b([A-Z0-9]{2,4}) \((?:H|A)\)", roh_text)
            # "Rückkehr gegen B04 (H)": erst dann wieder dabei – beim nächsten Gegner fraglich, sonst Ausfall
            rueckkehr = re.findall(r"rückkehr\b[^,;.]*?\b([A-Z0-9]{2,4}) \((?:H|A)\)", roh_text, re.I)
            if naechster and naechster in genannt:
                ampel = "rot"
            elif rueckkehr and ampel != "gruen" or rueckkehr and status == 0 and text:
                ampel = "gelb" if naechster in [r.upper() for r in rueckkehr] else "rot"
            elif re.search(r"fällt\b.*\baus\b|ausfall|nächste woche|wochen|monate|saisonaus|kreuzband"
                           # noch nicht im Mannschaftstraining → spielt am Wochenende nicht
                           r"|individuell|laufprogramm|aufbautraining|reha\b|keine option"
                           r"|(nach|vor) der lsp|rückkehr ins (team|mannschafts)training|trainingseinstieg", text):
                ampel = "rot"
            elif status == 0 and text:
                # Kickbase lässt den Status oft auf 0, obwohl der Text eine Blessur meldet
                if re.search(r"fällt .*aus", text):
                    ampel = "rot"
                elif not re.search(r"soll morgen|wieder (voll )?im training|zurück im", text):
                    ampel = "gelb"
            eintrag = db.get(str(p.get("id"))) or {}
            anstoss = ((p.get("next_match") or {}).get("date_iso") or "")[:10]
            tm_grund = ""
            for h in eintrag.get("tm_hinweise", []):
                bis = re.search(r"(?:bis|am) (\d\d)\.(\d\d)\.(\d{4})", h)
                datum = f"{bis.group(3)}-{bis.group(2)}-{bis.group(1)}" if bis else ""
                if "sperre" in h.lower():
                    # nur Bundesliga- oder wettbewerbsübergreifende Sperren zählen
                    if re.search(r"bundesliga|wettbewerbsübergreifend", h, re.I) and (not datum or not anstoss or datum >= anstoss):
                        ampel, tm_grund = "rot", h.split(" – ")[0] + (f" bis {bis.group(1)}.{bis.group(2)}." if bis else "")
                elif "Rückkehr vsl." in h and datum and anstoss and datum > anstoss:
                    ampel, tm_grund = "rot", h
            grund = roh_text.replace("AchKrankes", "Achilles").strip()
            # Hinweise auf andere Spiele als das nächste sind für die Anzeige irreführend
            grund = re.sub(r"\s*[-,]?\s*verpasst\b[^,;.]*?\b([A-Z0-9]{2,4}) \((?:H|A)\)",
                           lambda m: m.group(0) if m.group(1) == naechster else "", grund).strip(" -,")
            grund = tm_grund or grund or STATUS_TEXT.get(status, "" if status == 0 else "fehlt laut Kickbase")
            news = hinweise.get((logo, _nachname(p.get("name"))))
            if news:
                grund = news.get("grund") or grund
                ampel = {"faellt_aus": "rot", "fraglich": "gelb"}.get(news["status"], "gruen")
            kader.append({
                "name": eintrag.get("name") or p.get("name", ""),
                "reihe": POS_REIHE.get(eintrag.get("gruppe")) or POS_REIHE[p["position"]],
                "pos": eintrag.get("position", ""),
                "nr": eintrag.get("nr") or p.get("shirtNumber"), "ampel": ampel, "grund": grund,
                "news": news["pfad"] if news else "", "angekuendigt": bool(news and news["status"] == "startelf"),
                "starts": p.get("starts") or 0, "spiele": p.get("matchesPlayed") or 0,
                "starts_vor": p.get("startsPrevSeason") or 0, "minuten": p.get("avgMinutes") or 0,
                "spiele_team": spiele_team, "mw": p.get("marketValue") or 0,
            })

        quellen_team = fremd.get(logo, {})
        zuordnung = {}
        for quelle, d in quellen_team.items():
            for art in ("start", "wackel", "alt"):
                for n in d.get(art, []):
                    k = _finde_spieler(n, kader)
                    if k is not None:
                        zuordnung.setdefault(id(k), {})[quelle] = art

        def wert(p):
            """Mittel aus LigaInsider, RotoWire und eigenem Modell."""
            if p["ampel"] == "rot":
                return 0.0
            anteile = [(modell(p), 0.25)]
            z = zuordnung.get(id(p), {})
            if "ligainsider" in quellen_team:
                anteile.append(({"start": 1.0, "wackel": 0.6, "alt": 0.35}.get(z.get("ligainsider"), 0.03), 0.4))
            if "rotowire" in quellen_team:
                anteile.append((1.0 if z.get("rotowire") == "start" else 0.03, 0.35))
            w = sum(a * g for a, g in anteile) / sum(g for _, g in anteile)
            if p["ampel"] == "gelb":
                w = min(w, 0.6)
            if p["angekuendigt"]:
                w = max(w, 0.9)
            return round(min(0.97, w), 3)

        def modell(p):
            """Startelf-Wahrscheinlichkeit 0..1: Startquote dieser Saison, mit der
            Vorsaison als Vorwissen geglättet (zählt wie zwei Spiele)."""
            if p["ampel"] == "rot":
                return 0.0
            if p["angekuendigt"]:
                return 0.95
            vor = min(1, p["starts_vor"] / 30) if p["starts_vor"] else min(0.5, p["mw"] / 4e7)
            # Wer in fast jedem seiner Einsätze begonnen hat, hat verpasste Spiele meist
            # wegen Verletzung/Sperre gefehlt – die zählen nicht gegen ihn.
            basis = spiele_team
            if p["spiele"] and p["starts"] >= 0.75 * p["spiele"]:
                basis = p["spiele"]
            if not p["spiele"] and spiele_team >= 2:
                # diese Saison noch keine Minute: Vorsaison zählt kaum
                w = min(0.15, (2 * vor) / (spiele_team + 2) * 0.5)
            else:
                w = (p["starts"] + 2 * vor) / (basis + 2)
            if p["ampel"] == "gelb":
                w *= 0.5
            return max(0.0, min(0.95, w))

        verfuegbar = sorted([p for p in kader if p["ampel"] != "rot"], key=wert, reverse=True)
        anz = _formation_aus_statistik(kader)
        news_form = formationen.get(logo)
        form_txt = f"{anz['abw']}-{anz['mf']}-{anz['st']}"
        if news_form:
            teile = [int(x) for x in news_form["formation"].split("-")]
            anz = {"abw": teile[0], "st": teile[-1], "mf": sum(teile[1:-1])}
            form_txt = news_form["formation"]

        # Elf: bester Torwart + zehn Feldspieler mit höchster Wahrscheinlichkeit,
        # dabei 3–5 Verteidiger (eine Elf ohne Abwehr wäre offensichtlich falsch)
        elf = {"tw": [p for p in verfuegbar if p["reihe"] == "tw"][:1], "abw": [], "mf": [], "st": []}
        feld = [p for p in verfuegbar if p["reihe"] != "tw"]
        abw_min = 4 if len([p for p in feld if p["reihe"] == "abw" and wert(p) >= 0.4]) >= 4 else 3
        gewaehlt = [p for p in feld if p["reihe"] == "abw"][:abw_min]
        for p in feld:
            if len(gewaehlt) >= 10:
                break
            if p in gewaehlt:
                continue
            if p["reihe"] == "abw" and sum(q["reihe"] == "abw" for q in gewaehlt) >= 5:
                continue
            gewaehlt.append(p)
        for p in gewaehlt:
            elf[p["reihe"]].append(p)
        in_elf = {id(p) for v in elf.values() for p in v}

        def sauber(p, sicher=None):
            q = {k: p[k] for k in ("name", "nr", "ampel", "grund", "news", "reihe", "pos")}
            q["prozent"] = round(wert(p) * 100)
            if not q["grund"] and p["ampel"] == "gruen":
                if not spiele_team:
                    q["grund"] = ""
                elif not p["spiele"]:
                    q["grund"] = "noch ohne Einsatz"
                else:
                    q["grund"] = f"{p['starts']} von {p['spiele']} Einsätzen in der Startelf · Ø {p['minuten']} min"
                    if p["spiele"] < spiele_team:
                        fehlt = spiele_team - p["spiele"]
                        q["grund"] += f" · {fehlt} Spiel{'e' if fehlt > 1 else ''} ohne Einsatz"
            if sicher is not None:
                q["sicher"] = sicher
            return q

        ergebnis_teams[team] = {
            "logo": logo, "formation": form_txt if news_form else "",
            "quellen": sorted(quellen_team),
            "formation_quelle": news_form["pfad"] if news_form else "",
            "elf": {k: [sauber(p) for p in sorted(v, key=wert, reverse=True)] for k, v in elf.items()},
            "bank": [sauber(p) for p in verfuegbar
                     if id(p) not in in_elf and p["ampel"] == "gruen" and wert(p) >= 0.1][:9],
            "fraglich": [sauber(p) for p in verfuegbar if p["ampel"] == "gelb" and id(p) not in in_elf],
            "ausfall": [sauber(p) for p in sorted(kader, key=lambda p: -p["mw"]) if p["ampel"] == "rot"],
        }

        nm = roh[0].get("next_match") or {}
        md = roh[0].get("match_data") or {}
        if nm.get("date_iso") and md.get("home_game") is not None:
            heim, gast = (team, md.get("next_opponent")) if md["home_game"] else (md.get("next_opponent"), team)
            # date_iso ist nicht verlässlich zeitzonenbehaftet – "date" ist deutsche Ortszeit
            tag = datetime.date.fromisoformat(nm["date_iso"][:10])
            wt = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][tag.weekday()]
            spiele[(heim, gast)] = {"heim": heim, "gast": gast, "anstoss": nm["date_iso"],
                                   "anstoss_text": f"{wt} {nm.get('date', '')}".strip(),
                                   "spieltag": nm.get("matchday")}

    # Gegnernamen aus match_data können von teamName abweichen ("FC Bayern" vs. "FC Bayern München")
    def team_key(name):
        logo = _comunio_logo(name)
        return next((t for t in ergebnis_teams if ergebnis_teams[t]["logo"] == logo), name)

    partien = {}
    for sp in spiele.values():
        heim, gast = team_key(sp["heim"]), team_key(sp["gast"])
        partien[(heim, gast)] = {**sp, "heim": heim, "gast": gast}
    partien = sorted(partien.values(), key=lambda s: s["anstoss"])

    result = {
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "spieltag": partien[0]["spieltag"] if partien else None,
        "partien": partien,
        "teams": ergebnis_teams,
    }
    Path("aufstellung.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ aufstellung.json geschrieben ({len(partien)} Partien, {len(ergebnis_teams)} Teams)")


def kickbase_fetch():
    """Kickbase-Daten via BaseXI (base-xi.de) holen — kein Login nötig."""
    import requests as _req

    session = _req.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.base-xi.de/players"})

    try:
        # Session-Cookie setzen
        session.get("https://www.base-xi.de/players", timeout=10)
        r = session.get("https://www.base-xi.de/api/players?comp=bl1&t=1", timeout=20)
        r.raise_for_status()
        data = r.json()
        print(f"  → {len(data)} Spieler von BaseXI geladen")
    except Exception as e:
        print(f"❌ BaseXI Fetch fehlgeschlagen: {e}")
        return

    # Ohne Mindesteinsatz besteht die Effizienz-Liste aus billigen Bankspielern:
    # wer 1,1 Mio wert ist und 85 Punkte holt, schlaegt rechnerisch jeden Stammspieler.
    max_spieltage = max((p.get("matchesPlayed") or 0) for p in data) if data else 0
    min_spiele = max(1, round(max_spieltage * 0.75))
    min_starts = 1 if max_spieltage < 3 else 2

    players = []
    for p in data:
        mw  = p.get("marketValue") or 0
        pts = p.get("totalPoints") or 0
        mvt = p.get("mvTrend") or 0
        spiele = p.get("matchesPlayed") or 0
        starts = p.get("starts") or 0
        stammspieler = spiele >= min_spiele and starts >= min_starts
        players.append({
            "name":   p.get("name", ""),
            "logo":   p.get("image") or p.get("fallbackImage") or "",
            "team":   p.get("teamName", ""),
            "pos":    p.get("position", ""),
            "mw":     mw,
            "pts":    pts,
            "ap":     p.get("avgPoints") or 0,
            "mvt":    mvt,
            "t7":     p.get("trend7d") or 0,
            "fair":   p.get("fairValue") or 0,
            "spiele": spiele,
            "stamm":  stammspieler,
            "apvor":  p.get("avgPrevSeason") or 0,
            "formdiff": (p.get("avgPoints") or 0) - (p.get("avgPrevSeason") or 0),
            "status": p.get("status") or 0,
            "info":   (p.get("statusText") or "").strip(),
            "eff":    round(pts / (mw / 1e6), 2) if (mw > 500000 and pts > 0 and stammspieler) else 0,
        })

    def top(lst, key, n=10, reverse=True):
        return sorted([x for x in lst if x.get(key)], key=lambda x: x[key], reverse=reverse)[:n]

    # Formcheck: Punkteschnitt jetzt gegen Vorsaison. Nur wer in beiden Saisons
    # genug gespielt hat, sonst vergleicht man Zufallswerte.
    formspieler = [p for p in players if p["stamm"] and p["apvor"]]

    # Angeschlagene und ausfallende Spieler (status != 0)
    angeschlagen = [p for p in players if p["status"]]
    angeschlagen.sort(key=lambda p: p["mw"], reverse=True)

    # Unterbewertet: fairValue deutlich ueber Marktwert.
    # Zwei Fallstricke der Quelle:
    #   0,5 Mio ist ein Platzhalter statt einer Schaetzung -> erst ab 1 Mio.
    #   fairValue haengt an der Vorsaison (r=0,81) und kaum an der laufenden
    #   (r=0,37). Ohne Einsatzhuerde stehen Spieler oben, die letztes Jahr stark
    #   waren und jetzt auf der Bank sitzen - Kramaric fuehrte die Liste mit
    #   minus drei Punkten und null Startelf-Einsaetzen an.
    schnaeppchen = sorted(
        (p for p in players
         if p["fair"] > 1_000_000 and p["mw"] > 1_000_000 and p["pts"] > 0 and p["stamm"]),
        key=lambda p: p["fair"] / p["mw"], reverse=True)

    result = {
        "updated":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "teuerste":  [{"name":p["name"],"logo":p["logo"],"mw":p["mw"]}   for p in top(players,"mw")],
        "punkte":    [{"name":p["name"],"logo":p["logo"],"pts":p["pts"]}  for p in top(players,"pts")],
        "effizienz": [{"name":p["name"],"logo":p["logo"],"eff":p["eff"]}  for p in top(players,"eff")],
        "raketen":   [{"name":p["name"],"logo":p["logo"],"diff":p["mvt"],"mw":p["mw"]} for p in top(players,"mvt")],
        "crash":     [{"name":p["name"],"logo":p["logo"],"diff":p["mvt"],"mw":p["mw"]} for p in top(players,"mvt",reverse=False) if p["mvt"] < 0],
        "schnitt":   [{"name":p["name"],"logo":p["logo"],"ap":p["ap"]}
                      for p in top([p for p in players if p["spiele"] >= 2], "ap")],
        "woche":     [{"name":p["name"],"logo":p["logo"],"diff":p["t7"],"mw":p["mw"]} for p in top(players,"t7")],
        "wocheminus":[{"name":p["name"],"logo":p["logo"],"diff":p["t7"],"mw":p["mw"]}
                      for p in top(players,"t7",reverse=False) if p["t7"] < 0],
        "schnaeppchen": [{"name":p["name"],"logo":p["logo"],"mw":p["mw"],
                          "fair":p["fair"],"faktor":round(p["fair"]/p["mw"],2)}
                         for p in schnaeppchen[:10]],
        "verletzt":  [{"name":p["name"],"logo":p["logo"],"mw":p["mw"],
                       "info":p["info"] or "angeschlagen"} for p in angeschlagen[:10]],
        "formauf":   [{"name":p["name"],"logo":p["logo"],"diff":p["formdiff"],
                       "ap":p["ap"],"vor":p["apvor"]} for p in top(formspieler,"formdiff")],
        "formab":    [{"name":p["name"],"logo":p["logo"],"diff":p["formdiff"],
                       "ap":p["ap"],"vor":p["apvor"]}
                      for p in top(formspieler,"formdiff",reverse=False) if p["formdiff"] < 0],
    }
    for feld, pos in (("torwart", "Torwart"), ("abwehr", "Abwehr"),
                      ("mittelfeld", "Mittelfeld"), ("sturm", "Sturm")):
        result[feld] = [{"name":p["name"],"logo":p["logo"],"ap":p["ap"]}
                        for p in top([x for x in players
                                      if x["pos"] == pos and x["stamm"]], "ap")]
    Path("kickbase.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ kickbase.json geschrieben ({len(players)} Spieler, via BaseXI)")


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
        scorer_data = get_json("https://api.openligadb.de/getgoalgetters/bl1/2026")
    except Exception as e:
        print(f"❌ OpenLigaDB Fehler: {e}")
        return

    top_scorer = sorted(scorer_data, key=lambda x: x["goalCount"], reverse=True)[:15]

    # goalGetterId → teamId via Spieldaten (letzter Spieltag reicht)
    player_team = {}
    try:
        matches = get_json("https://api.openligadb.de/getmatchdata/bl1/2026")
        for m in matches:
            for g in (m.get("goals") or []):
                if g.get("goalGetterID") and g.get("scoringTeamId") and not g.get("isOwnGoal"):
                    player_team[g["goalGetterID"]] = g["scoringTeamId"]
    except Exception as e:
        print(f"⚠️  Spieldaten Fehler: {e}")

    # teamId → Name
    team_names = {}
    try:
        teams = get_json("https://api.openligadb.de/getavailableteams/bl1/2026")
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
        comunio_fetch()
    except Exception as e:
        print(f"❌ comunio_fetch Fehler: {e}")
    try:
        db_datei = Path("spieler_db.json")
        if not db_datei.exists() or time.time() - db_datei.stat().st_mtime > 20 * 3600:
            spieler_db_fetch()
    except Exception as e:
        print(f"❌ spieler_db_fetch Fehler: {e}")
    try:
        aufstellung_fetch()
    except Exception as e:
        print(f"❌ aufstellung_fetch Fehler: {e}")
    try:
        spieler_fetch()
    except Exception as e:
        print(f"❌ spieler_fetch Fehler: {e}")
    main()
    try:
        spieler_news_index()
    except Exception as e:
        print(f"❌ spieler_news_index Fehler: {e}")
    try:
        spieler_seiten()
    except Exception as e:
        print(f"❌ spieler_seiten Fehler: {e}")
