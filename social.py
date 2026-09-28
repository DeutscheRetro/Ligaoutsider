"""Postet neue Artikel auf Bluesky und Telegram.

generate.py legt jeden neuen Artikel in data/social_queue.json ab. Die Seite
geht aber nur ein paarmal am Tag live (Netlify-Credits), deshalb postet dieses
Skript einen Artikel erst, wenn seine Seite wirklich erreichbar ist. Bis dahin
bleibt er in der Warteschlange und wird beim nächsten Lauf erneut geprüft.

Zugangsdaten kommen aus GitHub-Secrets; fehlt eins, wird das Netzwerk übersprungen:
  BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL   (z. B. "@ligaoutsider")
"""
import datetime
import html
import json
import os
import re
from pathlib import Path

import requests

QUEUE = Path("data/social_queue.json")
BASIS = "https://ligaoutsider.de"
MAX_ALTER_STUNDEN = 48          # ältere Einträge nicht mehr posten
MAX_POSTS_PRO_LAUF = 15         # nicht die Timeline fluten


# Vereinsnamen aus feed.json -> gängige Hashtags
HASHTAGS = {
    "bayern": "FCBayern", "dortmund": "BVB", "leverkusen": "Bayer04", "leipzig": "RBLeipzig",
    "stuttgart": "VfB", "frankfurt": "SGE", "gladbach": "Gladbach", "freiburg": "SCFreiburg",
    "hoffenheim": "TSG", "mainz": "Mainz05", "augsburg": "FCA", "union": "FCUnion",
    "werder": "Werder", "hamburger": "HSV", "hsv": "HSV", "köln": "effzeh", "koeln": "effzeh",
    "schalke": "S04", "elversberg": "SVE", "paderborn": "SCP07",
}


def hashtags(e: dict) -> list:
    tags = ["Bundesliga"]
    for v in [e.get("hauptklub", "")] + list(e.get("vereine") or []):
        for teil, tag in HASHTAGS.items():
            if teil in str(v).lower() and tag not in tags:
                tags.append(tag)
    return tags[:4]


def lade_queue() -> list:
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:
        return []


def ist_live(url: str) -> bool:
    try:
        return requests.head(url, timeout=15, allow_redirects=True).status_code == 200
    except Exception:
        return False


# ─── Bluesky ──────────────────────────────────────────────────────────────────
_bsky_sitzung = None

def _bsky_login():
    global _bsky_sitzung
    if _bsky_sitzung is None:
        r = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={
            "identifier": os.environ["BLUESKY_HANDLE"],
            "password":   os.environ["BLUESKY_APP_PASSWORD"],
        }, timeout=20)
        r.raise_for_status()
        _bsky_sitzung = r.json()
    return _bsky_sitzung


def bluesky_post(e: dict):
    s = _bsky_login()
    kopf = {"Authorization": f"Bearer {s['accessJwt']}"}
    thumb = None
    og = Path(e.get("og", ""))
    if og.exists():
        r = requests.post("https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
                          headers={**kopf, "Content-Type": "image/jpeg"},
                          data=og.read_bytes(), timeout=30)
        r.raise_for_status()
        thumb = r.json()["blob"]
    tags = hashtags(e)
    tag_text = " ".join("#" + t for t in tags)
    text = e["titel"][:300 - len(tag_text) - 2] + "\n\n" + tag_text
    facets = []
    roh = text.encode("utf-8")
    for t in tags:
        start = roh.find(("#" + t).encode("utf-8"))
        if start >= 0:
            facets.append({"index": {"byteStart": start, "byteEnd": start + len(("#" + t).encode("utf-8"))},
                           "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": t}]})
    karte = {"uri": e["url"], "title": e["titel"], "description": e.get("anriss", "")[:300]}
    if thumb:
        karte["thumb"] = thumb
    r = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=kopf, json={
        "repo": s["did"],
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": text,
            "facets": facets,
            "langs": ["de"],
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "embed": {"$type": "app.bsky.embed.external", "external": karte},
        },
    }, timeout=20)
    r.raise_for_status()


# ─── Telegram ─────────────────────────────────────────────────────────────────
def telegram_post(e: dict):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    kanal = os.environ["TELEGRAM_CHANNEL"]
    text = (f"<b>{html.escape(e['titel'])}</b>\n\n{html.escape(e.get('anriss', ''))}\n\n"
            f'<a href="{html.escape(e["url"])}">Weiterlesen auf Ligaoutsider.de</a>\n\n'
            + " ".join("#" + t for t in hashtags(e)))
    og = Path(e.get("og", ""))
    if og.exists() and len(text) <= 1024:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                          data={"chat_id": kanal, "caption": text, "parse_mode": "HTML"},
                          files={"photo": og.open("rb")}, timeout=30)
    else:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": kanal, "text": text, "parse_mode": "HTML"}, timeout=30)
    r.raise_for_status()


NETZWERKE = {
    "bluesky":  (("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"), bluesky_post),
    "telegram": (("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL"), telegram_post),
}


def main():
    queue = lade_queue()
    aktiv = {n: f for n, (env, f) in NETZWERKE.items() if all(os.environ.get(v) for v in env)}
    if not aktiv:
        print("Social: keine Zugangsdaten hinterlegt – nichts zu tun")
    jetzt = datetime.datetime.now()
    geposted = 0
    behalten = []
    for e in queue:
        try:
            alter = jetzt - datetime.datetime.fromisoformat(e["zeit"])
        except Exception:
            alter = datetime.timedelta(0)
        offen = [n for n in aktiv if n not in e.get("erledigt", [])]
        if alter > datetime.timedelta(hours=MAX_ALTER_STUNDEN):
            continue                                   # zu alt, verwerfen
        if not offen or geposted >= MAX_POSTS_PRO_LAUF or not ist_live(e["url"]):
            behalten.append(e)
            continue
        for n in offen:
            try:
                aktiv[n](e)
                e.setdefault("erledigt", []).append(n)
                print(f"✅ {n}: {e['titel'][:60]}")
            except Exception as ex:
                print(f"⚠️ {n} fehlgeschlagen: {ex}")
        geposted += 1
        # Fertig, wenn alle aktiven Netzwerke erledigt sind
        if any(n not in e.get("erledigt", []) for n in aktiv) or not aktiv:
            behalten.append(e)
    QUEUE.parent.mkdir(exist_ok=True)
    QUEUE.write_text(json.dumps(behalten, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Social: {geposted} Artikel geposted, {len(behalten)} in der Warteschlange")


if __name__ == "__main__":
    main()
