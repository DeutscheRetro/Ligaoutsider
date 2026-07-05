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
    "bayern": "Bayern", "fcb": "Bayern",
    "borussia dortmund": "Dortmund", "dortmund": "Dortmund", "bvb": "Dortmund",
    "bayer leverkusen": "Leverkusen", "bayer 04": "Leverkusen", "leverkusen": "Leverkusen",
    "rb leipzig": "Leipzig", "rasenballsport": "Leipzig", "leipzig": "Leipzig",
    "eintracht frankfurt": "Frankfurt", "frankfurt": "Frankfurt", "sge": "Frankfurt",
    "vfb stuttgart": "Stuttgart", "stuttgart": "Stuttgart",
    "tsg hoffenheim": "Hoffenheim", "hoffenheim": "Hoffenheim", "tsg 1899": "Hoffenheim",
    "sc freiburg": "Freiburg", "freiburg": "Freiburg",
    "fc augsburg": "Augsburg", "augsburg": "Augsburg",
    "1. fsv mainz": "Mainz", "mainz 05": "Mainz", "mainz": "Mainz",
    "1. fc union berlin": "Union", "union berlin": "Union", "union": "Union",
    "borussia mönchengladbach": "Gladbach", "mönchengladbach": "Gladbach", "gladbach": "Gladbach", "bmg": "Gladbach",
    "werder bremen": "Werder", "werder": "Werder", "svw": "Werder",
    "hamburger sv": "Hamburger", "hamburger": "Hamburger", "hsv": "Hamburger",
    "1. fc köln": "Köln", "fc köln": "Köln", "köln": "Köln",
    "fc schalke": "Schalke", "schalke 04": "Schalke", "schalke": "Schalke",
    "sc paderborn": "Paderborn", "paderborn": "Paderborn",
    "sv elversberg": "Elversberg", "elversberg": "Elversberg",
    "hertha bsc": "Hertha", "hertha": "Hertha",
    "fortuna düsseldorf": "Düsseldorf", "düsseldorf": "Düsseldorf",
    "1. fc heidenheim": "Heidenheim", "heidenheim": "Heidenheim",
    "vfl bochum": "Bochum", "bochum": "Bochum",
    "1. fc nürnberg": "Nürnberg", "nürnberg": "Nürnberg",
}

def vereine_im_text(text: str) -> list:
    t = text.lower()
    gefunden = set()
    for key in sorted(VEREIN_FILTER, key=len, reverse=True):
        if key in t:
            gefunden.add(VEREIN_FILTER[key])
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
updated = 0

for artikel in feed:
    if artikel.get("vereine"):
        continue  # bereits vorhanden
    text = artikel.get("titel", "") + " " + artikel_text(artikel["id"])
    vereine = vereine_im_text(text)
    artikel["vereine"] = vereine
    updated += 1

FEED_JSON.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backfill abgeschlossen: {updated} Artikel aktualisiert, {len(feed)} gesamt.")
