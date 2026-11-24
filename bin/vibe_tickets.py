#!/usr/bin/env python3
"""vibe_tickets — Ticketspeicher ``.vibe/tickets.json`` (GH-48).

Ein einziges maschinenlesbares Ticketformat ersetzt die getrennten Markdown-
Ledger ``TICKETS.md``/``FEEDBACK.md``. Arbeitspakete, Bugs und Feedback sind
einheitliche Tickets mit einem ``type``-Feld und liegen im Projektordner unter
``.vibe/tickets.json`` (Laufzeitstand, nie committet).

Dieses Modul ist bewusst eigenständig: Es importiert ausschließlich
``vibe_storage`` und die Standardbibliothek, damit ``bin/vibe``,
``vibe_packages``, ``vibe_issues``, ``vibe_github``, ``vibe_services`` und
``vibe-web`` es ohne Zirkularität nutzen können.

Schreiben erfolgt ausschließlich über die gemeinsame Storage-Schicht
(``vibe_storage``): atomar über eine temporäre Datei, mit erwarteter
Prüfsumme. Ein Konflikt (fremde Änderung zwischen Lesen und Schreiben) wird
als ``TicketStoreConflict`` gemeldet, nie still überschrieben. Ungültiges
JSON wird als ``ValueError`` gemeldet und nie still repariert.
"""
import json
import os
import re
from datetime import datetime, timezone

import vibe_storage

# ---------- Konstanten ----------
STATES = ("draft", "open", "in-progress", "blocked", "waiting-merge", "done")
TYPES = ("task", "bug", "feature", "feedback")
TYPE_PREFIXES = {"task": "AP", "bug": "B", "feedback": "F"}
STORE_REL = os.path.join(".vibe", "tickets.json")     # ".vibe/tickets.json"
TICKET_FILE_TEMPLATE = "TICKET-{id}.json"             # Arbeitskopie, sichtbar

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*[0-9]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_PRIORITY_RE = re.compile(r"^P[0-8]$")

_STATE_LABELS = {
    "done": "erledigt",
    "blocked": "BLOCKIERT",
    "waiting-merge": "WARTET AUF MERGE",
    "in-progress": "In Progress",
    "draft": "Draft",
    "open": "offen",
}


class TicketStoreError(ValueError):
    """Basisfehler des Ticketspeichers."""


class TicketStoreConflict(TicketStoreError):
    """Der Ticketspeicher wurde zwischenzeitlich geändert (Konflikt)."""


def _now_utc():
    """Aktueller Zeitpunkt als ISO-8601-UTC (zeitzonenbewusst)."""
    return datetime.now(timezone.utc).isoformat()


def store_path(project):
    """Pfad des Ticketspeichers eines Projekts."""
    return os.path.join(os.fspath(project), ".vibe", "tickets.json")


def _parse_document(text, path):
    """Dokument aus Text lesen; ungültige Struktur ist ein ValueError."""
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("Ticketspeicher unlesbar: " + str(path) + ": "
                         + str(error)) from None
    if not isinstance(doc, dict) or not isinstance(doc.get("tickets"), list):
        raise ValueError("Ticketspeicher unlesbar: " + str(path)
                         + ": ungültige Dokumentstruktur")
    return doc


def _tickets_from_snapshot(snapshot):
    """Ticketliste aus einem Snapshot; eine fehlende Datei liefert ``[]``."""
    if not snapshot.exists:
        return []
    return _parse_document(snapshot.text, snapshot.path)["tickets"]


def load(project):
    """Liest alle Tickets; fehlender Speicher liefert ``[]``, defekter wirft.

    Unbekannte Schlüssel auf Dokument- und Ticketebene bleiben beim späteren
    Schreiben erhalten; hier wird ausschließlich die Ticketliste geliefert.
    """
    return _tickets_from_snapshot(vibe_storage.read_snapshot(store_path(project)))


def save(project, tickets, expected=None):
    """Schreibt den Ticketspeicher atomar; ``expected`` ist eine Prüfsumme.

    Das Dokument erhält ``version=1``; unbekannte Schlüssel eines vorhandenen
    Dokuments bleiben erhalten (Vorwärtskompatibilität, keine Datenvernichtung).
    Bei einer konkurrierenden Änderung wird ``TicketStoreConflict`` geworfen.
    """
    path = store_path(project)
    snapshot = vibe_storage.read_snapshot(path)
    doc = _parse_document(snapshot.text, path) if snapshot.exists else {}
    doc["version"] = 1
    doc["tickets"] = tickets
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    try:
        vibe_storage.write_text(path, text, expected=expected)
    except vibe_storage.ConcurrentChangeError as error:
        raise TicketStoreConflict(
            "Ticketspeicher-Konflikt beim Schreiben: " + str(error)) from None


