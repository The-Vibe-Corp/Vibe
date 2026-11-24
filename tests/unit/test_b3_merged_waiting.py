"""B3 (neu vergeben): Abgeschlossene Pakete mit zitierten Markern.

Der Projektordner meldete ein gemergtes, abgehaktes Paket weiterhin als
„WARTET AUF MERGE“, weil sein Block als Nutzer-Evidenz wörtlich eine
``WARTET AUF MERGE:``-Zeile enthält. Die Zustandserkennung prüfte die
Marker-Substrings über den ganzen Block **vor** der Abhaken-Prüfung.

Die Fälle leiten sich aus FEEDBACK.md (B3), SPEC.md („Erledigt bedeutet:
Akzeptanzkriterien erfüllt und Nachweise vorhanden.“, „Blockierte Einträge
werden nicht automatisch als erledigt interpretiert.“) und den GUI-Anforderungen
ab:

* Erledigt-Vorrang: Ein abgehaktes Paket mit gültigem Nachweis gilt überall
  als erledigt, auch wenn sein Blocktext zitierte ``BLOCKIERT:``- oder
  ``WARTET AUF MERGE:``-Zeilen enthält.
* Nicht abgehakte Einträge mit echten Markern behalten ihre Zustände;
  BLOCKIERT wiegt weiterhin schwerer als WARTET AUF MERGE.
* Ein abgehaktes Feedback ohne gültigen Nachweis bleibt im Markenzustand
  (nicht erledigt, nicht „ohne Nachweis“).
* Die klassische Oberfläche (``app.js``) bietet „Paket abschließen“ für
  blockierte und wartende Paketzeilen, aber nicht für Feedback und nicht für
  erledigte Zeilen; i18n erhält das englische und das deutsche Paar.

Browser stehen in dieser Umgebung nicht zur Verfügung; die GUI-Verträge
werden deshalb wie in ``test_ap5_korbat_waiting_state.py`` über
Quelltext-/Strukturprüfungen abgesichert. Alle Zustandsfälle laufen gegen
temporäre Projektordner mit einem echten lokalen Git-Repository (für
``proof_ok``); keine produktive ``HOME``/``VIBE``-Konfiguration, keine
Netzaufrufe, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_b3_merged_waiting -v
"""
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"
CLI = REPO / "bin" / "vibe"
APP_JS = REPO / "bin" / "web" / "app.js"
I18N = REPO / "bin" / "web" / "i18n.js"

WAITING = "WARTET AUF MERGE"
BLOCKED = "BLOCKIERT"
DONE = "erledigt"
CLOSE_LABEL = "Paket abschließen"


# --------------------------------------------------------------------------
# Ladepfade und Fixtures
# --------------------------------------------------------------------------
def load_packages():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b3_merged_waiting_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b3_merged_waiting_cli_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def init_git_repo(path):
    """Legt ein Repository mit einem echten Commit an; liefert den Kurzhash.

    ``proof_ok`` prüft den Commit mit ``git cat-file`` im Projektordner; ohne
    ein echtes Repository wäre jeder Nachweis ungültig und die
    Erledigt-Erkennung ließe sich nicht von der Marker-Erkennung trennen.
    """
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=str(path),
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_project(root, tickets="", feedback="", env_text="TYPE=generic\n"):
    """Temporäres Projekt mit TICKETS.md und FEEDBACK.md.

    Das Projekt liegt unter einem vom Test angelegten Git-Repository; der
    Commit-Hash muss deshalb vor dem Schreiben der Blöcke bekannt sein und
    wird von den Tests über ``self.commit`` eingesetzt.
    """
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    (project / "TICKETS.md").write_text(
        "# TICKETS\n\n" + tickets, encoding="utf-8")
    (project / "FEEDBACK.md").write_text(
        "# FEEDBACK\n\n" + feedback, encoding="utf-8")
    return project


def js_region(text, marker, fallback=6000):
    """Schneidet den Quelltextabschnitt ab ``marker`` bis zur nächsten
    Top-Level-Funktion; ohne Treffer einen leeren String."""
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


