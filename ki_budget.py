"""Kostenwächter für alle Claude-Aufrufe.

Jeder Aufruf läuft über aufruf(). Vorher wird geprüft, ob das Budget dieses
Laufs den Aufruf auch im teuersten Fall (volle max_tokens) noch trägt –
dadurch kann das Monatsbudget nie überschritten werden. Hinterher werden die
echten Kosten aus response.usage verbucht und in data/api_kosten.json
gespeichert, das der Workflow mit committet.

Budget: MONATSBUDGET_USD (Standard 20) pro Kalendermonat. Jeder Lauf bekommt
seinen Anteil am Monatsrest, gemessen an allen noch geplanten Läufen des Monats
(LAUFPLAN_UTC). Läufe von Freitag bis Sonntag zählen 1,5-fach, weil an
Spieltagen mehr passiert. Was ein Lauf nicht braucht, verteilt sich auf die
folgenden.

Abo statt Guthaben: Ist CLAUDE_CODE_OAUTH_TOKEN gesetzt (claude setup-token),
laufen die Aufrufe über die Claude-Code-CLI und damit über das Claude-Abo –
ohne Kosten pro Token. Ist das Abo-Kontingent erschöpft oder schlägt der
Aufruf fehl, geht dieser und jeder weitere Aufruf des Laufs über die API mit
dem Budget oben.
"""
import datetime
import json
import os
import shutil
import subprocess
from types import SimpleNamespace
from pathlib import Path

import anthropic

DATEI = Path("data/api_kosten.json")

# USD pro 1 Mio. Tokens (Eingabe, Ausgabe)
PREISE = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5":          (1.00, 5.00),
    "claude-sonnet-4-6":         (3.00, 15.00),
    "claude-opus-5-5":           (5.00, 25.00),
}
PREIS_UNBEKANNT = (5.00, 25.00)   # lieber zu teuer schätzen

# Geplante Läufe in UTC je Wochentag (0 = Montag), wie in .github/workflows/update.yml.
# Berliner Sommerzeit = UTC+2, Winterzeit = UTC+1.
_WERKTAG = ["05:00", "08:00", "11:00", "14:00", "17:00"]
LAUFPLAN_UTC = {
    0: _WERKTAG, 1: _WERKTAG, 2: _WERKTAG, 3: _WERKTAG,
    # Freitag: vor und nach dem Abendspiel
    4: ["05:00", "08:00", "11:00", "14:00", "17:30", "20:30"],
    # Samstag: Aufstellungen vor 15:30, Ergebnisse danach, Topspiel 18:30
    5: ["06:00", "08:00", "10:00", "11:00", "12:30", "15:30", "16:30", "18:00", "20:30"],
    # Sonntag: drei Spielslots
    6: ["07:00", "09:00", "11:00", "12:30", "15:30", "16:30", "17:30", "19:30", "21:00"],
}
GEWICHT = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.5, 5: 1.5, 6: 1.5}


class BudgetErschoepft(Exception):
    """Für diesen Lauf ist kein Geld mehr da (oder das Guthaben ist leer)."""


_client = None
_stand: dict = {}
_tag = ""
_monatsbudget = 20.0
_lauf_budget = 0.0
_lauf_usd = 0.0
_zwecke: dict = {}
_guthaben_leer = False
_abo = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) and bool(shutil.which("claude"))
ABO_TIMEOUT_SEK = 300
_abo_tokens: dict = {}


def abo_aktiv() -> bool:
    return _abo


