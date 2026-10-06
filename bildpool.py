"""Bilderpool: pro Bundesliga-Spieler ein freies Foto von Wikimedia Commons.

Ablauf (lokal ausführen, braucht rembg + opencv, siehe unten):
  1. Spieler über die Transfermarkt-ID (Wikidata P2446) finden, Bild aus P18.
  2. Lizenz prüfen: nur CC0, gemeinfrei, CC BY, CC BY-SA (keine NC/ND).
  3. Gesicht erkennen, Kopf + Schultern ausschneiden, freistellen (rembg).
  4. Speichern: bilder/spieler/<tm_id>.webp (freigestellt), <tm_id>.jpg (Artikelbild
     im Sticker-Stil), index.json mit Fotograf/Lizenz/Quelle.
  5. Platzhalter je Verein (Silhouette) in bilder/platzhalter/<verein>.jpg.

    venv/bin/pip install "rembg[cpu]" "opencv-python-headless<5"
    venv/bin/python bildpool.py            # nur neue Spieler
    venv/bin/python bildpool.py --alle     # alles neu
"""
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter
from rembg import new_session, remove

import bildstil

POOL = Path("bilder/spieler")
PLATZHALTER = Path("bilder/platzhalter")
INDEX = POOL / "index.json"
UA = {"User-Agent": "Ligaoutsider-Bilderpool/1.0 (https://ligaoutsider.de; Kontakt über Impressum)"}
ERLAUBT = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? \d)", re.I)


def holen(url: str, json_antwort=True):
    for versuch in range(4):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
            return json.loads(r) if json_antwort else r
        except Exception:
            if versuch == 3:
                raise
            time.sleep(3 * (versuch + 1))


def wikidata_bilder(tm_ids: list[str]) -> dict:
    erg = {}
    for i in range(0, len(tm_ids), 200):
        werte = " ".join(f'"{x}"' for x in tm_ids[i:i + 200])
        q = f"SELECT ?tm ?img WHERE {{ VALUES ?tm {{ {werte} }} ?p wdt:P2446 ?tm . ?p wdt:P18 ?img }}"
        r = holen("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q))
        for b in r["results"]["bindings"]:
            erg.setdefault(b["tm"]["value"], urllib.parse.unquote(b["img"]["value"].rsplit("/", 1)[1]))
    return erg


def fotograf_name(roh: str) -> str:
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", roh)).strip()
    t = re.sub(r",?\s*(via |from )?Wikimedia Commons$", "", t, flags=re.I).strip(" ,")
    return t[:60] or "unbekannt"


def commons_info(dateien: list[str]) -> dict:
    erg = {}
    for i in range(0, len(dateien), 40):
        titel = "|".join("File:" + f for f in dateien[i:i + 40])
        r = holen("https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo"
                  "&iiprop=url|extmetadata&iiurlwidth=1600&format=json&titles=" + urllib.parse.quote(titel))
        norm = {n["to"]: n["from"] for n in r["query"].get("normalized", [])}
        for p in r["query"]["pages"].values():
            ii = (p.get("imageinfo") or [{}])[0]
            m = ii.get("extmetadata", {})
            name = norm.get(p["title"], p["title"]).removeprefix("File:")
            erg[name] = {
                "url": ii.get("thumburl") or ii.get("url"),
                "seite": ii.get("descriptionurl", ""),
                "fotograf": fotograf_name(m.get("Artist", {}).get("value", "")),
                "lizenz": m.get("LicenseShortName", {}).get("value", ""),
                "lizenz_url": m.get("LicenseUrl", {}).get("value", ""),
            }
    return erg


_GESICHT = [cv2.CascadeClassifier(cv2.data.haarcascades + n)
            for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
                      "haarcascade_profileface.xml")]


