"""Unit-Abnahme AP19 (Teil 1): Session-Register und Zustandsableitung.

Arbeitspaket AP19 „Session Management“ verlangt, dass vibe die letzten
Sessions (Standard 5, konfigurierbar) auflisten, wiederfinden und fortsetzen
kann. Grundlage dafür ist ein eigenes Register ``<laufzeit>/sessions.json``
neben ``runs.json``:

* Struktur ``{"limit": <int Standard 5>, "sessions": [...]}``; ein Eintrag
  trägt ``session``, ``project`` (realer Projektpfad), ``name``,
  ``run_id`` (darf leer sein), ``agent``, ``harness``, ``first_seen`` und
  ``last_seen`` (Sekunden seit Epoche).
* ``SessionRegistry(runtime)`` führt das Register im Muster von
  ``RunRegistry``: eigene Sperrdatei ``sessions.lock``, atomare Schreibweise
  über die bestehende ``_atomic_write``-Hilfe, höchstens 100 Einträge (die
  jüngsten bleiben).
* ``observe(...)`` legt je Session-Kennung genau einen Eintrag an bzw.
  aktualisiert ihn (Upsert). Ungültige Kennungen (leer oder nicht
  ``[A-Za-z0-9_-]+``) werden ignoriert und niemals geschrieben.
* ``limit()`` liefert den gespeicherten Standard (5), ``set_limit(n)``
  validiert 1..100 und wirft sonst ``ValueError``.
* ``session_overview(runtime, project=None, limit=None, text=None)`` leitet je
  Eintrag einen Zustand aus dem Laufregister ab (Join über ``run_id``) und
  liefert ihn mit deutscher Anzeigeform (``state_label``). Die Rangfolge des
  Limits ist Parameter > gespeicherter Standard > 5; gültig ist nur 1..100.
  Projektfilter vergleicht über ``os.path.realpath``, der Textfilter sucht
  ohne Rücksicht auf Groß-/Kleinschreibung in der Session-Kennung.

Fachliche Bedeutung der Zustände (AK2 „Wiederfinden“):

=====================  ============  =========================================
Laufzustand            state         state_label
=====================  ============  =========================================
starting/running       running       läuft
finished               finished      abgeschlossen
failed                 failed        fehlgeschlagen
stopped                stopped       gestoppt
paused                 paused        pausiert
blocked                blocked       blockiert
ended                  aborted       abgebrochen (unerwarteter Abbruch)
kein/kein Treffer      unknown       unbekannt
=====================  ============  =========================================

Es werden keine Modellaufrufe ausgeführt; alle Läufe entstehen über das echte
``RunRegistry`` in temporären Verzeichnissen.
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"

sys.path.insert(0, str(BIN))

# Annahme (im Bericht hervorgehoben): ``observe`` heißt wie in der
# Auftragsbeschreibung und akzeptiert die Schlüsselwortargumente session,
# project, name, run_id, agent, harness und now; ``session_overview`` heißt
# wie dort und akzeptiert project, limit und text.
RUNTIME_MODULE = None


def load_runs_module():
    """Lädt bin/vibe_runs.py als Testunterlage (ohne Installation)."""
    global RUNTIME_MODULE
    if RUNTIME_MODULE is None:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_runs_ap19_under_test", str(BIN / "vibe_runs.py")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        RUNTIME_MODULE = module
    return RUNTIME_MODULE


# Feste Zustandsableitung als Vertrag der Abnahme.
EXPECTED_STATES = (
    ("starting", "running", "läuft"),
    ("running", "running", "läuft"),
    ("finished", "finished", "abgeschlossen"),
    ("failed", "failed", "fehlgeschlagen"),
    ("stopped", "stopped", "gestoppt"),
    ("paused", "paused", "pausiert"),
    ("blocked", "blocked", "blockiert"),
    ("ended", "aborted", "abgebrochen"),
)

INVALID_SESSIONS = ("", "ses/../x", "ses x", "ses;rm", "ses.punkt", "ä", None, 17)


class RegistryFixture(unittest.TestCase):
    """Temporärer Laufzeitordner mit Register und Laufregister."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "_logs"
        self.addCleanup(self.tmp.cleanup)
        self.module = load_runs_module()

    # ---------- Helfer ----------

    def registry(self):
        return self.module.SessionRegistry(str(self.runtime))

    def sessions_file(self):
        return self.runtime / "sessions.json"

    def read_file(self):
        return json.loads(self.sessions_file().read_text(encoding="utf-8"))

    def project(self, name="proj"):
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def observe(self, session, project=None, name="proj", run_id="",
                agent="vibe-agent", harness="opencode", now=None):
        target = project if project is not None else self.project()
        return self.registry().observe(
            session=session, project=target, name=name, run_id=run_id,
            agent=agent, harness=harness, now=now,
        )

    def add_run(self, run_id, state, project=None, name="proj"):
        """Legt einen Lauf im echten Laufregister an (Join-Ziel)."""
        return self.module.RunRegistry(str(self.runtime)).start(
            project=project if project is not None else self.project(),
            name=name, key=name, agent="vibe-agent", session="vibe-" + name,
            run_id=run_id, state=state,
        )

    def overview(self, **kwargs):
        return self.module.session_overview(str(self.runtime), **kwargs)


