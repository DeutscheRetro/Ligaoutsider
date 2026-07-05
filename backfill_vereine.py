"""
Backfill: vereine-Feld für alle bestehenden feed.json Artikel nachholen.
Liest Titel + Artikel-HTML, berechnet vereine_im_text(), schreibt feed.json neu.
"""
import json, re
from pathlib import Path

ARTIKEL_ORDNER = Path("artikel")
FEED_JSON = Path("feed.json")

VEREIN_FILTER = {
    "fc bayern münchen": "Bayern", "fc bayern": "Bayern", "bayern münchen": "Bayern",
    "fc-bayern": "Bayern",
    "borussia dortmund": "Dortmund", "bvb": "Dortmund", "dortmund": "Dortmund",
    "rb leipzig": "Leipzig", "rasenballsport": "Leipzig", "leipzig": "Leipzig",
    "bayer 04 leverkusen": "Leverkusen", "bayer leverkusen": "Leverkusen",
    "bayer 04": "Leverkusen", "leverkusen": "Leverkusen",
    # Frankfurt: nur compound – alle kürzeren Keywords zu generisch
    "eintracht frankfurt": "Frankfurt",
    # Stuttgart: "stuttgart" entfernt – oft Stadtname
    "vfb stuttgart": "Stuttgart", "vfb": "Stuttgart",
    "borussia mönchengladbach": "Gladbach", "mönchengladbach": "Gladbach",
    "gladbach": "Gladbach", "bmg": "Gladbach", "die fohlen": "Gladbach",
    "sc freiburg": "Freiburg", "freiburg": "Freiburg",
    # Union: "union" allein zu generisch
    "1. fc union berlin": "Union", "union berlin": "Union", "fc union": "Union",
    "1. fsv mainz": "Mainz", "fsv mainz": "Mainz", "mainz 05": "Mainz", "mainz": "Mainz",
    "fc augsburg": "Augsburg", "augsburg": "Augsburg",
    "sv werder bremen": "Werder", "werder bremen": "Werder", "werder": "Werder",
    "tsg hoffenheim": "Hoffenheim", "tsg 1899": "Hoffenheim", "hoffenheim": "Hoffenheim",
    # Hamburger: "hamburger" allein zu generisch
    "hamburger sv": "Hamburger", "hsv": "Hamburger",
    # Köln: bare "köln" entfernt – Stadtname
    "1. fc köln": "Köln", "fc köln": "Köln", "effzeh": "Köln",
    "fc schalke 04": "Schalke", "fc schalke": "Schalke", "schalke 04": "Schalke",
    "schalke": "Schalke", "s04": "Schalke",
    "sc paderborn": "Paderborn", "paderborn": "Paderborn",
    "sv elversberg": "Elversberg", "elversberg": "Elversberg",
}

def _count_key(key, text):
    return len(re.findall(r'(?<!\w)' + re.escape(key) + r'(?!\w)', text))

def vereine_im_text(titel: str, body: str) -> list:
    t_lower = titel.lower()
    body_lower = body.lower()
    gefunden = set()
    bereits: set = set()
    for key in sorted(VEREIN_FILTER, key=len, reverse=True):
        club = VEREIN_FILTER[key]
        if club in bereits:
            continue
        if _count_key(key, t_lower) > 0 or _count_key(key, body_lower) >= 2:
            gefunden.add(club)
            bereits.add(club)
    return sorted(gefunden)

def artikel_text(artikel_id: str) -> str:
    pfad = ARTIKEL_ORDNER / f"{artikel_id}.html"
    if not pfad.exists():
        return ""
    try:
        html = pfad.read_text(encoding="utf-8")
        text = re.sub(r'<[^>]+>', ' ', html)
        return re.sub(r'\s+', ' ', text).strip()[:3000]
    except Exception:
        return ""

feed = json.loads(FEED_JSON.read_text(encoding="utf-8"))

for artikel in feed:
    titel = artikel.get("titel", "")
    body = artikel_text(artikel["id"])
    artikel["vereine"] = vereine_im_text(titel, body)

FEED_JSON.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backfill abgeschlossen: {len(feed)} Artikel aktualisiert.")
