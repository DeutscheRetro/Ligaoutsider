"""Kaputte Zustandsdateien dürfen den Lauf nicht mit leeren Daten weiterlaufen lassen oder abstürzen."""
import os, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generate as g
from url_cache import URLCache


class Robust(unittest.TestCase):
    def test_kaputter_url_cache_eintrag(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "seen.json"
            p.write_text('{"a": "kaputt", "b": 5, "c": "%s"}' % datetime.now().isoformat(), encoding="utf-8")
            c = URLCache(str(p))
            self.assertEqual(list(c.seen_urls), ["c"])
            c.save()
            self.assertFalse((Path(t) / "seen.json.tmp").exists())

    def test_url_cache_alte_url_schluessel_bleiben_gesehen(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "seen.json"
            url = "https://news.google.com/rss/articles/abc"
            p.write_text('{"%s": "%s"}' % (url, datetime.now().isoformat()), encoding="utf-8")
            c = URLCache(str(p))
            self.assertTrue(c.is_seen(url))
            c.mark_seen("https://example.org/x")
            c.save()
            self.assertTrue(URLCache(str(p)).is_seen("https://example.org/x"))
            self.assertNotIn("http", p.read_text(encoding="utf-8"))

    def test_kaputter_feed_bricht_ab(self):
        with tempfile.TemporaryDirectory() as t:
            alt = g.FEED_JSON
            g.FEED_JSON = Path(t) / "feed.json"
            g.FEED_JSON.write_text("{kaputt", encoding="utf-8")
            try:
                with self.assertRaises(RuntimeError):
                    g.feed_laden()
            finally:
                g.FEED_JSON = alt

    def test_atomar_schreiben(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.json"
            g._atomar_schreiben(p, "[]")
            self.assertEqual(p.read_text(encoding="utf-8"), "[]")
            self.assertFalse((Path(t) / "x.json.tmp").exists())


class Auswahl(unittest.TestCase):
    def test_feedzeit_in_ortszeit(self):
        import time
        t = time.gmtime(1_700_000_000)
        self.assertEqual(g._pub_lokal(t), datetime.fromtimestamp(1_700_000_000))

    def test_paywall_nur_ganze_woerter(self):
        regel = g.PAYWALL_RE
        self.assertIsNone(regel.search("kaboré trifft im labor"))
        self.assertTrue(regel.search("lesen sie weiter im abo"))


if __name__ == "__main__":
    unittest.main()