class ObserveTest(RegistryFixture):
    """AK2: Erfassung je Session-Kennung (Upsert), Grenzen und Robustheit."""

    def test_observe_creates_one_entry_with_all_contract_fields(self):
        """Vorbedingung: leeres Register.
        Aktion: eine Hauptsession beobachten.
        Erwartung: genau ein Eintrag mit allen Vertragsfeldern; ``first_seen``
        und ``last_seen`` sind ganze Sekunden und ``first_seen == last_seen``.
        Fehlerfall: Feld fehlt, Datei fehlt oder Zeitwerte sind keine ints.
        """
        before = int(time.time())
        self.observe("ses_main", run_id="", agent="vibe-agent",
                     harness="opencode")

        self.assertTrue(
            self.sessions_file().is_file(),
            "sessions.json wurde nicht angelegt: " + str(self.sessions_file()),
        )
        data = self.read_file()
        self.assertEqual(5, data.get("limit"), data)
        entries = data.get("sessions")
        self.assertIsInstance(entries, list, data)
        self.assertEqual(1, len(entries), entries)
        entry = entries[0]
        self.assertEqual("ses_main", entry.get("session"), entry)
        self.assertEqual(
            os.path.realpath(self.project()),
            os.path.realpath(str(entry.get("project"))),
            "Der Eintrag hält nicht den realen Projektpfad: " + repr(entry),
        )
        self.assertEqual("proj", entry.get("name"), entry)
        self.assertEqual("", entry.get("run_id"), entry)
        self.assertEqual("vibe-agent", entry.get("agent"), entry)
        self.assertEqual("opencode", entry.get("harness"), entry)
        for key in ("first_seen", "last_seen"):
            self.assertIsInstance(entry.get(key), int, entry)
            self.assertGreaterEqual(entry.get(key), before, entry)
            self.assertLessEqual(entry.get(key), int(time.time()), entry)
        self.assertEqual(
            entry.get("first_seen"), entry.get("last_seen"),
            msg="Beim ersten Sehen müssen first_seen und last_seen gleich "
                "sein: " + repr(entry),
        )

    def test_observe_updates_the_same_entry_and_keeps_first_seen(self):
        """Vorbedingung: Session bereits mit ``first_seen=100`` erfasst.
        Aktion: dieselbe Session mit neuen Werten und ``now=200`` beobachten.
        Erwartung: genau ein Eintrag; ``first_seen`` bleibt 100,
        ``last_seen`` ist 200, Name/Run/Agent/Harness sind aktualisiert.
        Fehlerfall: Duplikat oder verlorene Aktualisierung.
        """
        self.observe("ses_main", run_id="", now=100)
        self.observe("ses_main", run_id="lauf-1", agent="tester",
                     harness="pi", now=200)

        entries = self.read_file().get("sessions") or []
        self.assertEqual(
            1, len(entries),
            "Upsert erzeugte mehrere Einträge: " + repr(entries),
        )
        entry = entries[0]
        self.assertEqual(100, entry.get("first_seen"), entry)
        self.assertEqual(200, entry.get("last_seen"), entry)
        self.assertEqual("lauf-1", entry.get("run_id"), entry)
        self.assertEqual("tester", entry.get("agent"), entry)
        self.assertEqual("pi", entry.get("harness"), entry)

    def test_observe_keeps_entries_apart_per_session(self):
        """Vorbedingung: leeres Register.
        Aktion: drei verschiedene Sessions beobachten.
        Erwartung: drei Einträge, je Session genau einer.
        Fehlerfall: Einträge überschreiben sich gegenseitig.
        """
        for session in ("ses_a", "ses_b", "ses_c"):
            self.observe(session, now=100)

        sessions = [item.get("session")
                    for item in self.read_file().get("sessions") or []]
        self.assertEqual(["ses_a", "ses_b", "ses_c"], sessions)

    def test_observe_ignores_invalid_session_ids_and_writes_nothing(self):
        """Vorbedingung: leeres Register.
        Aktion: ungültige Kennungen (leer, Pfadanteile, Leerzeichen,
        Sonderzeichen) beobachten.
        Erwartung: keine Datei, keine Einträge; die Kennungen erscheinen nie
        im Register oder in der Auflistung.
        Fehlerfall: ungültige Kennung landet im Register (Pfad-/Kommando-
        Injektion über die Session-Kennung).
        """
        for session in INVALID_SESSIONS:
            with self.subTest(session=session):
                self.observe(session)

        written = self.sessions_file().exists()
        self.assertFalse(
            written,
            "Ungültige Kennungen haben sessions.json geschrieben: "
            + (self.sessions_file().read_text(encoding="utf-8")
               if written else ""),
        )
        self.assertEqual([], self.registry().all())
        self.assertEqual([], self.overview())

    def test_observe_limits_the_register_to_the_newest_100_entries(self):
        """Vorbedingung: leeres Register.
        Aktion: 105 Sessions mit aufsteigender Zeit beobachten.
        Erwartung: höchstens 100 Einträge; die fünf ältesten fehlen, die
        jüngste ist vorhanden.
        Fehlerfall: unbegrenztes Wachstum oder Verlust der jüngsten Einträge.
        """
        for index in range(1, 106):
            self.observe("ses_%03d" % index, now=index)

        sessions = [item.get("session")
                    for item in self.read_file().get("sessions") or []]
        self.assertEqual(
            100, len(sessions),
            "Das Register ist nicht auf 100 Einträge begrenzt: " + str(len(sessions)),
        )
        self.assertNotIn("ses_001", sessions, "Ältester Eintrag blieb erhalten")
        self.assertNotIn("ses_005", sessions, "Ältester Eintrag blieb erhalten")
        self.assertIn("ses_006", sessions, sessions[:3])
        self.assertIn(
            "ses_105", sessions, "Jüngster Eintrag wurde verdrängt"
        )


