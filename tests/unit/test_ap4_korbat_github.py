"""AP4-Korbat (GitHub-Teil): T-G0, T-G7, T-G1, T-G2, T-G3, T-G4.

Die Fälle leiten sich aus dem Arbeitspaket AP4-Korbat (TICKETS.md), der
freigegebenen Spezifikation (AP3.md §3–§8, AP2.md §4/§5) und den
verbindlichen Design-Entscheidungen des Koordinators ab — nicht aus einem
Implementierungsdiff. Abgedeckt sind:

* T-G0: ``GITHUB_AUTO_MERGE`` ist ein binärer Schalter in
  ``.vibe/project.env``. ``vibe_github.read_config`` liefert den Schlüssel
  ``auto_merge`` (leer/fehlend = aus). ``vibe_github.status`` trägt
  ``auto_merge``. Der Läufer mergt den PR nur bei ``GITHUB_AUTO_MERGE="1"``
  über die REST-Schnittstelle (squash); ohne Schalter bleibt es bei PR-only
  (kein lokaler Merge, Arbeitskopie bleibt registriert).
* T-G7: ``vibe_packages.py ensure-mergeable --project <WORKTREE> --base
  origin/<base>`` holt die Basis und mergt sie in den Paketbranch
  (``--no-ff``). Ist die Basis bereits Vorfahr, passiert nichts. Bei Konflikt
  bleibt der Merge im Arbeitsbaum stehen (kein ``merge --abort``), die
  konfliktbehafteten Pfade werden ausgegeben und der Exit ist ungleich 0;
  ein Push findet nicht statt. Nach einer Reparatur ist der erneute Aufruf
  erfolgreich.
* T-G1: Nach erfolgreichem ``github-complete`` wird im PR-only-Standard
  nicht lokal gemergt; der Lauf hält mit dem Hinweis auf
  ``vibe package close <projekt> <id>`` an, die Arbeitskopie bleibt
  registriert und das Ticket bleibt offen (Blockievermerk).
* T-G2: Jeder Fetch-Pfad nutzt ``--prune`` (``fetch``, ``pull_integration``,
  ``integration_state`` und der ensure-mergeable-Fetch).
* T-G3: ``github_link`` setzt best-effort den Upstream für lokale Branches,
  deren ``origin/<branch>`` existiert; Fehler sind nicht fatal.
* T-G4: ``checkout_branch`` verweigert einen Branch, der in einer anderen
  Arbeitskopie ausgecheckt ist, mit verständlicher Meldung.

Kein Netz: GitHub wird nie kontaktiert. Git läuft ausschließlich in
temporären Verzeichnissen mit fester Test-Identität gegen lokale
Bare-Repositories (``file://``); REST nur gegen einen Fake auf 127.0.0.1.
Keine Modellaufrufe, keine produktiven Pfade oder Geheimnisse.

Run:

    python3 -m unittest tests.unit.test_ap4_korbat_github -v
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
GITHUB_MODULE = BIN / "vibe_github.py"
PACKAGES = BIN / "vibe_packages.py"
RUNS_PY = BIN / "vibe_runs.py"
CLI = BIN / "vibe"

FAKE_TOKEN = "ap4-korbat-env-token-0815"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "VIBE_GITHUB_CREDENTIAL",
)

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

_CACHE = {}


def github_module():
    """Lädt ``bin/vibe_github.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "gh" in _CACHE:
        return _CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_ap4_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _CACHE["gh"] = module
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
            "vibe_ap4_github_cli_under_test", str(CLI))
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


def real_git(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


def real_git_out(cwd, *argv):
    return real_git(cwd, *argv).stdout.strip()


def fresh_env(**extra):
    env = {key: value for key, value in os.environ.items()
           if key not in ISOLATED_ENV and not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_PROXY": "127.0.0.1,localhost",
    })
    env.update(GIT_IDENTITY)
    env.update({key: str(value) for key, value in extra.items()})
    return env


def seed_bare(root, name):
    """Bare-Origin mit einem Ausgangscommit; liefert (url, seed-pfad)."""
    work = Path(root) / "seed" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "shared.txt").write_text("base\n", encoding="utf-8")
    real_git(work, "init", "-q", "-b", "main")
    real_git(work, "add", "-A")
    real_git(work, "commit", "-q", "-m", "seed")
    bare = Path(root) / "origin" / (name + ".git")
    bare.mkdir(parents=True, exist_ok=True)
    real_git(bare, "init", "-q", "--bare")
    real_git(work, "remote", "add", "origin", str(bare))
    real_git(work, "push", "-q", "origin", "main")
    real_git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare), work


