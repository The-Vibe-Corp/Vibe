"""Regressionstest für die Blockstruktur der echten FEEDBACK.md (F7).

Der Paketläufer (``_toolchain/verify/next_item.py``) und ``bin/vibe`` lesen
einen Feedback-Punkt nur so weit, wie die Folgezeilen eingerückt sind. Eine
nicht eingerückte Fortsetzungszeile beendet den Block; ein darunter stehender
Nachweis zählt dann nicht mehr zum Punkt. Ein abgehakter Punkt ohne Nachweis
wird erneut als offenes Arbeitspaket ausgewählt.

Der Test prüft deshalb die tatsächliche FEEDBACK.md des Repositories mit
denselben Blockregeln wie der Läufer. Er prüft die Struktur, nicht die
Existenz der genannten Commits; das übernimmt der Läufer selbst.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FEEDBACK = REPO / "FEEDBACK.md"

COMMENT = re.compile(r"<!--.*?-->", re.S)
CHECKED = re.compile(r"^- \[x\]\s+(\S+)")
PROOF_COMMIT = re.compile(r"(?m)^\s+Commit:\s*[0-9a-f]{7,40}\b")
PROOF_RESULT = re.compile(r"(?:Test|Datei):\s*\S+")


def blocks(text):
    """Bildet Blöcke wie der Paketläufer: nur eingerückte Zeilen gehören dazu."""
    text = COMMENT.sub("", text)
    current = None
    result = []
    for line in text.splitlines():
        if line.startswith("- "):
            if current is not None:
                result.append(current)
            current = line
        elif current is not None and line.startswith((" ", "\t")):
            current += "\n" + line
        elif current is not None and not line.strip():
            current += "\n"
        else:
            if current is not None:
                result.append(current)
            current = None
    if current is not None:
        result.append(current)
    return result


class FeedbackBlockStructureTest(unittest.TestCase):
    def setUp(self):
        self.entries = blocks(FEEDBACK.read_text(encoding="utf-8"))

    def checked(self):
        return [entry for entry in self.entries if CHECKED.match(entry)]

    def test_every_checked_entry_keeps_its_proof_inside_the_block(self):
        problems = []
        for entry in self.checked():
            ident = CHECKED.match(entry).group(1)
            if not PROOF_COMMIT.search(entry):
                problems.append(f"{ident}: Commit fehlt im Block")
            if not PROOF_RESULT.search(entry):
                problems.append(f"{ident}: Test/Datei fehlt im Block")

        self.assertEqual([], problems)

    def test_f7_continuation_and_proof_belong_to_the_item(self):
        f7 = next(
            entry for entry in self.entries if entry.startswith("- [x] F7 ")
        )

        self.assertIn("\n  ist es möglich", f7)
        self.assertRegex(f7, r"\n  Commit: 0406429; Test: Sandbox")


if __name__ == "__main__":
    unittest.main()