def normalize(record, require_done_proof=True):
    """Setzt Defaults und validiert ein Ticket; liefert ein neues Dict.

    Unbekannte Felder bleiben erhalten. ``ValueError`` bei ungültigen
    Pflichtfeldern, geschlossenen Aufzählungen, ungültigem Commit/Priorität
    oder einer verletzten Done-Invariante (erledigt braucht ``test`` sowie
    ``commit`` oder ``github``). ``require_done_proof=False`` gilt nur für
    das manuelle Schließen durch den Nutzer (siehe :func:`close`).
    """
    if not isinstance(record, dict):
        raise ValueError("Ticket muss ein Objekt sein")
    out = dict(record)

    tid = str(out.get("id") or "").strip()
    if not _ID_RE.match(tid):
        raise ValueError("Ungültige Ticket-ID: " + repr(tid))
    out["id"] = tid

    title = out.get("title")
    if title is None:
        raise ValueError("Titel fehlt (ID " + tid + ")")
    title = str(title).strip()
    if not title:
        raise ValueError("Titel fehlt (ID " + tid + ")")
    if "\n" in title or "\r" in title:
        raise ValueError("Titel darf keinen Zeilenumbruch enthalten (ID " + tid + ")")
    out["title"] = title

    typ = out.get("type", "task")
    if typ not in TYPES:
        raise ValueError("Unbekannter Tickettyp: " + str(typ))
    out["type"] = typ

    state = out.get("state", "open")
    if state not in STATES:
        raise ValueError("Unbekannter Ticketzustand: " + str(state))
    out["state"] = state

    out["description"] = out.get("description") or ""

    github = out.get("github")
    if github is not None and not isinstance(github, int):
        raise ValueError("GitHub-Bezug muss eine Issuenummer (int) sein")
    out["github"] = github

    out["pr_url"] = out.get("pr_url") or ""
    out["blocked_reason"] = out.get("blocked_reason") or ""
    out["waiting_note"] = out.get("waiting_note") or ""

    commit = out.get("commit") or ""
    if commit and not _COMMIT_RE.match(commit):
        raise ValueError("Commit muss ein Hex-Hash mit 7 bis 40 Zeichen sein")
    out["commit"] = commit

    out["test"] = out.get("test") or ""

    priority = out.get("priority") or ""
    if priority and not _PRIORITY_RE.match(priority):
        raise ValueError("Priorität muss leer oder P0 bis P8 sein")
    out["priority"] = priority

    dependencies = out.get("dependencies")
    if dependencies is None:
        dependencies = []
    if not isinstance(dependencies, list):
        raise ValueError("Abhängigkeiten müssen eine Liste sein")
    for dep in dependencies:
        if not isinstance(dep, str) or not _ID_RE.match(dep):
            raise ValueError("Ungültige Abhängigkeits-ID: " + repr(dep))
    out["dependencies"] = list(dependencies)

    if state == "done" and require_done_proof:
        has_test = bool(out["test"])
        has_commit = bool(out["commit"])
        has_github = out["github"] is not None
        if not has_test or not (has_commit or has_github):
            raise ValueError(
                "Erledigt erfordert das test-Feld sowie commit oder github-Bezug "
                "(ID " + tid + ")")

    return out


def find(tickets, tid):
    """Ticket mit dieser ID oder ``None``."""
    for record in tickets:
        if record.get("id") == tid:
            return record
    return None


def find_by_github(tickets, number):
    """Ticket mit dieser GitHub-Issuenummer oder ``None``."""
    for record in tickets:
        if record.get("github") == number:
            return record
    return None


def next_number(tickets, prefix):
    """Nächste freie Nummer für ``prefix`` (exakt ``prefix<Ziffern>``)."""
    pattern = re.compile(re.escape(prefix) + r"(\d+)$")
    numbers = []
    for record in tickets:
        match = pattern.fullmatch(str(record.get("id") or ""))
        if match:
            numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def _create(project, record_factory):
    """Legt ein Ticket kollisionssicher an; ``record_factory(tickets)`` liefert
    den anzuhängenden Datensatz. Konkurrierende Schreiber werden erkannt und
    mit neuer Nummer/Prüfsumme erneut versucht (bis 20 Versuche)."""
    for _ in range(20):
        snapshot = vibe_storage.read_snapshot(store_path(project))
        tickets = _tickets_from_snapshot(snapshot)
        record = record_factory(tickets)
        expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
        try:
            save(project, tickets + [record], expected=expected)
            return record
        except TicketStoreConflict:
            continue
    raise TicketStoreConflict(
        "Ticketspeicher wurde gleichzeitig geändert; bitte erneut versuchen.")