class LimitTest(RegistryFixture):
    """AK1: Gespeicherter Standard (5) und seine Validierung."""

    def test_default_limit_is_five_and_an_integer(self):
        """Vorbedingung: leeres Register.
        Aktion: ``limit()`` lesen.
        Erwartung: 5 als int, ohne dass eine Datei nötig ist.
        Fehlerfall: anderer Standard oder String-Rückgabe.
        """
        value = self.registry().limit()

        self.assertIsInstance(value, int, f"limit() liefert {value!r}")
        self.assertEqual(5, value, f"Standardlimit ist {value!r}, erwartet 5")

    def test_set_limit_persists_and_survives_an_observe(self):
        """Vorbedingung: leeres Register.
        Aktion: ``set_limit(7)``, dann eine Session beobachten, dann mit einer
        neuen Registry-Instanz lesen.
        Erwartung: 7 bleibt gespeichert (auch über Instanzen/Beobachtungen).
        Fehlerfall: Limit geht beim Schreiben verloren.
        """
        self.registry().set_limit(7)
        self.observe("ses_main", now=100)

        self.assertEqual(7, self.registry().limit())
        self.assertEqual(7, self.read_file().get("limit"), self.read_file())

    def test_set_limit_accepts_the_boundaries_one_and_hundred(self):
        """Vorbedingung: leeres Register.
        Aktion: ``set_limit(1)`` und ``set_limit(100)``.
        Erwartung: beide Werte werden gespeichert und gelesen.
        Fehlerfall: gültige Randwerte werden abgelehnt.
        """
        for value in (1, 100):
            with self.subTest(value=value):
                self.registry().set_limit(value)
                self.assertEqual(value, self.registry().limit())

    def test_set_limit_rejects_values_outside_one_to_hundred(self):
        """Vorbedingung: gespeichertes Limit 5.
        Aktion: ungültige Werte setzen (0, -1, 101, 1000, "sieben", None).
        Erwartung: ``ValueError``; das gespeicherte Limit bleibt 5.
        Fehlerfall: ungültiger Wert wird übernommen.
        """
        for value in (0, -1, 101, 1000, "sieben", None, 5.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError, msg=f"{value!r} akzeptiert"):
                    self.registry().set_limit(value)
                self.assertEqual(
                    5, self.registry().limit(),
                    f"Ungültiges Limit {value!r} wurde gespeichert",
                )


