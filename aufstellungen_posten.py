"""Offizielle Aufstellungen an Spieltagen als Artikel veröffentlichen.

Läuft kurz vor jedem Anpfiff (Cloudflare-Cron in worker.js startet den Workflow
aufstellungen.yml im Fenster 75 bis 20 Minuten vor Spielbeginn). Sobald RotoWire
beide Startelfen als bestätigt markiert, entsteht ein kurzer Artikel ohne KI:
Intro, beide Startelfen, Hinweis auf die Aufstellungsseite. Jede Partie nur einmal
(data/aufstellungen_gepostet.json).
"""
import datetime
import html as _html
import json
import os
import re
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "nicht-benutzt")   # generate.py legt beim Import einen Client an

import requests  # noqa: E402

import generate as gen  # noqa: E402

GEPOSTET = Path("data/aufstellungen_gepostet.json")
ROTOWIRE = "https://www.rotowire.com/soccer/lineups.php?league=BUND"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
VORLAUF_MIN = 90      # Partien, die in so vielen Minuten beginnen …
NACHLAUF_MIN = 30     # … oder vor höchstens so vielen Minuten begonnen haben


def partien_jetzt() -> list[dict]:
    """Bundesliga-Partien rund um jetzt (OpenLigaDB, aktueller Spieltag)."""
    spiele = requests.get("https://api.openligadb.de/getmatchdata/bl1", timeout=20).json()
    jetzt = datetime.datetime.now()
    aus = []
    for s in spiele:
        try:
            anpfiff = datetime.datetime.fromisoformat(s["matchDateTime"])
        except Exception:
            continue
        delta = (anpfiff - jetzt).total_seconds() / 60
        if -NACHLAUF_MIN <= delta <= VORLAUF_MIN:
            aus.append({"id": s["matchID"], "anpfiff": anpfiff, "heim": s["team1"]["teamName"],
                        "gast": s["team2"]["teamName"], "spieltag": (s.get("group") or {}).get("groupOrderID")})
    return aus


def rotowire() -> dict:
    """{logo: {"elf": [(pos, name)…], "bestaetigt": bool}} für alle Partien auf RotoWire."""
    t = requests.get(ROTOWIRE, headers=UA, timeout=25).text
    ergebnis = {}
    for spiel in t.split('class="lineup is-soccer"')[1:]:
        teams = [re.sub(r"\s+", " ", _html.unescape(n)).strip()
                 for n in re.findall(r'class="lineup__mteam is-(?:home|visit)">\s*([^<]+)', spiel)]
        listen = re.findall(r'<ul class="lineup__list is-(home|visit)">(.*?)</ul>', spiel, re.S)
        for (_, inhalt), team in zip(listen, teams):
            vor_verletzt = re.split(r'lineup__title', inhalt)[0]
            elf = [(p.strip(), _html.unescape(n)) for p, n in re.findall(
                r'<div class="lineup__pos[^"]*">([^<]*)</div>\s*<a title="([^"]+)"', vor_verletzt)]
            if len(elf) >= 11:
                ergebnis[gen._comunio_logo(team)] = {"elf": elf[:11], "bestaetigt": "is-confirmed" in vor_verletzt}
    return ergebnis


REIHE = {"GK": 0, "DL": 1, "DC": 1, "DR": 1, "DML": 2, "DMC": 2, "DMR": 2, "ML": 2, "MC": 2, "MR": 2,
         "AML": 3, "AMC": 3, "AMR": 3, "FWL": 4, "FW": 4, "FWR": 4}


_KADER: dict | None = None


def richtiger_name(name: str, logo: str) -> str:
    """RotoWire schreibt ohne Umlaute (Grull, Fullkrug): Schreibweise aus unserem Kader."""
    global _KADER
    if _KADER is None:
        db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
        _KADER = {t["logo"]: t["spieler"] for t in db["teams"].values()}
    treffer = gen._finde_spieler(name, _KADER.get(logo, []))
    return treffer["name"] if treffer else name


def elf_text(elf: list, logo: str = "") -> str:
    """Startelf nach Mannschaftsteilen: Tor – Abwehr – Mittelfeld – Angriff."""
    teile = {}
    for pos, name in elf:
        name = richtiger_name(name, logo) if logo else name
        teile.setdefault(REIHE.get(pos.upper(), 2), []).append(name)
    return " – ".join(", ".join(teile[r]) for r in sorted(teile))