def gesicht(img: Image.Image) -> tuple | None:
    """Größtes Gesicht (x, y, w, h) in Pixeln des übergebenen Bildes."""
    klein = img.copy()
    klein.thumbnail((900, 900))
    f = img.width / klein.width
    grau = cv2.equalizeHist(cv2.cvtColor(np.array(klein.convert("RGB")), cv2.COLOR_RGB2GRAY))
    for kaskade in _GESICHT:
        g = kaskade.detectMultiScale(grau, scaleFactor=1.08, minNeighbors=6, minSize=(40, 40))
        if len(g):
            return tuple(int(v * f) for v in max(g, key=lambda r: r[2] * r[3]))
    return None


def kopf_box(img: Image.Image) -> tuple | None:
    """Ausschnitt um das größte Gesicht, nur Kopf (für rembg, spart Rechenzeit)."""
    g = gesicht(img)
    if not g:
        return None
    x, y, w, h = g
    cx = x + w / 2
    return (max(0, int(cx - w * 1.35)), max(0, int(y - h * 1.0)),
            min(img.width, int(cx + w * 1.35)), min(img.height, int(y + h * 1.9)))


MIN_GESICHT = 110       # Pixel Gesichtsbreite im Originalfoto, sonst wird der Kopf beim Skalieren unscharf
MIN_KOPF_BREITE = 300   # fertiger Kopf mindestens so breit (das Banner zeigt ihn ~500 px groß)
MIN_SCHAERFE = 80       # Varianz des Laplace-Filters im Gesicht


def schaerfe(foto: Image.Image, g: tuple) -> float:
    x, y, w, h = g
    ausschnitt = foto.crop((x, y, x + w, y + h)).convert("L").resize((200, int(200 * h / max(w, 1))))
    return float(cv2.Laplacian(np.array(ausschnitt), cv2.CV_64F).var())


def kopf_maske(groesse: tuple, g: tuple, box: tuple) -> Image.Image:
    """Erlaubte Fläche: Kopf-Block bis unter das Kinn plus Hals, der zum Kragen hin schmaler wird.
    Bewusst großzügig (auch bei gedrehten Köpfen, wo das Gesichtsrechteck außermittig sitzt);
    Hände, Nachbarn und Schultern fängt der Rest ab (größte Fläche, Proportionsregel)."""
    from PIL import ImageDraw
    x, y, w, h = g
    cx, oben = x + w / 2 - box[0], y - box[1]
    m = Image.new("L", groesse, 0)
    d = ImageDraw.Draw(m)
    d.ellipse([cx - w * 1.35, oben - h * 0.95, cx + w * 1.35, oben + h * 0.75], fill=255)                # Schädel mit Haaren/Ohren, auch bei gedrehtem Kopf
    d.rounded_rectangle([cx - w * 0.95, oben - h * 0.2, cx + w * 0.95, oben + h * 0.98], radius=int(w * 0.55), fill=255)  # Gesicht bis Kinn
    d.polygon([(cx - w * 0.6, oben + h * 0.6), (cx + w * 0.6, oben + h * 0.6),
               (cx + w * 0.48, oben + h * 1.5), (cx - w * 0.48, oben + h * 1.5)], fill=255)            # nur Hals, keine Schultern
    return m.filter(ImageFilter.GaussianBlur(2))


def groesste_flaeche(rgba: Image.Image) -> Image.Image:
    """Nur die größte zusammenhängende Fläche behalten (entfernt Reste)."""
    a = np.array(rgba.getchannel("A"))
    n, lab, stat, _ = cv2.connectedComponentsWithStats((a > 40).astype(np.uint8), connectivity=8)
    if n <= 2:
        return rgba
    groesste = 1 + int(np.argmax(stat[1:, cv2.CC_STAT_AREA]))
    a2 = np.where(lab == groesste, a, 0).astype(np.uint8)
    out = rgba.copy()
    out.putalpha(Image.fromarray(a2))
    return out


