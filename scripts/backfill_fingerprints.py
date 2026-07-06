"""
Einmaliges Script: Fingerprints für published_stories.json-Einträge mit fingerprint=null nachgenerieren.
Idempotent — überspringt Einträge die bereits einen Fingerprint haben.
"""
import json
import re
import time
import shutil
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")

PUBLISHED_JSON = Path("data/published_stories.json")
MODEL = "claude-haiku-4-5-20251001"
client = anthropic.Anthropic()


def fingerprint_generieren(titel: str) -> dict | None:
    try:
        antwort = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f'Extrahiere einen Story-Fingerprint als reines JSON (kein Markdown):\n'
                f'{{"event_type":"transfer|verletzung|trainerwechsel|spielergebnis|testspiel|geruecht|vereinsnews|analyse|sonstiges",'
                f'"main_teams":["max 3 Teams"],'
                f'"main_players":["max 3 Spieler"],'
                f'"one_sentence_summary":"1 Satz Kern-Ereignis"}}\n\n'
                f'Titel: {titel}'
            )}]
        )
        roh = antwort.content[0].text.strip()
        m = re.search(r'\{.*\}', roh, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        log.error(f"API-Error für '{titel[:60]}': {e}")
    return None


def main():
    if not PUBLISHED_JSON.exists():
        log.error(f"{PUBLISHED_JSON} nicht gefunden")
        return

    stories = json.loads(PUBLISHED_JSON.read_text(encoding="utf-8"))
    to_fill = [s for s in stories if not s.get("fingerprint")]
    log.info(f"Gesamt: {len(stories)} | Ohne Fingerprint: {len(to_fill)}")

    if not to_fill:
        log.info("Alle Einträge haben bereits Fingerprints. Fertig.")
        return

    # Backup
    bak = PUBLISHED_JSON.with_suffix(".json.bak")
    shutil.copy(PUBLISHED_JSON, bak)
    log.info(f"Backup: {bak}")

    updated = 0
    for i, story in enumerate(stories):
        if story.get("fingerprint"):
            continue
        titel = story.get("generated_title") or story.get("title", "")
        if not titel:
            log.warning(f"Kein Titel für id={story.get('id')} — übersprungen")
            continue

        log.info(f"[{updated+1}/{len(to_fill)}] Fingerprint für: {titel[:70]}")
        fp = fingerprint_generieren(titel)
        if fp:
            story["fingerprint"] = fp
            updated += 1
        else:
            log.warning(f"Fingerprint fehlgeschlagen — übersprungen: {titel[:60]}")

        time.sleep(0.3)  # sanfte Rate-Limiting

    if updated:
        PUBLISHED_JSON.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"Gespeichert. {updated}/{len(to_fill)} Fingerprints nachgefüllt.")
    else:
        log.warning("Keine Änderungen — Datei nicht überschrieben.")


if __name__ == "__main__":
    main()
