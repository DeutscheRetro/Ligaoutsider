"""
Ligaoutsider Admin-Panel
Starten: python admin.py
Öffnen:  http://localhost:5001
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FEED_JSON     = Path("feed.json")
ARTIKEL_ORDER = Path("artikel")
PASSWORT      = "ligaoutsider2026"   # ← hier ändern

W = "https://upload.wikimedia.org/wikipedia"
LOGOS = {
    "FC Bayern München":       f"{W}/commons/thumb/8/8d/FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg/60px-FC_Bayern_M%C3%BCnchen_logo_%282024%29.svg.png",
    "Borussia Dortmund":       f"{W}/commons/thumb/6/67/Borussia_Dortmund_logo.svg/60px-Borussia_Dortmund_logo.svg.png",
    "RB Leipzig":              f"{W}/commons/thumb/0/04/RB_Leipzig_2014_logo.svg/60px-RB_Leipzig_2014_logo.svg.png",
    "Bayer 04 Leverkusen":     f"{W}/de/thumb/f/f7/Bayer_Leverkusen_Logo.svg/60px-Bayer_Leverkusen_Logo.svg.png",
    "Eintracht Frankfurt":     f"{W}/de/thumb/3/32/Logo_Eintracht_Frankfurt_1998.svg/60px-Logo_Eintracht_Frankfurt_1998.svg.png",
    "VfB Stuttgart":           f"{W}/commons/thumb/e/eb/VfB_Stuttgart_1893_Logo.svg/60px-VfB_Stuttgart_1893_Logo.svg.png",
    "TSG Hoffenheim":          f"{W}/commons/thumb/e/e7/Logo_TSG_Hoffenheim.svg/60px-Logo_TSG_Hoffenheim.svg.png",
    "SC Freiburg":             f"{W}/de/thumb/b/bf/SC_Freiburg_Logo.svg/60px-SC_Freiburg_Logo.svg.png",
    "FC Augsburg":             f"{W}/de/thumb/b/b5/Logo_FC_Augsburg.svg/60px-Logo_FC_Augsburg.svg.png",
    "1. FSV Mainz 05":         f"{W}/commons/thumb/9/9e/Logo_Mainz_05.svg/60px-Logo_Mainz_05.svg.png",
    "1. FC Union Berlin":      f"{W}/commons/thumb/4/44/1._FC_Union_Berlin_Logo.svg/60px-1._FC_Union_Berlin_Logo.svg.png",
    "Borussia Mönchengladbach":f"{W}/commons/thumb/8/81/Borussia_M%C3%B6nchengladbach_logo.svg/60px-Borussia_M%C3%B6nchengladbach_logo.svg.png",
    "Hamburger SV":            f"{W}/commons/thumb/f/f7/Hamburger_SV_logo.svg/60px-Hamburger_SV_logo.svg.png",
    "1. FC Köln":              f"{W}/commons/thumb/0/01/1._FC_Koeln_Logo_2014%E2%80%93.svg/60px-1._FC_Koeln_Logo_2014%E2%80%93.svg.png",
    "SV Werder Bremen":        f"{W}/commons/thumb/b/be/SV-Werder-Bremen-Logo.svg/60px-SV-Werder-Bremen-Logo.svg.png",
    "FC Schalke 04":           f"{W}/commons/thumb/6/6d/FC_Schalke_04_Logo.svg/60px-FC_Schalke_04_Logo.svg.png",
    "SC Paderborn 07":         f"{W}/commons/thumb/6/67/SC_Paderborn_07_Logo_new.svg/60px-SC_Paderborn_07_Logo_new.svg.png",
    "SV Elversberg":           f"{W}/commons/thumb/d/d4/SV_Elversberg_Logo_2021.svg/60px-SV_Elversberg_Logo_2021.svg.png",
    "Bundesliga":              "https://upload.wikimedia.org/wikipedia/en/thumb/d/df/Bundesliga_logo_%282017%29.svg/120px-Bundesliga_logo_%282017%29.svg.png",
}

def feed_laden():
    if FEED_JSON.exists():
        return json.loads(FEED_JSON.read_text(encoding="utf-8"))
    return []

def feed_speichern(data):
    FEED_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def artikel_html_lesen(pfad):
    p = Path(pfad)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")

def artikel_titel_aus_html(html):
    m = re.search(r'<h1 class="artikel-titel">(.*?)</h1>', html)
    return m.group(1) if m else ""

def artikel_text_aus_html(html):
    m = re.search(r'<div class="artikel-text">(.*?)</div>', html, re.DOTALL)
    if not m:
        return ""
    return re.sub(r'<p>(.*?)</p>', r'\1\n\n', m.group(1), flags=re.DOTALL).strip()

def logo_optionen(aktuell):
    opts = ""
    for name, url in LOGOS.items():
        sel = 'selected' if url == aktuell else ''
        opts += f'<option value="{url}" {sel}>{name}</option>\n'
    return opts

CSS = """
body { font-family: -apple-system, sans-serif; background: #0d0d0d; color: #e0e0e0; margin: 0; padding: 20px; }
h1 { color: #e8c000; margin-bottom: 20px; }
h2 { color: #e8c000; font-size: 16px; margin-bottom: 12px; }
a { color: #e8c000; }
.card { background: #161616; border: 1px solid #2a2a2a; border-radius: 8px; padding: 16px; margin-bottom: 12px; display: flex; align-items: center; gap: 14px; }
.card img { width: 40px; height: 40px; object-fit: contain; }
.card-body { flex: 1; }
.card-title { font-weight: 700; font-size: 14px; margin-bottom: 4px; }
.card-meta { font-size: 12px; color: #666; }
.btn { padding: 6px 14px; border-radius: 5px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-edit { background: #e8c000; color: #000; }
.btn-del  { background: #c62828; color: #fff; }
.btn-save { background: #2e7d32; color: #fff; padding: 10px 24px; font-size: 14px; }
.form-group { margin-bottom: 16px; }
label { display: block; font-size: 12px; color: #aaa; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
input[type=text], textarea, select { width: 100%; background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 5px; color: #e0e0e0; padding: 8px 12px; font-size: 14px; box-sizing: border-box; }
textarea { min-height: 200px; font-family: inherit; line-height: 1.6; }
select { height: 36px; }
.login-box { max-width: 360px; margin: 100px auto; background: #161616; border: 1px solid #2a2a2a; border-radius: 8px; padding: 32px; }
.warn { background: #c62828; color: #fff; padding: 10px 16px; border-radius: 5px; margin-bottom: 16px; font-size: 13px; }
"""

class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args): pass  # Logs unterdrücken

    def send_html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def auth_ok(self):
        from http.cookies import SimpleCookie
        cookie_header = self.headers.get("Cookie", "")
        c = SimpleCookie(cookie_header)
        return c.get("auth") and c["auth"].value == PASSWORT

    def login_page(self, fehler=False):
        warn = '<div class="warn">Falsches Passwort</div>' if fehler else ""
        return f"""<!DOCTYPE html><html><head><title>Admin Login</title>
        <style>{CSS}</style></head><body>
        <div class="login-box">
          <h1>Admin</h1>{warn}
          <form method="POST" action="/login">
            <div class="form-group"><label>Passwort</label>
            <input type="password" name="pw" autofocus /></div>
            <button class="btn btn-save" type="submit">Einloggen</button>
          </form>
        </div></body></html>"""

    def uebersicht(self):
        artikel = feed_laden()
        karten = ""
        for a in artikel:
            wappen = a.get("wappen_url", "")
            img = f'<img src="{wappen}" />' if wappen else '<div style="width:40px;height:40px;background:#333;border-radius:50%"></div>'
            karten += f"""
            <div class="card">
              {img}
              <div class="card-body">
                <div class="card-title">{a['titel']}</div>
                <div class="card-meta">{a['datum']} · {a['badge']}</div>
              </div>
              <a href="/edit?id={a['id']}"><button class="btn btn-edit">Bearbeiten</button></a>
              <form method="POST" action="/delete" style="margin:0">
                <input type="hidden" name="id" value="{a['id']}" />
                <button class="btn btn-del" onclick="return confirm('Wirklich löschen?')">Löschen</button>
              </form>
            </div>"""
        return f"""<!DOCTYPE html><html><head><title>Ligaoutsider Admin</title>
        <style>{CSS}</style></head><body>
        <h1>⚽ Ligaoutsider Admin</h1>
        <p style="color:#666;margin-bottom:20px">{len(artikel)} Artikel · <a href="/logout">Ausloggen</a></p>
        {karten}
        </body></html>"""

    def edit_page(self, aid, fehler=None):
        artikel = feed_laden()
        a = next((x for x in artikel if x["id"] == aid), None)
        if not a:
            self.send_html("<h1>Nicht gefunden</h1>", 404); return
        html = artikel_html_lesen(a["pfad"])
        titel = artikel_titel_aus_html(html) or a["titel"]
        text  = artikel_text_aus_html(html)
        logo_opts = logo_optionen(a.get("wappen_url", ""))
        warn = f'<div class="warn">{fehler}</div>' if fehler else ""
        return f"""<!DOCTYPE html><html><head><title>Bearbeiten</title>
        <style>{CSS}</style></head><body>
        <h1><a href="/">← Zurück</a></h1>
        <h2>Artikel bearbeiten</h2>{warn}
        <form method="POST" action="/save">
          <input type="hidden" name="id" value="{aid}" />
          <div class="form-group"><label>Titel</label>
            <input type="text" name="titel" value="{titel}" /></div>
          <div class="form-group"><label>Vereinslogo</label>
            <select name="wappen_url">{logo_opts}</select></div>
          <div class="form-group"><label>Text (Absätze mit Leerzeile trennen)</label>
            <textarea name="text">{text}</textarea></div>
          <button class="btn btn-save" type="submit">💾 Speichern</button>
        </form>
        </body></html>"""

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/logout":
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", "auth=; Max-Age=0; Path=/")
            self.end_headers(); return

        if not self.auth_ok():
            self.send_html(self.login_page()); return

        if path == "/" or path == "":
            self.send_html(self.uebersicht())
        elif path == "/edit":
            params = parse_qs(parsed.query)
            aid = params.get("id", [""])[0]
            self.send_html(self.edit_page(aid))
        else:
            self.send_html("<h1>404</h1>", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)

        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/login":
            pw = params.get("pw", [""])[0]
            if pw == PASSWORT:
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"auth={PASSWORT}; Path=/; HttpOnly")
                self.end_headers()
            else:
                self.send_html(self.login_page(fehler=True))
            return

        if not self.auth_ok():
            self.send_html(self.login_page()); return

        if path == "/delete":
            aid = params.get("id", [""])[0]
            artikel = feed_laden()
            a = next((x for x in artikel if x["id"] == aid), None)
            if a:
                Path(a["pfad"]).unlink(missing_ok=True)
                artikel = [x for x in artikel if x["id"] != aid]
                feed_speichern(artikel)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        elif path == "/save":
            aid        = params.get("id", [""])[0]
            neuer_titel = params.get("titel", [""])[0]
            neuer_text  = params.get("text", [""])[0]
            neue_url    = params.get("wappen_url", [""])[0]

            artikel = feed_laden()
            idx = next((i for i, x in enumerate(artikel) if x["id"] == aid), None)
            if idx is None:
                self.send_html("<h1>Nicht gefunden</h1>", 404); return

            # feed.json aktualisieren
            artikel[idx]["titel"]     = neuer_titel
            artikel[idx]["wappen_url"] = neue_url
            feed_speichern(artikel)

            # HTML-Datei aktualisieren
            pfad = Path(artikel[idx]["pfad"])
            if pfad.exists():
                html = pfad.read_text(encoding="utf-8")
                # Titel ersetzen
                html = re.sub(r'<h1 class="artikel-titel">.*?</h1>',
                              f'<h1 class="artikel-titel">{neuer_titel}</h1>', html)
                # Text ersetzen
                absaetze = "".join(f"<p>{p.strip()}</p>"
                                   for p in neuer_text.split("\n\n") if p.strip())
                html = re.sub(r'<div class="artikel-text">.*?</div>',
                              f'<div class="artikel-text">{absaetze}</div>',
                              html, flags=re.DOTALL)
                # Wappen ersetzen
                if neue_url:
                    html = re.sub(
                        r'<img src="[^"]*" class="artikel-wappen"[^>]*/?>',
                        f'<img src="../{neue_url}" class="artikel-wappen" alt="Wappen" />',
                        html)
                pfad.write_text(html, encoding="utf-8")

            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

if __name__ == "__main__":
    print("=" * 50)
    print("  Ligaoutsider Admin läuft")
    print("  → http://localhost:5001")
    print("  Passwort: ligaoutsider2026")
    print("  Stoppen: Ctrl+C")
    print("=" * 50)
    HTTPServer(("", 5001), Handler).serve_forever()
