"""Modellvergleich: dieselben Geschichten mit denselben Quellen von mehreren
Modell-/Effort-Varianten schreiben lassen – ohne Veröffentlichung.
Ergebnis: vergleich.json (Texte, Tokens, API-Gegenwert, Dauer je Variante)."""
import datetime
import json
import os
import time
from pathlib import Path

import anthropic

import generate as gen
import ki_budget
import storys

VARIANTEN = [
    {"name": "Opus 5.5 · medium", "model": "claude-opus-5-5", "effort": "medium"},
    {"name": "Sonnet 5.5 · high", "model": "claude-sonnet-5-5", "effort": "high"},
    {"name": "Sonnet 5.5 · low", "model": "claude-sonnet-5-5", "effort": "low"},
]
ANZAHL = int(os.environ.get("VERGLEICH_ANZAHL", "5"))


def geschichten_waehlen() -> list[tuple[dict, list[dict]]]:
    """Wichtigste, frische Geschichten mit genug Quelltext – möglichst verschiedene Arten."""
    schlange = json.loads(Path("data/news_warteschlange.json").read_text(encoding="utf-8"))
    kandidaten = [g for g in schlange if (g.get("prio") or 0) >= 2
                  and not gen.SAMMELARTIKEL.search(g["titel"].lower())
                  and not gen.NICHT_FUER_UNS.search(g["titel"].lower())]
    kandidaten.sort(key=lambda g: g.get("erstmals", ""), reverse=True)      # neueste zuerst …
    kandidaten.sort(key=lambda g: -(g.get("prio") or 0))                    # … innerhalb der Priorität
    gewaehlt, klassen = [], {}
    for g in kandidaten:
        if len(gewaehlt) >= ANZAHL:
            break
        if klassen.get(g.get("klasse"), 0) >= 2:          # Vielfalt: höchstens zwei je Art
            continue
        texte = gen.quellen_laden(g)
        if sum(len(t["text"].split()) for t in texte) < gen.MIN_QUELL_WOERTER:
            continue
        gewaehlt.append((g, texte))
        klassen[g.get("klasse")] = klassen.get(g.get("klasse"), 0) + 1
        print(f"Geschichte: [{g.get('klasse')}] {g['titel'][:80]}")
    return gewaehlt


def main():
    storys.init(Path("spieler_db.json"), gen.VEREIN_FILTER)
    ki_budget.init(anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or "nicht-benutzt"))
    if not ki_budget.abo_aktiv():
        raise SystemExit("Abo nicht aktiv – Vergleich läuft nur über CLAUDE_CODE_OAUTH_TOKEN")
    os.environ["KI_NUR_ABO"] = "1"
    ergebnis = {"zeit": datetime.datetime.now().isoformat(timespec="minutes"),
                "varianten": [v["name"] for v in VARIANTEN], "geschichten": []}
    summen = {v["name"]: {"ein": 0, "aus": 0, "api_wert_usd": 0.0, "sek": 0.0, "fehler": 0} for v in VARIANTEN}
    for g, texte in geschichten_waehlen():
        eintrag = {"titel": g["titel"], "klasse": g.get("klasse"), "quellen": [t["quelle"] for t in texte],
                   "quell_woerter": sum(len(t["text"].split()) for t in texte), "artikel": {}}
        for v in VARIANTEN:
            vorher = json.loads(json.dumps(ki_budget._abo_tokens.get("schreiben", {})))
            start = time.time()
            try:
                a = gen.artikel_generieren(g, texte, model=v["model"], effort=v["effort"])
                a["text"] = gen.floskeln_entfernen(str(a.get("text", "")))
                fehler = None
            except Exception as e:
                a, fehler = {}, str(e)[:200]
                summen[v["name"]]["fehler"] += 1
            sek = time.time() - start
            nach = ki_budget._abo_tokens.get("schreiben", {})
            d = {k: nach.get(k, 0) - vorher.get(k, 0) for k in ("ein", "cache_schreiben", "cache_lesen", "aus", "api_wert_usd")}
            ein = d["ein"] + d["cache_schreiben"] + d["cache_lesen"]
            eintrag["artikel"][v["name"]] = {
                "titel": a.get("titel", ""), "text": a.get("text", ""),
                "woerter": len(str(a.get("text", "")).split()), "relevant": a.get("relevant"),
                "genug_stoff": a.get("genug_stoff"), "ein": ein, "aus": d["aus"],
                "api_wert_usd": round(d["api_wert_usd"], 4), "sek": round(sek, 1), "fehler": fehler}
            s = summen[v["name"]]
            s["ein"] += ein; s["aus"] += d["aus"]; s["api_wert_usd"] += d["api_wert_usd"]; s["sek"] += sek
            print(f"  {v['name']}: {ein:,} rein / {d['aus']:,} raus, {d['api_wert_usd']:.3f} $, {sek:.0f}s"
                  + (f" FEHLER {fehler}" if fehler else ""))
        ergebnis["geschichten"].append(eintrag)
    ergebnis["summen"] = {k: {**v, "api_wert_usd": round(v["api_wert_usd"], 4), "sek": round(v["sek"])}
                          for k, v in summen.items()}
    Path("vergleich.json").write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(ergebnis["summen"], indent=1))


if __name__ == "__main__":
    main()
