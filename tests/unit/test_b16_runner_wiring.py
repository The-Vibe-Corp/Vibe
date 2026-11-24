"""Abnahme B16 „Arbeitspakete für GitHub vorbereiten und als PR erstellen“
(Bug): Der echte Läufer verlangt Push und Merge-Request als Abschluss.

Die Testfälle leiten sich aus Arbeitspaket B16 (FEEDBACK.md) und SPEC.md ab,
unabhängig von einer Implementierung. Geprüft wird ``bin/vibe-run.sh`` in
einer Fake-Toolchain (Muster ``test_ap9_runner_wiring.py``):

* ``create_worktree`` ermittelt den Branch-Namen über das Subkommando
  ``branch-name``; es entsteht kein ``vibe/...``-Name mehr. Der gepushte
  Branch heißt nach dem Standardmuster ``feature/<owner>/<id>``.
* Ein Fehlschlag von ``github-complete`` ist eine echte Abschlussschranke:
  ``BLOCKIERT: GitHub-Abschluss für <ID> fehlgeschlagen
  (Push/Merge-Request): ...``, kein lokaler Merge, kein ``[x]`` im Projekt,
  Status blockiert, Arbeitskopie bleibt liegen.
* Bei divergiertem ``dev`` blockiert der Abschluss mit ``divergiert``; der
  ``github-pull`` bleibt wie in AP9 ein HINWEIS.
* Ein erfolgreicher ``github-complete`` führt im PR-only-Standard (ohne
  ``GITHUB_AUTO_MERGE``) NICHT zu einem lokalen Merge: Der Lauf hält mit
  „wartet auf Merge“/``vibe package close`` an, die Arbeitskopie bleibt
  registriert und das Ticket bleibt offen (AP4-Korbat T-G0/T-G1). Der
  automatische Merge samt Cleanup ist Fall von ``test_ap4_korbat_github``.
* Der Abschlussbericht nennt je geschlossenem Paket Branch, Commit und
  Merge-Request-URL; der Commit-Anteil der Berichtszeile wird in Report und
  Log gegen den Projekt-HEAD geprüft. Ohne GitHub-Verknüpfung erscheint
  ``Merge-Request: keine (GitHub nicht aktiv oder kein origin)``.
* Nutzerbestätigung 19.11.2026: Die Prüfung ist nur verpflichtend, wenn
  GitHub für das Projekt aktiviert ist. Ein rein lokales Projekt ohne GitHub
  schließt mit Commit und lokalem Merge; der Skip-Pfad ist Soll-Semantik.

Kein echtes Netz: github.com wird nie berührt. Git läuft in temporären
Verzeichnissen mit fester Test-Identität gegen lokale Bare-Repositories
(``file://``); REST geht nur an einen Fake auf 127.0.0.1. Keine
Modellaufrufe, keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_b16_runner_wiring -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

from tests.unit.test_ap9_runner_github import RestFakeServer  # noqa: E402
from tests.unit.test_ap9_runner_wiring import AP9WiringFixture, git  # noqa: E402

# GH-48: Tickets liegen im Projekt-Speicher; der frühere FEEDBACK.md-Ledger
# existiert nicht mehr.
FEEDBACK_ONE = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]

GITHUB_ENV = (
    'GITHUB_ENABLED="1"\n'
    'GITHUB_REPO="owner/name"\n'
    'GITHUB_BASE="main"\n'
)


def install_rejecting_hook(bare):
    """pre-receive-Hook, der jede Ref-Erstellung wie GH013 ablehnt."""
    hooks = Path(bare) / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "echo 'GH013: Cannot create ref due to creations being restricted' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


class B16WiringFixture(AP9WiringFixture):
    """AP9-Fixture plus GitHub-Verknüpfung und Prüfhelfer für B16."""

    def github_env(self, api=""):
        text = GITHUB_ENV
        if api:
            text += 'GITHUB_API="%s"\n' % api
        return text

    def make_github_project(self, name="proj", api=""):
        return self.make_project(
            env_extra=self.github_env(api), feedback=FEEDBACK_ONE, name=name)

    def report(self, project):
        path = self.runtime / (project.name + ".report.txt")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def blocked_line(self, log):
        """Erste Protokollzeile der GitHub-Abschlussschranke."""
        for line in log.splitlines():
            if line.startswith(
                    "BLOCKIERT: GitHub-Abschluss für F1 fehlgeschlagen "
                    "(Push/Merge-Request):"):
                return line
        return ""

    def assert_not_merged(self, project, pid="F1"):
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-" + pid + ".txt"
                   ).returncode,
            "Das Paket darf nicht lokal gemergt sein")

    def ticket(self, project, pid="F1"):
        """Liest das Ticket aus dem GH-48-Projektspeicher."""
        path = project / ".vibe" / "tickets.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data["tickets"]:
            if record["id"] == pid:
                return record
        self.fail("Ticket %s fehlt im Speicher %s" % (pid, path))

    def assert_ticket_open(self, project, pid="F1"):
        record = self.ticket(project, pid)
        self.assertNotEqual(
            "done", record["state"],
            "Das Ticket muss offen bleiben: %r" % (record,))


# --------------------------------------------------------------- PR-only-Fall
class PrOnlyClosureTest(B16WiringFixture):
    """AK AP4/T-G1: Ohne GITHUB_AUTO_MERGE bleibt es beim PR-only-Abschluss.

    Die frühere B16-Erwartung (sofortiger lokaler Merge, Cleanup und
    „Geschlossen“) gilt nur noch im Auto-Merge-Modus. AP4-Korbat macht
    PR-only zum Standard: Push und Merge-Request sind weiterhin eine harte
    Schranke, aber der Lauf hält nach dem Öffnen des PRs an, die Arbeitskopie
    bleibt registriert und das Ticket bleibt offen.

    Vorbedingung: Projekt mit aktivierter GitHub-Verknüpfung, ein offenes
    Paket F1, ``GITHUB_AUTO_MERGE`` nicht gesetzt.
    Aktion: Läufer einmal ausführen (Repo wird gepusht, Merge-Request
    gestellt).
    Erwartung: ``FEEDBACK.md`` trägt den Wartezustand ``WARTET AUF MERGE``
    und keinen ``BLOCKIERT``-Vermerk mehr. Grund: AP5-Korbat 4b ersetzt den
    bisherigen PR-only-BLOCKIERT-Vermerk ausdrücklich durch den neuen
    Wartezustand (analog zu ``test_ap4_korbat_github.PrOnlyRunnerTest``).
    Fehlerfall: Der Lauf vermerkt weiterhin BLOCKIERT oder gar keinen
    Wartezustand; dann wäre die geforderte Zustandsänderung nicht umgesetzt.
    """

    def test_successful_run_pushes_and_opens_the_pr_then_waits_for_merge(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-ok")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        self.publish(project, bare)

        result = self.run_runner(project)

        log = self.log(project)
        # Branch-Regel: feature/<owner>/<id>, nicht vibe/...
        self.assertEqual(
            0, git(bare, "rev-parse", "--verify",
                   "refs/heads/feature/test/f1").returncode,
            "Der Branch wurde nicht unter dem Repository-Namensschema "
            "gepusht:\n" + log)
        posts = [post for post in server.posts
                 if post["path"].startswith("/repos/owner/name/pulls")]
        self.assertTrue(posts, "Der Merge-Request wurde nicht gestellt")
        self.assertEqual("feature/test/f1", posts[-1]["body"].get("head"))
        # PR-only: kein lokaler Merge, kein Cleanup, Ticket bleibt offen.
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        record = self.ticket(project)
        self.assertEqual("waiting-merge", record["state"],
                         "AP5-Korbat 4b: PR-only muss als Wartezustand "
                         "vermerkt sein: %r" % (record,))
        self.assertTrue(record["waiting_note"],
                        "Der Wartezustand braucht eine Notiz: %r" % (record,))
        self.assertFalse(record["blocked_reason"],
                         "PR-only darf nicht als blockiert vermerkt "
                         "werden: %r" % (record,))
        self.assertTrue(self.worktrees(),
                        "Die Arbeitskopie muss bis zum Merge registriert "
                        "bleiben:\n" + log)
        self.assertIn("wartet auf merge", log.lower(),
                      "Der Lauf muss auf den Merge warten:\n" + log)
        self.assertIn("vibe package close", log,
                      "Der nächste Schritt muss genannt sein:\n" + log)


# --------------------------------------------------------------- Fehlerpfade
class BlockedClosureTest(B16WiringFixture):
    """AK: Push-/PR-Fehler blockieren ohne Merge und ohne [x]."""

    def test_rejected_push_blocks_without_merge_or_ticket_update(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-gh013")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        self.publish(project, bare)
        install_rejecting_hook(bare)

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        blocked = self.blocked_line(log)
        self.assertTrue(blocked, log)
        self.assertIn("GH013", blocked,
                      "Die Push-Ablehnung muss in der BLOCKIERT-Zeile stehen:\n"
                      + log)
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        report = self.report(project)
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        self.assertTrue(self.worktrees(),
                        "Die blockierte Arbeitskopie muss liegen bleiben")
        self.assertEqual([], server.posts,
                         "Nach abgelehntem Push kein Merge-Request")

    def test_failed_merge_request_blocks_but_the_push_happened(self):
        server = RestFakeServer(post_status=422).start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-prfehler")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        self.publish(project, bare)

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        blocked = self.blocked_line(log)
        self.assertTrue(blocked, log)
        self.assertIn("Merge-Request fehlgeschlagen", blocked,
                      "Der PR-Fehler muss in der BLOCKIERT-Zeile stehen:\n"
                      + log)
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        report = self.report(project)
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        # Beabsichtigtes Teilergebnis: Der Push ist erfolgt, nur der
        # Merge-Request scheiterte.
        self.assertEqual(
            0, git(bare, "rev-parse", "--verify",
                   "refs/heads/feature/test/f1").returncode,
            "Der Push muss trotz PR-Fehler erfolgt sein")
        self.assertTrue(self.worktrees(),
                        "Die blockierte Arbeitskopie muss liegen bleiben")


# ------------------------------------------------------------- Divergenz dev
class DivergenceTest(B16WiringFixture):
    """AK: Bei divergiertem dev vor Abschluss abbrechen und informieren."""

    def test_diverged_integration_branch_blocks_with_divergiert(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-divergiert")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        # Fernstand zieht um einen Commit voraus; der lokale Stand wird
        # danach um einen eigenen, ungepushten Commit ergänzt → divergiert.
        self.publish(project, bare, ahead_commits=1)
        self.assertEqual(
            0, git(project, "commit", "--allow-empty", "-q", "-m",
                   "lokal").returncode)

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        # Der Pull bleibt ein HINWEIS (AP9-Semantik für den Pull).
        self.assertIn(
            "HINWEIS: GitHub-Pull des Haupt-Branchs vor F1 fehlgeschlagen",
            log, log)
        blocked = self.blocked_line(log)
        self.assertTrue(blocked, log)
        self.assertIn("divergiert", blocked,
                      "Die Divergenz muss in der BLOCKIERT-Zeile stehen:\n"
                      + log)
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        report = self.report(project)
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        self.assertTrue(self.worktrees(),
                        "Die blockierte Arbeitskopie muss liegen bleiben")


# ------------------------------------------------- Bericht ohne GitHub-Verknüpfung
class ReportWithoutGithubTest(B16WiringFixture):
    """AK: Rein lokale Projekte schließen mit Commit und Merge.

    Nutzerbestätigung 19.11.2026: Die GitHub-Prüfung ist nur verpflichtend,
    wenn GitHub für das Projekt aktiviert ist. Ein rein lokales Projekt ohne
    GitHub braucht nur einen erfolgreichen Commit und ggf. das lokale Merge
    des Feature-Branchs. Der Skip-Pfad ist damit Soll-Semantik, kein
    Kompromiss.
    """

    def test_report_without_github_names_branch_commit_and_keine(self):
        project = self.make_project(feedback=FEEDBACK_ONE)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = self.report(project)
        self.assertIn("Geschlossen: F1 — Branch feature/test/f1", report)
        self.assertIn(
            "Merge-Request: keine (GitHub nicht aktiv oder kein origin)",
            report)
        # Der Commit-Anteil der Berichtszeile muss den Projekt-HEAD nennen.
        head_sha = git(project, "rev-parse", "--short", "HEAD").stdout.strip()
        self.assertTrue(head_sha, "Projekt-HEAD nicht ermittelbar")
        self.assertIn(", Commit " + head_sha + ",", report)
        self.assertIn(", Commit " + head_sha + ",", self.log(project))
        self.assertEqual(0, git(project, "cat-file", "-e",
                                "HEAD:impl-F1.txt").returncode)

    def test_github_enabled_but_without_origin_still_closes_locally(self):
        """Ohne origin gibt es nichts zu pushen: bewusster Skip, lokales Merge."""
        project = self.make_project(
            env_extra=self.github_env(), feedback=FEEDBACK_ONE)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = self.report(project)
        self.assertIn("Geschlossen: F1 — Branch feature/test/f1", report)
        self.assertIn(
            "Merge-Request: keine (GitHub nicht aktiv oder kein origin)",
            report)
        self.assertEqual(0, git(project, "cat-file", "-e",
                                "HEAD:impl-F1.txt").returncode)


if __name__ == "__main__":
    unittest.main()