class GetTest(RegistryFixture):
    """AK2: Einzelabruf einer Session."""

    def test_get_returns_the_entry_or_none(self):
        """Vorbedingung: eine erfasste Session.
        Aktion: ``get`` für diese und für eine unbekannte Kennung.
        Erwartung: bekannter Eintrag mit Kennung; unbekannt ``None``.
        Fehlerfall: Ausnahme bei unbekannter Kennung oder falscher Treffer.
        """
        self.observe("ses_known", now=100)

        entry = self.registry().get("ses_known")
        self.assertIsNotNone(entry, "Bekannte Session wurde nicht gefunden")
        self.assertEqual("ses_known", entry.get("session"), entry)
        self.assertIsNone(
            self.registry().get("ses_fremd"),
            "Unbekannte Session liefert keinen None-Wert",
        )


class StateDerivationTest(RegistryFixture):
    """AK2: Zustand je Session aus dem Laufregister (Join über ``run_id``)."""

    def seed(self, run_state, run_id="lauf-1"):
        project = self.project()
        self.add_run(run_id, run_state, project=project)
        self.observe("ses_main", project=project, run_id=run_id, now=100)
        return self.overview(project=project)

    def test_every_run_state_maps_to_the_contract_state(self):
        """Vorbedingung: je Laufzustand ein Lauf im Register und eine Session
        mit dieser ``run_id``.
        Aktion: ``session_overview`` ableiten.
        Erwartung: exakt der vertragliche ``state`` samt deutschem
        ``state_label`` (u. a. ``ended`` → ``aborted``/„abgebrochen“).
        Fehlerfall: falsche Zuordnung, fehlende Anzeigeform oder Ausnahme.
        """
        for run_state, expected_state, expected_label in EXPECTED_STATES:
            with self.subTest(run_state=run_state):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                runtime = Path(tmp.name) / "_logs"
                project = Path(tmp.name) / "proj"
                project.mkdir(parents=True)
                self.module.RunRegistry(str(runtime)).start(
                    project=str(project), name="proj", key="proj",
                    agent="vibe-agent", session="vibe-proj",
                    run_id="lauf-1", state=run_state,
                )
                self.module.SessionRegistry(str(runtime)).observe(
                    session="ses_main", project=str(project), name="proj",
                    run_id="lauf-1", agent="vibe-agent", harness="opencode",
                    now=100,
                )

                overview = self.module.session_overview(str(runtime))

                self.assertEqual(1, len(overview), overview)
                entry = overview[0]
                self.assertEqual(
                    expected_state, entry.get("state"),
                    f"Laufzustand {run_state!r} ergibt {entry.get('state')!r}",
                )
                self.assertEqual(
                    expected_label, entry.get("state_label"),
                    f"Anzeigeform für {run_state!r} ist "
                    f"{entry.get('state_label')!r}",
                )

    def test_missing_or_unknown_run_id_is_unknown(self):
        """Vorbedingung: eine Session ohne Lauf-ID und eine mit unbekannter
        Lauf-ID.
        Aktion: ``session_overview`` ableiten.
        Erwartung: beide ``state='unknown'``, ``state_label='unbekannt'``.
        Fehlerfall: Ausnahme oder erfundener Zustand.
        """
        project = self.project()
        self.observe("ses_ohne_lauf", project=project, run_id="", now=100)
        self.observe("ses_fremder_lauf", project=project, run_id="lauf-fehlt",
                     now=200)

        overview = {entry["session"]: entry for entry in self.overview(project=project)}

        self.assertEqual(2, len(overview), overview)
        for session in ("ses_ohne_lauf", "ses_fremder_lauf"):
            self.assertEqual("unknown", overview[session].get("state"),
                             overview[session])
            self.assertEqual("unbekannt", overview[session].get("state_label"),
                             overview[session])

    def test_overview_entries_carry_all_contract_fields(self):
        """Vorbedingung: eine laufende Session.
        Aktion: ``session_overview`` lesen.
        Erwartung: alle Felder aus dem Vertrag sind vorhanden und belegt.
        Fehlerfall: fehlendes Feld für die Anzeige (API/UI bauen darauf auf).
        """
        project = self.project()
        self.add_run("lauf-1", "running", project=project)
        self.observe("ses_main", project=project, run_id="lauf-1",
                     agent="vibe-agent", harness="opencode", now=100)

        entry = self.overview(project=project)[0]

        for field in ("session", "project", "name", "run_id", "agent",
                      "harness", "first_seen", "last_seen", "state",
                      "state_label"):
            self.assertIn(field, entry, f"Feld {field!r} fehlt: {entry}")
        self.assertEqual("lauf-1", entry["run_id"], entry)
        self.assertEqual("running", entry["state"], entry)
        self.assertEqual("läuft", entry["state_label"], entry)


