"""GH-48: Vertragstests für den Ticketspeicher (``bin/vibe_tickets.py``).

Quelle der Ableitung: Arbeitspaket GH-48, ``SPEC.md`` (Arbeitspakete und
Feedback, Qualität und Abnahme, Sicherheit und Datenintegrität) und der
verbindliche Implementierungsvertrag GH-48. Geprüft wird ausschließlich der
Speicherkern — Dateiformat, Feldschema, Invarianten, ID-Vergabe,
Konfliktschutz und die Einzeldatei ``TICKET-<ID>.json``.

Keine Netzzugriffe, keine Modellaufrufe, keine produktiven Pfade: jedes
Projekt liegt in einem ``tempfile``-Verzeichnis.

Run:

    python3 -m unittest tests.unit.test_gh48_ticket_store -v
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
STORE_MODULE = BIN / "vibe_tickets.py"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

_CACHE = {}


def tickets_module():
    """Lädt ``bin/vibe_tickets.py``; fehlt es, scheitert der Fall sichtbar."""
    if "tickets" not in _CACHE:
        if not STORE_MODULE.is_file():
            raise AssertionError(
                "bin/vibe_tickets.py fehlt (Ticketspeicher-Modul nach GH-48).")
        loader = importlib.machinery.SourceFileLoader(
            "vibe_tickets_gh48_store_under_test", str(STORE_MODULE))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        _CACHE["tickets"] = module
    return _CACHE["tickets"]


class StoreCase(unittest.TestCase):
    """Frisches Projektverzeichnis je Fall; kein Speicher vorhanden."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.project.mkdir()
        self.store = self.project / ".vibe" / "tickets.json"

    @property
    def module(self):
        return tickets_module()

    def write_store(self, payload, name="tickets.json"):
        path = self.project / ".vibe" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        path.write_text(payload, encoding="utf-8")
        return path

    def read_json(self, path=None):
        path = Path(path or self.store)
        return json.loads(path.read_text(encoding="utf-8"))

    def add(self, **fields):
        fields.setdefault("title", "Titel")
        return self.module.add(self.project, **fields)


