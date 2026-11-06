"""Ein-Klick-Umfrage unter einem Artikel: welches Format zum Ereignis passt und ob die Frage
der KI zum Text passt. Die Umfrage hängt am Ereignis, nicht an der Rubrik ("Transfer" enthält
auch Vertragsverlängerungen, "Nationalmannschaft" auch Kritik an der Länderspielpause).
Nur `re` und `html`, damit der Test ohne die Abhängigkeiten der Pipeline läuft."""
import html
import re

FORMATE = {
    "reaktion": ["💚\u2002Gute Besserung"],
    "spiel": ["🔥\u2002Spektakel", "😐\u2002Geht so", "😴\u2002Schlafmittel"],
    "deal": ["👍\u2002Guter Deal", "👎\u2002Fehler"],
    "recht": ["Ja", "Nein"],
}
MAX_FRAGE = 90

VERLETZUNG_STUFEN = {"verletzung", "fraglich", "ausfall", "reha"}
DEAL_STUFEN = {"geruecht", "angebot", "einigung", "vollzogen", "vertrag"}

VERLETZUNG = re.compile(
    r"verletz|muskel|knie|kreuzband|sprunggelenk|oberschenkel|wade|adduktor|zerrung|faserriss|bänder|"
    r"bruch|prellung|gehirnerschütterung|operation|operiert|krank|infekt|grippe|erkält|fieber|"
    r"beschwerden|blessur|reha", re.I)
ERGEBNIS = re.compile(r"\b\d{1,2}:\d{1,2}\b")
TESTSPIEL = re.compile(r"testspiel|freundschaftsspiel", re.I)
# Hier ist eine Abstimmung geschmacklos oder eine Unterstellung
SENSIBEL = re.compile(
    r"\btod\b|\btot\b|gestorben|verstorben|trauer|unfall|ermittl|anklage|staatsanwalt|polizei|"
    r"vorwurf|vorwürfe|missbrauch|rassis|gewalt|suizid|depression|herzstillstand", re.I)
FLOSKEL = re.compile(r"was (denkt|meint|sagt) ihr|wie seht ihr|eure meinung", re.I)


def _frage_ok(frage: str, text: str) -> bool:
    if not frage.endswith("?") or len(frage) > MAX_FRAGE or "!" in frage or FLOSKEL.search(frage):
        return False
    # Mindestens ein Eigenname aus dem Text (großgeschriebenes Wort, nicht das erste der Frage)
    namen = [w for w in re.findall(r"\b[A-ZÄÖÜ][\wäöüßéèáàíóúñçøå'-]{2,}", frage)[1:]]
    if not any(re.search(r"\b" + re.escape(w), text) for w in namen):
        return False
    # Keine Zahl, die nicht im Text steht
    return all(z in text for z in re.findall(r"\d+", frage))


def waehlen(ereignis: str, kategorie: str, text: str, ki: dict | None) -> dict | None:
    """Gibt {typ, frage, antworten} zurück oder None, wenn keine Umfrage passt."""
    if not text or SENSIBEL.search(text):
        return None
    ki = ki if isinstance(ki, dict) else {}
    typ = ki.get("typ")
    frage = " ".join(str(ki.get("frage") or "").split())
    if ereignis in VERLETZUNG_STUFEN:
        return {"typ": "reaktion", "frage": "", "antworten": FORMATE["reaktion"]} if VERLETZUNG.search(text) else None
    if ereignis == "spielbericht":
        if ERGEBNIS.search(text) and not TESTSPIEL.search(text):
            return {"typ": "spiel", "frage": "Wie war das Spiel?", "antworten": FORMATE["spiel"]}
        return None
    if typ == "deal" and ereignis in DEAL_STUFEN and "deal" in frage.lower() and _frage_ok(frage, text):
        return {"typ": "deal", "frage": frage, "antworten": FORMATE["deal"]}
    if (typ == "recht" and kategorie in ("interview", "analyse", "news") and "„" in text
            and re.match(r"^(Hat|Haben)\b", frage) and " recht" in frage and _frage_ok(frage, text)):
        return {"typ": "recht", "frage": frage, "antworten": FORMATE["recht"]}
    return None


def box_html(aid: str, u: dict | None) -> str:
    """Box unter dem Artikeltext. Ergebnisse lädt umfrage.js erst nach der eigenen Stimme."""
    if not u or not re.fullmatch(r"[0-9a-f]{10}", aid or ""):
        return ""
    e = html.escape
    knoepfe = "".join(f'<button type="button" class="u-knopf" data-i="{i}">{e(a)}</button>'
                      for i, a in enumerate(u["antworten"]))
    frage = f'<p class="umfrage-frage">{e(u["frage"])}</p>' if u.get("frage") else ""
    fuss = ('' if u["typ"] == "reaktion" else
            '<p class="u-fuss" hidden>Warum? <a href="#kommentare" class="u-warum">Schreib es in die Kommentare</a></p>')
    return (f'<aside class="umfrage" data-id="{aid}" data-typ="{e(u["typ"])}" hidden>'
            f'{frage}<div class="u-knoepfe">{knoepfe}</div><div class="u-ergebnis" hidden></div>{fuss}</aside>')