class FilterTest(RegistryFixture):
    """AK1: Projektfilter (realpath) und Suchtext (case-insensitiv)."""

    def test_project_filter_compares_over_realpath(self):
        """Vorbedingung: Projekt über einen Symlink-Alias erfasst.
        Aktion: Auflistung mit dem realen Pfad und mit dem Alias filtern.
        Erwartung: beide Schreibweisen finden dieselbe Session; ein fremdes
        Projekt liefert nichts.
        Fehlerfall: Filter verwechselt Alias und Realpfad oder mischt Projekte.
        """
        real = Path(self.project("proj"))
        alias = self.root / "alias"
        if not alias.exists():
            os.symlink(real, alias)
        other = self.project("fremd")
        self.observe("ses_alias", project=str(alias), now=100)
        self.observe("ses_fremd", project=other, name="fremd", now=200)

        by_real = self.overview(project=str(real))
        by_alias = self.overview(project=str(alias))
        by_other = self.overview(project=other)

        self.assertEqual(["ses_alias"], [item["session"] for item in by_real],
                         "Filter über den realen Pfad findet die Session nicht")
        self.assertEqual(["ses_alias"], [item["session"] for item in by_alias],
                         "Filter über den Alias findet die Session nicht")
        self.assertEqual(["ses_fremd"], [item["session"] for item in by_other],
                         "Projektfilter mischt fremde Projekte")

    def test_text_filter_is_case_insensitive_substring_of_the_session(self):
        """Vorbedingung: Sessions ``SES_Alpha1`` und ``ses_beta2``.
        Aktion: mit ``alpha`` (klein) und ``SES_`` filtern.
        Erwartung: ``alpha`` findet nur ``SES_Alpha1``; ``SES_`` beide.
        Fehlerfall: Groß-/Kleinschreibung zählt oder der Filter greift im
        Projektnamen statt in der Kennung.
        """
        self.observe("SES_Alpha1", now=100)
        self.observe("ses_beta2", now=200)

        lower = self.overview(text="alpha")
        upper = self.overview(text="SES_")

        self.assertEqual(["SES_Alpha1"], [item["session"] for item in lower],
                         "Suchtext ist nicht unabhängig von der Schreibweise")
        self.assertEqual(
            {"SES_Alpha1", "ses_beta2"},
            {item["session"] for item in upper},
            "Suchtext findet nicht beide Kennungen",
        )

    def test_text_filter_without_match_returns_an_empty_list(self):
        """Vorbedingung: eine Session.
        Aktion: einen nicht enthaltenen Suchtext filtern.
        Erwartung: leere Liste (kein Fehler).
        Fehlerfall: Ausnahme oder ungefilterte Rückgabe.
        """
        self.observe("ses_main", now=100)

        self.assertEqual([], self.overview(text="gibtesnicht"))


