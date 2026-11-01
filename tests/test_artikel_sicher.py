"""Sicherheits-Regression: Feed- und KI-Texte dürfen kein HTML einschleusen; interne Adressen werden nicht abgerufen."""
import os, sys, unittest
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generate as g


class ArtikelSicher(unittest.TestCase):
    def test_kein_html_aus_feed(self):
        h = g.artikel_html("abc1234567", 'T </title><script>alert(1)</script> & "x"',
                           "A <img src=x onerror=alert(2)> Müller & Co\n\nZwei", "transfer", "Q",
                           'https://a.de/x" onmouseover="alert(3)', "01.11.2026 10:00", 'x" onerror="alert(4)')
        for roh in ("<script>alert", "<img src=x onerror", 'onmouseover="alert', 'onerror="alert(4)'):
            self.assertNotIn(roh, h)
        self.assertIn("<p>A &lt;img", h)

    def test_nur_oeffentliche_hosts(self):
        for u in ("http://127.0.0.1/", "http://169.254.169.254/x", "http://localhost", "file:///etc/passwd"):
            self.assertFalse(g._host_oeffentlich(u), u)

    def test_json_ld_bleibt_gueltig(self):
        import json, re
        h = g.artikel_html("abc1234567", 'Müller & Co </script> "x"', "Text &amp; mehr <b>x</b>\n\nZwei", "transfer", "Q",
                           "https://a.de/x?a=1&b=2", "01.11.2026 10:00", "logos/x.png")
        blöcke = re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
        self.assertTrue(blöcke)
        for b in blöcke:
            json.loads(b)

    def test_liga_schalter_in_vorlagen(self):
        h = g.artikel_html("abc1234567", "Titel", "Text eins\n\nZwei", "transfer", "Q", "https://a.de/x", "01.11.2026 10:00", "logos/x.png")
        self.assertIn('class="liga-schalter"', h)
        self.assertIn("https://2liga.ligaoutsider.de/", h)


if __name__ == "__main__":
    unittest.main()