class LoadSaveTest(StoreCase):
    """Dateiformat: fehlend -> leer; defekt -> ValueError; Schreiben atomar."""

    def test_a_missing_store_reads_as_an_empty_list(self):
        """Vor: kein .vibe/tickets.json. Aktion: load. Erwartet: []."""
        self.assertEqual([], self.module.load(self.project))

    def test_save_creates_folder_and_document_with_version_and_newline(self):
        """Vor: kein Speicher. Aktion: save mit einem Ticket.
        Erwartet: .vibe/tickets.json wird angelegt, UTF-8, indent=1,
        abschließender Zeilenumbruch, Dokument {"version": 1, "tickets": [...]},
        Umlaute bleiben unescaped (ensure_ascii=False)."""
        record = {"id": "AP1", "title": "Größe prüfen"}

        self.module.save(self.project, [record])

        self.assertTrue(self.store.is_file())
        raw = self.store.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"), repr(raw[-5:]))
        self.assertIn("Größe", raw, raw)
        self.assertNotIn("\\u00e4", raw, raw)
        document = json.loads(raw)
        self.assertEqual(1, document["version"])
        self.assertEqual(1, len(document["tickets"]))
        self.assertEqual("AP1", document["tickets"][0]["id"])

    def test_load_returns_the_saved_tickets(self):
        """Vor: gespeichertes Ticket. Aktion: load. Erwartet: Ticket mit
        normalisierten Feldern, Reihenfolge bleibt erhalten."""
        self.module.save(self.project, [
            {"id": "B2", "title": "Zweiter", "type": "bug"},
            {"id": "AP1", "title": "Erster"},
        ])

        tickets = self.module.load(self.project)

        self.assertEqual(["B2", "AP1"], [item["id"] for item in tickets])
        self.assertEqual("bug", tickets[0]["type"])

    def test_invalid_json_is_reported_and_never_repaired(self):
        """Vor: Speicher mit defektem JSON. Aktion: load.
        Erwartet: ValueError mit "Ticketspeicher unlesbar" und Pfad; die Datei
        bleibt byte-identisch (kein stilles Reparieren)."""
        broken = '{"version": 1, "tickets": ['
        path = self.write_store(broken)
        before = path.read_bytes()

        with self.assertRaises(ValueError) as caught:
            self.module.load(self.project)

        self.assertIn("Ticketspeicher unlesbar", str(caught.exception))
        self.assertIn(str(path), str(caught.exception))
        self.assertEqual(before, path.read_bytes())

    def test_a_conflicting_write_is_reported_and_preserves_foreign_state(self):
        """Vor: Speicher gelesen (Prüfsumme), danach von außen verändert.
        Aktion: save mit der veralteten Prüfsumme.
        Erwartet: ValueError (Konflikt), fremder Stand bleibt unverändert."""
        path = self.write_store({"version": 1, "tickets": [
            {"id": "AP1", "title": "Alt"}]})
        import vibe_storage

        stale = vibe_storage.read_snapshot(str(path)).digest
        foreign = {"version": 1, "tickets": [{"id": "AP9", "title": "Fremd"}]}
        path.write_text(json.dumps(foreign, ensure_ascii=False), encoding="utf-8")
        before = path.read_bytes()

        with self.assertRaises(ValueError) as caught:
            self.module.save(self.project, [{"id": "AP1", "title": "Neu"}],
                             expected=stale)

        self.assertIn("konflikt", str(caught.exception).lower())
        self.assertEqual(before, path.read_bytes())

    def test_unknown_keys_on_document_and_ticket_level_survive_a_rewrite(self):
        """Vor: Speicher mit Zusatzschlüsseln auf Dokument- und Ticketebene.
        Aktion: load, save. Erwartet: alle unbekannten Schlüssel bleiben
        erhalten (Vorwärtskompatibilität, keine Datenvernichtung)."""
        self.write_store({
            "version": 1,
            "custom_doc": {"team": "a"},
            "tickets": [{"id": "AP1", "title": "Titel", "custom": "bleibt"}],
        })

        tickets = self.module.load(self.project)
        self.module.save(self.project, tickets)

        document = self.read_json()
        self.assertEqual({"team": "a"}, document["custom_doc"])
        self.assertEqual("bleibt", document["tickets"][0]["custom"])

    def test_unknown_fields_of_an_updated_ticket_are_kept(self):
        """Vor: Ticket mit Zusatzfeld. Aktion: update des Titels.
        Erwartet: Zusatzfeld bleibt, Titel ist neu."""
        self.add(tid="AP1", title="Alt", extra={"custom": "bleibt"})

        self.module.update(self.project, "AP1", title="Neu")

        record = self.module.find(self.module.load(self.project), "AP1")
        self.assertEqual("Neu", record["title"])
        self.assertEqual("bleibt", record["custom"])


