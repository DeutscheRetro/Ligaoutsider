"""Story-Bündelung und Archivabgleich – ohne KI, also ohne Kosten.

Schlagzeilen aus vielen Quellen werden zu Geschichten zusammengefasst:
dieselbe Hauptperson (oder derselbe Klub) und dieselbe Ereignisart ergeben
eine Geschichte. Personen und Klubs kommen aus unserer Spielerdatenbank
(spieler_db.json) und den Klubnamen, die Ereignisart aus Schlüsselwörtern.

Jede Geschichte wird mit dem Archiv der letzten Tage verglichen:
gleiche Geschichte + gleiche Stufe = Doppelmeldung, spätere Stufe = echtes
Update. Unklare Fälle entscheidet die Redaktionskonferenz in generate.py.
"""
import datetime
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz

# ─── Ereignisse ───────────────────────────────────────────────────────────────

# Stufe -> Klasse. Die Stufen sind dieselben wie event_stage im News-Archiv.
STUFEN_KLASSE = {
    "geruecht": "transfer", "angebot": "transfer", "einigung": "transfer",
    "vollzogen": "transfer", "geplatzt": "transfer",
    "verletzung": "verletzung", "fraglich": "verletzung", "ausfall": "verletzung",
    "reha": "verletzung", "rueckkehr": "verletzung",
    "vertrag": "vertrag",
    "trainer_kandidat": "trainer", "trainer_neu": "trainer", "entlassung": "trainer",
    "spielbericht": "spiel", "kader": "kader", "sonstiges": "sonstiges",
}
STUFEN = list(STUFEN_KLASSE)

# Reihenfolge innerhalb einer Klasse: höhere Zahl = spätere Entwicklung
STUFEN_REIHE = {"geruecht": 1, "angebot": 2, "einigung": 3, "vollzogen": 4, "geplatzt": 4,
                "trainer_kandidat": 1, "trainer_neu": 2, "entlassung": 2}

# So lange gilt eine Geschichte als schon berichtet (Tage)
FENSTER_TAGE = {"transfer": 14, "vertrag": 14, "trainer": 14, "verletzung": 5,
                "spiel": 2, "kader": 2, "sonstiges": 2}
ARCHIV_TAGE = 14

# Stufe aus Schlüsselwörtern; Reihenfolge = Vorrang
_REGELN = [
    ("entlassung", r"entlass|freigestellt|beurlaubt|trennt sich von (?:trainer|coach|chefcoach)|trainer-aus|rauswurf|gefeuert"),
    ("trainer_neu", r"neuer (?:trainer|cheftrainer|chefcoach|coach)|wird (?:neuer )?trainer|übernimmt das traineramt|als neuer trainer"),
    ("trainer_kandidat", r"trainersuche|trainerfrage|trainer-?kandidat|nachfolger für|neuen trainer"),
    ("rueckkehr", r"zurück im (?:mannschafts)?training|comeback|kehrt zurück|wieder (?:fit|dabei|im training|einsatzbereit|im kader)|rückkehr|trainiert wieder|steigt wieder ein"),
    ("reha", r"\breha\b|aufbautraining|individuelles training|trainiert individuell|lauftraining"),
    ("ausfall", r"fällt (?:aus|lange|wochen|monate)|fällt\b[^.:;!?]{0,40}\baus\b|\bfehlt\b|nicht zur verfügung|\bausfall\b|verpasst|gesperrt|\bsperre\b|rote karte|gelbsperre|saison-?aus|operiert|operation\b|verzichten|muss passen"),
    ("fraglich", r"fraglich|angeschlagen|einsatz (?:offen|wackelt|gefährdet)|wackelt|bangt um|sorgen um|droht auszufallen"),
    ("verletzung", r"verletz|muskelfaserriss|faserriss|kreuzband|bänderriss|zerrung|prellung|knöchel|oberschenkel|adduktoren|blessur|diagnose|meniskus"),
    ("geplatzt", r"geplatzt|absage|sagt ab|vom tisch|kein wechsel|bleibt doch|dementiert|dementi|gescheitert"),
    ("vollzogen", r"offiziell|perfekt|unterschreibt|unterschrieben|verpflichtet|wechselt (?:zu|nach|in|zum)|neuzugang|leihe fix|ist fix|bestätigt den wechsel"),
    ("einigung", r"einigung|\beinig\b|mündliche zusage|vor (?:dem |einem )?wechsel|steht vor (?:dem|einem) wechsel|medizincheck"),
    ("angebot", r"angebot|bietet|offerte|ablöseforderung|ablösesumme|preisschild"),
    ("vertrag", r"verlänger|vertrag|bis 20\d\d"),
    ("geruecht", r"interesse|im visier|beobachtet|heiß auf|gerücht|spekulation|liebäugel|flirt|denkt an|auf dem zettel|kandidat|umworben|buhlt|buhlen|transfer"),
    ("spielbericht", r"\b\d{1,2}:\d{1,2}\b|\bsieg\b|siegt|gewinnt|verliert|niederlage|remis|unentschieden|punktet|pleite|testspiel"),
    ("kader", r"startelf|aufstellung|kader|rotation|stellt um|formation|personal|nominiert|\bstartet\b|von beginn|\bbeginnt\b"),
]
_REGELN = [(s, re.compile(m)) for s, m in _REGELN]


