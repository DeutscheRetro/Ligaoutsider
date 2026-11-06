"""Nach dem Rebase im Hauptlauf: Feed-Einträge von origin/main zurückholen, die "-X theirs" verworfen hat.

Beispiel: Der 15-Uhr-Lauf startet, um 15:15 postet aufstellungen.yml eine Aufstellung samt Feed-Eintrag.
Beim Push des Hauptlaufs gewinnt dessen feed.json, der Eintrag wäre weg, obwohl die Seite existiert.
Gibt 1 zurück, wenn feed.json geändert wurde.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def nachziehen(hier: list, fern: list, geloescht: set) -> list:
    ids = {a["id"] for a in hier}
    neu = [a for a in fern if a.get("id") not in ids and a.get("id") not in geloescht
           and Path(a.get("pfad") or "-").exists()]
    if not neu:
        return hier
    return sorted(hier + neu, key=lambda a: datetime.strptime(a["datum"], "%d.%m.%Y %H:%M"), reverse=True)


def main() -> int:
    try:
        fern = json.loads(subprocess.check_output(["git", "show", "origin/main:feed.json"]))
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"feed_nachziehen: origin/main nicht lesbar ({e}), nichts zu tun")
        return 0
    hier = json.loads(Path("feed.json").read_text())
    weg = Path("deleted_ids.json")
    geloescht = set(json.loads(weg.read_text())) if weg.exists() else set()
    neu = nachziehen(hier, fern, geloescht)
    if len(neu) == len(hier):
        return 0
    tmp = Path("feed.json.tmp")
    tmp.write_text(json.dumps(neu, ensure_ascii=False, indent=2))
    tmp.replace("feed.json")
    print(f"feed_nachziehen: {len(neu) - len(hier)} Einträge von origin/main zurückgeholt")
    return 1


if __name__ == "__main__":
    sys.exit(main())