def _per_abo(model: str, messages: list, output_config: dict | None):
    """Ein Aufruf über die Claude-Code-CLI (Abo). Gibt ein Objekt zurück, das wie
    eine API-Antwort aussieht (content[0].text, stop_reason, usage)."""
    prompt = "\n\n".join(m["content"] if isinstance(m["content"], str)
                         else json.dumps(m["content"], ensure_ascii=False) for m in messages)
    befehl = ["claude", "-p", "--model", model, "--tools", "", "--output-format", "json",
              "--no-session-persistence", "--setting-sources", "",
              "--system-prompt", "Du arbeitest für die Redaktion von ligaoutsider.de. "
                                 "Halte dich genau an die Anweisungen und das verlangte Antwortformat."]
    if "opus" in model:
        befehl += ["--effort", "medium"]
    schema = ((output_config or {}).get("format") or {}).get("schema")
    if schema:
        befehl += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    # Ohne API-Key in der Umgebung, sonst rechnet die CLI über das Guthaben ab statt übers Abo
    umgebung = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    lauf = subprocess.run(befehl, input=prompt, capture_output=True, text=True,
                          timeout=ABO_TIMEOUT_SEK, env=umgebung)
    try:
        d = json.loads(lauf.stdout)
    except Exception:
        raise RuntimeError(f"CLI ohne JSON (exit {lauf.returncode}): {(lauf.stderr or lauf.stdout)[:200]}")
    if d.get("is_error") or d.get("subtype") != "success":
        raise RuntimeError(f"CLI-Fehler: {str(d.get('result') or d.get('subtype'))[:200]}")
    if schema:
        if d.get("structured_output") is None:
            raise RuntimeError("CLI ohne strukturierte Ausgabe")
        text = json.dumps(d["structured_output"], ensure_ascii=False)
    else:
        text = d.get("result") or ""
    u = d.get("usage") or {}
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                           stop_reason=d.get("stop_reason") or "end_turn",
                           usage=SimpleNamespace(input_tokens=u.get("input_tokens", 0) or 0,
                                                 output_tokens=u.get("output_tokens", 0) or 0,
                                                 cache_creation_input_tokens=u.get("cache_creation_input_tokens", 0) or 0,
                                                 cache_read_input_tokens=u.get("cache_read_input_tokens", 0) or 0),
                           api_wert_usd=float(d.get("total_cost_usd") or 0.0))


def _gewicht_rest(jetzt: datetime.datetime) -> float:
    """Summe der Gewichte aller nach jetzt noch geplanten Läufe dieses Monats."""
    summe = 0.0
    tag = jetzt.date()
    while tag.month == jetzt.month:
        for hhmm in LAUFPLAN_UTC[tag.weekday()]:
            h, m = map(int, hhmm.split(":"))
            zeit = datetime.datetime(tag.year, tag.month, tag.day, h, m, tzinfo=datetime.timezone.utc)
            if zeit > jetzt:
                summe += GEWICHT[tag.weekday()]
        tag += datetime.timedelta(days=1)
    return summe


def init(client) -> None:
    """Einmal pro Lauf aufrufen, bevor der erste Claude-Aufruf passiert."""
    global _client, _stand, _tag, _monatsbudget, _lauf_budget, _lauf_usd
    _client = client
    _monatsbudget = float(os.environ.get("MONATSBUDGET_USD", "20"))
    jetzt = datetime.datetime.now()                       # Workflow läuft mit TZ=Europe/Berlin
    monat, _tag = jetzt.strftime("%Y-%m"), jetzt.strftime("%Y-%m-%d")
    try:
        _stand = json.loads(DATEI.read_text(encoding="utf-8"))
    except Exception:
        _stand = {}
    if _stand.get("monat") != monat:
        _stand = {"monat": monat, "monat_usd": 0.0, "tage": {}}
    heute = _stand["tage"].setdefault(_tag, {"usd": 0.0, "laeufe": 0})
    heute["laeufe"] += 1

    rest_monat = max(0.0, _monatsbudget - _stand["monat_usd"])
    utc = datetime.datetime.now(datetime.timezone.utc)
    w = GEWICHT[utc.weekday()]            # dieser Lauf (oft verspätet gestartet) + alle folgenden
    _lauf_budget = rest_monat * w / (w + _gewicht_rest(utc))
    _lauf_usd = 0.0
    _speichern()


def _speichern() -> None:
    DATEI.parent.mkdir(exist_ok=True)
    DATEI.write_text(json.dumps(_stand, ensure_ascii=False, indent=1), encoding="utf-8")


def _laenge(messages: list) -> int:
    n = 0
    for m in messages:
        c = m.get("content", "")
        n += len(c) if isinstance(c, str) else len(json.dumps(c, ensure_ascii=False))
    return n