class NormalizeTest(StoreCase):
    """Feldschema, Defaults und Validierung."""

    def test_defaults_fill_all_contract_fields(self):
        """Vor: minimales Ticket. Aktion: normalize. Erwartet: type=task,
        state=open, description/pr_url/commit/test/blocked_reason/
        waiting_note/priority leer, github=None, dependencies=[]."""
        record = self.module.normalize({"id": "AP7", "title": "Titel"})

        self.assertEqual("task", record["type"])
        self.assertEqual("open", record["state"])
        for field in ("description", "pr_url", "commit", "test",
                      "blocked_reason", "waiting_note", "priority"):
            self.assertEqual("", record[field], field)
        self.assertIsNone(record["github"])
        self.assertEqual([], record["dependencies"])

    def test_id_must_end_with_digits_and_start_with_a_letter(self):
        """Vor: gültige IDs (GH-48, AP7, T-01, B12, F3) und ungültige
        (48, AP, -AP1, "AP 1"). Aktion: normalize.
        Erwartet: gültige werden normalisiert, ungültige lösen ValueError aus."""
        for value in ("GH-48", "AP7", "T-01", "B12", "F3"):
            with self.subTest(valid=value):
                self.assertEqual(value, self.module.normalize(
                    {"id": value, "title": "Titel"})["id"])
        for value in ("48", "AP", "-AP1", "AP 1", ""):
            with self.subTest(invalid=value):
                with self.assertRaises(ValueError):
                    self.module.normalize({"id": value, "title": "Titel"})

    def test_title_is_required_and_single_line(self):
        """Vor: fehlender, leerer und mehrzeiliger Titel. Aktion: normalize.
        Erwartet: ValueError in allen drei Fällen; ein einzeiliger Titel wird
        getrimmt übernommen."""
        for value in ("", "   ", "Zeile 1\nZeile 2", "Zeile 1\rZeile 2"):
            with self.subTest(title=value):
                with self.assertRaises(ValueError):
                    self.module.normalize({"id": "AP1", "title": value})
        with self.assertRaises(ValueError):
            self.module.normalize({"id": "AP1"})
        self.assertEqual("Titel", self.module.normalize(
            {"id": "AP1", "title": "  Titel  "})["title"])

    def test_type_and_state_are_closed_enumerations(self):
        """Vor: alle Vertragswerte und ein Fremdwert je Feld. Aktion: normalize.
        Erwartet: task/bug/feature/feedback und draft/open/in-progress/blocked/
        waiting-merge/done sind gültig; "chore" bzw. "erledigt" nicht."""
        module = self.module
        for value in module.TYPES:
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "type": value})["type"])
        for value in module.STATES:
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "state": value,
                 "commit": "abcdef1", "test": "test_x"}
                if value == "done" else
                {"id": "AP1", "title": "T", "state": value})["state"])
        for field, value in (("type", "chore"), ("state", "erledigt")):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    module.normalize(
                        {"id": "AP1", "title": "T", field: value})

    def test_commit_must_be_a_hex_hash_of_7_to_40_characters(self):
        """Vor: gültige Hex-Hashes (7 und 40 Zeichen) und ungültige
        (6 Zeichen, Nicht-Hex). Aktion: normalize.
        Erwartet: gültige übernommen, ungültige ValueError."""
        module = self.module
        for value in ("abcdef1", "a" * 40):
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "commit": value})["commit"])
        for value in ("abcdef", "ZZZZZZZ", "abcdefg"):
            with self.subTest(commit=value):
                with self.assertRaises(ValueError):
                    module.normalize({"id": "AP1", "title": "T",
                                      "commit": value})

    def test_done_requires_commit_and_test(self):
        """Vor: state=done ohne Nachweis, nur Commit, nur Test, mit beidem.
        Aktion: normalize. Erwartet: die ersten drei Fälle sind ValueError;
        mit Commit und Test ist done gültig (der alte Zustand "ohne Nachweis"
        entfällt)."""
        base = {"id": "AP1", "title": "T", "state": "done"}
        for extra in ({}, {"commit": "abcdef1"}, {"test": "test_x"}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    self.module.normalize(dict(base, **extra))
        record = self.module.normalize(dict(base, commit="abcdef1",
                                            test="test_x"))
        self.assertEqual("done", record["state"])

    def test_priority_is_empty_or_p0_to_p8(self):
        """Vor: "", P0, P8, P9. Aktion: normalize.
        Erwartet: ""/P0/P8 gültig, P9 ValueError."""
        module = self.module
        for value in ("", "P0", "P8"):
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "priority": value})["priority"])
        with self.assertRaises(ValueError):
            module.normalize({"id": "AP1", "title": "T", "priority": "P9"})

    def test_github_is_an_integer_and_dependencies_a_list_of_ids(self):
        """Vor: github=12, dependencies=["AP1","B2"]. Aktion: normalize.
        Erwartet: Werte bleiben; ein ungültiges Abhängigkeitsformat ist
        ValueError."""
        record = self.module.normalize({
            "id": "AP2", "title": "T", "github": 12,
            "dependencies": ["AP1", "B2"]})
        self.assertEqual(12, record["github"])
        self.assertEqual(["AP1", "B2"], record["dependencies"])
        with self.assertRaises(ValueError):
            self.module.normalize({"id": "AP2", "title": "T",
                                   "dependencies": "AP1"})
        with self.assertRaises(ValueError):
            self.module.normalize({"id": "AP2", "title": "T",
                                   "dependencies": ["keine id"]})


