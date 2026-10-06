"""Chefredaktion: Opus prüft zweimal am Tag (12 und 18 Uhr) alle Artikel seit der
letzten Prüfung gegen ihre Quelle und verbessert sie bei Bedarf.

Geändert werden nur Titel und Text, die Adresse des Artikels bleibt gleich.
Jede Prüfung landet mit Urteil und Gründen in data/qualitaet_log.json.
"""
import datetime
import html
import json
import os
import re
import time
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "nicht-benutzt")   # generate.py legt beim Import einen Client an

import anthropic  # noqa: E402

import generate as gen  # noqa: E402
import ki_budget  # noqa: E402

PRUEFER = "claude-opus-5-5"
PRUEFER_EFFORT = "medium"
STAND = Path("data/qualitaet_stand.json")
LOG = Path("data/qualitaet_log.json")
ZEITBUDGET_SEK = 15 * 60        # danach Rest beim nächsten Termin
QUELL_ZEICHEN = 3500
FORMAT = "%d.%m.%Y %H:%M"


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "urteil": {"type": "string", "enum": ["ok", "verbessert"]},
            "gruende": {"type": "array", "items": {"type": "string"}},
            "titel": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["urteil", "gruende", "titel", "text"],
        "additionalProperties": False,
    }


def _prompt(titel: str, text: str, quellen: list[str]) -> str:
    q = ("\n\n".join(f"=== QUELLE {i + 1} ===\n{t}" for i, t in enumerate(quellen))
         if quellen else "(Quelle nicht mehr abrufbar – prüfe nur Sprache und Aufbau, ändere keine Fakten)")
    return f"""Du bist Chefredakteur bei Ligaoutsider.de (Bundesliga-News für Fans und Kickbase-/Comunio-Manager).
Prüfe diesen bereits veröffentlichten Artikel gegen seine Quelle und verbessere ihn, wenn nötig.

PRÜFE:
1. Fakten: Steht jede Angabe (Namen, Zahlen, Alter, Daten, Zitate) in der Quelle? Alles, was nicht drinsteht,
   wird gestrichen oder korrigiert. Füge NIE Fakten hinzu, die nicht in der Quelle stehen.
2. Aufbau: Intro (die Nachricht in zwei bis drei Sätzen), Mittelteil (Details, Zitate, Einordnung), Schluss
   (Ausblick oder weiterer Fakt, keine bloße Wiederholung des Intros). Der Artikel darf nicht mitten in Details enden.
3. Thema: Es geht nur um das Thema der Schlagzeile. Fremde Themen aus Sammelquellen raus.
4. Namen: beim ersten Nennen Vor- und Nachname, danach Nachname; Akzente korrekt.
5. Sprache: sachlich wie kicker.de, Sätze höchstens 25 Wörter, keine Floskeln, keine Ausrufezeichen, keine
   Gedankenstriche als Satzzeichen, deutsche Anführungszeichen „…“, Absätze durch Leerzeile getrennt.
6. "Wie berichtet" nur, wenn der Text eine frühere Entwicklung einordnet, die auch in der Quelle steht.
7. Titel: präzise, höchstens 80 Zeichen, passt zum Text.

Länge: im Schnitt 150 bis 300 Wörter, einfache Meldungen auch 70 bis 150. Nicht künstlich verlängern.

Antwort:
- urteil: "ok", wenn nichts Wesentliches zu verbessern ist (dann titel und text unverändert zurückgeben),
  sonst "verbessert".
- gruende: kurze Stichpunkte, was du geändert hast (bei "ok" leer).
- titel, text: die (verbesserte) Fassung.

ARTIKEL
Titel: {titel}

{text}

QUELLEN
{q}"""


