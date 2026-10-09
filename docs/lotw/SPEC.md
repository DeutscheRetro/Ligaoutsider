# LotW – Spezifikation (Entwurf v2)

Clean-Room-Western-Dialogspiel, inspiriert von *Law of the West*
(Accolade, 1985). Eigener Code, eigene Texte, Grafiken, Musik und Namen.
Hintergrund steht in [RESEARCH.md](RESEARCH.md).

**Arbeitstitel**: *Sheriff of Dusty Creek* (Titel und Stadtname offen)

## Entscheidungen

| Thema | Entscheidung |
|---|---|
| Plattform | **Steam** (Windows zuerst, Linux/Steam Deck und macOS danach) |
| Sprache | **Englisch**, authentischer Western-Slang |
| Repo | eigenes Repo `LotW` |
| Engine | Vorschlag: **Godot 4** (offen, siehe unten) |

### Warum Godot 4 (Vorschlag)

- Export für Windows, Linux und macOS, läuft auf dem Steam Deck
- Steamworks (Achievements, Cloud-Saves) über die GodotSteam-Erweiterung
- MIT-Lizenz, keine Gebühren
- 2D und Pixel-Art sind eine Stärke der Engine
- Spiellogik in GDScript lässt sich mit GUT ohne Grafik testen

Alternative: TypeScript mit Electron oder Tauri, wenn du lieber im Browser
entwickelst. Das ist für Steam schwerer und schwerer bei der Performance.

## 1. Spielidee

Du bist neu als Sheriff einer kleinen Grenzstadt. Ein Tag, von morgens bis
Sonnenuntergang. Leute kommen auf die Hauptstraße und sprechen dich an:
Freunde, Klatschmäuler, Flirts, Säufer, Ganoven. Mit dem, was du sagst und
ob du ziehst, entscheidest du, wer lebt, wer im Knast landet, welcher
Überfall verhindert wird und was die Stadt am Abend von dir hält.

## 2. Spielschleife

1. **Morgen**: Tagesplan mit ca. 11 Begegnungen. Feste Figuren, die
   Reihenfolge wird teilweise gemischt (Seed). Das Spiel lässt sich
   so wiederholen.
2. **Begegnung**: Figur tritt aus dem Hintergrund, eröffnet das Gespräch.
3. **Gespräch**: 3 Phasen, je 4 Antworten (sanft → hart). Jederzeit ziehen
   möglich (die „fünfte Antwort“).
4. **Ausgang**: friedlich, Verhaftung, Flucht, Date, Hinweis oder Duell.
5. **Folgen**: Hinweise lösen spätere Überfall-Szenen aus. Gelassene Ganoven
   können später als Hinterhalt zurückkommen.
6. **Sonnenuntergang**: Zeitungsartikel bzw. Bewertung in 7 Kategorien.

## 3. Mechaniken

### Dialog
- Gegenüber spricht eine Zeile, du wählst aus 4 Antworten von
  apologetic über friendly und firm bis aggressive. Die Reihenfolge ist
  nicht immer gleich, das Spiel soll nicht durchschaubar sein.
- Jede Figur hat **Stimmung** (−3 … +3) und **Temperament** (Geduld,
  Reizbarkeit, Ziehgeschwindigkeit).
- Bestimmte Antworten setzen **Flags** (z. B. `promised_protection`,
  `knows_bank_job`), die spätere Begegnungen verändern.

### Revolver
- Ziehen: Taste/Stick hoch → Fadenkreuz in der oberen Bildhälfte.
- Ziehen vor dem Eröffnungssatz: Figur schweigt, bis du wegsteckst.
  Ziehen ohne Grund senkt Autorität und Stimmung.
- Passanten fliehen beim Ziehen.
- Wegstecken jederzeit (mit Reaktion des Gegenübers).

### Duell
- Gegner zieht nach einer Wartezeit, die von Temperament und
  Spannung abhängt. Kurzes visuelles oder akustisches Signal (wählbar),
  denn Fairness ist uns wichtiger als im Original.
- Treffer am Gegner: tot oder verwundet (je nach Zielpunkt), ein
  Schuss in den Arm erlaubt eine Verhaftung.
- Wirst du getroffen: Blackout, der **Doc** kommt. Ob er rettet,
  hängt ab von Beziehung, Nüchternheit (wurde er zum Trinken verleitet?)
  und ob er in der Stadt ist. Rettung kostet Zeit und Autorität.
  Keine Rettung → Spielende.