class AddUpdateDeleteTest(StoreCase):
    """ID-Vergabe, Zeitstempel, Teilaktualisierung und Nachweisschutz."""

    def test_auto_ids_follow_the_type_prefix(self):
        """Vor: leerer Speicher. Aktion: add task/bug/feedback/feature.
        Erwartet: AP1, B1, F1; ein feature-Ticket ohne eigene ID erhält AP2
        (B1: feature nutzt den AP-Zähler gemeinsam mit task); ein
        feature-Ticket mit eigener ID bleibt erhalten. Die IDs sind
        eindeutig."""
        self.assertEqual("AP1", self.add(type="task")["id"])
        self.assertEqual("B1", self.add(type="bug", title="Bug")["id"])
        self.assertEqual("F1", self.add(type="feedback", title="Idee")["id"])
        self.assertEqual("AP2", self.add(type="feature", title="Feature")["id"])
        self.assertEqual("FEAT-1", self.add(type="feature", tid="FEAT-1",
                                            title="Feature benannt")["id"])
        self.assertEqual(["AP1", "B1", "F1", "AP2", "FEAT-1"],
                         [item["id"] for item in self.module.load(self.project)])

    def test_auto_ids_continue_after_the_highest_number(self):
        """Vor: AP9 existiert. Aktion: add ohne ID (task), danach feature.
        Erwartet: AP10, danach AP11 (nächste freie Nummer über den
        gemeinsamen AP-Zähler; bestehende Lücke füllt nicht)."""
        self.add(tid="AP9", title="Neun")
        self.assertEqual("AP10", self.add(title="Zehn")["id"])
        self.assertEqual("AP11", self.add(type="feature", title="Elf")["id"])

    def test_an_explicit_id_is_validated_and_must_be_unique(self):
        """Vor: Ticket AP1. Aktion: add mit AP1 erneut, add mit ungültiger ID.
        Erwartet: ValueError (existiert bereits / ungültig)."""
        self.add(tid="AP1")
        with self.assertRaises(ValueError):
            self.add(tid="AP1")
        with self.assertRaises(ValueError):
            self.add(tid="keine id")

    def test_gh_prefix_ids_are_reserved_for_issue_imports(self):
        """Vor: leerer Speicher. Aktion: add mit GH-7.
        Erwartet: ValueError — GH-IDs entstehen nur über Sync/verbundene
        Anlage, nicht über die freie Anlage."""
        with self.assertRaises(ValueError):
            self.add(tid="GH-7")

    def test_created_and_updated_are_iso_utc_and_updated_changes(self):
        """Vor: Ticket mit altem updated-Stand. Aktion: update des Titels.
        Erwartet: created bleibt, updated ist ein neuer ISO-8601-UTC-Wert
        (zeitzonenbewusst)."""
        self.write_store({"version": 1, "tickets": [{
            "id": "AP1", "title": "Alt",
            "created": "2000-01-01T00:00:00+00:00",
            "updated": "2000-01-01T00:00:00+00:00"}]})

        self.module.update(self.project, "AP1", title="Neu")

        record = self.module.find(self.module.load(self.project), "AP1")
        self.assertEqual("2000-01-01T00:00:00+00:00", record["created"])
        changed = datetime.datetime.fromisoformat(record["updated"])
        self.assertIsNotNone(changed.tzinfo)
        self.assertGreater(changed.year, 2000)

    def test_update_is_a_partial_update_and_validates(self):
        """Vor: Ticket AP1 offen mit Beschreibung. Aktion: update nur state
        und priority. Erwartet: übrige Felder bleiben, unbekannte ID ist
        ValueError, ungültiger Zustand ist ValueError."""
        self.add(tid="AP1", title="Titel", description="Beschreibung")

        self.module.update(self.project, "AP1", state="in-progress",
                           priority="P2")

        record = self.module.find(self.module.load(self.project), "AP1")
        self.assertEqual("in-progress", record["state"])
        self.assertEqual("P2", record["priority"])
        self.assertEqual("Titel", record["title"])
        self.assertEqual("Beschreibung", record["description"])
        with self.assertRaises(ValueError):
            self.module.update(self.project, "X9", title="Unbekannt")
        with self.assertRaises(ValueError):
            self.module.update(self.project, "AP1", state="erledigt")

    def test_update_refuses_done_without_proof(self):
        """Vor: offenes Ticket. Aktion: update(state="done") ohne Commit/Test.
        Erwartet: ValueError; das Ticket bleibt offen."""
        self.add(tid="AP1")

        with self.assertRaises(ValueError):
            self.module.update(self.project, "AP1", state="done")

        self.assertEqual("open", self.module.find(
            self.module.load(self.project), "AP1")["state"])

    def test_delete_removes_exactly_one_ticket(self):
        """Vor: AP1 und AP2. Aktion: delete AP1. Erwartet: nur AP2 bleibt."""
        self.add(tid="AP1")
        self.add(tid="AP2", title="Zwei")

        self.module.delete(self.project, "AP1")

        self.assertEqual(["AP2"],
                         [item["id"] for item in self.module.load(self.project)])
        with self.assertRaises(ValueError):
            self.module.delete(self.project, "X9")

    def test_done_tickets_are_protected_from_delete_and_editing(self):
        """Vor: erledigtes Ticket mit Commit/Test. Aktion: delete und
        update(Titel/Beschreibung). Erwartet: jeweils ValueError (Nachweis-
        schutz); das Ticket bleibt unverändert erhalten."""
        self.add(tid="AP1", title="Titel", description="Text")
        self.module.update(self.project, "AP1", state="done",
                           commit="abcdef1", test="test_ap1")
        before = self.read_json()

        for action in (
            lambda: self.module.delete(self.project, "AP1"),
            lambda: self.module.update(self.project, "AP1", title="Neu"),
            lambda: self.module.update(self.project, "AP1",
                                       description="Neu"),
        ):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(before, self.read_json())