def _datum(s: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.strptime(s, FORMAT)
    except Exception:
        return None


def _artikel_lesen(pfad: Path) -> tuple[str, str, list[str]] | None:
    roh = pfad.read_text(encoding="utf-8")
    t = re.search(r'<h1 class="artikel-titel">(.*?)</h1>', roh, re.S)
    body = re.search(r'<div class="artikel-text">(.*?)</div>', roh, re.S)
    if not t or not body:
        return None
    absaetze = re.findall(r"<p>(.*?)</p>", body.group(1), re.S)
    quellen = re.findall(r'<div class="artikel-quelle">.*?</div>', roh, re.S)
    links = re.findall(r'href="([^"]+)"', quellen[0]) if quellen else []
    return t.group(1), "\n\n".join(a.strip() for a in absaetze), links


def _html_anpassen(pfad: Path, alt_titel: str, alt_text: str, neu_titel: str, neu_text: str) -> None:
    roh = pfad.read_text(encoding="utf-8")
    neu_abs = "".join(f"<p>{p.strip()}</p>" for p in neu_text.split("\n\n") if p.strip())
    roh = re.sub(r'(<div class="artikel-text">\s*).*?(\s*</div>)',
                 lambda m: m.group(1) + neu_abs + m.group(2), roh, count=1, flags=re.S)
    # Beschreibung (erster Absatz) in Meta-Tags und JSON-LD
    alt_erster = alt_text.split("\n\n")[0].strip()
    neu_erster = neu_text.split("\n\n")[0].strip()
    if alt_erster != neu_erster:
        roh = roh.replace(json.dumps(alt_erster[:200], ensure_ascii=False),
                          json.dumps(neu_erster[:200], ensure_ascii=False))
        roh = roh.replace(alt_erster[:155].replace('"', "&quot;").replace("\n", " "),
                          neu_erster[:155].replace('"', "&quot;").replace("\n", " "))
    if alt_titel != neu_titel:
        roh = roh.replace(json.dumps(alt_titel, ensure_ascii=False), json.dumps(neu_titel, ensure_ascii=False))
        roh = roh.replace(alt_titel.replace('"', "&quot;"), neu_titel.replace('"', "&quot;"))
        roh = roh.replace(alt_titel, neu_titel)
    pfad.write_text(roh, encoding="utf-8")


def main():
    start = time.time()
    ki_budget.init(anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))
    stand = json.loads(STAND.read_text(encoding="utf-8")) if STAND.exists() else {}
    # Geprüfte Artikel merken wir per ID (viele Artikel eines Laufs haben dieselbe Minute).
    # Beim allerersten Mal nur die letzten 12 Stunden, danach alles Ungeprüfte der letzten 2 Tage.
    geprueft = set(stand.get("geprueft", []))
    seit = datetime.datetime.now() - datetime.timedelta(hours=48 if stand else 12)
    feed = json.loads(gen.FEED_JSON.read_text(encoding="utf-8"))
    offen = sorted((e for e in feed if e.get("id") not in geprueft and (_datum(e.get("datum", "")) or seit) > seit),
                   key=lambda e: _datum(e["datum"]))
    print(f"Qualitätsprüfung: {len(offen)} Artikel seit {seit.strftime(FORMAT)}")
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    geaendert = 0
    for e in offen:
        if time.time() - start > ZEITBUDGET_SEK:
            print("Zeitbudget erreicht – Rest beim nächsten Termin")
            break
        pfad = Path(e.get("pfad", ""))
        gelesen = _artikel_lesen(pfad) if pfad.exists() else None
        if not gelesen:
            geprueft.add(e["id"])
            continue
        titel, text, links = gelesen
        quellen = []
        for url in links[:2]:
            q, grund = gen.fetch_fulltext(html.unescape(url))
            if grund == "ok" and q:
                quellen.append(q[:QUELL_ZEICHEN])
        try:
            antwort = ki_budget.aufruf(
                "qualitaet", model=PRUEFER, effort=PRUEFER_EFFORT, max_tokens=2500,
                messages=[{"role": "user", "content": _prompt(html.unescape(titel), html.unescape(text), quellen)}],
                output_config={"format": {"type": "json_schema", "schema": _schema()}})
            r = json.loads(gen._text_aus(antwort))
        except ki_budget.BudgetErschoepft as ex:
            print(f"Abbruch: {ex}")
            break
        except Exception as ex:
            print(f"  ⚠️ {e['titel'][:60]}: {ex}")
            geprueft.add(e["id"])
            continue
        neu_text = gen.floskeln_entfernen(str(r.get("text", "")).strip())
        neu_titel = gen.anfuehrungszeichen(str(r.get("titel", "")).strip())[:120]
        # Maßgeblich ist, ob sich Titel oder Text tatsächlich geändert haben (das Urteil allein
        # ist nicht verlässlich: Modelle melden "ok" und ändern trotzdem)
        norm = lambda x: re.sub(r"\s+", " ", x).strip()
        ok = (len(neu_text.split()) >= 60 and bool(neu_titel)
              and (norm(neu_text) != norm(html.unescape(text)) or neu_titel != html.unescape(titel)))
        if ok:
            _html_anpassen(pfad, titel, text, neu_titel, neu_text)
            e["titel"] = neu_titel
            e["anriss"] = " ".join(neu_text.split()[:30])
            if neu_titel != html.unescape(titel):
                gen.og_karte(e["id"], neu_titel, e.get("kategorie", "news"), e.get("wappen_url", ""), e.get("bild_tm") or None)
            geaendert += 1
        print(f"  {'✏️ ' if ok else '✅'} {neu_titel[:70]}" + (f" | {'; '.join(r.get('gruende', []))[:200]}" if ok else ""))
        log.append({"zeit": datetime.datetime.now().strftime(FORMAT), "id": e["id"], "pfad": e["pfad"],
                    "urteil": "verbessert" if ok else "ok", "gruende": r.get("gruende", []) if ok else [],
                    "alt_titel": html.unescape(titel) if ok else None, "quelle_gelesen": bool(quellen)})
        geprueft.add(e["id"])

    zeit = {x["id"]: _datum(x.get("datum", "")) or datetime.datetime.min for x in feed}
    stand["geprueft"] = sorted(geprueft, key=lambda i: zeit.get(i, datetime.datetime.min))[-1000:]
    stand["letzte_pruefung"] = datetime.datetime.now().strftime(FORMAT)
    gen.FEED_JSON.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    STAND.write_text(json.dumps(stand, ensure_ascii=False, indent=1), encoding="utf-8")
    LOG.write_text(json.dumps(log[-2000:], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {geaendert} von {len(offen)} Artikeln verbessert | {ki_budget.bericht().get('abo_tokens', {}).get('qualitaet')}")


if __name__ == "__main__":
    main()