def clone_project(root, name, url):
    project = Path(root) / name
    real_git(root, "clone", "-q", url, str(project))
    return project


def push_remote_change(seed, name, content, message="remote"):
    (seed / name).write_text(content, encoding="utf-8")
    real_git(seed, "add", "-A")
    real_git(seed, "commit", "-q", "-m", message)
    real_git(seed, "push", "-q", "origin", "main")


class GithubCase(unittest.TestCase):
    """Isolierte Prozessumgebung; GitHub/REST nie echt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy", "https_proxy",
                    "all_proxy", "VIBE_GITHUB_CREDENTIAL"):
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------- T-G0 config
class AutoMergeConfigTest(GithubCase):
    """AK T-G0: Binärer Schalter ``auto_merge`` mit Standard aus."""

    def write_env(self, text):
        env_path = self.base / "project.env"
        env_path.write_text(text, encoding="utf-8")
        return env_path

    def test_missing_key_defaults_auto_merge_off(self):
        """Vorbedingung: project.env ohne GITHUB_AUTO_MERGE.
        Aktion: ``read_config`` lesen.
        Erwartung: ``auto_merge`` ist ``False`` (PR-only ist der Standard).
        Fehlerfall: fehlender Schlüssel, Wahrwert oder Ausnahme.
        """
        env_path = self.write_env('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n')

        config = self.gh.read_config(str(env_path))

        self.assertIn("auto_merge", config, config)
        self.assertIs(config["auto_merge"], False, config)

    def test_empty_and_one_values_are_read_binary(self):
        """Vorbedingung: project.env mit GITHUB_AUTO_MERGE leer bzw. "1".
        Aktion: ``read_config`` je Wert lesen.
        Erwartung: "" → False, "1" → True; ein Enum gibt es nicht.
        Fehlerfall: leerer Wert gilt als an oder "1" wird nicht erkannt.
        """
        for value, expected in (("", False), ("1", True)):
            with self.subTest(value=value):
                env_path = self.write_env(
                    'GITHUB_ENABLED="1"\nGITHUB_AUTO_MERGE="%s"\n' % value)
                config = self.gh.read_config(str(env_path))
                self.assertIs(config["auto_merge"], expected, config)

    def test_status_exposes_auto_merge(self):
        """Vorbedingung: Projekt ohne/mit aktiviertem Auto-Merge.
        Aktion: ``status(project)`` lesen.
        Erwartung: ``status["auto_merge"]`` entspricht der Konfiguration.
        Fehlerfall: Status verschweigt den Schalter oder liefert einen String.
        """
        for value, expected in (("", False), ("1", True)):
            with self.subTest(value=value):
                project = self.base / ("status-%s" % (value or "aus"))
                project.mkdir()
                real_git(project, "init", "-q", "-b", "main")
                real_git(project, "commit", "--allow-empty", "-q", "-m", "init")
                (project / ".vibe").mkdir()
                (project / ".vibe" / "project.env").write_text(
                    'GITHUB_ENABLED="1"\nGITHUB_AUTO_MERGE="%s"\n' % value,
                    encoding="utf-8")
                view = self.gh.status(project, remote=False)
                self.assertIn("auto_merge", view, view)
                self.assertIs(view["auto_merge"], expected, view)


# ------------------------------------------------------------ T-G7 mergeability
class EnsureMergeableTest(GithubCase):
    """AK T-G7: Basis in den Paketbranch mergen, Konflikte stehen lassen."""

    def run_ensure(self, project, base="origin/main"):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "ensure-mergeable",
             "--project", str(project), "--base", base],
            cwd=str(REPO), env=fresh_env(), capture_output=True,
            text=True, timeout=120, check=False,
        )

    def feature_project(self, name, conflicting=False):
        url, seed = seed_bare(self.base, name)
        project = clone_project(self.base, name, url)
        real_git(project, "checkout", "-q", "-b", "feature/x")
        if conflicting:
            (project / "shared.txt").write_text("feature\n", encoding="utf-8")
        else:
            (project / "feature.txt").write_text("feature\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "feature: change")
        if conflicting:
            push_remote_change(seed, "shared.txt", "remote\n")
        else:
            push_remote_change(seed, "remote.txt", "remote\n")
        return project, seed

    def test_base_already_ancestor_is_ok_without_a_new_commit(self):
        """Vorbedingung: Featurebranch zweigt vom aktuellen origin/main ab.
        Aktion: ``ensure-mergeable --base origin/main``.
        Erwartung: Exit 0, HEAD unverändert, kein Merge-Commit.
        Fehlerfall: unnötiger Merge oder Fehlschlag.
        """
        url, _seed = seed_bare(self.base, "ancestor")
        project = clone_project(self.base, "ancestor", url)
        real_git(project, "checkout", "-q", "-b", "feature/x")
        (project / "feature.txt").write_text("x\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "feature: x")
        before = real_git_out(project, "rev-parse", "HEAD")

        result = self.run_ensure(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, real_git_out(project, "rev-parse", "HEAD"),
                         "Die Basis war bereits Vorfahr; kein Commit erwartet")

    def test_advanced_base_is_merged_with_a_merge_commit_and_not_pushed(self):
        """Vorbedingung: origin/main ist um einen Commit voraus.
        Aktion: ``ensure-mergeable`` im Featurebranch ausführen.
        Erwartung: Exit 0; HEAD ist ein Merge-Commit mit origin/main als
        zweitem Elternteil; beide Änderungen sind vorhanden; der Branch wird
        NICHT gepusht (kein origin/feature/x).
        Fehlerfall: kein Merge, Fast-Forward, Push oder fehlende Änderung.
        """
        project, _seed = self.feature_project("advanced")
        bare = self.base / "origin" / "advanced.git"

        result = self.run_ensure(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        parents = real_git_out(
            project, "rev-list", "--parents", "-n", "1", "HEAD").split()
        self.assertEqual(3, len(parents),
                         "HEAD ist kein Merge-Commit: " + " ".join(parents))
        self.assertEqual("remote\n",
                         (project / "remote.txt").read_text(encoding="utf-8"),
                         "Die Fernänderung fehlt nach dem Merge")
        self.assertEqual("base\n",
                         (project / "shared.txt").read_text(encoding="utf-8"),
                         "Unveränderte Datei darf durch den Merge nicht "
                         "verändert werden")
        self.assertTrue((project / "feature.txt").is_file())
        remote_branch = real_git(
            bare, "rev-parse", "--verify", "refs/heads/feature/x", check=False)
        self.assertNotEqual(
            0, remote_branch.returncode,
            "ensure-mergeable darf den Branch nicht pushen")

    def test_conflict_is_left_in_the_worktree_and_paths_are_reported(self):
        """Vorbedingung: basis und Feature ändern dieselbe Datei.
        Aktion: ``ensure-mergeable`` ausführen.
        Erwartung: Exit ≠ 0; ``.git/MERGE_HEAD`` zeigt einen laufenden Merge
        (kein Abbruch); ``shared.txt`` ist als konfliktbehaftet gemeldet und
        im Index als unmerged geführt.
        Fehlerfall: Merge wird abgebrochen, Pfad fehlt in der Ausgabe oder es
        wird fälschlich Erfolg gemeldet.
        """
        project, _seed = self.feature_project("konflikt", conflicting=True)

        result = self.run_ensure(project)

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertTrue((project / ".git" / "MERGE_HEAD").exists(),
                        "Der Merge wurde abgebrochen statt stehen gelassen")
        unmerged = real_git_out(project, "ls-files", "-u")
        self.assertIn("shared.txt", unmerged)
        self.assertIn("shared.txt", output,
                      "Der konfliktbehaftete Pfad wurde nicht gemeldet:\n"
                      + output)

    def test_after_a_repair_the_second_run_is_clean(self):
        """Vorbedingung: Konfliktfall aus dem vorigen Fall.
        Aktion: Konflikt im Arbeitsbaum lösen, ``git add`` und committen,
        danach ``ensure-mergeable`` erneut ausführen.
        Erwartung: zweiter Aufruf Exit 0, sauberer Baum, kein MERGE_HEAD.
        Fehlerfall: Reparatur wird nicht erkannt oder es bleibt ein Konflikt.
        """
        project, _seed = self.feature_project("reparatur", conflicting=True)
        first = self.run_ensure(project)
        self.assertNotEqual(0, first.returncode)

        (project / "shared.txt").write_text("feature\nremote\n", encoding="utf-8")
        real_git(project, "add", "shared.txt")
        real_git(project, "commit", "-q", "-m", "Konflikt gelöst")
        second = self.run_ensure(project)

        self.assertEqual(0, second.returncode,
                         second.stdout + second.stderr)
        self.assertFalse((project / ".git" / "MERGE_HEAD").exists())
        self.assertEqual("", real_git_out(project, "status", "--porcelain"))


# ----------------------------------------------------------------- T-G2 prune
class PruneFetchTest(GithubCase):
    """AK T-G2: Jeder Fetch entfernt veraltete Fern-Referenzen."""

    def project_with_origin(self, name):
        url, seed = seed_bare(self.base, name)
        project = clone_project(self.base, name, url)
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            'GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
            'GITHUB_BASE="main"\n', encoding="utf-8")
        # Eine temporäre Fern-Referenz anlegen und wieder löschen.
        real_git(project, "push", "-q", "origin", "main:temp")
        real_git(project, "fetch", "-q", "origin")
        real_git(seed, "push", "-q", "origin", "--delete", "temp")
        return project

    def stale_ref_exists(self, project):
        return real_git(
            project, "rev-parse", "--verify", "--quiet",
            "refs/remotes/origin/temp", check=False).returncode == 0

    def test_fetch_prunes_deleted_remote_branches(self):
        """Vorbedingung: origin/temp ist lokal bekannt, auf dem Fern gelöscht.
        Aktion: ``vibe_github.fetch(project)``.
        Erwartung: ``origin/temp`` ist danach entfernt.
        Fehlerfall: veraltete Fern-Referenz bleibt stehen.
        """
        project = self.project_with_origin("prune-fetch")
        self.assertTrue(self.stale_ref_exists(project), "Vorbedingung fehlt")

        ok, message = self.gh.fetch(project)

        self.assertTrue(ok, message)
        self.assertFalse(self.stale_ref_exists(project),
                         "fetch hat veraltete Fern-Referenzen nicht entfernt: "
                         + message)

    def test_pull_integration_prunes_deleted_remote_branches(self):
        """Vorbedingung: wie oben; GitHub ist aktiviert.
        Aktion: ``pull_integration(project)``.
        Erwartung: ``origin/temp`` ist entfernt, der Branch bleibt aktuell.
        Fehlerfall: Pull lässt veraltete Fern-Referenzen zurück.
        """
        project = self.project_with_origin("prune-pull")
        self.assertTrue(self.stale_ref_exists(project), "Vorbedingung fehlt")

        performed, ok, message = self.gh.pull_integration(project)

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertFalse(self.stale_ref_exists(project),
                         "pull_integration hat nicht gepruned: " + message)

    def test_integration_state_prunes_deleted_remote_branches(self):
        """Vorbedingung: wie oben; GitHub ist aktiviert.
        Aktion: ``integration_state(project)``.
        Erwartung: ``origin/temp`` ist entfernt und der Zustand bleibt ok.
        Fehlerfall: Prüfung lässt veraltete Fern-Referenzen zurück.
        """
        project = self.project_with_origin("prune-state")
        self.assertTrue(self.stale_ref_exists(project), "Vorbedingung fehlt")

        state = self.gh.integration_state(project)

        self.assertTrue(state["ok"], state["message"])
        self.assertFalse(self.stale_ref_exists(project),
                         "integration_state hat nicht gepruned: "
                         + state["message"])

    def test_ensure_mergeable_source_fetches_with_prune(self):
        """Vorbedingung: Quelltext der Läufermodule.
        Aktion: Umgebung des neuen Subkommandos lesen.
        Erwartung: Der ensure-mergeable-Fetch ist mit ``--prune`` verdrahtet
        (der enge Refspec lässt sich nicht verhaltensbasiert prüfen).
        Fehlerfall: Fetch ohne ``--prune``.
        """
        source = (PACKAGES.read_text(encoding="utf-8")
                  + GITHUB_MODULE.read_text(encoding="utf-8"))
        self.assertRegex(
            source,
            r"ensure[-_]mergeable[\s\S]{0,2000}?--prune",
            "ensure-mergeable nutzt keinen prune-Fetch")


# --------------------------------------------------------------- T-G3 upstream
class GithubLinkUpstreamTest(unittest.TestCase):
    """AK T-G3: ``github_link`` setzt best-effort den Upstream."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.saved = {key: os.environ.get(key)
                      for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME",
                                  "GITHUB_TOKEN", "GH_TOKEN")}
        self.addCleanup(self.restore)
        for key in ("GITHUB_TOKEN", "GH_TOKEN"):
            os.environ.pop(key, None)
        self.project = self.workspace / "proj"
        self.url, self.seed = seed_bare(self.base, "link-origin")
        self.bare = self.base / "origin" / "link-origin.git"
        real_git(self.workspace, "clone", "-q", self.url, "proj")
        (self.project / ".vibe").mkdir()
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        real_git(self.project, "add", "-A")
        real_git(self.project, "commit", "-q", "-m", "projekt")
        self.cli = load_cli(self.workspace, self.home)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_link_sets_upstream_for_branches_with_a_remote_counterpart(self):
        """Vorbedingung: lokale Branches ``main`` und ``feature/up`` haben
        beide ``origin/<branch>``; ``feature/up`` hat noch keinen Upstream.
        Aktion: ``github_link(proj, file://…)`` aufrufen.
        Erwartung: beide Branches zeigen auf ``origin/<branch>``.
        Fehlerfall: Upstream fehlt weiterhin.
        """
        real_git(self.project, "checkout", "-q", "-b", "feature/up")
        (self.project / "up.txt").write_text("up\n", encoding="utf-8")
        real_git(self.project, "add", "-A")
        real_git(self.project, "commit", "-q", "-m", "up")
        real_git(self.project, "push", "-q", "origin", "feature/up")
        real_git(self.project, "checkout", "-q", "main")

        self.cli.github_link("proj", "file://" + str(self.bare))

        for branch in ("main", "feature/up"):
            with self.subTest(branch=branch):
                upstream = real_git(
                    self.project, "rev-parse", "--abbrev-ref",
                    branch + "@{upstream}", check=False)
                self.assertEqual(
                    0, upstream.returncode,
                    "Kein Upstream für %s: %s" % (branch, upstream.stderr))
                self.assertEqual("origin/" + branch, upstream.stdout.strip())

    def test_link_is_not_fatal_when_a_local_branch_has_no_counterpart(self):
        """Vorbedingung: lokaler Branch ``nur-lokal`` ohne ``origin/``-Pendant.
        Aktion: ``github_link`` aufrufen.
        Erwartung: Aufruf gelingt; der Branch bleibt ohne Upstream.
        Fehlerfall: Link bricht wegen des fehlenden Gegenstücks ab.
        """
        real_git(self.project, "branch", "nur-lokal")

        view = self.cli.github_link("proj", "file://" + str(self.bare))

        self.assertTrue(view.get("enabled"), view)
        upstream = real_git(
            self.project, "rev-parse", "--abbrev-ref",
            "nur-lokal@{upstream}", check=False)
        self.assertNotEqual(0, upstream.returncode,
                            "Für einen Branch ohne Fern-Pendant darf kein "
                            "Upstream gesetzt werden")