class LookupTest(StoreCase):
    """Nachschlagefunktionen und Anzeigezustand."""

    def test_find_and_find_by_github(self):
        """Vor: AP1 (github 5) und AP2. Aktion: find/find_by_github.
        Erwartet: Treffer bzw. None; find_by_github findet die Issuenummer."""
        tickets = [self.module.normalize({"id": "AP1", "title": "T",
                                          "github": 5}),
                   self.module.normalize({"id": "AP2", "title": "U"})]

        self.assertEqual("AP1", self.module.find(tickets, "AP1")["id"])
        self.assertIsNone(self.module.find(tickets, "X9"))
        self.assertEqual("AP1", self.module.find_by_github(tickets, 5)["id"])
        self.assertIsNone(self.module.find_by_github(tickets, 99))

    def test_next_number_uses_the_exact_prefix(self):
        """Vor: AP3, AP7, GH-48, B9. Aktion: next_number.
        Erwartet: AP -> 8, B -> 10, F -> 1 (fremde Präfixe zählen nicht)."""
        tickets = [{"id": value} for value in ("AP3", "AP7", "GH-48", "B9")]
        self.assertEqual(8, self.module.next_number(tickets, "AP"))
        self.assertEqual(10, self.module.next_number(tickets, "B"))
        self.assertEqual(1, self.module.next_number(tickets, "F"))

    def test_display_state_uses_the_known_labels(self):
        """Vor: je Zustand ein Ticket. Aktion: display_state.
        Erwartet: done=erledigt, blocked=BLOCKIERT,
        waiting-merge=WARTET AUF MERGE, in-progress=In Progress, draft=Draft,
        open=offen."""
        expected = {"done": "erledigt", "blocked": "BLOCKIERT",
                    "waiting-merge": "WARTET AUF MERGE",
                    "in-progress": "In Progress", "draft": "Draft",
                    "open": "offen"}
        for state, label in expected.items():
            with self.subTest(state=state):
                self.assertEqual(label, self.module.display_state({"state": state}))


class TicketFileTest(StoreCase):
    """Sichtbare Einzeldatei ``TICKET-<ID>.json`` in der Arbeitskopie."""

    def test_file_name_follows_the_template(self):
        """Vor: Kennung AP7. Aktion: ticket_file_name.
        Erwartet: TICKET-AP7.json."""
        self.assertEqual("TICKET-AP7.json", self.module.ticket_file_name("AP7"))
        self.assertEqual("TICKET-GH-48.json",
                         self.module.ticket_file_name("GH-48"))

    def test_write_and_read_roundtrip(self):
        """Vor: gültiges Ticket. Aktion: write_ticket_file, read_ticket_file.
        Erwartet: gelesenes Ticket entspricht dem normalisierten Ticket."""
        record = self.module.normalize({"id": "AP7", "title": "Titel",
                                        "state": "in-progress"})
        path = self.root / self.module.ticket_file_name("AP7")

        self.module.write_ticket_file(path, record)

        self.assertEqual(record, self.module.read_ticket_file(path))
        self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_broken_or_invalid_files_raise_value_error(self):
        """Vor: defektes JSON und JSON ohne Pflichtfelder. Aktion:
        read_ticket_file. Erwartet: ValueError in beiden Fällen."""
        broken = self.root / "TICKET-AP1.json"
        broken.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.read_ticket_file(broken)

        missing_title = self.root / "TICKET-AP2.json"
        missing_title.write_text(
            json.dumps({"id": "AP2", "state": "open"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.read_ticket_file(missing_title)

        bad_state = self.root / "TICKET-AP3.json"
        bad_state.write_text(
            json.dumps({"id": "AP3", "title": "T", "state": "erledigt"}),
            encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.read_ticket_file(bad_state)


if __name__ == "__main__":
    unittest.main()
