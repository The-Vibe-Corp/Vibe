"""B8 — Projekt öffnen, obwohl ``origin`` nicht erreichbar ist.

Die Fälle sind aus dem Arbeitspaket B8 und SPEC.md abgeleitet, nicht aus dem
Implementierungsdiff. Geprüft wird ausschließlich beobachtbares Verhalten:

* AK1: ``vibe_services.project_detail`` darf für ein Projekt mit unerreichbarem
  ``origin`` keine Netzwerk-Git-Abfrage (``ls-remote``, ``fetch``) auslösen und
  muss ohne Warten ein Ergebnis liefern.
* AK2: ``vibe_github.status(path, remote=False)`` und
  ``vibe_github.branches(path, remote=False)`` liefern Branch, Remotes und
  Ahead/Behind aus den lokalen ``origin/<branch>``-Referenzen, ohne
  ``ls-remote`` oder ``fetch``.
* AK3: Ohne ``GITHUB_ENABLED`` im Projekt darf auch der normale
  ``vibe_github.status(path)`` keine Fernabfrage auslösen.

Die Tests arbeiten mit echten temporären Git-Repositories. Der ``origin`` zeigt
absichtlich auf die nicht erreichbare TEST-NET-1-Adresse
``https://192.0.2.1/...``. Damit die Rotphase nicht in den 120-s-Timeout läuft,
wird ``vibe_github.git`` so umhüllt, dass ``ls-remote``/``fetch`` sofort
fehlschlagen und ihr Aufruf nachgewiesen wird. Alle anderen Git-Aufrufe gehen
an das echte Git. Es gibt keine externen Dienste, keine Modellaufrufe und keine
Kosten.

Testfälle und Zuordnung:

* ``test_project_detail_does_not_touch_unreachable_origin`` (AK1)
  Vorbedingung: Git-Repo mit ``origin`` auf 192.0.2.1, lokale ``origin/main``-
  Referenz, ein lokaler Commit voraus, ``GITHUB_ENABLED=1``.
  Aktion: ``project_detail`` unter Netzwerk-Sperre aufrufen.
  Erwartung: kein ``ls-remote``/``fetch``, Laufzeit < 5 s, Branch/Ahead/Behind
  und Branchliste sind aus lokalen Referenzen gefüllt, kein Degradationsfehler.
* ``test_status_offline_uses_local_origin_refs`` (AK2)
  Vorbedingung: wie oben.
  Aktion: ``status(path, remote=False)``.
  Erwartung: kein Netzwerkzugriff, ``main`` ist 1 voraus/0 hinter ``origin/main``.
* ``test_branches_offline_uses_local_origin_refs`` (AK2)
  Vorbedingung: ``main`` 1 voraus, ``feature`` 1 hinter ``origin/feature``,
  ``local-only`` ohne ``origin``-Referenz.
  Aktion: ``branches(path, remote=False)``.
  Erwartung: kein Netzwerkzugriff; Abstände je Branch aus lokalen Referenzen,
  ``local-only`` bleibt bei 0/0.
* ``test_status_without_github_enabled_does_not_query_remote`` (AK3)
  Vorbedingung: ``.vibe/project.env`` ohne ``GITHUB_ENABLED``.
  Aktion: ``status(path)`` ohne ``remote``-Argument.
  Erwartung: kein ``ls-remote``/``fetch`` und ``enabled`` ist ``False``.

Fehlerfälle: Jede unerwartete Netzwerk-Git-Abfrage wird aufgezeichnet und lässt
den jeweiligen Test fehlschlagen. Eine fehlende ``remote``-Schnittstelle äußert
sich vor der Implementierung als ``TypeError``.

Testbefehl:

    python3 -m unittest tests.unit.test_b8_project_open_without_remote -v
"""
import contextlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_github  # noqa: E402 - Pfad muss zuerst gesetzt sein
import vibe_services  # noqa: E402 - nutzt dasselbe vibe_github-Modul

