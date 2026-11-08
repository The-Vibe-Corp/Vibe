"""Browserabnahme F24: Aktiver Agent, Subagentenausgabe und Tabs in der
Ausgabemaske des Projekt-Details.

Startpunkt ist das echte Dashboard (bin/vibe-web.py) auf einem eigenen Port
mit eigenem HOME und isoliertem VIBE-Root, analog tests/browser/
test_run_autostop_ui.py. Der aktive Lauf wird ohne tmux nachgebildet: Der
Laufregistereintrag (``_logs/runs.json``, Zustand ``running``) ist laut F19
Autorität für die Laufaktivität. Subagenten-Zustand und deren Ausgabe stehen
in ``_logs/proj.log.state.json``; ein kleines ``_logs/proj.log`` füttert den
SSE-Stream mit Hauptschriftler-Ausgabe. Keine produktive Installation, keine
echten Läufe, keine Modellkosten.

Seeds:
 * Laufregister via bin/vibe_runs.py start --agent vibe-agent --state running
   (Projektname und Key konsistent "proj", Logpfad ``_logs/proj.log``);
 * Zustandsdatei mit eingebettetem ``output``; der Lauf-Key ist hart gesetzt
   (``proj``), sodass Log- und Zustandspfad eindeutig stimmen.

Testfälle (Akzeptanzkriterien aus dem Arbeitspaket F24):

a) test_active_agent_is_shown_in_the_output_area        [AK1]
   Vorbedingung: Registereintrag running mit agent "vibe-agent"; Ausgabe-Tab
   geöffnet.
   Aktion: Projektdetail öffnen, Detailtab "Ausgabe" wählen.
   Erwartung: Der Ausgabebereich zeigt den Agentennamen "vibe-agent" (Pill
   #agent-active). Ohne aktiven Lauf (Register finished, frischer Aufruf):
   "vibe-agent" erscheint nicht wieder im Ausgabebereich; geprüft wird
   poll-basiert über mehrere 3-s-Pollzyklen der Ausgabekarte.
   Fehlerfall: Agentenname fehlt trotz aktivem Lauf oder bleibt nach dem
   Laufende stehen.

b) test_parallel_agents_get_one_tab_each                [AK3]
   Vorbedingung: aktiver Lauf + Subagent ses_subA (tester, Untersuche X)
   status running in proj.log.state.json.
   Aktion: Ausgabebereich öffnen.
   Erwartung: Genau eine [role=tablist] im Ausgabebereich sichtbar; ein Tab
   enthält "Hauptagent", ein weiterer Tab den Subagenten ("tester" /
   "Untersuche X"); genau ein Tab ist aktiv (aria-selected="true").
   Fehlerfall: Tabliste fehlt, Tabs fehlen oder mehrere Tabs aktiv.

c) test_tab_switch_loads_the_subagent_output            [AK2, AK3]
   Vorbedingung: wie b); Klick auf den Subagent-Tab.
   Aktion: Tab betitelt mit "tester"/"Untersuche X" anklicken, dann erneut
   den "Hauptagent"-Tab.
   Erwartung: Nach dem Klick enthält die sichtbare Ausgabe "Ausgabe A";
   nach dem Rückwechsel die Hauptmarkierung "HAUPT-4711"; kein
   JavaScript-Fehler (pageerror) bei den Wechseln.
   Fehlerfall: Ausgabe wechselt nicht, erscheint leer, oder Wechsel wirft
   einen Skriptfehler.

d) test_finishing_a_subagent_closes_its_tab             [AK4]
   Vorbedingung: wie b); danach Zustandsdatei geändert: Subagent status
   "completed" (ended gesetzt).
   Aktion: Änderung abwarten (Poll-Zyklus ≤ 5 s, toleranter 12 s).
   Erwartung: Der Subagent-Tab verschwindet; bleibt nur der Hauptagent
   aktiv, ist anschließend keine Tabliste mehr vorhanden. Die Prüfung gilt
   der Ausgabekarte (.logcard): Dort bleiben weder Tab noch Inhalt des
   beendeten Subagenten; die Hauptausgabe bleibt sichtbar. Die F19-
   Übersichtskarte führt beendete Subagenten dokumentiert weiter (F19) und
   wird nicht beanstandet.
   Fehlerfall: Tab bleibt über den Abwartungszeitraum bestehen.

f) test_keyboard_navigation_through_agent_tabs          [AK3]
   Vorbedinung: aktiver Lauf + zwei laufende Subagenten (tester/"Untersuche
   X" mit "Ausgabe A", builder/"Prüfe Y" mit "Ausgabe B") → Tabliste
   "Hauptagent", Subagent A, Subagent B; Tab-Button fokussiert (Klick).
   Aktion: Pfeiltasten und Home/End auf dem fokussierten Tab-Button senden.
   Erwartung: Die *Auswahl* (aria-selected, genau ein Tab) läuft index-
   basiert relativ zum aktuell gewählten Tab: ArrowRight wandert der Reihe
   nach und rotiert am Listenende, ArrowLeft rotiert zurück; Home wählt den
   ersten, End den letzten Tab. Der sichtbare Pane/Pre-Inhalt passt zur
   Auswahl ("Ausgabe A", "Ausgabe B" bzw. Hauptausgabe "HAUPT-4711"). Der
   Fokus bleibt während der Tastaturbedienung innerhalb der Tabliste
   operabel (fokussiertes Element bleibt ein Tab-Button). Kein pageerror.
   Hinweis: Ob der Fokus der Selektionsänderung folgt, ist weder im
   Arbeitspaket noch in der Funkdoko festgelegt; geprüft wird die
   dokumentierte Tastaturbedienung der Auswahl samt inhaltsbezogenem
   Pane-Wechsel.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

AGENT = "vibe-agent"
MAIN_MARKER = "HAUPT-4711: Der Hauptagent schreibt sein Protokoll."
SUB_SESSION = "ses_subA"
SUB_OUTPUT = "Ausgabe A"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class F24OutputTabsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F24 Tababnahme\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        # Ererbte vibe-Umgebung ist keine Testisolierung: Der Dev-Aufruf
        # bekommt ausschließlich eigene Pfade (wie die Unit-Fixtur F19).
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "TMPDIR": str(cls.root / "tmp"),
                "TMUX_TMPDIR": str(cls.tmux_dir),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
            }
        )
        (cls.root / "tmp").mkdir(parents=True)
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.root.joinpath("web-server.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            if cls.proc.stdout:
                cls.proc.stdout.close()
            cls.tmp.cleanup()

    # ---------- Seeds und Helfer ----------

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        (self.log_dir / "proj.log.state.json").unlink(missing_ok=True)
        self.page_errors = []
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})
        self.page.on(
            "pageerror",
            lambda e: self.page_errors.append(str(e)),
        )

    def tearDown(self):
        self.page.close()

    def register_run(self, state="running", agent=AGENT):
        """Aktiver Lauf ohne tmux: Laufregistereintrag mit dem echten
        Werkzeug (die Web-API behandelt den LIVE-Zustand als aktiv)."""
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.log_dir),
                "--project", str(self.project),
                "--name", "proj", "--key", "proj", "--agent", agent,
                "--state", state,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def write_log(self):
        (self.log_dir / "proj.log").write_text(
            "=== Agentenlauf proj ===\n" + MAIN_MARKER + "\n",
            encoding="utf-8",
        )

    def write_state(self, subs):
        """Zustandsdatei mit eingebetteter Subagenten-Ausgabe."""
        payload = {
            "session": "ses_main",
            "subagents": subs,
        }
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def running_sub(self, session=SUB_SESSION, agent="tester",
                    description="Untersuche X", output=SUB_OUTPUT):
        return {
            "session": session,
            "agent": agent,
            "description": description,
            "prompt": description + " gründlich",
            "status": "running",
            "started": int(time.time()),
            "ended": 0,
            "output": output,
        }

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail(message)

    def panel(self):
        """Der Ausgabebereich des Projekt-Details."""
        return self.page.locator("[data-panel='ausgabe']")

    def open_detail(self, wait_running=True):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=15000)
        row.click()
        if wait_running:
            self.wait_until(
                lambda: self.page.locator("#runstate").inner_text().strip()
                in ("läuft", "gestoppt"),
                message="Projektdetail zeigte keinen Laufstatus",
            )

    def open_output(self):
        """Detailbereich "Ausgabe" über den Projekttablist wählen."""
        tabs = self.page.locator("[aria-label='Projektbereiche'] button[role=tab]")
        out_tab = tabs.filter(has_text="Ausgabe").first
        out_tab.click()
        self.panel().wait_for(state="visible", timeout=10000)

    def visible_text(self, *texts, timeout=12):
        """True, sobald jeder Text im Ausgabebereich sichtbar ist."""
        deadline = time.time() + timeout
        target = self.panel()
        while time.time() < deadline:
            content = target.inner_text(timeout=2000)
            if all(text in content for text in texts):
                return True
            time.sleep(0.15)
        return False

    def output_tablist(self):
        """Tabliste im Ausgabebereich (nicht der Projektbereichstablist)."""
        return self.panel().locator("[role='tablist']")

    def output_tabs(self):
        return self.output_tablist().locator("[role='tab']")

    def absent_from_output(self, text, timeout=12):
        """True, sobald der Text im Ausgabebereich verschwunden ist; geprueft
        wird poll-basiert über die angegebene Frist (mehrere 3-s-Zyklen)."""
        deadline = time.time() + timeout
        target = self.panel()
        while time.time() < deadline:
            if text not in target.inner_text(timeout=2000):
                return True
            time.sleep(0.25)
        return False

    def card_contains(self, text, timeout=12):
        """True, sobald der Text in der Ausgabekarte sichtbar ist."""
        deadline = time.time() + timeout
        target = self.log_card()
        while time.time() < deadline:
            if text in target.inner_text(timeout=2000):
                return True
            time.sleep(0.15)
        return False

    def log_card(self):
        """Die Ausgabekarte mit Agentenzeile, Tabs und Ausgabe (F24-Bereich);
        die F19-Subagenten-Übersichtskarte daneben ist nicht Teil dieser
        Prüfung."""
        return self.panel().locator(".logcard")


class ActiveAgentShown(F24OutputTabsBrowserTest):
    def test_active_agent_is_shown_in_the_output_area(self):
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state([])
        self.open_detail()
        self.open_output()
        self.assertTrue(
            self.visible_text(AGENT, timeout=12),
            "Bei aktivem Lauf zeigt der Ausgabebereich nicht den Agenten "
            + AGENT,
        )
        # Ohne aktiven Lauf: Register finished → KEIN Agentenname mehr.
        self.register_run(state="finished", agent=AGENT)
        url = self.base + "/#t=" + self.token
        self.page.goto(url)
        # Die SPA ersetzt den Hash beim Laden (history.replaceState auf
        # location.pathname). Ohne vollständiges Neuladen wäre der zweite
        # Aufruf nur eine Fragment-Navigation und liefe in der Detailansicht.
        self.page.reload()
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=15000)
        row.click()
        self.open_output()
        self.wait_until(
            lambda: self.page.locator("#runstate").inner_text().strip()
            == "gestoppt",
            message="Lauf wurde nach Registerende nicht als gestoppt angezeigt",
        )
        # Poll-basiert über mehrere Ausgabekarten-Pollzyklen statt festem
        # Sleep-Fenster: Der Agentenname muss innerhalb der Wartefrist
        # verschwinden; die Pill kehrt auf die Plätze-Meldung zurück.
        self.wait_until(
            lambda: self.page.locator("#agent-active").inner_text().strip()
            == "—",
            message="Agentenzeile bleibt nach dem Laufende auf dem Agentennamen stehen",
            timeout=12,
        )
        self.assertTrue(
            self.absent_from_output(AGENT, timeout=12),
            "Nach dem Laufende wird der Agentenname noch angezeigt",
        )


class ParallelTabs(F24OutputTabsBrowserTest):
    def seed_two_agents(self):
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state([self.running_sub()])
        self.open_detail()
        self.open_output()

    def test_parallel_agents_get_one_tab_each(self):
        self.seed_two_agents()
        tablist = self.output_tablist()
        self.assertTrue(
            tablist.count() == 1 and tablist.first.is_visible(),
            "Es gibt nicht genau eine sichtbare Tabliste im Ausgabebereich",
        )
        tabs = self.output_tabs()
        self.wait_until(
            lambda: tabs.count() >= 2,
            message="Hauptagent-Tab und Subagent-Tab fehlen (Anzahl: "
            + str(tabs.count()) + ")",
        )
        labels = [tabs.nth(i).inner_text() for i in range(tabs.count())]
        self.assertTrue(
            any("Hauptagent" in label for label in labels),
            "Hauptagent-Tab fehlt: " + repr(labels),
        )
        self.assertTrue(
            any(("tester" in label or "Untersuche X" in label)
                for label in labels),
            "Subagent-Tab fehlt: " + repr(labels),
        )
        selected = sum(
            1 for i in range(tabs.count())
            if tabs.nth(i).get_attribute("aria-selected") == "true"
        )
        self.assertEqual(
            selected, 1, "Genau ein Tab muss aktiv sein: " + repr(labels)
        )

    def test_tab_switch_loads_the_subagent_output(self):
        self.seed_two_agents()
        tabs = self.output_tabs()
        self.wait_until(
            lambda: tabs.count() >= 2,
            message="Subagent-Tab fehlt",
        )
        seltab = tabs.filter(has_text="Untersuche X").first
        self.assertGreater(seltab.count(), 0, "Subagent-Tab nicht gefunden")
        seltab.click()
        self.assertTrue(
            self.visible_text(SUB_OUTPUT, timeout=12),
            "Ausgabe des Subagenten erscheint nach dem Tabwechsel nicht",
        )
        main = tabs.filter(has_text="Hauptagent").first
        self.assertGreater(main.count(), 0, "Hauptagent-Tab nicht gefunden")
        main.click()
        self.assertTrue(
            self.visible_text("HAUPT-4711", timeout=12),
            "Nach dem Rückwechsel erscheint die Hauptausgabe nicht",
        )
        self.assertEqual(
            [str(e) for e in self.page_errors], [],
            "Der Tabwechsel erzeugte JavaScript-Fehler",
        )

    def test_finishing_a_subagent_closes_its_tab(self):
        self.seed_two_agents()
        tabs = self.output_tabs()
        self.wait_until(
            lambda: tabs.count() >= 2,
            message="Vorbedingung: Subagent-Tab fehlt",
        )
        # Subagent fertig: Zustandsdatei mit status completed (ended gesetzt).
        done = self.running_sub()
        done["status"] = "completed"
        done["ended"] = int(time.time()) + 1
        self.write_state([done])
        # Tab Wegfall spätestens nach dem nächsten Poll(-Zyklen).
        self.wait_until(
            lambda: not tabs.filter(has_text="Untersuche X").count()
            or not self.output_tablist().first.is_visible(),
            message="Der Subagent-Tab blieb nach dem Abschluss bestehen",
            timeout=12,
        )
        # Prüfumfang Ausgabekarte: Der beendete Subagent darf dort weder als
        # Tab noch als Inhalt bleiben; die F19-Übersichtskarte rechts führt
        # beendete Subagenten weiter und wird hier bewusst nicht beanstandet.
        card = self.log_card()
        card_text = card.inner_text()
        self.assertNotIn(
            "Untersuche X", card_text,
            "Der beendete Subagent bleibt in der Ausgabekarte sichtbar",
        )
        self.assertIn(
            "HAUPT-4711", card_text,
            "Die Hauptausgabe fehlt in der Ausgabekarte",
        )
        self.assertTrue(
            self.visible_text("HAUPT-4711", timeout=8),
            "Der Hauptagent wird nach dem Tab-Rückfall nicht angezeigt",
        )
        # Nur noch ein aktiver Agent → keine Tabliste nötig.
        self.wait_until(
            lambda: self.output_tablist().count() == 0
            or not self.output_tablist().first.is_visible(),
            message="Tabliste blieb bestehen, obwohl nur der Hauptagent aktiv ist",
            timeout=12,
        )


class KeyboardTabs(F24OutputTabsBrowserTest):
    """AK3, Tastaturbedienung: Die Auswahl (aria-selected, genau ein Tab)
    laeuft indexbasiert relativ zum gewaehlten Tab (Pfeile rotieren; Home/End
    springen); der sichtbare Pane-Inhalt folgt der Auswahl. Der Fokus bleibt
    bei der Tastaturbedienung ein Tab-Button der Liste (Bedienbarkeit); ob er
    der Selektionsaenderung folgt, ist nicht fachlich festgelegt."""

    MAIN = "Hauptagent"
    SUB_A = "tester — Untersuche X"
    SUB_B = "builder — Prüfe Y"

    def seed_three_tabs(self):
        """Hauptagent + 2 laufende Subagenten; Ausgabebereich geöffnet."""
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state([
            self.running_sub(
                session="ses_subA", agent="tester",
                description="Untersuche X", output="Ausgabe A"),
            self.running_sub(
                session="ses_subB", agent="builder",
                description="Prüfe Y", output="Ausgabe B"),
        ])
        self.open_detail()
        self.open_output()
        tabs = self.output_tabs()
        self.wait_until(
            lambda: tabs.count() == 3,
            message=f"Vorbedingung: Tabliste hat nicht 3 Tabs, sondern {tabs.count()}",
            timeout=12,
        )

    def selected_labels(self):
        """Labels der Tabs mit aria-selected="true" (genau eines erwartet)."""
        tabs = self.output_tabs()
        return [
            tabs.nth(i).inner_text() for i in range(tabs.count())
            if tabs.nth(i).get_attribute("aria-selected") == "true"
        ]

    def focus_is_inside_tablist(self):
        return self.page.evaluate(
            "!!(document.activeElement && document.activeElement.closest"
            "('div[aria-label=\"Aktive Agenten\"][role=tablist]'))"
        )

    def press_key(self, key, expect_label, expect_inside, expect_absent):
        """Taste auf dem fokussierten Tab-Button senden; Auswahl-Label,
        Pane-Inhalt und Fokuslage prüfen."""
        self.page.keyboard.press(key)
        self.wait_until(
            lambda: self.selected_labels() == [expect_label],
            message=f"Taste {key} sollte {expect_label!r} auswaehlen, tatsächlich "
            + repr(self.selected_labels()),
            timeout=12,
        )
        for text in expect_inside:
            self.assertTrue(
                self.card_contains(text, timeout=10),
                f"Nach {key} erscheint {text!r} nicht in der Ausgabekarte",
            )
        for text in expect_absent:
            self.assertNotIn(
                text, self.log_card().inner_text(),
                f"Nach {key} bleibt {text!r} trotzdem sichtbar",
            )
        self.assertTrue(
            self.focus_is_inside_tablist(),
            f"Nach {key} liegt der Fokus außerhalb der Agent-Tabliste",
        )

    def test_keyboard_navigation_through_agent_tabs(self):
        self.seed_three_tabs()
        # Fokussierter Start: Hauptagent-Tab wählen (Klick setzt den Fokus).
        main_tab = self.output_tabs().filter(has_text=self.MAIN).first
        self.assertGreater(main_tab.count(), 0, "Hauptagent-Tab nicht gefunden")
        main_tab.click()
        self.wait_until(
            lambda: self.selected_labels() == [self.MAIN],
            message="Klick auf den Hauptagent-Tab wählt diesen nicht aus",
            timeout=10,
        )
        self.assertIn("HAUPT-4711", self.log_card().inner_text())
        # ArrowRight-Kette: main -> subA -> subB -> main (Rotation am Ende).
        self.press_key("ArrowRight", self.SUB_A, ("Ausgabe A",), ("HAUPT-4711",))
        self.press_key("ArrowRight", self.SUB_B, ("Ausgabe B",), ("Ausgabe A",))
        self.press_key("ArrowRight", self.MAIN, ("HAUPT-4711",), ("Ausgabe B",))
        # ArrowLeft rotiert von main zurück zum letzten Tab.
        self.press_key("ArrowLeft", self.SUB_B, ("Ausgabe B",), ("HAUPT-4711",))
        # Home -> erster Tab, End -> letzter Tab.
        self.press_key("Home", self.MAIN, ("HAUPT-4711",), ("Ausgabe B",))
        self.press_key("End", self.SUB_B, ("Ausgabe B",), ("HAUPT-4711",))
        self.assertEqual(
            [str(e) for e in self.page_errors], [],
            "Die Tastaturbedienung erzeugte JavaScript-Fehler",
        )

if __name__ == "__main__":
    unittest.main()
