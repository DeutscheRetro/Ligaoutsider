"""python3 -m unittest discover tests  –  findet Namen, die in generate.py benutzt, aber nirgends definiert sind.
Zweimal hat ein gelöschter Funktionsblock eine Konstante mitgenommen; main brach dann still nach dem Veröffentlichen ab."""
import ast, builtins, unittest
from pathlib import Path

DATEIEN = ["generate.py", "social.py", "storys.py", "ki_budget.py", "qualitaet.py"]


def undefiniert(pfad: Path) -> set:
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    definiert = set(dir(builtins)) | {"__file__", "__name__"}
    for n in ast.walk(baum):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            definiert.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definiert.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            definiert.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.arg):
            definiert.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            definiert.add(n.name)
    benutzt = {n.id for n in ast.walk(baum) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return benutzt - definiert


class Namen(unittest.TestCase):
    def test_keine_undefinierten_namen(self):
        basis = Path(__file__).resolve().parent.parent
        for d in DATEIEN:
            with self.subTest(datei=d):
                self.assertEqual(undefiniert(basis / d), set())


if __name__ == "__main__":
    unittest.main()