def proportion_ok(kopf: Image.Image) -> str:
    """Leer = in Ordnung, sonst Ablehnungsgrund. Gute Köpfe sind 1,3- bis 1,85-mal so hoch wie breit:
    breiter heißt Nachbar, Mütze oder Arm im Bild, höher heißt ganzer Körper."""
    verhaeltnis = kopf.height / kopf.width
    if verhaeltnis < 1.20:
        return f"zu breit ({verhaeltnis:.2f}) – vermutlich Nachbar, Mütze oder Arm im Bild"
    if verhaeltnis > 1.85:
        return f"zu hoch ({verhaeltnis:.2f}) – vermutlich ganzer Körper"
    grau = Image.new("RGB", kopf.size, (128, 128, 128))
    grau.paste(kopf, mask=kopf.getchannel("A"))
    g = gesicht(grau)
    if g and g[2] / kopf.width < 0.55:
        return f"Gesicht nur {g[2] / kopf.width:.0%} der Kopfbreite – viel Beiwerk"
    return ""


# Qualitätslatte = Niveau von Kane (Schärfe 662) und Guirassy (471); weiche Köpfe lagen alle unter 120
Q_MIN_GESICHT = 240        # Gesichtsbreite im fertigen Kopf in Pixeln
Q_MIN_SCHAERFE = 160       # Laplace-Varianz des auf 200 px normierten Gesichts
Q_HELLIGKEIT = (85, 200)   # mittlere Helligkeit des Gesichts: nicht zu dunkel, nicht überstrahlt
Q_MIN_KONTRAST = 26        # Standardabweichung der Helligkeit im Gesicht
Q_RAND = (0.12, 0.18, 0.04)  # Mindestabstand Gesicht zum Rand: oben (Haare), unten (Kinn+Hals), seitlich


def kopf_qualitaet(kopf: Image.Image) -> str:
    """Leer = gut genug. Sonst Ablehnungsgrund: unscharf, zu klein, zu dunkel, Gesicht am Rand abgeschnitten."""
    grau = Image.new("RGB", kopf.size, (128, 128, 128))
    grau.paste(kopf, mask=kopf.getchannel("A"))
    g = gesicht(grau)
    if not g:
        return "kein Gesicht erkannt"
    x, y, w, h = g
    if w < Q_MIN_GESICHT:
        return f"Gesicht zu klein ({w} px)"
    face = np.array(grau.crop((x, y, x + w, y + h)).convert("L").resize((200, max(1, int(200 * h / w)))))
    schaerfe_wert = float(cv2.Laplacian(face, cv2.CV_64F).var())
    if schaerfe_wert < Q_MIN_SCHAERFE:
        return f"nicht scharf genug ({schaerfe_wert:.0f})"
    hell, kon = float(face.mean()), float(face.std())
    if hell < Q_HELLIGKEIT[0] or hell > Q_HELLIGKEIT[1]:
        return f"Gesicht zu {'dunkel' if hell < Q_HELLIGKEIT[0] else 'hell'} ({hell:.0f})"
    if kon < Q_MIN_KONTRAST:
        return f"zu wenig Kontrast ({kon:.0f})"
    oben, unten = y / kopf.height, (kopf.height - (y + h)) / kopf.height
    links, rechts = x / kopf.width, (kopf.width - (x + w)) / kopf.width
    if oben < Q_RAND[0]:
        return "Stirn/Haare oben abgeschnitten"
    if unten < Q_RAND[1]:
        return "Kinn/Hals unten abgeschnitten"
    if min(links, rechts) < Q_RAND[2]:
        return "Gesicht reicht bis an den seitlichen Rand (vermutlich abgeschnitten)"
    a = np.array(kopf.getchannel("A"))[y + int(h * 0.1):y + int(h * 0.95), x + int(w * 0.15):x + int(w * 0.85)]
    if a.size and a.mean() / 255 < 0.93:
        return "Gesicht teilweise transparent (Teile weggeschnitten)"
    return ""


