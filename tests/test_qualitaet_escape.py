import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import qualitaet  # noqa: E402


class HtmlAnpassen(unittest.TestCase):
    def test_text_von_opus_wird_escaped(self):
        seite = Path(tempfile.mkdtemp()) / "a.html"
        seite.write_text('<h1 class="artikel-titel">Alt</h1><div class="artikel-text"><p>Alt.</p></div>', encoding="utf-8")
        qualitaet._html_anpassen(seite, "Alt", "Alt.", "Neu <b>", "Mit <script>x</script> & mehr.")
        roh = seite.read_text(encoding="utf-8")
        self.assertNotIn("<script>", roh)
        self.assertNotIn("<b>", roh)
        self.assertIn("&lt;script&gt;", roh)


if __name__ == "__main__":
    unittest.main()