def proof_line(commit, name="test_b3_merged_waiting.py"):
    """Nachweiszeile im Projektformat: Commit plus Test."""
    return "  Commit: %s; Test: tests/unit/%s\n" % (commit, name)


# --------------------------------------------------------------------------
# AK1/AK2/AK3: ``bin/vibe`` — _parse_entry
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# GH-48: Die Markdown-Marker- und „erledigt hat Vorrang“-Fälle des alten
# Textparsers entfallen. Zustände (auch blocked/waiting-merge) sind
# Speicherfelder; die Aussagen (Anzeige, Statusbericht, Prioritätsansicht,
# Auswahl) tragen tests/unit/test_gh48_runner_tickets.py und
# tests/unit/test_gh48_ticket_store.py. Die weiterhin gültige
# Oberflächenprüfung für „Paket abschließen“ bleibt hier erhalten.
# --------------------------------------------------------------------------


# AK5: klassische Oberfläche — „Paket abschließen“
# --------------------------------------------------------------------------
class ClassicGuiPackageCloseTest(unittest.TestCase):
    """AK5: ``app.js`` bietet den Abschluss-Button nur passenden Paketen."""

    def setUp(self):
        self.text = APP_JS.read_text(encoding="utf-8")
        self.tickets = js_region(self.text, "function ticketCard(")
        self.feedback = js_region(self.text, "function feedbackCard(")

    def test_classic_ticket_card_offers_package_close_button(self):
        """AK5. Vorbedingung: ``bin/web/app.js``, Funktion ``ticketCard``.
        Aktion: Quelltext der Ticketkarte prüfen.
        Erwartung: Sie enthält den Button „Paket abschließen“.
        Fehlerfall: In der klassischen Oberfläche fehlt der Abschluss-Button.
        """
        self.assertTrue(self.tickets, "ticketCard nicht gefunden")
        self.assertIn(CLOSE_LABEL, self.tickets)

    def test_classic_package_close_posts_to_the_package_endpoint(self):
        """AK5. Vorbedingung: Abschluss-Button in ``ticketCard``.
        Aktion: Aufruf von ``/api/package`` prüfen.
        Erwartung: Der Aufruf sendet ``name``, ``id`` und
        ``action: 'close'``.
        Fehlerfall: Der Button ruft einen falschen Endpunkt oder ohne ID auf.
        """
        call = re.search(
            r"api\(\s*['\"]/api/package['\"]\s*,\s*\{([^}]*)\}",
            self.tickets,
        )
        self.assertIsNotNone(
            call, "Kein api('/api/package', …)-Aufruf in ticketCard")
        arguments = call.group(1)
        self.assertIn("name", arguments, call.group(0))
        self.assertRegex(arguments, r"id\s*:\s*i\.id|id\b",
                         call.group(0))
        self.assertRegex(arguments, r"action\s*:\s*['\"]close['\"]",
                         call.group(0))

    def test_classic_package_close_is_limited_to_blocked_and_waiting_tickets(self):
        """AK5. Vorbedingung: ``ticketCard`` in ``app.js``.
        Aktion: Bedingung für den Abschluss-Button prüfen.
        Erwartung: Der Button ist an die Zustände ``BLOCKIERT`` und
        ``WARTET AUF MERGE`` gebunden (echte ``i.state``-Prüfung); damit
        erscheint er nicht für ``offen``, ``ohne Nachweis`` oder ``erledigt``.
        Fehlerfall: Der Button erscheint bei jedem Paket oder fehlt bei
        wartenden Paketen.
        """
        conditions = (
            r"i\.state\s*===?\s*['\"]BLOCKIERT['\"][\s\S]{0,200}"
            r"i\.state\s*===?\s*['\"]WARTET AUF MERGE['\"]",
            r"i\.state\s*===?\s*['\"]WARTET AUF MERGE['\"][\s\S]{0,200}"
            r"i\.state\s*===?\s*['\"]BLOCKIERT['\"]",
            r"\[\s*['\"]BLOCKIERT['\"]\s*,\s*['\"]WARTET AUF MERGE['\"]\s*\]"
            r"\.includes\(\s*i\.state\s*\)",
            r"\[\s*['\"]WARTET AUF MERGE['\"]\s*,\s*['\"]BLOCKIERT['\"]\s*\]"
            r"\.includes\(\s*i\.state\s*\)",
        )
        self.assertTrue(
            any(re.search(pattern, self.tickets) for pattern in conditions),
            "Keine Zustandsbindung an BLOCKIERT und WARTET AUF MERGE:\n"
            + self.tickets,
        )

    def test_classic_package_close_reports_backend_message_and_refreshes(self):
        """AK5. Vorbedingung: Abschluss-Button in ``ticketCard``.
        Aktion: Erfolgs-/Fehlerbehandlung um den Button prüfen.
        Erwartung: Die Backend-Meldung wird per ``toast`` gezeigt und die
        Projektansicht bei Erfolg über ``detail(name)`` neu geladen.
        Fehlerfall: Fehler bleiben unsichtbar oder die Ansicht bleibt veraltet.
        """
        position = self.tickets.find(CLOSE_LABEL)
        self.assertGreaterEqual(position, 0, "Abschluss-Button fehlt")
        window = self.tickets[max(0, position - 800):position + 300]
        self.assertIn("/api/package", window)
        self.assertIn("toast", window)
        self.assertIn("message", window)
        self.assertIn("detail(name)", window)

    def test_classic_feedback_card_offers_no_package_close(self):
        """AK5. Vorbedingung: ``feedbackCard`` in ``app.js``.
        Aktion: Quelltext der Feedback-Karte prüfen.
        Erwartung: Kein „Paket abschließen“-Button und kein
        ``/api/package``-Aufruf.
        Fehlerfall: Feedback ließe sich fälschlich als Paket abschließen.
        """
        self.assertTrue(self.feedback, "feedbackCard nicht gefunden")
        self.assertNotIn(CLOSE_LABEL, self.feedback)
        self.assertNotIn("/api/package", self.feedback)