def schaetzung(model: str, max_tokens: int, zeichen: int) -> float:
    """Teuerster Fall in USD: ~3 Zeichen pro Token, Ausgabe voll ausgeschöpft."""
    ein, aus = PREISE.get(model, PREIS_UNBEKANNT)
    return (zeichen / 3 * ein + max_tokens * aus) / 1e6


def aufruf(zweck: str, *, model: str, max_tokens: int, messages: list,
           reserve: float = 0.0, **kw):
    """messages.create mit Budgetprüfung. reserve = Geld, das danach noch frei
    bleiben muss (z. B. für die Qualitätsprüfung am Ende des Laufs)."""
    global _lauf_usd, _guthaben_leer, _abo
    if _client is None:
        raise RuntimeError("ki_budget.init() fehlt")
    if _abo:
        try:
            antwort = _per_abo(model, messages, kw.get("output_config"))
            anzahl, summe = _zwecke.get(zweck + " (abo)", (0, 0.0))
            _zwecke[zweck + " (abo)"] = (anzahl + 1, summe)
            # Echter Verbrauch im Abo (Tokens und was er über die API gekostet hätte)
            u = antwort.usage
            t = _abo_tokens.setdefault(zweck, {"aufrufe": 0, "ein": 0, "cache_schreiben": 0,
                                               "cache_lesen": 0, "aus": 0, "api_wert_usd": 0.0})
            t["aufrufe"] += 1
            t["ein"] += u.input_tokens
            t["cache_schreiben"] += u.cache_creation_input_tokens
            t["cache_lesen"] += u.cache_read_input_tokens
            t["aus"] += u.output_tokens
            t["api_wert_usd"] = round(t["api_wert_usd"] + antwort.api_wert_usd, 4)
            return antwort
        except Exception as e:
            # Kontingent erschöpft oder CLI-Problem: Rest des Laufs über die API
            print(f"⚠️ Abo-Aufruf fehlgeschlagen ({zweck}): {e} – ab jetzt API")
            _abo = False
    if _guthaben_leer:
        raise BudgetErschoepft("Claude-Guthaben leer")
    kosten_max = schaetzung(model, max_tokens, _laenge(messages))
    if _lauf_usd + kosten_max + reserve > _lauf_budget:
        raise BudgetErschoepft(f"{zweck}: Laufbudget {_lauf_budget:.3f} $ ausgeschöpft "
                               f"(verbraucht {_lauf_usd:.3f} $)")
    try:
        antwort = _client.messages.create(model=model, max_tokens=max_tokens,
                                          messages=messages, **kw)
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            _guthaben_leer = True
            raise BudgetErschoepft("Claude-Guthaben leer") from e
        raise

    u = antwort.usage
    ein, aus = PREISE.get(model, PREIS_UNBEKANNT)
    eingabe = ((u.input_tokens or 0)
               + 1.25 * (getattr(u, "cache_creation_input_tokens", 0) or 0)
               + 0.10 * (getattr(u, "cache_read_input_tokens", 0) or 0))
    kosten = (eingabe * ein + (u.output_tokens or 0) * aus) / 1e6

    _lauf_usd += kosten
    _stand["monat_usd"] = round(_stand["monat_usd"] + kosten, 6)
    heute = _stand["tage"][_tag]
    heute["usd"] = round(heute["usd"] + kosten, 6)
    anzahl, summe = _zwecke.get(zweck, (0, 0.0))
    _zwecke[zweck] = (anzahl + 1, summe + kosten)
    _speichern()
    return antwort


def rest() -> float:
    if _abo:
        return float("inf")          # Abo: keine Kosten pro Aufruf
    return max(0.0, _lauf_budget - _lauf_usd)


def bericht() -> dict:
    heute = _stand.get("tage", {}).get(_tag, {})
    return {
        "lauf_usd": round(_lauf_usd, 4),
        "lauf_budget_usd": round(_lauf_budget, 4),
        "heute_usd": round(heute.get("usd", 0.0), 4),
        "monat_usd": round(_stand.get("monat_usd", 0.0), 4),
        "monatsbudget_usd": _monatsbudget,
        "aufrufe": {z: {"anzahl": a, "usd": round(s, 4)} for z, (a, s) in _zwecke.items()},
        "guthaben_leer": _guthaben_leer,
        "abo": _abo,
        "abo_tokens": _abo_tokens,
    }
