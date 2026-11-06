import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import aufstellungen_posten as ap


class OffiziellEintragen(unittest.TestCase):
    def test_traegt_nur_bestaetigte_teams_ein(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "aufstellung.json"
            pfad.write_text(json.dumps({"teams": {"Hamburger SV": {"logo": "logos/hsv.png"},
                                                  "Borussia Mönchengladbach": {"logo": "logos/gladbach.png"}}}))
            p = {"heim": "Hamburger SV", "gast": "Borussia Mönchengladbach",
                 "anpfiff": datetime.datetime(2026, 11, 6, 20, 30)}
            roto = {"logos/hsv.png": {"elf": [("GK", "Heuer Fernandes")] * 11, "bestaetigt": True},
                    "logos/gladbach.png": {"elf": [("GK", "Nicolas")] * 11, "bestaetigt": False}}
            with mock.patch.object(ap.gen, "_comunio_logo", lambda v: "logos/hsv.png" if "Hamburg" in v else "logos/gladbach.png"), \
                 mock.patch.object(ap, "richtiger_name", lambda n, logo: n):
                self.assertEqual(ap.offiziell_eintragen([p], roto, pfad), 1)
                self.assertEqual(ap.offiziell_eintragen([p], roto, pfad), 0)   # unverändert: nichts schreiben
            teams = json.loads(pfad.read_text())["teams"]
            self.assertEqual(teams["Hamburger SV"]["offiziell"]["anstoss"], "2026-11-06T20:30:00")
            self.assertEqual(len(teams["Hamburger SV"]["offiziell"]["elf"]), 11)
            self.assertNotIn("offiziell", teams["Borussia Mönchengladbach"])


if __name__ == "__main__":
    unittest.main()
