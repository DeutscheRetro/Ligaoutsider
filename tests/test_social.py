"""python3 -m unittest discover tests  –  prüft die Postgrenzen in social.py ohne Netzwerk."""
import datetime, json, os, tempfile, unittest, importlib, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class PostFilter(unittest.TestCase):
    def test_grenzen(self):
        alt = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                Path("data").mkdir()
                Path("feed.json").write_text("[]")
                import social
                importlib.reload(social)
                jetzt = datetime.datetime.now().isoformat(timespec="seconds")
                kat = ["transfer", "news", "verletzung", "interview", "analyse", "aufstellung"]
                q = [{"id": str(i), "titel": f"T{i}", "url": "u", "zeit": jetzt, "kategorie": kat[i % 6],
                      "hauptklub": "Bayern" if i < 20 else f"V{i}"} for i in range(60)]
                Path("data/social_queue.json").write_text(json.dumps(q))
                gesendet = {"bluesky": [], "telegram": []}
                social.ist_live = lambda u: True
                social.MAX_POSTS_PRO_LAUF = 100
                social.NETZWERKE = {n: ((), (lambda e, n=n: gesendet[n].append(e))) for n in gesendet}
                social.main()
            finally:
                os.chdir(alt)
        b = gesendet["bluesky"]
        self.assertEqual(len(gesendet["telegram"]), 60)
        self.assertLessEqual(len(b), social.MAX_PRO_TAG)
        self.assertLessEqual(sum(social.ist_gerede(e) for e in b), social.MAX_MEINUNG_PRO_TAG)
        self.assertLessEqual(sum(e["hauptklub"] == "Bayern" for e in b), social.MAX_PRO_VEREIN_PRO_TAG)


if __name__ == "__main__":
    unittest.main()