class OverviewLimitTest(RegistryFixture):
    """AK1: Rangfolge Parameter > gespeicherter Standard > 5."""

    def seed_ten(self):
        for index in range(1, 11):
            self.observe("ses_%02d" % index, now=index)

    def test_default_limit_five_returns_the_five_newest_sessions(self):
        """Vorbedingung: zehn Sessions, kein gespeichertes Limit.
        Aktion: Auflistung ohne ``limit``.
        Erwartung: fünf Einträge, jüngste zuerst (``ses_10`` … ``ses_06``).
        Fehlerfall: mehr als fünf oder die falschen Einträge.
        """
        self.seed_ten()

        entries = self.overview()

        self.assertEqual(
            ["ses_10", "ses_09", "ses_08", "ses_07", "ses_06"],
            [item["session"] for item in entries],
            "Standardauflistung zeigt nicht die fünf jüngsten Sessions",
        )

    def test_stored_limit_wins_over_the_default(self):
        """Vorbedingung: zehn Sessions, gespeichertes Limit 3.
        Aktion: Auflistung ohne ``limit``.
        Erwartung: drei Einträge (jüngste zuerst).
        Fehlerfall: gespeicherter Standard wird ignoriert.
        """
        self.seed_ten()
        self.registry().set_limit(3)

        entries = self.overview()

        self.assertEqual(["ses_10", "ses_09", "ses_08"],
                         [item["session"] for item in entries])

    def test_parameter_limit_wins_over_the_stored_limit(self):
        """Vorbedingung: zehn Sessions, gespeichertes Limit 3.
        Aktion: Auflistung mit ``limit=7``.
        Erwartung: sieben Einträge; der Parameter hat Vorrang.
        Fehlerfall: Parameter wird ignoriert.
        """
        self.seed_ten()
        self.registry().set_limit(3)

        entries = self.overview(limit=7)

        self.assertEqual(7, len(entries), [item["session"] for item in entries])
        self.assertEqual("ses_10", entries[0]["session"], entries[0])
        self.assertEqual("ses_04", entries[-1]["session"], entries[-1])

    def test_parameter_limit_above_the_register_size_returns_all(self):
        """Vorbedingung: drei Sessions.
        Aktion: Auflistung mit ``limit=100``.
        Erwartung: alle drei Einträge (kein Auffüllen mit Attrappen).
        Fehlerfall: Ausnahme oder erfundene Einträge.
        """
        for index in range(1, 4):
            self.observe("ses_%02d" % index, now=index)

        entries = self.overview(limit=100)

        self.assertEqual(3, len(entries), entries)

    def test_invalid_parameter_limit_raises_value_error(self):
        """Vorbedingung: zehn Sessions.
        Aktion: Auflistung mit ``limit`` 0, -1, 101, 1000, "viele".
        Erwartung: ``ValueError`` für jeden Wert (gültig ist nur 1..100).
        Fehlerfall: stilles Deckeln oder unbegrenzte Rückgabe.
        """
        self.seed_ten()

        for value in (0, -1, 101, 1000, "viele"):
            with self.subTest(limit=value):
                with self.assertRaises(ValueError, msg=f"{value!r} akzeptiert"):
                    self.overview(limit=value)

    def test_reobserved_old_entry_survives_the_100_limit_trim(self):
        """Review M2: Die Obergrenze verwirft nach ``last_seen``, nicht nach
        Einfügereihenfolge.

        Vorbedingung: genau 100 Sessions ``ses_001``..``ses_100`` mit
        ``last_seen`` 1..100 in Einfügereihenfolge.
        Aktion: ``ses_001`` erneut mit ``now=200`` beobachten (Upsert an alter
        Position, neues ``last_seen``), danach ``ses_neu`` mit ``now=201``
        beobachten, wodurch das Kürzen auf 100 erzwungen wird.
        Erwartung: ``ses_001`` bleibt im Register; der Eintrag mit dem
        kleinsten ``last_seen`` (``ses_002``) fällt weg; genau 100 Einträge;
        die Übersicht beginnt mit ``ses_neu``, ``ses_001``, ``ses_100`` …
        Fehlerfall: Kürzen nach Einfügereihenfolge verwirft ausgerechnet den
        erneut gesehenen, fortsetzbaren Eintrag.
        """
        for index in range(1, 101):
            self.observe("ses_%03d" % index, now=index)
        self.observe("ses_001", now=200)
        self.observe("ses_neu", now=201)

        sessions = [item.get("session")
                    for item in self.read_file().get("sessions") or []]
        self.assertEqual(
            100, len(sessions),
            "Das Register ist nach dem Kürzen nicht bei 100 Einträgen: "
            + str(len(sessions)))
        self.assertIn(
            "ses_001", sessions,
            "Der erneut gesehene Eintrag wurde nach Einfügereihenfolge "
            "verworfen: " + repr(sessions[:5]))
        self.assertNotIn(
            "ses_002", sessions,
            "Verworfen wurde nicht der Eintrag mit dem kleinsten last_seen: "
            + repr(sessions[:5]))

        overview = self.overview(limit=100)
        self.assertEqual(100, len(overview), len(overview))
        self.assertEqual(
            ["ses_neu", "ses_001", "ses_100"],
            [item["session"] for item in overview[:3]],
            "Die Übersicht sortiert nicht nach dem aktuellen last_seen: "
            + repr([item["session"] for item in overview[:5]]))