def _insert(project, record):
    """Hängt ein fertig normalisiertes Ticket kollisionssicher an (intern).

    Genutzt von ``vibe_issues``/``vibe_github`` für ``GH-<n>``-Tickets, die
    ausschließlich über Sync/verbundene Anlage entstehen und daher nicht über
    die freie Anlage (:func:`add`) laufen.
    """
    def factory(tickets):
        if find(tickets, record["id"]) is not None:
            raise ValueError("Ticket existiert bereits: " + record["id"])
        return record
    return _create(project, factory)


def add(project, title, description="", type="task", tid="", state="open",
        github=None, priority="", dependencies=None, extra=None):
    """Legt ein Ticket an; ohne ``tid`` wird eine Auto-ID vergeben.

    ``GH-``-IDs sind Issue-Importen vorbehalten und werden hier abgelehnt.
    Liefert den normalisierten Datensatz inklusive ``created``/``updated``.
    """
    tid = str(tid or "").strip()
    if tid.startswith("GH-"):
        raise ValueError("GH-IDs sind Issue-Importen vorbehalten: " + tid)
    if type not in TYPES:
        raise ValueError("Unbekannter Tickettyp: " + str(type))

    def factory(tickets):
        actual_tid = tid
        if not actual_tid:
            prefix = TYPE_PREFIXES.get(type)
            if prefix is None:
                raise ValueError("Für diesen Typ wird eine eigene ID benötigt: "
                                 + type)
            actual_tid = prefix + str(next_number(tickets, prefix))
        if find(tickets, actual_tid) is not None:
            raise ValueError("Ticket existiert bereits: " + actual_tid)
        record = {
            "id": actual_tid,
            "title": title,
            "description": description,
            "type": type,
            "state": state,
            "github": github,
            "priority": priority,
        }
        if dependencies is not None:
            record["dependencies"] = dependencies
        if extra:
            record.update(extra)
        normalized = normalize(record)
        normalized["created"] = _now_utc()
        normalized["updated"] = normalized["created"]
        return normalized

    return _create(project, factory)


def update(project, tid, **fields):
    """Teilaktualisierung eines Tickets; setzt ``updated`` und validiert.

    Erledigte Tickets sind gegen Titel-/Beschreibungsänderung geschützt; der
    Übergang nach ``done`` verlangt den Nachweis (Done-Invariante).
    """
    tid = str(tid or "").strip()
    for _ in range(20):
        snapshot = vibe_storage.read_snapshot(store_path(project))
        tickets = _tickets_from_snapshot(snapshot)
        record = find(tickets, tid)
        if record is None:
            raise ValueError("Ticket nicht gefunden im Ticketspeicher: " + tid)
        if record.get("state") == "done" and \
                ("title" in fields or "description" in fields):
            raise ValueError("Erledigte Tickets sind nicht bearbeitbar: " + tid)
        merged = dict(record)
        merged.update(fields)
        merged["updated"] = _now_utc()
        normalized = normalize(merged)
        expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
        try:
            save(project,
                 [normalized if item.get("id") == tid else item
                  for item in tickets], expected=expected)
            return normalized
        except TicketStoreConflict:
            continue
    raise TicketStoreConflict(
        "Ticketspeicher wurde gleichzeitig geändert; bitte erneut versuchen.")


def close(project, tid):
    """Schließt ein Ticket manuell (``state=done``) und liefert es zurück.

    Das ist bewusst getrennt vom Läufer-Abschluss: Ein Mensch darf ein Ticket
    ohne Nachweis schließen, während die Zustands-API und der Läufer weiterhin
    die Done-Invariante durchsetzen. Die übrigen Felder bleiben unverändert.
    Bereits geschlossene Tickets werden nicht erneut verändert.
    """
    tid = str(tid or "").strip()
    for _ in range(20):
        snapshot = vibe_storage.read_snapshot(store_path(project))
        tickets = _tickets_from_snapshot(snapshot)
        record = find(tickets, tid)
        if record is None:
            raise ValueError("Ticket nicht gefunden im Ticketspeicher: " + tid)
        if record.get("state") == "done":
            raise ValueError("Ticket ist bereits geschlossen: " + tid)
        merged = dict(record)
        merged["state"] = "done"
        merged["updated"] = _now_utc()
        normalized = normalize(merged, require_done_proof=False)
        expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
        try:
            save(project,
                 [normalized if item.get("id") == tid else item
                  for item in tickets], expected=expected)
            return normalized
        except TicketStoreConflict:
            continue
    raise TicketStoreConflict(
        "Ticketspeicher wurde gleichzeitig geändert; bitte erneut versuchen.")


