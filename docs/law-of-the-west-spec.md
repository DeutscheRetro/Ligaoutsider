# Law of the West – Neubau (Spezifikation, Entwurf)

Clean-Room-Nachbau eines Western-Dialogspiels im Stil des C64-Klassikers
*Law of the West* (Accolade, 1985). Es wird kein Originalcode und kein
Originalmaterial verwendet. Name, Dialoge, Grafiken und Sounds sind
eigene Werke. Der Arbeitstitel ist **Sheriff of Dusty Creek**.

> Alles, was ich aus dem Original beschreibe, stammt aus dem Gedächtnis und
> ist **nicht verifiziert**. Mit `[prüfen]` markierte Punkte müssen gegen
> Handbuch, Videos oder eigenes Spielen geprüft werden.

## 1. Spielidee

Der Spieler ist Sheriff einer Westernstadt. Pro Tag kommen Figuren in die
Stadt und sprechen ihn an. Er wählt aus Antworten und entscheidet,
ob er sie verhaftet, vertreibt, ins Gefängnis steckt oder in Ruhe lässt.
Falsche Entscheidungen führen zu Streit oder Duell. Das Ziel ist, die Stadt
sicher zu halten und möglichst viele Punkte (Rang, Geld) zu erreichen.

## 2. Spielschleife

1. **Tagesbeginn**: Eine Zufallsliste von Besuchern wird erzeugt (Seed).
2. **Begegnung**: Ein Besucher erscheint, ein Dialog läuft ab.
3. **Auswahl**: Der Spieler wählt eine von 2–4 Antworten.
4. **Auflösung**: Zustand ändert sich, Folge: Ende, Verhaftung, Duell, Tod.
5. **Tagesende**: Abrechnung (Punkte, Ruf), nächster Tag oder Spielende.

## 3. Datenmodell

```ts
type Character = {
  id: string;
  name: string;
  role: "bürger" | "gauner" | "reisender" | "ganove-gesucht" | "händler";
  mood: number;        // -2 (feindselig) .. +2 (freundlich)
  guilt: boolean;      // gesucht? (für den Spieler zunächst verborgen)
  dialogStart: string; // Id des ersten Dialogknotens
};

type DialogNode = {
  id: string;
  text: string;
  options: {
    text: string;
    next?: string;             // weiterer Dialogknoten
    outcome?: Outcome;         // oder direktes Ergebnis
    requires?: Condition[];
  }[];
};

type Outcome =
  | { kind: "arrest" }
  | { kind: "banish" }
  | { kind: "duel"; difficulty: number }
  | { kind: "ignore" }
  | { kind: "reward"; amount: number };

type GameState = {
  day: number;
  reputation: number;  // Ruf bei den Bürgern
  money: number;
  health: number;
  jail: Character[];
  rngSeed: number;
};
```

## 4. Regeln (Eigenentwurf)

- **Stimmung**: Jede Antwort ändert `mood` des Gegenübers. Bei `-2` droht
  ein Duell, bei `+2` bessere Hinweise.
- **Schuld**: Ein Besucher mit `guilt = true` lässt sich nur durch
  passende Fragen (Hinweise im Dialogbaum) überführen. Falsche Verhaftung
  senkt den Ruf. `[prüfen: Original nutzt wohl Steckbrief-Abgleich]`
- **Duell**: Echtzeitminispiel. Nach zufälliger Wartezeit erscheint ein
  Signal, der Spieler muss schneller schießen als der Gegner.
  Schwierigkeit bestimmt die Reaktionszeit des Gegners.
- **Rang**: Aus Ruf, Geld und gelösten Fällen wird ein Titel berechnet
  (Hilfssheriff → Sheriff → Marshal).

## 5. Technik

- Reines TypeScript, Spiellogik in `core/` ohne DOM-Zugriff und mit
  deterministischem Zufall (Seed), damit alles testbar ist.
- Oberfläche in `ui/` (Canvas oder DOM). Optik im Pixel-Look, gerne an den
  C64 angelehnt (16 Farben, 320x200), mit eigenen Grafiken.
- Dialoge als JSON in `content/`, leicht erweiterbar.
- Tests: Vitest für Dialogbaum, Ergebnisse und Duell-Timing.

## 6. Meilensteine

1. **M1** Kern ohne UI: Dialogengine, Zustand, ein Tag mit 3 Besuchern, Tests.
2. **M2** Textbasierte Oberfläche, Duell als einfacher Reaktionstest.
3. **M3** Pixel-UI, Sprites, Sound (eigene Assets).
4. **M4** 15–20 Charaktere, Tageszyklus, Rangliste, Speichern.

## 7. Offene Fragen

- Spielen wir das Original nach, um Abläufe zu vergleichen? (Dann brauche ich
  Beobachtungsnotizen oder Aufzeichnungen davon.)
- Zielplattform: Browser oder nativ?
- Ton der Dialoge: ernst, humorvoll, deutsch oder englisch?
- Soll das Projekt hier im Repo bleiben oder in ein eigenes Repo?

## 8. Rechtliches

Nachbau der Spielidee mit eigenem Code und eigenen Inhalten. Keine
Original-ROMs, -Grafiken, -Texte oder -Sounds. Den Originalnamen verwenden
wir für eine Veröffentlichung nicht.