# --------------------------------------------------------------------------
# AK6: i18n
# --------------------------------------------------------------------------
class I18nPackageCloseTest(unittest.TestCase):
    """AK6: englische Übersetzung und deutsches Identitätspaar."""

    def setUp(self):
        self.text = I18N.read_text(encoding="utf-8")
        self.marker = "    de: {"
        self.assertIn(self.marker, self.text, "DICTS.de nicht gefunden")
        split = self.text.index(self.marker)
        self.en_region = self.text[:split]
        self.de_region = self.text[split:]

    def test_english_dictionary_translates_package_close(self):
        """AK6. Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.en``.
        Aktion: Eintrag für „Paket abschließen“ im englischen Bereich suchen.
        Erwartung: Ein nichtleerer englischer Wert, der „package“ nennt und
        nicht der deutsche Schlüssel ist.
        Fehlerfall: ``tr('Paket abschließen')`` fällt in der englischen
        Oberfläche auf den deutschen Text zurück.
        """
        match = re.search(
            r'"Paket abschließen"\s*:\s*"([^"]*)"', self.en_region)
        self.assertIsNotNone(match, "Kein englischer Eintrag")
        value = match.group(1).strip()
        self.assertTrue(value, "Englischer Eintrag ist leer")
        self.assertNotEqual(value, CLOSE_LABEL,
                            "Englischer Eintrag ist nur der Schlüssel")
        self.assertRegex(value, r"(?i)package",
                         "Englischer Eintrag nennt kein Paket: " + value)

    def test_german_dictionary_keeps_package_close_identity(self):
        """AK6. Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.de``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: Identitätspaar
        ``"Paket abschließen": "Paket abschließen"``.
        Fehlerfall: Die deutsche Oberfläche zeigt einen englischen Default.
        """
        self.assertRegex(
            self.de_region,
            r'"Paket abschließen"\s*:\s*"Paket abschließen"',
            "Deutsches Identitätspaar fehlt in DICTS.de",
        )


if __name__ == "__main__":
    unittest.main()
