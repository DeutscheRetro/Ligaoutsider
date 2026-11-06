import os
import tempfile
import unittest
from pathlib import Path

from feed_nachziehen import nachziehen


class NachziehenTest(unittest.TestCase):
    def setUp(self):
        self.alt = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        Path("artikel").mkdir()
        for n in ("a", "b", "c"):
            Path(f"artikel/{n}.html").write_text("x")

    def tearDown(self):
        os.chdir(self.alt)
        self.tmp.cleanup()

    def test_holt_verlorenen_eintrag_zurueck_und_sortiert(self):
        hier = [{"id": "a", "datum": "06.11.2026 15:00", "pfad": "artikel/a.html"}]
        fern = [{"id": "b", "datum": "06.11.2026 15:15", "pfad": "artikel/b.html"}, hier[0]]
        self.assertEqual([x["id"] for x in nachziehen(hier, fern, set())], ["b", "a"])

    def test_ignoriert_geloeschte_und_fehlende_seiten(self):
        hier = [{"id": "a", "datum": "06.11.2026 15:00", "pfad": "artikel/a.html"}]
        fern = [{"id": "c", "datum": "06.11.2026 15:15", "pfad": "artikel/c.html"},
                {"id": "z", "datum": "06.11.2026 15:20", "pfad": "artikel/z.html"}]
        self.assertIs(nachziehen(hier, fern, {"c"}), hier)


if __name__ == "__main__":
    unittest.main()