def artikel(p: dict, heim: dict, gast: dict) -> dict:
    zeit = p["anpfiff"].strftime("%H:%M")
    spieltag = f"{p['spieltag']}. Spieltag, " if p.get("spieltag") else ""
    titel = f"Offizielle Aufstellungen: {p['heim']} gegen {p['gast']}"
    text = (f"Die Startformationen für die Partie {p['heim']} gegen {p['gast']} stehen fest. "
            f"Anpfiff ist um {zeit} Uhr ({spieltag}Bundesliga).\n\n"
            f"{p['heim']}: {elf_text(heim['elf'], gen._comunio_logo(p['heim']))}\n\n"
            f"{p['gast']}: {elf_text(gast['elf'], gen._comunio_logo(p['gast']))}\n\n"
            "Alle Startelfen des Spieltags und die voraussichtlichen Aufstellungen der übrigen Partien "
            "stehen auf unserer Aufstellungsseite.")
    return {"titel": titel, "text": text}


def offiziell_eintragen(partien: list, roto: dict, pfad: Path = Path("aufstellung.json")) -> int:
    """Bestätigte Startelfen in aufstellung.json: die Aufstellungsseite zeigt sie sofort statt der Prognose.
    Gibt die Zahl der neu eingetragenen Teams zurück."""
    if not pfad.exists():
        return 0
    au = json.loads(pfad.read_text(encoding="utf-8"))
    nach_logo = {t.get("logo"): t for t in au.get("teams", {}).values()}
    neu = 0
    for p in partien:
        for verein in (p["heim"], p["gast"]):
            logo = gen._comunio_logo(verein)
            r, t = roto.get(logo), nach_logo.get(logo)
            if not (r and r["bestaetigt"] and t):
                continue
            eintrag = {"anstoss": p["anpfiff"].isoformat(timespec="seconds"),
                       "elf": [{"pos": pos, "name": richtiger_name(n, logo)} for pos, n in r["elf"]]}
            if t.get("offiziell") != eintrag:
                t["offiziell"] = eintrag
                neu += 1
    if neu:
        tmp = pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(au, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(pfad)
    return neu


def main():
    gepostet = json.loads(GEPOSTET.read_text(encoding="utf-8")) if GEPOSTET.exists() else {}
    alle = partien_jetzt()
    if not alle:
        print("Keine anstehende Partie")
        return
    roto = rotowire()
    print(f"Offizielle Startelfen auf der Aufstellungsseite: {offiziell_eintragen(alle, roto)} neu")
    partien = [p for p in alle if str(p["id"]) not in gepostet]
    feed = gen.feed_laden()
    neu = 0
    for p in partien:
        heim, gast = roto.get(gen._comunio_logo(p["heim"])), roto.get(gen._comunio_logo(p["gast"]))
        if not (heim and gast and heim["bestaetigt"] and gast["bestaetigt"]):
            print(f"  noch nicht bestätigt: {p['heim']} – {p['gast']}")
            continue
        a = artikel(p, heim, gast)
        aid = gen.artikel_id(f"aufstellung-bl1-{p['id']}")
        if any(e.get("id") == aid for e in feed):
            gepostet[str(p["id"])] = aid
            continue
        wappen = gen._comunio_logo(p["heim"])
        datum = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        dateiname = f"{gen.artikel_slug(a['titel'])}-{aid}.html"
        og = gen.og_karte(aid, a["titel"], "aufstellung", wappen, None)
        html = gen.artikel_html(datei_id=aid, titel=a["titel"], text=a["text"], kategorie="aufstellung",
                                quelle_name="RotoWire", quelle_url=ROTOWIRE, datum=datum,
                                wappen_url="../" + wappen if wappen else "",
                                vereine=[p["heim"], p["gast"]], og_image_url=og, dateiname=dateiname)
        # Link auf die Aufstellungsseite im Schlussabsatz
        html = html.replace("auf unserer Aufstellungsseite.",
                            'auf unserer <a href="../aufstellung.html">Aufstellungsseite</a>.', 1)
        (gen.ARTIKEL_ORDNER / dateiname).write_text(html, encoding="utf-8")
        label, bg, fg = gen.badge_fuer_kategorie("aufstellung")
        feed.append({"id": aid, "titel": a["titel"], "kategorie": "aufstellung", "badge": label,
                     "badge_bg": bg, "badge_fg": fg, "datum": datum, "wappen_url": wappen,
                     "vereine": [p["heim"], p["gast"]], "anriss": " ".join(a["text"].split()[:30]),
                     "spielerstatus": [], "formation": "", "hauptklub": p["heim"],
                     "pfad": f"artikel/{dateiname}", "bild_tm": ""})
        gepostet[str(p["id"])] = aid
        neu += 1
        print(f"  ✓ {a['titel']}")
    if neu:
        gen.feed_speichern(feed)
        gen.sitemap_generieren(feed)
        gen.rss_generieren(feed)
    # Nur die letzten 50 Partien merken: ältere sind vorbei, ein Doppelpost fiele zudem über die Feed-ID auf
    ids = list(gepostet)
    gepostet = {k: gepostet[k] for k in ids[-50:]}
    GEPOSTET.write_text(json.dumps(gepostet, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {neu} Aufstellungsartikel")


if __name__ == "__main__":
    main()