def stufe_aus_text(text: str) -> str:
    t = (text or "").lower()
    for stufe, muster in _REGELN:
        if muster.search(t):
            return stufe
    return "sonstiges"


# ─── Namen ────────────────────────────────────────────────────────────────────

def falten(t: str) -> str:
    """Kleinbuchstaben ohne Akzente: 'Grønbæk' -> 'gronbaek'."""
    t = str(t or "").lower()
    for a, b in (("ø", "o"), ("æ", "ae"), ("ß", "ss"), ("ł", "l"), ("đ", "d"), ("ı", "i")):
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


# Nachnamen, die zugleich gewöhnliche Wörter oder Vornamen sind ("Neuer Vertrag",
# "Raum für ...", "Albert Grønbaek"). Allein zählen sie nur, wenn auch der Klub
# des Spielers in der Schlagzeile steht.
_NACHNAME_NUR_MIT_KLUB = {
    "neuer", "wolf", "stark", "jung", "berg", "sauer", "stiller", "treu", "kuhn", "baum",
    "funk", "fleck", "koch", "lenz", "bischof", "stage", "can", "hack", "cat", "reis",
    "horst", "topp", "uno", "bell", "raum", "boss", "karl", "klaus", "anton", "albert",
    "adam", "james", "nicolas", "michel", "philipp", "leopold", "arthur", "sander", "silas",
    "kim", "lee", "beste", "burger", "schick", "nebel", "stange", "rohr", "bosch", "sticker",
    "silva", "costa", "moore", "gray", "brown", "banks", "collins", "martel", "noll", "mohr",
    "raab", "huth", "hein", "mala", "jung", "lang", "will", "kade",
}

# Klubnennungen in Schlagzeilen -> kanonischer Name (wie VEREIN_FILTER in generate.py)
_KLUB_EXTRA = {
    "frankfurt": "Frankfurt", "eintracht": "Frankfurt", "sge": "Frankfurt",
    "stuttgart": "Stuttgart", "köln": "Köln", "bremen": "Werder", "werkself": "Leverkusen",
    "fohlen": "Gladbach", "knappen": "Schalke", "königsblau": "Schalke", "geißböcke": "Köln",
    "eisernen": "Union", "nullfünfer": "Mainz", "kraichgauer": "Hoffenheim",
    "breisgauer": "Freiburg", "fuggerstädter": "Augsburg", "roten bullen": "Leipzig",
    "rothosen": "Hamburger", "hamburg": "Hamburger", "fcb": "Bayern",
    # in Fußball-Schlagzeilen praktisch immer der Klub; Zweitligisten wie
    # "1860 München" fliegen vorher über nur_fremdklub() raus
    "bayern": "Bayern", "münchen": "Bayern", "union": "Union",
}