class GithubCliStatusTest(unittest.TestCase):
    """AK Review-Befund 3: ``vibe github <projekt> status`` nennt Auto-Merge."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.saved = {key: os.environ.get(key)
                      for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
        self.addCleanup(self.restore)
        self.project = self.workspace / "proj"
        real_git(self.workspace, "init", "-q", "-b", "main", "proj")
        real_git(self.project, "config", "user.name", "Test")
        real_git(self.project, "commit", "--allow-empty", "-q", "-m", "init")
        (self.project / ".vibe").mkdir()
        self.cli = load_cli(self.workspace, self.home)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def status_output(self, auto_merge):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nGITHUB_ENABLED=""\nGITHUB_AUTO_MERGE="%s"\n'
            % auto_merge, encoding="utf-8")
        out = io.StringIO()
        self.cli.cmd_github("proj", "status", out=out)
        return out.getvalue()

    def auto_merge_line(self, output):
        for line in output.splitlines():
            if "Auto-Merge:" in line:
                return line
        return ""

    def test_status_names_auto_merge_ja_when_enabled(self):
        """Vorbedingung: ``GITHUB_AUTO_MERGE="1"``.
        Aktion: ``vibe github proj status`` über ``cmd_github(..., out=…)``.
        Erwartung: Eine Zeile „Auto-Merge:“ meldet „ja“.
        Fehlerfall: Der Status verschweigt den Schalter.
        """
        output = self.status_output("1")

        line = self.auto_merge_line(output)
        self.assertTrue(line, "Keine Auto-Merge-Zeile im Status:\n" + output)
        self.assertIn("ja", line.lower(), line)

    def test_status_names_auto_merge_nein_when_disabled(self):
        """Vorbedingung: ``GITHUB_AUTO_MERGE=""`` (Standard aus).
        Aktion: ``vibe github proj status``.
        Erwartung: Eine Zeile „Auto-Merge:“ meldet „nein“.
        Fehlerfall: Aus wird als an dargestellt.
        """
        output = self.status_output("")

        line = self.auto_merge_line(output)
        self.assertTrue(line, "Keine Auto-Merge-Zeile im Status:\n" + output)
        self.assertIn("nein", line.lower(), line)


# ------------------------------------------------------- T-G4 worktree checkout
class WorktreeCheckoutTest(GithubCase):
    """AK T-G4: Ein in einer Arbeitskopie ausgecheckter Branch bleibt tabu."""

    def test_checkout_branch_refuses_a_branch_held_by_another_worktree(self):
        """Vorbedingung: ``feature/held`` ist in einer zweiten Arbeitskopie
        ausgecheckt, das Projekt steht auf ``main``.
        Aktion: ``checkout_branch(project, "feature/held")``.
        Erwartung: Die Funktion verweigert mit einer Meldung, die die
        Arbeitskopie nennt; das Projekt bleibt auf ``main``.
        Fehlerfall: Der Branch wird gewaltsam ausgecheckt oder eine
        unverständliche Git-Fehlermeldung durchgereicht.
        """
        url, _seed = seed_bare(self.base, "worktree-held")
        project = clone_project(self.base, "worktree-held", url)
        real_git(project, "branch", "feature/held")
        second = self.base / "second-worktree"
        real_git(project, "worktree", "add", "-q", str(second), "feature/held")

        try:
            ok, message = self.gh.checkout_branch(project, "feature/held")
        except ValueError as error:
            ok, message = False, str(error)

        self.assertFalse(ok, "Branch in fremder Arbeitskopie wurde ausgecheckt")
        self.assertIn("Arbeitskopie", str(message), str(message))
        self.assertEqual("main", real_git_out(project, "rev-parse",
                                              "--abbrev-ref", "HEAD"))


# -------------------------------------------- T-G0/T-G1 runner ownership paths
class _MergeHandler(BaseHTTPRequestHandler):
    """REST-Fake: PR-Erstellung, Zustandsabfrage und Squash-Merge."""

    def log_message(self, fmt, *args):
        pass

    def _record(self, body=b""):
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "body": json.loads(body.decode("utf-8")) if body else None,
            "authorization": self.headers.get("Authorization") or "",
        })

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._record()
        merged = bool(self.server.merged)
        self._respond(200, {
            "number": 42, "state": "closed" if merged else "open",
            "merged": merged,
            "mergeable": True, "mergeable_state": "clean",
            "merged_at": "2026-01-01T00:00:00Z" if merged else None,
            "html_url": self.server.pr_url,
        })

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        if self.path.rstrip("/").endswith("/pulls"):
            self._respond(201, {"number": 42, "html_url": self.server.pr_url,
                                "state": "open", "merged": False})
            return
        self._respond(404, {"message": "Not Found"})

    def do_PUT(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        if self.path.rstrip("/").endswith("/merge"):
            try:
                self.server.on_merge()
            except Exception as error:  # noqa: BLE001 - im Fake sichtbar machen
                self.server.merge_error = repr(error)
                self._respond(500, {"message": "fake merge failed"})
                return
            self.server.merged = True
            self._respond(200, {"merged": True, "sha": "squash",
                                "message": "Pull Request successfully merged"})
            return
        self._respond(404, {"message": "Not Found"})


class MergeRestFakeServer:
    """Loopback-REST-Fake mit optionalem Squash-Merge-Callback."""

    def __init__(self, on_merge=None, port=None):
        self.requests = []
        self.on_merge = on_merge or (lambda: None)
        self.merge_error = ""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if port is None:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        self.port = port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _MergeHandler)
        self.httpd.requests = self.requests
        self.httpd.on_merge = self.on_merge
        self.httpd.merge_error = ""
        self.httpd.merged = False
        self.httpd.pr_url = "http://127.0.0.1:%d/pull/42" % port
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def calls(self, method):
        return [item for item in self.requests
                if item["method"] == method]

    def puts(self):
        return self.calls("PUT")

    def posts(self):
        return self.calls("POST")


class RunnerFixtureMixin:
    """AP9-Läuferfixture: echtes Git, Fake-Agent, lokale Bare-Quelle."""

    def _fixture(self):
        # Import hier, damit das Modul auch ohne die Fixture ladbar bleibt.
        from tests.unit.test_ap9_runner_wiring import AP9WiringFixture
        return AP9WiringFixture

    def setUp(self):
        fixture = self._fixture()
        self.fixture = fixture
        fixture.setUp(self)

    def tearDown(self):
        self.fixture.tearDown(self)

    def run_runner(self, project, **extra):
        return self.fixture.run_runner(self, project, **extra)

    def env(self, project, **extra):
        return self.fixture.env(self, project, **extra)

    def log(self, project=None):
        return self.fixture.log(self, project)

    def worktrees(self):
        return self.fixture.worktrees(self)

    def report(self, project):
        path = self.runtime / (project.name + ".report.txt")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def make_github_project(self, api, auto_merge=None, name="proj"):
        extra = ('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                 'GITHUB_BASE="main"\nGITHUB_API="%s"\n' % api)
        if auto_merge is not None:
            extra += 'GITHUB_AUTO_MERGE="%s"\n' % auto_merge
        from tests.unit.test_ap9_runner_wiring import FEEDBACK_ONE
        return self.fixture.make_project(
            self, env_extra=extra, feedback=FEEDBACK_ONE, name=name)

    def prepare_origin(self, project, name="proj"):
        bare = self.fixture.empty_bare(self, name)
        self.fixture.link_origin(self, project, bare)
        self.fixture.publish(self, project, bare)
        return bare

    def squash_merge_to_bare(self, bare, branch="feature/test/f1"):
        """Simuliert den GitHub-Squash-Merge auf dem Fern-Integrationsstand."""
        seed = self.root / "squash-seed"
        if not seed.exists():
            real_git(self.root, "clone", "-q", "file://" + str(bare), str(seed))
        real_git(seed, "fetch", "-q", "origin")
        real_git(seed, "checkout", "-q", "-B", "main", "origin/main")
        real_git(seed, "merge", "--squash", "-q", "origin/" + branch)
        real_git(seed, "-c", "user.name=Test", "-c",
                 "user.email=test@example.invalid", "commit", "-q", "-m",
                 "F1: squash")
        real_git(seed, "push", "-q", "origin", "main")
        return real_git_out(bare, "rev-parse", "main")

    def worktree_registry(self):
        sys.path.insert(0, str(BIN))
        try:
            from vibe_runs import WorktreeRegistry  # noqa: PLC0415
        finally:
            sys.path.remove(str(BIN))
        return WorktreeRegistry(str(self.runtime))


class PrOnlyRunnerTest(RunnerFixtureMixin, unittest.TestCase):
    """AK T-G0/T-G1: Ohne Schalter bleibt der PR-only-Standard stehen."""

    def test_pr_only_stops_without_local_merge_and_keeps_the_worktree(self):
        """Vorbedingung: GitHub aktiv, ``GITHUB_AUTO_MERGE`` nicht gesetzt;
        Paket und REST-Fake bereit.
        Aktion: Läufer ausführen.
        Erwartung: Branch wird gepusht und der MR gestellt; KEIN lokaler
        Merge, Arbeitskopie bleibt, Registry-Eintrag mit MR-URL existiert,
        Ticket bleibt offen mit Blockievermerk; Protokoll nennt „wartet auf
        Merge“ und ``vibe package close``; kein REST-Merge.
        Fehlerfall: lokaler Merge, Cleanup, stilles Verschlucken oder
        fehlender Wartehinweis.
        """
        server = MergeRestFakeServer().start()
        self.addCleanup(server.close)
        project = self.make_github_project(server.base)
        bare = self.prepare_origin(project)

        result = self.run_runner(project)
        log = self.log(project)

        self.assertIn("wartet auf merge", log.lower(),
                      "Kein Wartehinweis im Protokoll:\n" + log)
        self.assertIn("vibe package close", log,
                      "Der nächste Schritt fehlt im Protokoll:\n" + log)
        self.assertNotEqual(
            0, real_git(project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode,
            "PR-only darf nicht lokal mergen:\n" + log)
        self.assertEqual(
            0, real_git(bare, "rev-parse", "--verify",
                        "refs/heads/feature/test/f1", check=False).returncode,
            "Der Paketbranch muss gepusht sein")
        feedback = (project / "FEEDBACK.md").read_text(encoding="utf-8")
        self.assertIn("- [ ] F1", feedback, feedback)
        self.assertIn("BLOCKIERT", feedback.upper(), feedback)
        self.assertTrue(self.fixture.worktrees(self), "Arbeitskopie fehlt")
        entries = self.worktree_registry().all()
        self.assertTrue(
            any(entry.get("id") == "F1"
                and entry.get("pr_url", "").endswith("/pull/42")
                for entry in entries),
            "Registry-Eintrag mit MR-URL fehlt: " + repr(entries))
        self.assertEqual([], server.puts(),
                         "PR-only darf keinen REST-Merge auslösen")


class AutoMergeRunnerTest(RunnerFixtureMixin, unittest.TestCase):
    """AK T-G0: ``GITHUB_AUTO_MERGE="1"`` mergt den PR und räumt auf."""

    def test_auto_merge_squashes_the_pr_and_cleans_up(self):
        """Vorbedingung: ``GITHUB_AUTO_MERGE="1"``; REST-Fake kann PR
        anlegen, abfragen und squash-mergen; der Merge-Callback schreibt den
        Squash-Commit auf den Fern-Integrationsstand.
        Aktion: Läufer ausführen.
        Erwartung: Exit 0; genau ein REST-Merge mit ``merge_method=squash``;
        der Integrationsstand ist auf der Fernspitze, enthält die
        Paketänderung und den abgehakten Nachweis; Arbeitskopie, Branch und
        Registry-Eintrag sind entfernt.
        Fehlerfall: kein Merge, falsche Merge-Art, lokaler Altstand oder
        zurückbleibende Arbeitskopie.
        """
        bare = None
        server = None

        def merge():
            self.squash_merge_to_bare(bare)

        server = MergeRestFakeServer(on_merge=merge).start()
        self.addCleanup(server.close)
        project = self.make_github_project(server.base, auto_merge="1")
        bare = self.prepare_origin(project)

        result = self.run_runner(project)
        log = self.log(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", server.merge_error)
        puts = server.puts()
        self.assertTrue(puts, "Kein REST-Merge ausgelöst:\n" + log)
        self.assertEqual("squash", (puts[-1]["body"] or {}).get("merge_method"),
                         puts[-1])
        remote_tip = real_git_out(bare, "rev-parse", "main")
        self.assertEqual(remote_tip, real_git_out(project, "rev-parse", "HEAD"),
                         "Der Integrationsstand ist nicht auf der Fernspitze")
        self.assertEqual(
            0, real_git(project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode,
            "Die Paketänderung fehlt im Integrationsstand")
        self.assertIn("- [x] F1",
                      (project / "FEEDBACK.md").read_text(encoding="utf-8"))
        report = self.report(project)
        self.assertIn("Geschlossen: F1 — Branch feature/test/f1", report)
        self.assertIn("Merge-Request http://127.0.0.1:", report)
        self.assertNotEqual(
            0, real_git(project, "rev-parse", "--verify",
                        "refs/heads/feature/test/f1", check=False).returncode,
            "Der lokale Paketbranch muss entfernt sein")
        self.assertFalse(
            any((self.runtime / "worktrees").glob("*"))
            if (self.runtime / "worktrees").exists() else False,
            "Die Arbeitskopie muss entfernt sein")
        self.assertEqual([], self.worktree_registry().all(),
                         "Der Registry-Eintrag muss entfernt sein")

    def test_auto_merge_does_not_merge_when_the_gate_is_red(self):
        """Vorbedingung: Auto-Merge an, aber der Agent liefert keine
        Nachweise (Abschlussschranke rot).
        Aktion: Läufer ausführen.
        Erwartung: kein REST-Merge, kein lokaler Merge, Blockievermerk.
        Fehlerfall: Auto-Merge übergeht die Schranke.
        """
        server = MergeRestFakeServer().start()
        self.addCleanup(server.close)
        project = self.make_github_project(server.base, auto_merge="1")
        self.prepare_origin(project)

        result = self.run_runner(project, FAKE_MODE="no-artifacts")

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        self.assertEqual([], server.puts(),
                         "Auto-Merge darf eine rote Schranke nicht übergehen")
        self.assertNotEqual(
            0, real_git(project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode)


if __name__ == "__main__":
    unittest.main()