def kopf_erzeugen(foto: Image.Image, sess) -> tuple[Image.Image | None, str]:
    """Foto -> freigestellter Kopf. Gibt (Bild, '') oder (None, Ablehnungsgrund) zurück."""
    g = gesicht(foto)
    if not g:
        return None, "kein Gesicht erkannt"
    if g[2] < MIN_GESICHT:
        return None, f"Gesicht zu klein ({g[2]} px)"
    sch = schaerfe(foto, g)
    if sch < MIN_SCHAERFE:
        return None, f"unscharf ({sch:.0f})"
    box = kopf_box(foto)
    aus = foto.crop(box)
    kopf = remove(aus, session=sess)
    maske = kopf_maske(kopf.size, g, box)
    kopf.putalpha(ImageChops.multiply(kopf.getchannel("A"), maske))
    kopf = groesste_flaeche(kopf)
    # Unterkante weich ausblenden (kein harter Schnitt durch den Hals)
    al = np.array(kopf.getchannel("A")).astype(np.float32)
    hoehe = al.shape[0]
    start = int(hoehe * 0.90)
    al[start:] *= np.linspace(1.0, 0.0, hoehe - start)[:, None]
    kopf.putalpha(Image.fromarray(al.astype(np.uint8)))
    bb = kopf.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    if not bb:
        return None, "Freistellen fehlgeschlagen"
    kopf = kopf.crop(bb)
    if kopf.width < MIN_KOPF_BREITE:
        return None, f"Kopf nur {kopf.width} px breit"
    grund = proportion_ok(kopf) or kopf_qualitaet(kopf)
    if grund:
        return None, grund
    flaeche = np.array(kopf.getchannel("A")).mean() / 255
    if flaeche < 0.45:
        return None, f"Freistellen unsicher ({flaeche:.0%})"
    # Zweites Gesicht im fertigen Kopf? (z. B. Mitspieler direkt dahinter)
    grau = Image.new("RGB", kopf.size, (128, 128, 128))
    grau.paste(kopf, mask=kopf.getchannel("A"))
    if sum(1 for _ in _weitere_gesichter(grau, g[2] * kopf.width / (g[2] * 2.3))) > 0:
        return None, "mehr als ein Gesicht"
    return kopf, ""


def _weitere_gesichter(img: Image.Image, _):
    """Gesichter außer dem größten, die mindestens ein Drittel so groß sind."""
    klein = img.copy(); klein.thumbnail((700, 700))
    grau = cv2.equalizeHist(cv2.cvtColor(np.array(klein.convert("RGB")), cv2.COLOR_RGB2GRAY))
    gefunden = []
    for kaskade in _GESICHT[:2]:
        gefunden += [tuple(r) for r in kaskade.detectMultiScale(grau, 1.08, 6, minSize=(30, 30))]
    if len(gefunden) < 2:
        return []
    gefunden.sort(key=lambda r: -r[2] * r[3])
    gr = gefunden[0]
    return [r for r in gefunden[1:]
            if r[2] > gr[2] / 3 and abs((r[0] + r[2] / 2) - (gr[0] + gr[2] / 2)) > gr[2] * 0.6]


def eng_nachschneiden():
    """Schneidet schon freigestellte Bilder auf den Kopf zu (Gesicht + Haare + etwas Hals)."""
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    entfernen = []
    for tm, info in index.items():
        datei = POOL / f"{tm}.webp"
        if not datei.exists():
            entfernen.append(tm)
            continue
        if info.get("eng") and "--alle-pruefen" not in sys.argv:
            continue
        kopf = Image.open(datei).convert("RGBA")
        grau = Image.new("RGB", kopf.size, (128, 128, 128))
        grau.paste(kopf, mask=kopf.getchannel("A"))
        box = kopf_box(grau)
        if not box:
            print(f"  ✗ {info['name']}: Gesicht nicht erkannt – aus dem Pool genommen")
            entfernen.append(tm)
            continue
        neu = kopf.crop(box)
        bb = neu.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
        if not bb:
            continue
        neu = neu.crop(bb)
        neu.save(datei, "WEBP", quality=85, method=6)
        info["eng"] = True
        pass  # Artikelbild danach mit --hero neu erzeugen
    for tm in entfernen:
        for endung in ("webp", "jpg"):
            (POOL / f"{tm}.{endung}").unlink(missing_ok=True)
        index.pop(tm, None)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {len(index)} Köpfe im Pool, {len(entfernen)} entfernt")