_klub_muster: list = []          # (regex, kanonisch), längste zuerst
_voll_muster: list = []          # (regex, name, klub), längste zuerst
_nachnamen: dict = {}            # gefalteter Nachname -> [(name, klub)]


def _wort(muster: str, kurz: bool) -> re.Pattern:
    # links Wortgrenze, rechts offen für Beugungen ("Frankfurter", "Bayerns"),
    # Kürzel bis drei Zeichen auch rechts begrenzt ("SVE" nicht in "Sven")
    rechts = r"(?![a-z0-9])" if kurz else ""
    return re.compile(r"(?<![a-z0-9])" + re.escape(muster) + rechts)


def init(spieler_db: Path, verein_filter: dict) -> None:
    """verein_filter: VEREIN_FILTER aus generate.py (Nennung -> kanonischer Klub)."""
    global _klub_muster, _voll_muster, _nachnamen
    alle = {**{falten(k): v for k, v in verein_filter.items()},
            **{falten(k): v for k, v in _KLUB_EXTRA.items()}}
    _klub_muster = [(_wort(k, len(k) <= 3), v) for k, v in sorted(alle.items(), key=lambda x: -len(x[0]))]

    _voll_muster, _nachnamen = [], {}
    try:
        db = json.loads(Path(spieler_db).read_text(encoding="utf-8"))
    except Exception:
        return
    voll = {}
    for teamname, team in db.get("teams", {}).items():
        klubs = klubs_in(teamname)
        klub = klubs[0] if klubs else ""
        for sp in team.get("spieler", []):
            name = sp.get("name") or ""
            if not name:
                continue
            for variante in {name, (sp.get("kickbase") or {}).get("name") or ""}:
                if len(variante.split()) > 1:
                    voll[falten(variante)] = (name, klub)
            teile = name.split()
            if len(teile) > 1:
                _nachnamen.setdefault(falten(teile[-1]), []).append((name, klub))
    _voll_muster = [(_wort(k, False), n, kl) for k, (n, kl) in sorted(voll.items(), key=lambda x: -len(x[0]))]


def klubs_in(text: str) -> list[str]:
    """Kanonische Klubs in Reihenfolge ihres ersten Auftretens."""
    t = falten(text)
    gefunden = {}
    for muster, klub in _klub_muster:
        m = muster.search(t)
        if m and (klub not in gefunden or m.start() < gefunden[klub]):
            gefunden[klub] = m.start()
    return [k for k, _ in sorted(gefunden.items(), key=lambda x: x[1])]


def spieler_in(text: str, klubs: list[str] | None = None) -> list[tuple[str, str]]:
    """Bundesliga-Spieler (Name, Klub) in Reihenfolge ihres Auftretens."""
    t = falten(text)
    if klubs is None:
        klubs = klubs_in(text)
    belegt = []          # schon vergebene Textstellen (voller Name vor Nachname)
    treffer = []
    for muster, name, klub in _voll_muster:
        for m in muster.finditer(t):
            if any(a <= m.start() < b for a, b in belegt):
                continue
            belegt.append((m.start(), m.end()))
            treffer.append((m.start(), name, klub))
    for nach, kandidaten in _nachnamen.items():
        if len(nach) < 3:
            continue
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(nach) + r"(?![a-z0-9])", t):
            if any(a <= m.start() < b for a, b in belegt):
                continue
            passend = [k for k in kandidaten if k[1] in klubs]
            if len(kandidaten) == 1 and nach not in _NACHNAME_NUR_MIT_KLUB:
                wahl = kandidaten[0]
            elif len(passend) == 1:
                wahl = passend[0]
            else:
                continue      # mehrdeutig oder gewöhnliches Wort ohne Klubbezug
            belegt.append((m.start(), m.end()))
            treffer.append((m.start(), wahl[0], wahl[1]))
    treffer.sort()
    ergebnis, gesehen = [], set()
    for _, name, klub in treffer:
        if name not in gesehen:
            gesehen.add(name)
            ergebnis.append((name, klub))
    return ergebnis


