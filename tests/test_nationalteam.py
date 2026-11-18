"""Bundesflagge nur für das DFB-Team: "Nationalelf-Berufung" bei einem Argentinier ist kein DFB-Artikel."""
import os
import unittest
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import generate as G
import storys

storys.init(Path("spieler_db.json"), G.VEREIN_FILTER)


class Nationalteam(unittest.TestCase):
    def test_dfb_begriffe_immer(self):
        self.assertTrue(G.ist_nationalteam("El Mala fehlt beim DFB-Training, Mohya als Neuling dabei"))

    def test_fremdes_land_im_titel(self):
        self.assertFalse(G.ist_nationalteam("Gregoritsch steigt mit der österreichischen Nationalmannschaft auf"))

    def test_auslaendischer_spieler_ohne_land_im_titel(self):
        # Equi Fernández spielt für Argentinien (spieler_db.json)
        self.assertFalse(G.ist_nationalteam("Rolfes lobt Fernández: Leverkusens Stammkraft mit Nationalelf-Berufung"))

    def test_deutscher_spieler(self):
        self.assertTrue(G.ist_nationalteam("Klopp nominiert Kölns Said El Mala erneut für die Nationalmannschaft"))

    def test_laenderspielpause_ist_vereinsthema(self):
        self.assertFalse(G.ist_nationalteam("Union nutzt die Länderspielpause"))


if __name__ == "__main__":
    unittest.main()
