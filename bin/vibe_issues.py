#!/usr/bin/env python3
"""vibe_issues — GitHub-Issues-Sync für vibe (AP3-Korbat).

Das Modul ist das Backbone für den Issues-Sync: der vollständige
GitHub-REST-Zugriff und die Sync-Logik liegen hier; Oberfläche (Nova/JS) und
CLI rufen ausschließlich Dienstfunktionen auf, nie REST direkt. REST läuft
ausschließlich über die bestehenden Helpers von ``vibe_github``
(``token_for_rest``, ``_http_json``, ``GitHubError``, ``quote``,
``mask_embedded_credentials``); Tokens erscheinen nie in Meldungen oder Logs.

GitHub ist die Quelle der Wahrheit: Der Sync zieht alle Issues
(``state=all``, ohne Pull-Requests, optional mit Assignee-Filter) und
aktualisiert Titel und Zustand der lokalen Tickets im Ticketspeicher, legt
neue Tickets als ``GH-<n>`` an und setzt lokale Tickets, deren Issue auf
GitHub geschlossen wurde, auf ``done``. Offene lokale Pakete ohne
GitHub-Bezug werden als Issue angelegt und erhalten danach ``github=<n>``.
Zustände sind mindestens Open, In Progress (Label) und Closed; Entwürfe
bleiben ohne Ready-Label und werden vom Läufer übersprungen. Der
Ticketspeicher (``.vibe/tickets.json``) wird ausschließlich über
``vibe_tickets``/``vibe_storage`` geschrieben (erwartete Prüfsumme);
kollidierende Änderungen werden als Konflikt gemeldet, nie still
überschrieben.
"""
import hashlib
import os
import re
import urllib.parse

import vibe_github
import vibe_storage
import vibe_tickets

ISSUE_STATES = ("draft", "ready", "in-progress", "open")

# GH-Kennung eines importierten Tickets (``GH-<n>``).
_GH_ID = re.compile(r"^GH-(\d+)$")