def analysiere(titel: str, beschr: str = "") -> dict:
    """Personen, Klubs und Ereignis einer Schlagzeile."""
    beschr = re.sub(r"<[^>]+>", " ", beschr or "")[:300]
    klubs = klubs_in(titel)
    # Klub aus der Beschreibung hilft, kurze Nachnamen zuzuordnen
    # ("Hein fehlt Estland" auf der Werder-Seite von LigaInsider)
    kontext = klubs or klubs_in(beschr)
    spieler = spieler_in(titel, kontext)
    if not spieler and not klubs:
        klubs = kontext
        spieler = spieler_in(beschr, klubs)
    # Ereignis nur aus der Schlagzeile: Beschreibungen erwähnen vieles am Rand
    stufe = stufe_aus_text(titel)
    person = spieler[0][0] if spieler else ""
    klub = spieler[0][1] if spieler else (klubs[0] if klubs else "")
    for _, k in spieler:
        if k and k not in klubs:
            klubs.append(k)
    klasse = STUFEN_KLASSE[stufe]
    traeger = person or klub
    return {
        "person": person,
        "spieler": [n for n, _ in spieler],
        "klub": klub,
        "klubs": klubs,
        "stufe": stufe,
        "klasse": klasse,
        "schluessel": f"{falten(traeger)}|{klasse}" if traeger else "",
    }


# ─── Bündeln ──────────────────────────────────────────────────────────────────

# Bevorzugte Quellen für den Artikeltext (Reihenfolge = Vorrang)
_GUTE_QUELLEN = ("kicker.de", "sportschau.de", "transfermarkt", "sport1.de", "spox.com",
                 "sportbild", "bild.de", "ran.de", "11freunde", "faz.net", "sueddeutsche",
                 "spiegel.de", "tz.de", "abendzeitung", "ruhrnachrichten", "express.de",
                 "ksta.de", "mopo.de", "abendblatt", "weser-kurier", "stuttgarter-zeitung")


def quellen_rang(q: dict) -> tuple:
    url = q.get("url", "")
    rang = next((i for i, d in enumerate(_GUTE_QUELLEN) if d in url), len(_GUTE_QUELLEN))
    if "news.google.com" in url:
        rang += 2           # Google-Link muss erst aufgelöst werden
    return (rang, -len(q.get("beschr", "")))


def _gleiche_geschichte(a: dict, b: dict) -> bool:
    """Bewusst vorsichtig: lieber zwei Geschichten zu viel (die Redaktionskonferenz
    erkennt Doppelte in ihrer Liste) als zwei verschiedene Nachrichten in einem Artikel."""
    aehnlich = fuzz.token_sort_ratio(falten(a["titel"]), falten(b["titel"]))
    if aehnlich >= 80:
        return True
    if a["person"] and a["person"] == b["person"]:
        if a["klasse"] == b["klasse"] and a["klasse"] not in ("sonstiges", "kader"):
            return True           # "Kane fällt aus" / "Bayern bangt um Kane"
        return aehnlich >= 60
    if a["klasse"] == b["klasse"] == "spiel":
        gemeinsam = set(a["klubs"]) & set(b["klubs"])
        return len(gemeinsam) >= 2 or (len(gemeinsam) == 1 and aehnlich >= 55)
    if (not a["person"] and not b["person"] and a["klub"] and a["klub"] == b["klub"]
            and a["klasse"] == b["klasse"] == "trainer"):
        return True
    return False