class OverviewRobustnessTest(RegistryFixture):
    """Review Minor: Ein beschädigter ``last_seen`` darf die Auflistung nicht
    crashen. Festgelegte Erwartung: der beschädigte Eintrag wird
    übersprungen (nicht mit 0 geführt)."""

    def test_overview_skips_entries_with_corrupt_last_seen(self):
        """Vorbedingung: ``sessions.json`` von Hand mit je einem intakten und
        einem defekten Eintrag; die defekte Variante ist nichtnumerischer Text
        (``"last_seen": "abc"``) bzw. ein boolescher Wert
        (``"last_seen": true``), der wie ``observe``/``_read`` als unlesbar
        gilt.
        Aktion: ``session_overview`` je defekter Variante aufrufen.
        Erwartung: kein ``ValueError``; der defekte Eintrag wird übersprungen
        (nicht als 1 geführt), der intakte erscheint normal.
        Fehlerfall: die Auflistung bricht ab oder ein boolescher Wert wird als
        Zeit 1 missverstanden und mitgelistet.
        """
        intact = {
            "session": "ses_ok", "project": self.project(), "name": "proj",
            "run_id": "", "agent": "vibe-agent", "harness": "opencode",
            "first_seen": 10, "last_seen": 100,
        }
        corrupt_variants = {
            "text": "abc",
            "bool": True,
        }
        for label, value in corrupt_variants.items():
            corrupt = {
                "session": "ses_bad", "project": self.project(),
                "name": "proj", "run_id": "", "agent": "vibe-agent",
                "harness": "opencode", "first_seen": 10, "last_seen": value,
            }
            with self.subTest(last_seen=label):
                self.runtime.mkdir(parents=True, exist_ok=True)
                self.sessions_file().write_text(
                    json.dumps({"limit": 5, "sessions": [corrupt, intact]}),
                    encoding="utf-8")

                entries = self.overview(limit=100)

                self.assertEqual(
                    ["ses_ok"], [item["session"] for item in entries],
                    "Der beschädigte Eintrag wurde nicht übersprungen oder "
                    "die Auflistung brach ab: " + repr(entries))


if __name__ == "__main__":
    unittest.main()
