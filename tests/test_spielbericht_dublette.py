"""S7.6: Spielbericht ist kein Doppel zu einem Artikel über eine andere Partie desselben Klubs."""
import datetime
import unittest

import storys


def eintrag(titel, summary, klubs, spieler, stunden_alt=0):
    return {"id": titel[:8], "titel": titel, "zeit": datetime.datetime(2026, 11, 8, 18) - datetime.timedelta(hours=stunden_alt),
            "person": "", "summary": summary, "stufe": "spielbericht", "klasse": "spiel",
            "spieler": {storys.falten(s) for s in spieler}, "klubs": set(klubs)}


def geschichte(titel, summary, klubs, spieler):
    return {"titel": titel, "person": spieler[0], "spieler": spieler, "klub": klubs[0], "klubs": klubs,
            "stufe": "spielbericht", "klasse": "spiel", "summary": summary}


class SpielberichtDublette(unittest.TestCase):
    jetzt = datetime.datetime(2026, 11, 8, 18, 47)

    def test_andere_partie_mit_anderem_ergebnis_ist_kein_doppel(self):
        alt = eintrag("Leverkusen in der Krise: Andrich kritisiert García nach 0:1 gegen Marseille",
                      "Nach dem 0:1 gegen Marseille kritisiert Andrich García.", ["Leverkusen"], ["Aleix García"], 44)
        neu = geschichte("Garcia-Freistoß entscheidet Derby: Köln verliert 1:2 gegen Leverkusen",
                         "Leverkusen gewinnt 2:1 in Köln.", ["Köln", "Leverkusen"], ["Aleix García"])
        self.assertNotEqual(storys.archiv_abgleich(neu, [alt], self.jetzt)[0], "doppelt")

    def test_gleiche_partie_bleibt_doppelt(self):
        alt = eintrag("VfB Stuttgart gewinnt 1:0 gegen Werder", "Mittelstädt trifft zum 1:0.", ["Stuttgart", "Werder"], ["Maximilian Mittelstädt"], 3)
        neu = geschichte("Mittelstädt trifft früh: Stuttgart schlägt Werder 1:0", "Stuttgart siegt 1:0.", ["Stuttgart", "Werder"], ["Maximilian Mittelstädt"])
        status, treffer = storys.archiv_abgleich(neu, [alt], self.jetzt)
        self.assertEqual(status, "doppelt")
        self.assertIs(treffer[0], alt)

    def test_ohne_spielstand_anderer_gegner_ist_kein_doppel(self):
        alt = eintrag("Leverkusen siegt bei Bremen dank Schick", "Schick trifft doppelt.", ["Leverkusen", "Werder"], ["Patrik Schick"], 20)
        neu = geschichte("Leverkusen gewinnt Derby in Köln dank Schick", "Schick entscheidet das Derby.", ["Köln", "Leverkusen"], ["Patrik Schick"])
        self.assertTrue(storys.andere_partie(neu, alt, self.jetzt))
        self.assertNotEqual(storys.archiv_abgleich(neu, [alt], self.jetzt)[0], "doppelt")

    def test_ohne_spielstand_und_gegner_entscheidet_der_abstand(self):
        alt = eintrag("Leverkusen in der Krise: Andrich kritisiert García", "Andrich kritisiert García öffentlich.", ["Leverkusen"], ["Aleix García"], 44)
        neu = geschichte("Leverkusen gewinnt Derby in Köln dank García", "García entscheidet das Derby.", ["Köln", "Leverkusen"], ["Aleix García"])
        self.assertTrue(storys.andere_partie(neu, alt, self.jetzt))
        frisch = eintrag("Leverkusen gewinnt in Köln dank García", "García trifft per Freistoß.", ["Leverkusen"], ["Aleix García"], 3)
        self.assertFalse(storys.andere_partie(neu, frisch, self.jetzt))
        self.assertEqual(storys.archiv_abgleich(neu, [frisch], self.jetzt)[0], "doppelt")

    def test_ergebnisse_ohne_uhrzeit_und_seite(self):
        self.assertEqual(storys.ergebnisse("Anpfiff 18:30, Endstand 1:2, Pause 0:1"), {(1, 2), (0, 1)})
        self.assertEqual(storys.ergebnisse("2:1"), storys.ergebnisse("1:2"))
        self.assertEqual(storys.ergebnisse("Leipzig schlägt Augsburg 5:2: Gruda glänzt"), {(2, 5)})


if __name__ == "__main__":
    unittest.main()
