"""Regressionstest für die Blockstruktur von Feedback-Einträgen (F7).

Der Paketläufer (``_toolchain/verify/next_item.py``) und ``bin/vibe`` lesen
einen Feedback-Punkt nur so weit, wie die Folgezeilen eingerückt sind. Eine
nicht eingerückte Fortsetzungszeile beendet den Block; ein darunter stehender
Nachweis zählt dann nicht mehr zum Punkt. Ein abgehakter Punkt ohne Nachweis
wird erneut als offenes Arbeitspaket ausgewählt.

Warum Fixturedaten statt der echten Datei: ``FEEDBACK.md`` im
Repository-Wurzelverzeichnis ist **nicht versioniert**. Ihr Inhalt ist der
lokale Ledger-Zustand des jeweiligen Rechners und damit nicht
repo-verifizierbar; ein fehlender F7-Block führte zu ``StopIteration``.
Dieser Test prüft deshalb fest eingebettete Blöcke mit denselben
Blockregeln wie der Läufer. Er prüft die Struktur, nicht die Existenz der
genannten Commits; das übernimmt der Läufer selbst.
"""
import re
import unittest

COMMENT = re.compile(r"<!--.*?-->", re.S)
CHECKED = re.compile(r"^- \[x\]\s+(\S+)")
PROOF_COMMIT = re.compile(r"(?m)^\s+Commit:\s*[0-9a-f]{7,40}\b")
PROOF_RESULT = re.compile(r"(?:Test|Datei):\s*\S+")

# F7 im korrekten Zustand: Fortsetzung und Nachweis sind eingerückt und
# gehören damit zum Block. F8 sichert den allgemeinen Nachweisfall ab.
F7_FIXTURE = """# FEEDBACK

- [ ] F6 Offener Punkt
  Beschreibung: ohne Häkchen

- [x] F7 Fortsetzung und Nachweis
  Beschreibung: Der Punkt prüft, ob
  ist es möglich,
  Commit: 0406429; Test: Sandbox

- [x] F8 Zweiter Punkt mit Nachweis
  Beschreibung: Text
  Commit: 0123abc
  Test: python3 -m unittest tests.unit.test_feedback_entries
"""

# Derselbe Punkt mit nicht eingerückter Fortsetzung: Genau dieser Fehler war
# der Anlass für F7. Der Nachweis steht dadurch außerhalb des Blocks und
# zählt nicht mehr.
BROKEN_FIXTURE = """# FEEDBACK

- [x] F7 Fortsetzung ohne Einrückung
  Beschreibung: Der Punkt prüft, ob
ist es möglich,
  Commit: 0406429; Test: Sandbox
"""


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
        self.entries = blocks(F7_FIXTURE)

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

    def test_non_indented_continuation_ends_the_block(self):
        """Die Blockregel selbst: ohne Einrückung fällt der Nachweis heraus."""
        f7 = next(
            entry
            for entry in blocks(BROKEN_FIXTURE)
            if entry.startswith("- [x] F7 ")
        )

        self.assertNotIn("ist es möglich", f7)
        self.assertNotIn("Commit:", f7)
        self.assertNotRegex(f7, PROOF_RESULT)


if __name__ == "__main__":
    unittest.main()