def _text_hash(title, description):
    """hex-SHA256 über ``title + NUL + description`` als Textbasislinie."""
    raw = (str(title or "") + "\x00" + str(description or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _api(config):
    """API-Basis (Leerwert = offizielle GitHub-API)."""
    return str(config.get("api") or vibe_github.OFFICIAL_API).rstrip("/")


def _token(config, project_path):
    """Token für die REST-Ebene; nur über die bestehenden Wege."""
    return vibe_github.token_for_rest(_api(config), project_path)


def _repo(config):
    """Prüft owner/name; ungültig -> verständlicher Fehler ohne Token."""
    repo = str(config.get("repo") or "").strip()
    if not vibe_github.RE_REPO.match(repo):
        raise vibe_github.GitHubError("Repository in owner/name angeben")
    return repo


def list_issues(config, project_path=None, state="all"):
    """Alle GitHub-Issues (ohne Pull-Requests, optional Assignee-Filter).

    ``state`` ist ``all`` (Sync braucht auch geschlossene Issues); der
    Legacy-Label-Filter ``GITHUB_LABEL`` greift hier bewusst nicht.
    """
    repo = _repo(config)
    api = _api(config)
    query = {"state": state, "per_page": "100"}
    assignee = str(config.get("issues_assignee") or "").strip()
    if assignee:
        query["assignee"] = assignee
    url = (api + "/repos/" + vibe_github.quote(repo) + "/issues?"
           + urllib.parse.urlencode(query))
    results = vibe_github._http_json("GET", url, token=_token(config, project_path))
    if not isinstance(results, list):
        raise vibe_github.GitHubError("GitHub-Antwort für Issues ist ungewöhnlich.")
    issues = []
    for item in results:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue  # Pull-Requests erscheinen auch in der Issue-Liste
        issues.append(item)
    return issues


def get_issue(config, project_path, number):
    """Einzelnes Issue (für den aktuellen Label-Stand vor einem PATCH)."""
    url = (_api(config) + "/repos/" + vibe_github.quote(_repo(config))
           + "/issues/" + str(number))
    return vibe_github._http_json("GET", url, token=_token(config, project_path))


def create_issue(config, project_path, title, body="", labels=(), assignees=()):
    """Legt ein Issue an; Labels/Assignees sind optionale Listen."""
    url = _api(config) + "/repos/" + vibe_github.quote(_repo(config)) + "/issues"
    payload = {"title": str(title), "body": str(body or "")}
    label_list = [str(label) for label in (labels or ()) if str(label)]
    assignee_list = [str(assignee) for assignee in (assignees or ()) if str(assignee)]
    if label_list:
        payload["labels"] = label_list
    if assignee_list:
        payload["assignees"] = assignee_list
    return vibe_github._http_json("POST", url, token=_token(config, project_path),
                                  payload=payload)


def update_issue(config, project_path, number, payload):
    """PATCH auf ein Issue (z. B. Labels ändern)."""
    url = (_api(config) + "/repos/" + vibe_github.quote(_repo(config))
           + "/issues/" + str(number))
    return vibe_github._http_json("PATCH", url, token=_token(config, project_path),
                                  payload=payload)


def close_issue(config, project_path, number):
    """PATCH ``state=closed`` auf ein Issue (Best-effort-Close ohne echtes Löschen)."""
    return update_issue(config, project_path, number, {"state": "closed"})


def _label_names(issue):
    """Namen der Labels eines Issue-Datensatzes."""
    return [str(label.get("name", "")) for label in issue.get("labels", [])
            if isinstance(label, dict)]


# ---------------------------------------------------------------- Sync
def _sanitize_title(value, number):
    """Einzeiliger Issue-Titel (Fallback mit Nummer)."""
    text = " ".join(str(value or "").split())
    return text or ("Issue " + str(number))


def _type_from_labels(labels):
    """Tickettyp aus Issue-Labels: bug/feature gewinnen, sonst task."""
    if "bug" in labels:
        return "bug"
    if "feature" in labels:
        return "feature"
    return "task"


def _state_from_labels(labels, in_progress, ready):
    """Lokaler Zustand aus Labels: In-Progress > Ready > Draft."""
    if in_progress in labels:
        return "in-progress"
    if ready in labels:
        return "open"
    return "draft"


def _local_state_value(state):
    """State-Aktion -> lokaler Speicherzustand (``ready`` mappt auf ``open``)."""
    return {"draft": "draft", "ready": "open",
            "in-progress": "in-progress", "open": "open"}[state]


def _ticket_number(record):
    """Issuenummer eines Tickets (Feld ``github`` oder ``GH-<n>``-ID)."""
    number = record.get("github")
    if number is not None:
        return int(number)
    match = _GH_ID.match(str(record.get("id") or ""))
    if match:
        return int(match.group(1))
    return None


def _gh_ticket(number, title, description, typ, state):
    """Normalisierter ``GH-<n>``-Datensatz inkl. Zeitstempel und Textbasislinie."""
    title = _sanitize_title(title, number)
    description = str(description or "")
    record = vibe_tickets.normalize({
        "id": "GH-" + str(number),
        "title": title,
        "type": typ,
        "state": state,
        "github": number,
        "description": description,
        "gh_text": _text_hash(title, description),
    })
    now = vibe_tickets._now_utc()
    record["created"] = now
    record["updated"] = now
    return record


def _sync_text(project, config, number, record, issue, stats):
    """Drei-Wege-Textabgleich für ein offenes, nicht erledigtes Ticket.

    ``record`` ist der lokale Datensatz, ``issue`` der Remote-Stand. Über die
    Hashes (lokal jetzt, remote jetzt, gespeicherte Basislinie ``gh_text``)
    wird entschieden: gleich -> Basislinie ergänzen; nur remote geändert ->
    Titel und Beschreibung übernehmen (``text_pulled`` + ``updated``); nur
    lokal geändert -> PATCH (``text_pushed``); beide geändert oder fehlende
    Basislinie bei unterschiedlichen Texten -> lokale Fassung gewinnt
    (``conflicts``). done-Tickets werden vom Aufrufer ausgeschlossen.
    """
    tid = str(record.get("id") or "")
    local_title = record.get("title") or ""
    local_description = record.get("description") or ""
    remote_title = _sanitize_title(issue.get("title"), number)
    remote_description = str(issue.get("body") or "")

    local_hash = _text_hash(local_title, local_description)
    remote_hash = _text_hash(remote_title, remote_description)
    baseline = record.get("gh_text") or ""

    if local_hash == remote_hash:
        if baseline != local_hash:
            vibe_tickets.update(project, tid, gh_text=local_hash)
        return

    if baseline and baseline == remote_hash:
        update_issue(config, project, number,
                     {"title": local_title, "body": local_description})
        vibe_tickets.update(project, tid, gh_text=local_hash)
        stats["text_pushed"] += 1
        return

    if baseline and baseline == local_hash:
        vibe_tickets.update(project, tid, title=remote_title,
                            description=remote_description,
                            gh_text=remote_hash)
        stats["text_pulled"] += 1
        stats["updated"] += 1
        return

    update_issue(config, project, number,
                 {"title": local_title, "body": local_description})
    vibe_tickets.update(project, tid, gh_text=local_hash)
    stats["conflicts"] += 1


def sync_issues(project_path, config):
    """Zentrale Dienstfunktion: Pull + Push + Close + Tombstone-Nacharbeiten.

    Liefert die Statistik ``created``/``updated``/``closed``/``pushed`` plus
    ``text_pushed``/``text_pulled``/``conflicts``/``closed_remote``. Wirft bei
    einem Konflikt der Storage-Schicht ``ValueError`` (nie stilles
    Überschreiben) und bei REST-Fehlern ``vibe_github.GitHubError``.

    Bewusste Entscheidung: Ein lokal bereits erledigtes Ticket bleibt
    erledigt, auch wenn das zugehörige Issue auf GitHub wieder geöffnet
    wurde (kein Text-/Zustandssync in keine Richtung). Der Textabgleich ist
    bidirektional über ``gh_text``; bei beidseitiger Änderung oder fehlender
    Basislinie mit unterschiedlichen Texten gewinnt die lokale Fassung.
    """
    project = str(project_path)
    in_progress = config["issues_in_progress_label"]
    ready = config["issues_ready_label"]
    assignee = str(config.get("issues_assignee") or "").strip()

    stats = {"created": 0, "updated": 0, "closed": 0, "pushed": 0,
             "text_pushed": 0, "text_pulled": 0, "conflicts": 0,
             "closed_remote": 0}

    remote = list_issues(config, project, state="all")
    by_number = {}
    for issue in remote:
        number = int(issue.get("number") or 0)
        if number:
            by_number[number] = issue

    tombstones = set(vibe_tickets.github_deletions(project))

    tickets = vibe_tickets.load(project)
    by_github = {}
    for record in tickets:
        number = record.get("github")
        if number is not None:
            by_github[int(number)] = record

    # Phase A (Pull): bestehende Tickets aktualisieren/schließen, neue anlegen.
    # Offene Remote-Issues mit Tombstone werden bewusst nicht neu angelegt.
    for number, issue in by_number.items():
        issue_state = str(issue.get("state") or "")
        labels = _label_names(issue)
        remote_state = _state_from_labels(labels, in_progress, ready)
        located = by_github.get(number)
        if number in tombstones:
            continue
        if located is not None:
            tid = located["id"]
            if issue_state == "closed":
                if located.get("state") != "done":
                    # GH-48: Ein auf GitHub geschlossenes Issue gilt als
                    # erledigt; der github-Bezug ersetzt den Nachweis-Commit,
                    # das test-Feld hält die Herkunft fest (Done-Invariante).
                    vibe_tickets.update(project, tid, state="done",
                                        test="GitHub-Issue #" + str(number)
                                        + " geschlossen")
                    stats["closed"] += 1
                continue
            if located.get("state") == "done":
                # GH-48: Ein lokal erledigtes Ticket bleibt erledigt, auch
                # wenn das Issue remote wieder geöffnet wurde (Done-Schutz).
                continue
            _sync_text(project, config, number, located, issue, stats)
            if located.get("state") != remote_state:
                vibe_tickets.update(project, tid, state=remote_state)
                stats["updated"] += 1
        elif issue_state != "closed":
            vibe_tickets._insert(project, _gh_ticket(
                number, issue.get("title"), issue.get("body"),
                _type_from_labels(labels), remote_state))
            stats["created"] += 1

    # Phase B (Push): offene lokale Tickets ohne GitHub-Bezug als Issue anlegen.
    # Bewusste Änderung (GH-48): blocked/waiting-merge werden nicht gepusht;
    # nur open/in-progress (draft wird ohnehin nie gepusht).
    tickets = vibe_tickets.load(project)
    for record in tickets:
        tid = str(record.get("id") or "")
        if tid.startswith("GH-"):
            continue
        if record.get("github") is not None:
            continue
        if record.get("state") not in ("open", "in-progress"):
            continue
        labels = []
        if record.get("type") == "bug":
            labels.append("bug")
        elif record.get("type") == "feature":
            labels.append("feature")
        labels.append(ready)
        title = record.get("title") or tid
        description = record.get("description") or ""
        created = create_issue(
            config, project, title, description, labels=labels,
            assignees=([assignee] if assignee else ()))
        number = int(created.get("number") or 0)
        if not number:
            continue
        vibe_tickets.update(project, tid, github=number,
                            gh_text=_text_hash(title, description))
        stats["pushed"] += 1

    # Phase C (Tombstones nacharbeiten): gelöschte Tickets best effort schließen.
    # Ein Fehlschlag bricht den Sync nicht ab; der Tombstone bleibt und wird
    # beim nächsten Sync erneut versucht. Geschlossene oder verschwundene
    # Issues lassen den Tombstone entfallen.
    for number in sorted(tombstones):
        issue = by_number.get(number)
        if issue is None or str(issue.get("state") or "") == "closed":
            vibe_tickets.drop_github_deletion(project, number)
            continue
        try:
            close_issue(config, project, number)
        except vibe_github.GitHubError:
            continue
        vibe_tickets.drop_github_deletion(project, number)
        stats["closed_remote"] += 1

    return stats


def sync_message(stats):
    """Deutsche Sync-Meldung; nennt Text-/Konflikt-/Close-Anteile bei Werten > 0."""
    parts = [
        "%d angelegt" % stats["created"],
        "%d aktualisiert" % stats["updated"],
        "%d geschlossen" % stats["closed"],
        "%d gepusht" % stats["pushed"],
    ]
    if stats.get("text_pushed"):
        parts.append("%d Text hochgeladen" % stats["text_pushed"])
    if stats.get("text_pulled"):
        parts.append("%d Text übernommen" % stats["text_pulled"])
    if stats.get("conflicts"):
        parts.append("%d Konflikte (lokale Fassung gewinnt)" % stats["conflicts"])
    if stats.get("closed_remote"):
        parts.append("%d entfernte Issues geschlossen" % stats["closed_remote"])
    return "Issues synchronisiert: " + ", ".join(parts) + "."


def _state_labels(config, project_path, number, state):
    """Neue Label-Liste eines Issues für eine State-Aktion."""
    issue = get_issue(config, project_path, number)
    current = _label_names(issue)
    in_progress = config["issues_in_progress_label"]
    ready = config["issues_ready_label"]
    labels = [name for name in current if name not in (in_progress, ready)]
    if state in ("ready", "open"):
        # GH-47: ``open`` setzt das Ready-Label wie ``ready`` — sonst würde
        # der nächste Pull das Ticket ohne Ready-Label auf draft zurücksetzen.
        labels.append(ready)
    elif state == "in-progress":
        if ready in current:
            labels.append(ready)
        labels.append(in_progress)
    # draft: ready und in-progress sind bereits entfernt
    return labels


def set_issue_state(project_path, config, ticket_id, state):
    """State-Aktion: PATCH der Labels und sofortiger lokaler Zustand.

    ``state`` ist draft/ready/in-progress/open; ``ready`` mappt lokal auf
    ``open``. Liefert die Issuenummer; wirft bei fehlendem Bezug, unbekanntem
    Zustand, REST- oder Speicherfehler.
    """
    project = str(project_path)
    if state not in ISSUE_STATES:
        raise ValueError("Unbekannter Issues-Zustand: " + str(state)
                         + " (draft|ready|in-progress|open)")
    record = vibe_tickets.find(vibe_tickets.load(project), str(ticket_id))
    if record is None:
        raise ValueError("Ticket nicht gefunden im Ticketspeicher: "
                         + str(ticket_id))
    number = _ticket_number(record)
    if number is None:
        raise ValueError("Ticket hat keinen GitHub-Bezug: " + str(ticket_id))

    update_issue(config, project, number,
                 {"labels": _state_labels(config, project, number, state)})

    local_state = _local_state_value(state)
    if record.get("state") != local_state:
        vibe_tickets.update(project, str(ticket_id), state=local_state)
    return number


def delete_ticket_connected(project, config, ticket_id):
    """Löscht ein Ticket; bei GitHub-Bezug wird das Issue best effort geschlossen.

    done-Tickets werden vor jedem REST-Versuch abgelehnt (``ValueError``);
    ohne GitHub-Bezug wird nur lokal gelöscht. Mit Bezug wird das Issue per
    ``PATCH state=closed`` geschlossen; gelingt das, wird lokal gelöscht.
    Schlägt der Close fehl, wird die Nummer als Tombstone vermerkt, lokal
    gelöscht und eine Meldung geliefert, die den Fehlschlag und den erneuten
    Sync-Versuch nennt (nie das Token). Liefert die deutsche Meldung.
    """
    project = str(project)
    record = vibe_tickets.find(vibe_tickets.load(project), str(ticket_id))
    if record is None:
        raise ValueError("Ticket nicht gefunden im Ticketspeicher: "
                         + str(ticket_id))
    if record.get("state") == "done":
        raise ValueError("Erledigte Tickets bleiben als Nachweis erhalten: "
                         + str(ticket_id))
    number = _ticket_number(record)
    if number is None:
        vibe_tickets.delete(project, str(ticket_id))
        return str(ticket_id) + " gelöscht."
    try:
        close_issue(config, project, number)
    except vibe_github.GitHubError as error:
        vibe_tickets.mark_github_deletion(project, number)
        vibe_tickets.delete(project, str(ticket_id))
        return (str(ticket_id) + " lokal gelöscht; Issue #" + str(number)
                + " konnte nicht geschlossen werden (" + str(error)
                + ") — der Sync versucht es erneut.")
    vibe_tickets.delete(project, str(ticket_id))
    return (str(ticket_id) + " gelöscht; Issue #" + str(number)
            + " geschlossen.")


def add_ticket_connected(project_path, config, title, description, ttype,
                         draft):
    """Legt im verbundenen Projekt zuerst das Issue an, dann das Speicher-Ticket.

    ``ttype`` ist der eine Tickettyp (``bug``/``feature``/``feedback``/``task``)
    und bestimmt zugleich das GitHub-Typ-Label (nur bug/feature/feedback; task
    erhält kein Typ-Label) und den Speichertyp. ``draft`` (Standard True) lässt
    das Ready-Label weg und legt das Ticket als ``state=draft`` an. Schlägt die
    Issue-Anlage fehl, bleibt der Ticketspeicher unverändert (wirft).
    """
    project = str(project_path)
    title = " ".join(str(title or "").split())
    if not title:
        raise ValueError("Titel fehlt")
    if ttype not in vibe_tickets.TYPES:
        raise ValueError("Unbekannter Tickettyp: " + str(ttype))
    labels = []
    if ttype in ("bug", "feature", "feedback"):
        labels.append(ttype)
    if not draft:
        labels.append(config["issues_ready_label"])
    assignee = str(config.get("issues_assignee") or "").strip()
    created = create_issue(
        config, project, title, str(description or ""), labels=labels,
        assignees=([assignee] if assignee else ()))
    number = int(created.get("number") or 0)
    if not number:
        raise vibe_github.GitHubError("Issue-Anlage lieferte keine Nummer.")

    state = "draft" if draft else "open"
    vibe_tickets._insert(project, _gh_ticket(
        number, title, description, ttype, state))
    return "GH-" + str(number)
