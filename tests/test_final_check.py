import datetime
import unittest

import generate


def eintrag(titel, spieler=()):
    return {"title": titel, "published_at": datetime.datetime.now().isoformat(),
            "main_club": "Borussia Mönchengladbach", "event_stage": "geruecht", "main_players": list(spieler)}


class FinalCheckTest(unittest.TestCase):
    fp = {"main_club": "Borussia Mönchengladbach", "event_stage": "geruecht", "main_players": []}

    def test_ohne_spieler_und_anderer_titel_kein_duplikat(self):
        archiv = [eintrag("Gladbach an Stürmer aus Belgien interessiert", ["Max Muster"])]
        self.assertFalse(generate.final_pre_publish_check("Gladbach plant Wintertransfer für die Abwehr", self.fp, archiv))

    def test_ohne_spieler_aber_gleicher_titel_bleibt_duplikat(self):
        archiv = [eintrag("Gladbach plant Wintertransfer für die Abwehr")]
        self.assertTrue(generate.final_pre_publish_check("Gladbach plant einen Wintertransfer für die Abwehr", self.fp, archiv))

    def test_gemeinsamer_spieler_bleibt_duplikat(self):
        fp = dict(self.fp, main_players=["Max Muster"])
        archiv = [eintrag("Ganz anderer Titel", ["Max Muster"])]
        self.assertTrue(generate.final_pre_publish_check("Gladbach will Muster", fp, archiv))


if __name__ == "__main__":
    unittest.main()
