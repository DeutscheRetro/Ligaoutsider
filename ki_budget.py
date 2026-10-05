"""Kostenwächter für alle Claude-Aufrufe.

Jeder Aufruf läuft über aufruf(). Vorher wird geprüft, ob das Budget dieses
Laufs den Aufruf auch im teuersten Fall (volle max_tokens) noch trägt –
dadurch kann das Monatsbudget nie überschritten werden. Hinterher werden die
echten Kosten aus response.usage verbucht und in data/api_kosten.json
gespeichert, das der Workflow mit committet.

Budget: MONATSBUDGET_USD (Standard 20) pro Kalendermonat. Das Tagesbudget ist
der Monatsrest geteilt durch die verbleibenden Tage, was ein Tag nicht braucht,
steht also den folgenden zur Verfügung. Jeder Lauf bekommt den Tagesrest geteilt
durch die heute noch geplanten Läufe, damit der erste Lauf nicht alles aufbraucht.
"""
import calendar
import datetime
import json
import os
from pathlib import Path

import anthropic

DATEI = Path("data/api_kosten.json")

# USD pro 1 Mio. Tokens (Eingabe, Ausgabe)
PREISE = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5":          (1.00, 5.00),
    "claude-sonnet-4-6":         (3.00, 15.00),
}
PREIS_UNBEKANNT = (5.00, 25.00)   # lieber zu teuer schätzen

# Geplante Läufe in UTC, wie in .github/workflows/update.yml
LAUF_STUNDEN_UTC = [5, 6, 7, 9, 11, 13, 16, 18]
WOCHENENDE_EXTRA_UTC = [20]        # Fr, Sa, So nach den Abendspielen


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


def _laeufe_rest() -> int:
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    stunden = list(LAUF_STUNDEN_UTC)
    if jetzt.weekday() in (4, 5, 6):
        stunden += WOCHENENDE_EXTRA_UTC
    return max(1, sum(1 for h in stunden if h >= jetzt.hour))


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
    rest_tage = calendar.monthrange(jetzt.year, jetzt.month)[1] - jetzt.day + 1
    tagesbudget = (rest_monat + heute["usd"]) / rest_tage
    rest_heute = max(0.0, min(tagesbudget - heute["usd"], rest_monat))
    _lauf_budget = rest_heute / _laeufe_rest()
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
    global _lauf_usd, _guthaben_leer
    if _client is None:
        raise RuntimeError("ki_budget.init() fehlt")
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
    }