UNREACHABLE_ORIGIN = "https://192.0.2.1/b8/nie-erreichbar.git"
NETWORK_GIT = ("ls-remote", "fetch")

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    # Persönliche Git-Konfiguration darf den Test nicht beeinflussen.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *argv):
    """Echtes Git im temporären Verzeichnis mit fester Testidentität."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env, check=True,
        capture_output=True, text=True,
    )


def git_out(cwd, *argv):
    return git(cwd, *argv).stdout.strip()


class StubVibe:
    """Nur die für ``project_detail`` nötigen, nicht getesteten CLI-Ansichten.

    Die GitHub-Ebene wird bewusst nicht ersetzt: ``vibe_services`` ruft das
    echte ``vibe_github``-Modul gegen ein echtes Git-Repository auf.
    """

    def __init__(self, project):
        self.project = str(project)

    def ppath(self, name):
        return self.project

    def git_info(self, name):
        return "main", 1, "abc1234 lokaler Commit (jetzt)"

    def open_items(self, name):
        return []

    def run_state(self, name):
        return {
            "run_id": None, "state": "idle", "running": False,
            "started": False, "agent": "", "session": "", "log": "",
            "verify_log": "", "exit_code": None,
        }

    def ptype(self, name):
        return "generic"

    def is_init(self, name):
        return True

    def logpath(self, name, kind="run"):
        return os.path.join(self.project, "_logs", "proj.log")

    def pause_after_active(self, name):
        return False

    def feedback_items(self, name):
        return []

    def ticket_items(self, name):
        return []

    def verify_command(self, name, mode="quick"):
        return "true"

    def penv(self, name):
        return {"TYPE": "generic"}

    def write_dirs(self, name):
        return []

    def write_dirs_default(self, name):
        return []

    def write_dirs_custom(self, name):
        return False

    def sandbox_status(self, name):
        return {
            "enabled": False, "tools": [], "write_dirs": [], "tool_caches": [],
            "missing_tools": [], "bwrap": "", "state_dir": "", "error": "",
        }


class ProjectWithoutReachableOrigin(unittest.TestCase):
    """Echtes Git-Repo, dessen ``origin`` absichtlich nicht erreichbar ist."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.project.mkdir()
        self.real_git = vibe_github.git
        self.network_calls = []

        git(self.project, "init", "-q", "-b", "main")
        (self.project / "base.txt").write_text("Basis\n", encoding="utf-8")
        git(self.project, "add", "base.txt")
        git(self.project, "commit", "-q", "-m", "Basis")
        base_sha = git_out(self.project, "rev-parse", "HEAD")

        git(self.project, "remote", "add", "origin", UNREACHABLE_ORIGIN)
        # Lokale Fern-Referenzen: genau der Stand, den ein früherer Abgleich
        # hinterlassen hätte. Kein Netzwerk ist daran beteiligt.
        git(self.project, "update-ref", "refs/remotes/origin/main", base_sha)

        (self.project / "lokal.txt").write_text("lokal\n", encoding="utf-8")
        git(self.project, "add", "lokal.txt")
        git(self.project, "commit", "-q", "-m", "Lokaler Commit")
        self.local_sha = git_out(self.project, "rev-parse", "HEAD")

        # feature steht auf der Basis; origin/feature enthält einen nur dort
        # vorhandenen Commit -> feature ist 0 voraus und 1 hinter.
        git(self.project, "branch", "feature", base_sha)
        tree = git_out(self.project, "rev-parse", "HEAD^{tree}")
        remote_only = git_out(
            self.project, "commit-tree", tree, "-p", base_sha, "-m", "Nur remote"
        )
        git(self.project, "update-ref", "refs/remotes/origin/feature", remote_only)

        # Branch ohne jede origin-Referenz bleibt lokal bei 0/0.
        git(self.project, "branch", "local-only", base_sha)

        (self.project / ".vibe").mkdir()
        self.write_env(enabled=True)

    def write_env(self, enabled):
        """Projektkonfiguration mit oder ohne ``GITHUB_ENABLED`` schreiben."""
        lines = ["TYPE=generic", 'SANDBOX="off"']
        if enabled:
            lines += ['GITHUB_ENABLED="1"', 'GITHUB_REPO="example/b8"']
        (self.project / ".vibe" / "project.env").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    @contextlib.contextmanager
    def no_network_git(self):
        """Lässt ``ls-remote``/``fetch`` sofort scheitern und protokolliert sie.

        Alle übrigen Git-Aufrufe (rev-parse, for-each-ref, rev-list, ...) gehen
        unverändert an das echte Git im temporären Repository.
        """

        def guarded(project_path, *args):
            argv = [str(arg) for arg in args]
            if argv and argv[0] in NETWORK_GIT:
                self.network_calls.append(argv)
                return 128, "Netzwerk im Test gesperrt"
            return self.real_git(project_path, *args)

        with mock.patch.object(vibe_github, "git", side_effect=guarded):
            yield

    # ---------------------------------------------------------------- AK1
    def test_project_detail_does_not_touch_unreachable_origin(self):
        """AK1: Dashboard-Ansicht bleibt ohne Netzwerk-Git-Abfrage nutzbar."""
        vibe = StubVibe(self.project)
        paths = SimpleNamespace(runtime=str(self.root / "runtime"))

        started = time.monotonic()
        with self.no_network_git():
            data = vibe_services.project_detail(vibe, paths, "proj")
        elapsed = time.monotonic() - started

        self.assertEqual(
            self.network_calls, [],
            "project_detail hat eine Fernabfrage ausgelöst: %r" % (self.network_calls,),
        )
        self.assertLess(elapsed, 5.0, "project_detail hat zu lange gewartet")
        github = data["github"]
        self.assertNotIn("error", github, "GitHub-Ansicht wurde unerwartet degradiert")
        self.assertEqual(github["branch"], "main")
        self.assertEqual(github["ahead"], 1)
        self.assertEqual(github["behind"], 0)
        self.assertEqual([row["name"] for row in github["remotes"]], ["origin"])
        self.assertEqual(
            {row["name"] for row in github["branches"]},
            {"main", "feature", "local-only"},
        )

    # ---------------------------------------------------------------- AK2
    def test_status_offline_uses_local_origin_refs(self):
        """AK2: status(remote=False) rechnet gegen die lokale origin-Referenz."""
        with self.no_network_git():
            data = vibe_github.status(str(self.project), remote=False)

        self.assertEqual(
            self.network_calls, [],
            "status(remote=False) hat eine Fernabfrage ausgelöst: %r" % (self.network_calls,),
        )
        self.assertTrue(data["enabled"])
        self.assertEqual(data["branch"], "main")
        self.assertEqual((data["ahead"], data["behind"]), (1, 0))
        self.assertTrue(data["unpushed"])
        self.assertEqual([row["name"] for row in data["remotes"]], ["origin"])

    def test_branches_offline_uses_local_origin_refs(self):
        """AK2: branches(remote=False) liefert Abstände aus lokalen Referenzen."""
        with self.no_network_git():
            rows = vibe_github.branches(str(self.project), remote=False)

        self.assertEqual(
            self.network_calls, [],
            "branches(remote=False) hat eine Fernabfrage ausgelöst: %r" % (self.network_calls,),
        )
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(set(by_name), {"main", "feature", "local-only"})
        self.assertTrue(by_name["main"]["current"])
        self.assertEqual((by_name["main"]["ahead"], by_name["main"]["behind"]), (1, 0))
        self.assertFalse(by_name["feature"]["current"])
        self.assertEqual((by_name["feature"]["ahead"], by_name["feature"]["behind"]), (0, 1))
        self.assertEqual((by_name["local-only"]["ahead"], by_name["local-only"]["behind"]), (0, 0))

    # ---------------------------------------------------------------- AK3
    def test_status_without_github_enabled_does_not_query_remote(self):
        """AK3: Ohne GITHUB_ENABLED bleibt der normale Status rein lokal."""
        self.write_env(enabled=False)

        with self.no_network_git():
            data = vibe_github.status(str(self.project))

        self.assertEqual(
            self.network_calls, [],
            "status ohne GITHUB_ENABLED hat eine Fernabfrage ausgelöst: %r"
            % (self.network_calls,),
        )
        self.assertFalse(data["enabled"])
        self.assertEqual(data["branch"], "main")


if __name__ == "__main__":
    unittest.main()
