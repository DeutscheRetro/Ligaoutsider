"""IndexNow: neue und geänderte Seiten sofort bei Bing, DuckDuckGo, Ecosia, Yandex u. a. melden.
Google nutzt IndexNow nicht (dort gilt die Sitemap). Aufruf nach dem Veröffentlichen:
python indexnow.py [Commit]   (Standard: letzter Commit)"""
import json
import subprocess
import sys
import time
import urllib.request

HOST = "ligaoutsider.de"
KEY = "55ba00a40248a434af34a8c25dc582b4"
BASIS = f"https://{HOST}/"


def geaenderte_urls(commit: str = "HEAD") -> list[str]:
    roh = subprocess.run(["git", "diff", "--name-only", f"{commit}~1", commit], capture_output=True, text=True).stdout
    urls = []
    for pfad in roh.splitlines():
        if pfad.endswith(".html") and pfad.split("/")[0] in ("artikel", "verein", "spieler") or \
           pfad in ("archiv.html", "index.html", "community.html", "aufstellung.html") or pfad.startswith("archiv-seite-"):
            urls.append(BASIS + ("" if pfad == "index.html" else pfad))
    return sorted(set(urls))[:9000]


def melden(urls: list[str]) -> None:
    if not urls:
        print("IndexNow: nichts zu melden")
        return
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"{BASIS}{KEY}.txt", "urlList": urls}).encode()
    for versuch in range(3):
        try:
            req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                         headers={"Content-Type": "application/json; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"IndexNow: {len(urls)} URLs gemeldet (HTTP {r.status})")
                return
        except Exception as ex:
            print(f"IndexNow Versuch {versuch + 1}: {ex}")
            time.sleep(5)


if __name__ == "__main__":
    melden(geaenderte_urls(sys.argv[1] if len(sys.argv) > 1 else "HEAD"))