def buendeln(eintraege: list[dict]) -> list[dict]:
    """eintraege: {url, titel, beschr, quelle, zeit, aid} -> Geschichten.

    Geschichte: {id, schluessel, person, spieler, klub, klubs, stufe, klasse,
                 titel, quellen: [...]}; titel = Schlagzeile der besten Quelle."""
    infos = []
    for e in eintraege:
        a = analysiere(e["titel"], e.get("beschr", ""))
        infos.append({**a, "titel": e["titel"], "eintrag": e})
    # Union-Find über alle Paare (wenige hundert Schlagzeilen pro Lauf)
    eltern = list(range(len(infos)))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    for i in range(len(infos)):
        for j in range(i + 1, len(infos)):
            if wurzel(i) != wurzel(j) and _gleiche_geschichte(infos[i], infos[j]):
                eltern[wurzel(j)] = wurzel(i)

    gruppen: dict = {}
    for i, info in enumerate(infos):
        gruppen.setdefault(wurzel(i), []).append(info)

    geschichten = []
    for mitglieder in gruppen.values():
        # Konkreteste Einordnung gewinnt: mit Person vor ohne, bestimmtes Ereignis vor "sonstiges"
        haupt = sorted(mitglieder, key=lambda m: (not m["person"], m["klasse"] == "sonstiges",
                                                   quellen_rang(m["eintrag"])))[0]
        quellen = sorted((m["eintrag"] for m in mitglieder), key=quellen_rang)
        spieler = list(dict.fromkeys(s for m in mitglieder for s in m["spieler"]))
        klubs = list(dict.fromkeys(k for m in mitglieder for k in m["klubs"]))
        geschichten.append({
            "id": hashlib.md5((haupt["schluessel"] + "|" + quellen[0]["url"]).encode()).hexdigest()[:10],
            "schluessel": haupt["schluessel"], "person": haupt["person"],
            "spieler": spieler, "klub": haupt["klub"], "klubs": klubs,
            "stufe": haupt["stufe"], "klasse": haupt["klasse"],
            "titel": quellen[0]["titel"], "quellen": quellen,
        })
    return geschichten


# ─── Archiv ───────────────────────────────────────────────────────────────────

