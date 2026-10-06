"""Sticker-Stil für Spielerbilder (Variante 5 aus dem Entwurf vom 06.10.2026).

Freigestellter Spielerkopf mit weißer Kontur vor diagonalen Streifen in den
Vereinsfarben. Nur Pillow – läuft auch im GitHub-Workflow. Das Freistellen
selbst (rembg) passiert vorab in bildpool.py.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FETT = str(Path(__file__).parent / "fonts" / "InterDisplay-ExtraBold.ttf")
POOL = Path(__file__).parent / "bilder" / "spieler"
GELB = (232, 192, 0)

# Hauptfarbe je Verein (Schlüssel = Logo-Dateiname ohne Endung, wie in spieler_db.json)
VEREINSFARBE = {
    "bayern": (220, 5, 45), "dortmund": (240, 200, 0), "leverkusen": (227, 34, 25),
    "leipzig": (221, 1, 63), "frankfurt": (210, 0, 20), "stuttgart": (227, 34, 25),
    "freiburg": (210, 0, 20), "hoffenheim": (23, 92, 163), "werder": (29, 144, 83),
    "gladbach": (20, 120, 60), "mainz": (237, 28, 36), "augsburg": (186, 40, 45),
    "union": (213, 0, 30), "koeln": (237, 28, 36), "hsv": (0, 90, 170),
    "schalke": (0, 75, 155), "paderborn": (0, 85, 165), "elversberg": (40, 40, 40),
}
STANDARDFARBE = (60, 60, 70)


def farbe_fuer(logo: str) -> tuple:
    return VEREINSFARBE.get(Path(logo or "").stem, STANDARDFARBE)


def _dunkler(f, k=0.82):
    return tuple(int(c * k) for c in f)


def streifen(w: int, h: int, farbe: tuple) -> Image.Image:
    img = Image.new("RGBA", (w, h), farbe + (255,))
    d = ImageDraw.Draw(img)
    zweit = _dunkler(farbe)
    for x in range(-h, w, 70):
        d.polygon([(x, h), (x + 35, h), (x + 35 + h, 0), (x + h, 0)], fill=zweit + (255,))
    return img


def silhouette(hoehe: int = 640) -> Image.Image:
    """Platzhalter für Spieler ohne freies Foto: neutrale Kopf-Schulter-Silhouette."""
    b = int(hoehe * 0.82)
    img = Image.new("RGBA", (b, hoehe), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    farbe = (235, 235, 235, 255)
    kopf_r = int(b * 0.22)
    cx = b // 2
    d.ellipse([cx - kopf_r, int(hoehe * 0.12), cx + kopf_r, int(hoehe * 0.12) + 2 * kopf_r + 20], fill=farbe)
    d.rounded_rectangle([int(b * 0.08), int(hoehe * 0.62), int(b * 0.92), hoehe + 80], radius=int(b * 0.3), fill=farbe)
    d.rectangle([cx - int(kopf_r * 0.45), int(hoehe * 0.5), cx + int(kopf_r * 0.45), int(hoehe * 0.66)], fill=farbe)
    return img


def sticker(kopf: Image.Image, max_w: int, max_h: int) -> tuple[Image.Image, Image.Image]:
    """Kopf verkleinern, weiße Kontur und Schatten erzeugen. Gibt (sticker, schatten) zurück."""
    # Auf einheitliche Größe bringen – auch kleine Ausgangsbilder hochskalieren
    f = min(max_w / kopf.width, max_h / kopf.height)
    k = kopf.resize((max(1, round(kopf.width * f)), max(1, round(kopf.height * f))), Image.LANCZOS)
    alpha = k.getchannel("A").filter(ImageFilter.MaxFilter(25))
    kontur = Image.new("RGBA", k.size, (255, 255, 255, 255))
    kontur.putalpha(alpha)
    kontur.alpha_composite(k)
    schatten = Image.new("RGBA", k.size, (0, 0, 0, 255))
    schatten.putalpha(alpha.point(lambda a: int(a * 0.45)))
    return kontur, schatten


def _wappen(img, logo, pos, groesse):
    p = Path(str(logo).lstrip("./"))
    if p.exists():
        w = Image.open(p).convert("RGBA")
        w.thumbnail((groesse, groesse))
        img.alpha_composite(w, pos)


def credit_hochkant(img: Image.Image, text: str, groesse: int = 15):
    f = ImageFont.truetype(FETT, groesse)
    tw = int(ImageDraw.Draw(img).textlength(text, font=f)) + 10
    s = Image.new("RGBA", (tw, groesse + 7), (0, 0, 0, 0))
    ImageDraw.Draw(s).text((4, 2), text, font=f, fill=(255, 255, 255, 190))
    s = s.rotate(90, expand=True)
    img.alpha_composite(s, (img.width - s.width - 6, img.height - s.height - 12))


def bild_hero(kopf: Image.Image | None, logo: str, name: str = "", team: str = "",
              position: str = "", nr: str = "", w: int = 1200, h: int = 500) -> Image.Image:
    """Artikelbild: Vereinsstreifen, Spielerkarte links, Kopf rechts unten angeschnitten.
    Die Namensnennung des Fotografen kommt als HTML daneben, nicht ins Bild."""
    farbe = farbe_fuer(logo)
    img = streifen(w, h, farbe)
    k, sch = sticker(kopf if kopf is not None else silhouette(), 540, 560)
    x, y = w - k.width - 80, h - k.height + int(k.height * 0.16)       # unten vom Rand abgeschnitten
    img.alpha_composite(sch, (x + 12, y + 12))
    img.alpha_composite(k, (x, y))
    if name:
        vor, _, nach = name.rpartition(" ") if " " in name and len(name.split()) == 2 else ("", "", name)
        if len(name.split()) > 2:
            vor, nach = name.split(" ", 1)
        img.alpha_composite(Image.new("RGBA", (560, 340), (0, 0, 0, 185)), (50, 80))
        d = ImageDraw.Draw(img)
        _wappen(img, logo, (80, 108), 90)
        d.text((190, 116), team.upper(), font=ImageFont.truetype(FETT, 22), fill=GELB)
        sub = " · ".join(x for x in (position, f"#{nr}" if nr else "") if x)
        d.text((190, 148), sub, font=ImageFont.truetype(FETT, 22), fill=(200, 200, 200))
        d.text((80, 235), vor, font=ImageFont.truetype(FETT, 46), fill="white")
        gr = 84
        while gr > 36 and d.textlength(nach, font=ImageFont.truetype(FETT, gr)) > 500:
            gr -= 4
        d.text((80, 285), nach, font=ImageFont.truetype(FETT, gr), fill="white")
    else:
        _wappen(img, logo, (60, h - 190), 140)
    return img.convert("RGB")


def _umbruch(d, text, f, breite):
    zeilen, z = [], ""
    for wort in text.split():
        t = (z + " " + wort).strip()
        if d.textlength(t, font=f) <= breite:
            z = t
        else:
            zeilen.append(z)
            z = wort
    zeilen.append(z)
    return [x for x in zeilen if x]


def og_sticker(titel: str, label: str, badge_bg, badge_fg, kopf: Image.Image | None,
               logo: str, credit: str | None) -> Image.Image:
    """Social-Media-Karte 1200x630 im Sticker-Stil, Namensnennung hochkant eingebrannt."""
    W, H = 1200, 630
    img = streifen(W, H, farbe_fuer(logo))
    k, sch = sticker(kopf if kopf is not None else silhouette(), 520, 640)
    pos = (W - k.width - 50, H - k.height + 90)
    img.alpha_composite(sch, (pos[0] + 12, pos[1] + 12))
    img.alpha_composite(k, pos)
    # Dunkles Feld mit Badge, Titel und Wappen – Badge liegt darin, damit es auf jeder Vereinsfarbe lesbar bleibt
    img.alpha_composite(Image.new("RGBA", (640, 500), (0, 0, 0, 185)), (40, 50))
    d = ImageDraw.Draw(img)
    f_b = ImageFont.truetype(FETT, 22)
    bw = d.textlength(label.upper(), font=f_b)
    d.rounded_rectangle((70, 80, 70 + bw + 28, 118), 8, fill=badge_bg)
    d.text((84, 86), label.upper(), font=f_b, fill=badge_fg)
    for size in (52, 46, 41, 37):
        f = ImageFont.truetype(FETT, size)
        zeilen = _umbruch(d, titel, f, 580)
        if len(zeilen) <= 5:
            break
    for i, z in enumerate(zeilen[:5]):
        d.text((70, 145 + i * int(size * 1.15)), z, font=f, fill="white")
    _wappen(img, logo, (70, 440), 80)
    f_m = ImageFont.truetype(FETT, 26)
    x = 170
    for teil, farbe in (("Liga", GELB), ("outsider", (255, 255, 255)), (".de", (159, 179, 200))):
        d.text((x, 468), teil, font=f_m, fill=farbe)
        x += d.textlength(teil, font=f_m)
    if credit:
        credit_hochkant(img, credit)
    return img.convert("RGB")