def delete(project, tid):
    """Entfernt genau ein Ticket; erledigte Tickets sind geschützt."""
    tid = str(tid or "").strip()
    for _ in range(20):
        snapshot = vibe_storage.read_snapshot(store_path(project))
        tickets = _tickets_from_snapshot(snapshot)
        record = find(tickets, tid)
        if record is None:
            raise ValueError("Ticket nicht gefunden im Ticketspeicher: " + tid)
        if record.get("state") == "done":
            raise ValueError("Erledigte Tickets bleiben als Nachweis erhalten: "
                             + tid)
        expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
        try:
            save(project, [item for item in tickets if item.get("id") != tid],
                 expected=expected)
            return
        except TicketStoreConflict:
            continue
    raise TicketStoreConflict(
        "Ticketspeicher wurde gleichzeitig geändert; bitte erneut versuchen.")


def _normalize_deletions(values):
    """Deduplizierte, positive Int-Liste aus einem ``github_deletions``-Rohwert."""
    result = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number and number not in result:
            result.append(number)
    return result


def github_deletions(project):
    """Liste der zum Schließen vorgemerkten Issue-Nummern (dedupliziert)."""
    snapshot = vibe_storage.read_snapshot(store_path(project))
    if not snapshot.exists:
        return []
    document = _parse_document(snapshot.text, snapshot.path)
    return _normalize_deletions(document.get("github_deletions"))


def _mutate_deletions(project, change):
    """Atomar ``change(liste)`` auf ``github_deletions`` anwenden (kollisionssicher).

    Unbekannte Dokumentschlüssel bleiben erhalten; Tickets und ``version``
    werden nie angetastet. Eine konkurrierende Änderung wird als
    ``TicketStoreConflict`` gemeldet, nie still überschrieben.
    """
    path = store_path(project)
    for _ in range(20):
        snapshot = vibe_storage.read_snapshot(path)
        document = _parse_document(snapshot.text, path) if snapshot.exists else {}
        current = _normalize_deletions(document.get("github_deletions"))
        updated = change(current)
        if updated == current:
            return
        document["github_deletions"] = updated
        text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
        expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
        try:
            vibe_storage.write_text(path, text, expected=expected)
            return
        except vibe_storage.ConcurrentChangeError:
            continue
    raise TicketStoreConflict(
        "Ticketspeicher wurde gleichzeitig geändert; bitte erneut versuchen.")


def mark_github_deletion(project, number):
    """Vermerkt eine Issue-Nummer als Tombstone (dedupliziert, atomar)."""
    number = int(number)
    _mutate_deletions(project, lambda current: (
        current + [number] if number not in current else current))


def drop_github_deletion(project, number):
    """Entfernt eine Tombstone-Nummer (atomar)."""
    number = int(number)
    _mutate_deletions(project, lambda current: (
        [value for value in current if value != number]))


def ticket_file_name(tid):
    """Dateiname der sichtbaren Einzeldatei in der Arbeitskopie."""
    return TICKET_FILE_TEMPLATE.format(id=tid)


def write_ticket_file(path, record):
    """Schreibt die Einzeldatei ``TICKET-<ID>.json`` (atomar, Laufzeitstand)."""
    text = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
    vibe_storage.write_text(path, text)


def read_ticket_file(path):
    """Liest und validiert eine Einzeldatei; defektes JSON/Schema wirft."""
    snapshot = vibe_storage.read_snapshot(path)
    if not snapshot.exists:
        raise ValueError("Ticket-Datei nicht gefunden: " + str(path))
    try:
        record = json.loads(snapshot.text)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("Ticket-Datei unlesbar: " + str(path) + ": "
                         + str(error)) from None
    return normalize(record)


def display_state(record):
    """Anzeigezustand eines Tickets (deutsch, wie im Dashboard)."""
    state = (record or {}).get("state")
    return _STATE_LABELS.get(state, state)