def heros_neu():
    """Artikelbilder (jpg) aller Spieler aus den freigestellten Köpfen neu erzeugen."""
    db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
    daten = {str(s["tm_id"]): (t, v["logo"], s) for t, v in db["teams"].items() for s in v["spieler"]}
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    for tm, info in index.items():
        if tm not in daten:
            continue
        team, logo, sp = daten[tm]
        kopf = Image.open(POOL / f"{tm}.webp").convert("RGBA")
        bildstil.bild_hero(kopf, logo, sp["name"], team, sp.get("position", ""), sp.get("nr", "")
                           ).save(POOL / f"{tm}.jpg", quality=82)
        info.update(team=team, logo=logo)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(index)} Artikelbilder neu erzeugt")


def regeln_anwenden():
    """Prüft alle fertigen Köpfe gegen Proportions- und Qualitätsregeln, entfernt Verstöße
    und schreibt bilder/qualitaet_abgelehnt.txt sowie bilder/ohne_bild.txt neu."""
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
    alle = {str(sp["tm_id"]): (t, sp["name"]) for t, v in db["teams"].items() for sp in v["spieler"] if sp.get("tm_id")}
    raus = []
    for tm, info in index.items():
        datei = POOL / f"{tm}.webp"
        if not datei.exists():
            raus.append((tm, info["name"], "Datei fehlt"))
            continue
        kopf = Image.open(datei).convert("RGBA")
        grund = proportion_ok(kopf) or kopf_qualitaet(kopf)
        if grund:
            raus.append((tm, info["name"], grund))
    for tm, name, grund in raus:
        print(f"  ✗ {name}: {grund}")
        for endung in ("webp", "jpg"):
            (POOL / f"{tm}.{endung}").unlink(missing_ok=True)
        index.pop(tm, None)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    Path("bilder/qualitaet_abgelehnt.txt").write_text("\n".join(f"{n}: {g}" for _, n, g in raus) + "\n", encoding="utf-8")
    Path("bilder/ohne_bild.txt").write_text("\n".join(sorted(f"{t}: {n}" for k, (t, n) in alle.items() if k not in index)) + "\n", encoding="utf-8")
    print(f"{len(index)} Köpfe bleiben, {len(raus)} entfernt")


