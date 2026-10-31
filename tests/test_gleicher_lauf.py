"""python3 -m unittest discover tests  –  zwei Fassungen derselben Meldung im selben Lauf (Chatzialexiou, 31.10.)."""
import os, sys, unittest
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test")   # generate.py legt beim Import einen Client an
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generate


def fp(club, spieler, stage):
    return {"main_club": club, "main_players": spieler, "event_stage": stage}


class GleicherLauf(unittest.TestCase):
    def test_chatzialexiou_ist_doppelt(self):
        erster = ("Eintracht Frankfurt holt Joti Chatzialexiou als Sportvorstand", fp("Frankfurt", ["Joti Chatzialexiou"], "vertrag"))
        neu = ("Eintracht Frankfurt holt Joti Chatzialexiou als Krösche-Nachfolger",
               fp("Frankfurt", ["Joti Chatzialexiou", "Markus Krösche"], "vollzogen"))
        self.assertTrue(generate.gleiche_geschichte_im_lauf(neu[0], neu[1], [erster]))

    def test_andere_geschichte_desselben_spielers_bleibt(self):
        verlaengert = ("Bayern verlängert mit Kane bis 2030", fp("Bayern", ["Harry Kane"], "vertrag"))
        verletzt = ("Kane fällt mit Muskelfaserriss gegen Freiburg aus", fp("Bayern", ["Harry Kane"], "verletzung"))
        self.assertFalse(generate.gleiche_geschichte_im_lauf(verletzt[0], verletzt[1], [verlaengert]))

    def test_anderer_klub_bleibt(self):
        a = ("Müller wechselt zu Köln", fp("Köln", ["Müller"], "vollzogen"))
        b = ("Müller wechselt zu Köln", fp("Mainz", ["Müller"], "vollzogen"))
        self.assertFalse(generate.gleiche_geschichte_im_lauf(b[0], b[1], [a]))


if __name__ == "__main__":
    unittest.main()
