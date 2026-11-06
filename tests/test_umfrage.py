import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import umfrage  # noqa: E402

WEISER = ("Werders Mittelfeldspieler Mitchell Weiser hat sich gegen Hoffenheim früh verletzt. "
          "Im Juli 2025 hatte er sich einen Kreuzbandriss zugezogen.")
SPIEL = "Frankfurt schlägt den HSV mit 3:1. Uzun trifft doppelt."
TRANSFER = "Laut Bericht sind Bayern und der BVB über Zubimendis Lage informiert. Zubimendi denkt über einen Abschied nach."
HOENESS = "Uli Hoeneß kritisiert die Länderspielpause: „Ein Desaster der UEFA“, sagte Hoeneß."


class Umfrage(unittest.TestCase):
    def test_verletzung_gibt_reaktion(self):
        u = umfrage.waehlen("verletzung", "verletzung", WEISER, {"typ": "keine", "frage": ""})
        self.assertEqual(u["typ"], "reaktion")

    def test_sperre_ohne_verletzung_gibt_nichts(self):
        self.assertIsNone(umfrage.waehlen("ausfall", "news", "Bah ist nach Roter Karte zwei Spiele gesperrt.", None))

    def test_spielbericht_braucht_ergebnis(self):
        self.assertEqual(umfrage.waehlen("spielbericht", "news", SPIEL, None)["typ"], "spiel")
        self.assertIsNone(umfrage.waehlen("spielbericht", "news", "Frankfurt gewinnt das Testspiel 3:1.", None))
        self.assertIsNone(umfrage.waehlen("spielbericht", "news", "Frankfurt empfängt den HSV.", None))

    def test_deal_mit_name_aus_dem_text(self):
        ki = {"typ": "deal", "frage": "Wäre Zubimendi ein guter Deal für Bayern?"}
        self.assertEqual(umfrage.waehlen("geruecht", "transfer", TRANSFER, ki)["typ"], "deal")

    def test_deal_mit_fremdem_namen_fliegt(self):
        ki = {"typ": "deal", "frage": "Wäre Rodri ein guter Deal für Real?"}
        self.assertIsNone(umfrage.waehlen("geruecht", "transfer", TRANSFER, ki))

    def test_deal_nur_bei_transfer_oder_vertrag(self):
        ki = {"typ": "deal", "frage": "Wäre Zubimendi ein guter Deal für Bayern?"}
        self.assertIsNone(umfrage.waehlen("kader", "news", TRANSFER, ki))

    def test_recht_braucht_zitat_und_hat(self):
        ki = {"typ": "recht", "frage": "Hat Hoeneß recht mit seiner Kritik an der Länderspielpause?"}
        self.assertEqual(umfrage.waehlen("sonstiges", "interview", HOENESS, ki)["typ"], "recht")
        self.assertIsNone(umfrage.waehlen("sonstiges", "interview", HOENESS.replace("„", '"'), ki))
        self.assertIsNone(umfrage.waehlen("sonstiges", "interview", HOENESS,
                                          {"typ": "recht", "frage": "Was denkt ihr über Hoeneß?"}))

    def test_fremde_zahl_fliegt(self):
        ki = {"typ": "recht", "frage": "Hat Hoeneß recht, dass 12 Spiele zu viel sind?"}
        self.assertIsNone(umfrage.waehlen("sonstiges", "interview", HOENESS, ki))

    def test_zahl_als_teil_einer_groesseren_fliegt(self):
        text = "Uli Hoeneß kritisiert die 30 Millionen Ablöse: „Ein Desaster“, sagte Hoeneß."
        ki = {"typ": "recht", "frage": "Hat Hoeneß recht, dass 3 Millionen zu viel sind?"}
        self.assertIsNone(umfrage.waehlen("sonstiges", "interview", text, ki))

    def test_sensibles_thema_gibt_nichts(self):
        text = WEISER + " Die Staatsanwaltschaft ermittelt."
        self.assertIsNone(umfrage.waehlen("verletzung", "verletzung", text, None))

    def test_box_escaped_und_nur_mit_gueltiger_id(self):
        u = {"typ": "recht", "frage": "Hat <b>Hoeneß</b> recht?", "antworten": ["Ja", "Nein"]}
        h = umfrage.box_html("0123456789", u)
        self.assertIn("&lt;b&gt;", h)
        self.assertNotIn("<b>", h)
        self.assertEqual(umfrage.box_html("../x", u), "")
        self.assertEqual(umfrage.box_html("0123456789", None), "")


if __name__ == "__main__":
    unittest.main()