def main():
    if "--regeln" in sys.argv:
        return regeln_anwenden()
    if "--hero" in sys.argv:
        return heros_neu()
    if "--eng" in sys.argv:
        return eng_nachschneiden()
    alle = "--alle" in sys.argv
    POOL.mkdir(parents=True, exist_ok=True)
    PLATZHALTER.mkdir(parents=True, exist_ok=True)
    db = json.loads(Path("spieler_db.json").read_text(encoding="utf-8"))
    spieler = {str(s["tm_id"]): {"name": s["name"], "team": t, "logo": v["logo"]}
               for t, v in db["teams"].items() for s in v["spieler"] if s.get("tm_id")}
    index = {} if alle or not INDEX.exists() else json.loads(INDEX.read_text(encoding="utf-8"))
    pruefen = []

    # Platzhalter je Verein
    for t, v in db["teams"].items():
        bildstil.bild_hero(None, v["logo"]).save(PLATZHALTER / f"{Path(v['logo']).stem}.jpg", quality=82)

    ausschluss = set()
    if Path("bilder/ausschluss.txt").exists():       # TM-IDs, die du nach Sichtkontrolle ausschließt (eine pro Zeile, # = Kommentar)
        ausschluss = {z.split("#")[0].strip() for z in Path("bilder/ausschluss.txt").read_text().splitlines()} - {""}
    bilder = {k: v for k, v in wikidata_bilder(list(spieler)).items() if k not in ausschluss}
    infos = commons_info(sorted(set(bilder.values())))
    print(f"{len(spieler)} Spieler, {len(bilder)} mit Wikidata-Bild")
    sess = new_session("u2net_human_seg")
    for tm, datei in sorted(bilder.items(), key=lambda x: spieler[x[0]]["team"]):
        sp = spieler[tm]
        info = infos.get(datei)
        alt = index.get(tm)
        if alt and alt.get("datei") == datei and not alle:
            # Bild unverändert – nur Artikelbild neu, falls der Spieler den Verein gewechselt hat
            if alt.get("logo") != sp["logo"]:
                alt.update(team=sp["team"], logo=sp["logo"])     # Verein gewechselt: danach --hero
            continue
        if not info or not info["url"] or not ERLAUBT.match(info["lizenz"]) or re.search(r"\bN[CD]\b", info["lizenz"]):
            pruefen.append(f"{sp['name']} ({sp['team']}): Lizenz '{info and info['lizenz']}' – übersprungen")
            continue
        try:
            foto = Image.open(io.BytesIO(holen(info["url"], json_antwort=False))).convert("RGB")
        except Exception as e:
            pruefen.append(f"{sp['name']}: Download fehlgeschlagen ({e})")
            continue
        kopf, grund = kopf_erzeugen(foto, sess)
        if kopf is None:
            pruefen.append(f"{sp['name']} ({sp['team']}): {grund} – {info['seite']}")
            for endung in ("webp", "jpg"):
                (POOL / f"{tm}.{endung}").unlink(missing_ok=True)
            index.pop(tm, None)
            continue
        kopf.thumbnail((1000, 1200))
        kopf.save(POOL / f"{tm}.webp", "WEBP", quality=88, method=6)
        bildstil.bild_hero(kopf, sp["logo"], sp["name"], sp["team"], sp.get("position", ""),
                           sp.get("nr", "")).save(POOL / f"{tm}.jpg", quality=82)
        index[tm] = {"eng": True, "name": sp["name"], "team": sp["team"], "logo": sp["logo"], "datei": datei,
                     "fotograf": info["fotograf"] or "unbekannt", "lizenz": info["lizenz"],
                     "lizenz_url": info["lizenz_url"], "quelle": info["seite"]}
        print(f"  ✓ {sp['name']} ({sp['team']}) – {info['fotograf']}, {info['lizenz']}")
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    Path("bilder/pruefen.txt").write_text("\n".join(pruefen) + "\n", encoding="utf-8")
    ohne = sorted(f"{v['team']}: {v['name']}" for k, v in spieler.items() if k not in index)
    if ausschluss:
        for tm in ausschluss:
            for endung in ("webp", "jpg"):
                (POOL / f"{tm}.{endung}").unlink(missing_ok=True)
            index.pop(tm, None)
    Path("bilder/ohne_bild.txt").write_text("\n".join(ohne) + "\n", encoding="utf-8")

    # Kontaktbogen zur Sichtkontrolle (nicht veröffentlicht)
    kacheln = sorted(index)
    if kacheln:
        spalten, kw, kh = 12, 150, 190
        bogen = Image.new("RGB", (spalten * kw, ((len(kacheln) + spalten - 1) // spalten) * kh), (40, 40, 40))
        for i, tm in enumerate(kacheln):
            k = Image.open(POOL / f"{tm}.webp").convert("RGBA")
            k.thumbnail((kw - 10, kh - 10))
            bogen.paste(k, ((i % spalten) * kw + 5, (i // spalten) * kh + 5), k)
        bogen.save("bilder/kontaktbogen.jpg", quality=80)
    print(f"Fertig: {len(index)} Spieler mit Bild, {len(ohne)} ohne, {len(pruefen)} zum Prüfen")


if __name__ == "__main__":
    main()
