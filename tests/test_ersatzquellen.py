"""Themen, die nur von kicker (Bot-Sperre) kommen, bekommen Text von anderen Medien; falsche Treffer nicht."""
import os, sys, unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("ANTHROPIC_API_KEY", "test")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generate as g

G = {"id": "t1", "titel": "Kimmich nach Rückkehr: Hier am absolut richtigen Ort", "spieler": ["Joshua Kimmich"],
     "quellen": [{"url": "https://www.kicker.de/kimmich-1/artikel", "titel": "Kimmich nach Rückkehr", "quelle": "kicker"}]}


def eintrag(titel, link, host, medium):
    return {"title": f"{titel} - {medium}", "link": link, "source": {"href": host, "title": medium}}


class Ersatz(unittest.TestCase):
    def setUp(self):
        self._fp, self._ft, self._dec = g.feedparser.parse, g.fetch_fulltext, g._decode_google_news_url
        g._ERSATZ_GESUCHT.clear()
        g._GOOGLE_FEHLER_IN_FOLGE = 0

    def tearDown(self):
        g.feedparser.parse, g.fetch_fulltext, g._decode_google_news_url = self._fp, self._ft, self._dec

    def test_nur_passende_treffer_ohne_kicker(self):
        g.feedparser.parse = lambda url: SimpleNamespace(entries=[
            eintrag("Kimmich nach Rückkehr: Hier am absolut richtigen Ort", "https://news.google.com/a", "https://www.kicker.de", "kicker"),
            eintrag("Kimmich nach Rückkehr: Hier am absolut richtigen Ort", "https://news.google.com/b", "https://www.bild.de", "BILD"),
            eintrag("Neuer Sponsor für den FC Augsburg", "https://news.google.com/c", "https://www.sport.de", "sport.de"),
            eintrag("Union gewinnt Derby", "https://news.google.com/d", "https://www.faz.net", "FAZ")])
        treffer = g.ergaenzende_quellen(G)
        self.assertEqual([t["url"] for t in treffer], ["https://news.google.com/b"])

    def test_kicker_only_geschichte_bekommt_text(self):
        g.feedparser.parse = lambda url: SimpleNamespace(entries=[
            eintrag("Kimmich nach Rückkehr: Hier am absolut richtigen Ort", "https://news.google.com/b", "https://www.bild.de", "BILD")])
        g._decode_google_news_url = lambda u: "https://www.bild.de/kimmich-ort.html"
        abgerufen = []
        def fake_fetch(u):
            abgerufen.append(u)
            return " ".join(["Kimmich"] * 120), "ok"
        g.fetch_fulltext = fake_fetch
        texte = g.quellen_laden(dict(G))
        self.assertEqual(abgerufen, ["https://www.bild.de/kimmich-ort.html"])   # kicker wurde nicht abgerufen
        self.assertEqual(len(texte), 1)
        self.assertEqual(texte[0]["link"], "https://www.bild.de/kimmich-ort.html")

    def test_suche_nur_einmal_je_geschichte(self):
        aufrufe = []
        g.feedparser.parse = lambda url: (aufrufe.append(url) or SimpleNamespace(entries=[]))
        g.quellen_laden(dict(G)); g.quellen_laden(dict(G))
        self.assertEqual(len(aufrufe), 1)


if __name__ == "__main__":
    unittest.main()
