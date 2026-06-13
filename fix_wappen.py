"""
Korrigiert alle Wappen-URLs in feed.json und den Artikel-HTML-Dateien.
Starten: python fix_wappen.py
"""

import json, re
from pathlib import Path

FEED_JSON = Path("feed.json")
ARTIKEL   = Path("artikel")

W = "https://upload.wikimedia.org/wikipedia"

# Alle alten → neuen URL-Mappings
KORREKTUREN = {
    # Bayern (alt: 2002-2017 Logo)
    f"{W}/commons/thumb/1/1b/FC_Bayern_M%C3%BCnchen_logo_%282002%E2%80%932017%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282002%E2%80%932017%29.svg.png":
        f"{W}/commons/thumb/8/8d/FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg.png",

    # Leipzig (alte nicht-existierende Datei)
    f"{W}/commons/thumb/0/04/RB_Leipzig_2014_logo.svg/60px-RB_Leipzig_2014_logo.svg.png":
        f"{W}/commons/thumb/d/d6/VEREINFACHTES_LOGO_-_RB_Leipzig.svg/60px-VEREINFACHTES_LOGO_-_RB_Leipzig.svg.png",

    # Leverkusen (alte commons URL → de URL)
    f"{W}/commons/thumb/5/59/Bayer_04_Leverkusen_logo.svg/60px-Bayer_04_Leverkusen_logo.svg.png":
        f"{W}/de/thumb/f/f7/Bayer_Leverkusen_Logo.svg/60px-Bayer_Leverkusen_Logo.svg.png",

    # Frankfurt (alte commons URL → de URL)
    f"{W}/commons/thumb/0/04/Eintracht_Frankfurt_Logo.svg/60px-Eintracht_Frankfurt_Logo.svg.png":
        f"{W}/de/thumb/3/32/Logo_Eintracht_Frankfurt_1998.svg/60px-Logo_Eintracht_Frankfurt_1998.svg.png",

    # Freiburg (sicherheitshalber)
    f"{W}/commons/thumb/b/bf/SC_Freiburg_Logo.svg/60px-SC_Freiburg_Logo.svg.png":
        f"{W}/de/thumb/b/bf/SC_Freiburg_Logo.svg/60px-SC_Freiburg_Logo.svg.png",

    # Bundesliga-Fallback Logo (Werder URL die manchmal falsch zugeordnet wurde)
    f"{W}/commons/thumb/b/be/SV-Werder-Bremen-Logo.svg/60px-SV-Werder-Bremen-Logo.svg.png":
        f"{W}/commons/thumb/b/be/SV-Werder-Bremen-Logo.svg/60px-SV-Werder-Bremen-Logo.svg.png",  # korrekt, nix tun
}

def url_korrigieren(url: str) -> str:
    return KORREKTUREN.get(url, url)

# ─── feed.json aktualisieren ─────────────────────────────────────────────────
if FEED_JSON.exists():
    artikel_liste = json.loads(FEED_JSON.read_text(encoding="utf-8"))
    geaendert = 0
    for a in artikel_liste:
        alte_url = a.get("wappen_url", "")
        neue_url = url_korrigieren(alte_url)
        if neue_url != alte_url:
            a["wappen_url"] = neue_url
            geaendert += 1
    FEED_JSON.write_text(json.dumps(artikel_liste, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"feed.json: {geaendert} von {len(artikel_liste)} URLs korrigiert")
else:
    print("feed.json nicht gefunden")

# ─── Artikel-HTML-Dateien aktualisieren ──────────────────────────────────────
html_geaendert = 0
for html_datei in ARTIKEL.glob("*.html"):
    inhalt = html_datei.read_text(encoding="utf-8")
    neuer_inhalt = inhalt
    for alt, neu in KORREKTUREN.items():
        if alt != neu:
            neuer_inhalt = neuer_inhalt.replace(alt, neu)
    # Auch den ../https:// Bug fixen falls noch vorhanden
    neuer_inhalt = re.sub(r'src="\.\.(https://[^"]+)"', r'src="\1"', neuer_inhalt)
    if neuer_inhalt != inhalt:
        html_datei.write_text(neuer_inhalt, encoding="utf-8")
        html_geaendert += 1

print(f"Artikel-HTML: {html_geaendert} Dateien aktualisiert")
print("Fertig! Jetzt: git add -A && git commit -m '🔧 Wappen URLs gefixt' && git push")
