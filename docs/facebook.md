# Facebook-Seite automatisch bespielen

`social.py` postet jeden neuen Artikel als Link-Post auf die Facebook-Seite, sobald die Artikelseite live ist.
Facebook holt Titel und Bild aus den OG-Tags der Seite. Gleiche Regeln wie Bluesky/Telegram:
höchstens 15 Posts je Lauf, Artikel älter als 48 Stunden werden verworfen.

## Einmalige Einrichtung (ca. 15 Minuten)

1. **App anlegen**: https://developers.facebook.com/apps → „App erstellen“ → Typ „Business“ (oder „Sonstiges“), Name z. B. „Ligaoutsider Poster“.
   Die App bleibt im Entwicklungsmodus. Das reicht, weil nur die eigene Seite bespielt wird; eine App-Prüfung ist dafür nicht nötig.
2. **Seiten-ID**: Facebook-Seite öffnen → „Info“ → ganz unten „Seiten-ID“. Das ist `FB_PAGE_ID`.
3. **Seiten-Token holen** (Graph API Explorer, https://developers.facebook.com/tools/explorer):
   - oben rechts die App wählen
   - „Nutzer oder Seite“ → „Seiten-Zugriffsschlüssel“ → die Ligaoutsider-Seite
   - Berechtigungen hinzufügen: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`
   - „Generate Access Token“, Anmeldung bestätigen
4. **Token dauerhaft machen** (sonst läuft er nach 1 Stunde ab):
   - Im Explorer den erzeugten Token kopieren und im Access Token Debugger (https://developers.facebook.com/tools/debug/accesstoken) einfügen → „Extend Access Token“ → ergibt einen **langlebigen Nutzer-Token** (60 Tage)
   - Mit diesem Nutzer-Token im Explorer `GET /me/accounts` aufrufen → in der Antwort steht `access_token` der Seite. Ein Seiten-Token, der aus einem langlebigen Nutzer-Token stammt, **läuft nicht ab**.
   - Kontrolle im Debugger: „Expires: Never“. Das ist `FB_PAGE_TOKEN`.
5. **GitHub-Secrets** im Repo unter Settings → Secrets and variables → Actions:
   `FB_PAGE_ID` und `FB_PAGE_TOKEN`.
6. **Test**: Actions → „Social Media posten“ → Run workflow. Im Log erscheint `✅ facebook: …` oder eine Fehlermeldung von Facebook.

## Wenn es nicht postet
- `(#200) ... permission`: Token ohne `pages_manage_posts`, Schritt 3 wiederholen.
- `Error validating access token`: Token abgelaufen oder Passwort geändert, Schritt 3 und 4 wiederholen.
- Kein Vorschaubild: Facebook hat die Seite gecacht. Im Sharing Debugger (https://developers.facebook.com/tools/debug/) die URL einmal „Scrape Again“.