### Überfälle
- Drei mögliche Überfälle (Zug, Kutsche, Bank), eigene Banden.
- Nur mit dem passenden Hinweis aus einem Gespräch kannst du eingreifen:
  Dann folgt eine Schießerei mit mehreren namenlosen Räubern (Ziele tauchen
  hinter Deckungen auf).
- Ohne Hinweis: Nachricht später („The bank's been hit!“), Autorität sinkt.

### Wertung (7 Kategorien, je 0–12)
1. Authority (Autorität)
2. Outlaws jailed
3. Outlaws shot
4. Innocents shot (negativ)
5. Crimes prevented
6. Romance
7. Town's opinion / Survival (offen)

Gesamttitel: z. B. *Greenhorn → Tin Star → Lawman → Marshal → Legend of
the West*.

## 4. Besetzung (eigene Figuren)

Archetypen wie im Original, aber eigene Namen, Persönlichkeiten und Texte:

| Archetyp | Arbeitsname | Funktion |
|---|---|---|
| Fremder mit Tipp | *The Drifter* | Hinweis auf Zugüberfall |
| Saloon-Wirtin | *Lulu Delacroix* | Flirt, Hinweis gegen Schutz |
| Arzt mit Alkoholproblem | *Doc Hollis* | Rettet dich oder nicht |
| Lehrerin | *Miss Prudence* | Klatsch, Date |
| Kind mit Geheimnis | *Tad* | Hinweis gegen Süßigkeiten |
| Viehdiebin | *Calamity Rae* | Verhaftung, Freundschaft oder Duell |
| Grenzflüchtling | *El Coyote* | Gefährlich, Hinterhalt |
| Unzuverlässiger Deputy | *Deputy Buck* | Autorität, ggf. Duell |
| Angeber mit neuer Waffe | *Jimmy Two-Barrels* | Entschärfen oder Duell |
| Falschspieler | *Silk Everett* | Laufen lassen oder stellen |
| Letzter Revolverheld | *The Man in Black* | Finale am Abend |

## 5. Sprache und Ton

- Englisch mit glaubwürdigem Western-Slang, keine Parodie, aber mit
  trockenem Humor.
- Ein kleiner Glossar und Styleguide (`content/STYLE.md`) hält den Ton
  über alle Figuren gleich.
- Dialoge als Daten (JSON oder YAML), später lokalisierbar (z. B. Deutsch).

## 6. Technik und Struktur (Godot-Vorschlag)

```
LotW/
  project.godot
  core/        # reine Spiellogik: Tag, Dialog, Wertung, Zufall (Seed)
  content/     # Dialoge, Figuren, Tagesplan als JSON
  scenes/      # Straße, Begegnung, Duell, Wertung, Menü
  art/ audio/  # eigene Assets
  tests/       # GUT-Tests für core/
  docs/        # RESEARCH.md, SPEC.md
```

- Logik und Darstellung strikt getrennt, Logik deterministisch über Seed.
- Ein Dialog-Validator prüft, ob alle Knoten erreichbar sind und jeder Pfad
  ein Ende hat.
- CI auf GitHub Actions: Tests und Exportbuild.

## 7. Meilensteine

1. **M1 – Kern**: Dialogengine, Flags, Tagesablauf, Wertung, Tests.
   Drei Figuren, Text-Platzhalter-UI.
2. **M2 – Spielbar**: alle 11 Begegnungen als Rohtext, Duell mit Fadenkreuz,
   Doc-Rettung, Überfälle.
3. **M3 – Look & Sound**: Pixel-Art-Straße, Figuren, Animationen, Musik und
   Soundeffekte (eigene oder lizenzierte).
4. **M4 – Steam**: Menüs, Optionen, Speichern, Achievements, Steam-Deck-
   Steuerung, Store-Seite.

## 8. Offene Fragen

- Engine: Godot 4 in Ordnung?
- Endgültiger Titel und Stadtname?
- Grafikstil: C64-nah (wenige Farben, große Pixel) oder modernes Pixel-Art?
- Soll es wie das Original ein einziger kurzer Tag bleiben (ca. 20–30 Min.),
  oder mehrere Tage/Kampagne für den Steam-Preis?