def _liste(wert) -> list:
    """main_players steht im Archiv teils als Text ("['Kane']")."""
    if isinstance(wert, list):
        return [str(x) for x in wert]
    if isinstance(wert, str):
        return [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", wert)]
    return []


def _zeit(iso: str):
    try:
        z = datetime.datetime.fromisoformat(iso)
        return z.replace(tzinfo=None)
    except Exception:
        return None


def archiv_vorbereiten(archiv: list[dict], jetzt: datetime.datetime | None = None) -> list[dict]:
    """Archiv der letzten 14 Tage mit eigener Zuordnung von Personen und Klubs.

    Die alten Einträge stammen aus KI-Fingerprints, die Klubs teils falsch zuordnen
    (Gladbach-Test bei St. Pauli -> "FC St. Pauli"). Deshalb wird aus Titel und
    Kurzfassung neu bestimmt; die KI-Spielerliste kommt nur ergänzend dazu."""
    jetzt = jetzt or datetime.datetime.now()
    aus = []
    for e in archiv:
        zeit = _zeit(e.get("published_at", ""))
        if not zeit or (jetzt - zeit).days > ARCHIV_TAGE:
            continue
        titel = e.get("title", "")
        a = analysiere(titel, e.get("summary", ""))
        spieler = set(a["spieler"]) | set(_liste(e.get("main_players")))
        stufe = e.get("event_stage") if e.get("event_stage") in STUFEN_KLASSE else a["stufe"]
        if stufe == "sonstiges" and a["stufe"] != "sonstiges":
            stufe = a["stufe"]
        klubs = set(a["klubs"]) | set(klubs_in(e.get("main_club") or ""))
        aus.append({
            "id": e.get("id", ""), "titel": titel, "zeit": zeit, "person": falten(a["person"]),
            "summary": e.get("summary", ""), "stufe": stufe, "klasse": STUFEN_KLASSE[stufe],
            "spieler": {falten(s) for s in spieler if s}, "klubs": klubs,
        })
    return aus


def archiv_abgleich(g: dict, archiv: list[dict], jetzt: datetime.datetime | None = None) -> tuple[str, list[dict]]:
    """('doppelt' | 'update' | 'aehnlich' | 'neu', passende Archiv-Einträge, neueste zuerst)."""
    jetzt = jetzt or datetime.datetime.now()
    personen = {falten(s) for s in ([g["person"]] if g["person"] else []) + g.get("spieler", [])}
    treffer = []
    for e in archiv:
        person_gleich = bool(personen & e["spieler"])
        if g["person"]:
            if not person_gleich:
                continue
        elif not (g["klub"] and g["klub"] in e["klubs"] and g["klasse"] == e["klasse"]):
            continue
        elif g["klasse"] in ("sonstiges", "kader") and \
                fuzz.token_sort_ratio(falten(g["titel"]), falten(e["titel"])) < 45:
            continue        # gleicher Klub allein sagt bei Vermischtem nichts
        treffer.append((e, person_gleich))
    treffer.sort(key=lambda x: x[0]["zeit"], reverse=True)
    if not treffer:
        return "neu", []

    fenster = datetime.timedelta(days=FENSTER_TAGE[g["klasse"]])
    status = "aehnlich"
    for e, person_gleich in treffer:
        if e["klasse"] != g["klasse"] or jetzt - e["zeit"] > fenster:
            continue
        if g["klasse"] in ("sonstiges", "kader"):
            continue               # zu unscharf für eine sichere Entscheidung
        if e["stufe"] == g["stufe"]:
            # Ohne KI nur eindeutige Fälle verwerfen, alles andere entscheidet die
            # Redaktionskonferenz (Erwähnung als Nebenfigur ist kein Doppel)
            aehnlich = fuzz.token_sort_ratio(falten(g["titel"]), falten(e["titel"]))
            if g["klasse"] == "spiel":
                gemeinsam = len(set(g["klubs"]) & e["klubs"])
                sicher = gemeinsam >= 2 or (gemeinsam == 1 and aehnlich >= 50)
            else:
                hauptperson = bool(g["person"]) and e["person"] == falten(g["person"])
                endgueltig = g["stufe"] in ("vollzogen", "geplatzt", "entlassung", "trainer_neu")
                sicher = aehnlich >= 55 or (endgueltig and (hauptperson or not g["person"]))
            if sicher:
                return "doppelt", [x for x, _ in treffer][:3]
        elif STUFEN_REIHE.get(g["stufe"], 0) > STUFEN_REIHE.get(e["stufe"], 0) or g["klasse"] == "verletzung":
            status = "update"
    return status, [x for x, _ in treffer][:3]


# ─── Warteschlange ────────────────────────────────────────────────────────────

WARTESCHLANGE = Path("data/news_warteschlange.json")
MAX_ALTER_STUNDEN = 36


def warteschlange_laden(jetzt: datetime.datetime | None = None) -> list[dict]:
    jetzt = jetzt or datetime.datetime.now()
    try:
        liste = json.loads(WARTESCHLANGE.read_text(encoding="utf-8"))
    except Exception:
        return []
    frisch = []
    for g in liste:
        z = _zeit(g.get("erstmals", ""))
        if z and (jetzt - z).total_seconds() < MAX_ALTER_STUNDEN * 3600:
            frisch.append(g)
    return frisch


def warteschlange_speichern(liste: list[dict]) -> None:
    WARTESCHLANGE.parent.mkdir(exist_ok=True)
    WARTESCHLANGE.write_text(json.dumps(liste, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def einreihen(schlange: list[dict], g: dict) -> bool:
    """Gleiche Geschichte (Schlüssel + Stufe) schon in der Warteschlange? Dann nur
    die neuen Quellen anhängen und True zurückgeben."""
    for w in schlange:
        if g["schluessel"] and w["schluessel"] == g["schluessel"] and w["stufe"] == g["stufe"]:
            bekannt = {q["url"] for q in w["quellen"]}
            w["quellen"] += [q for q in g["quellen"] if q["url"] not in bekannt]
            w["quellen"].sort(key=quellen_rang)
            return True
    return False
