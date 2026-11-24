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
import os
import re
import urllib.parse

import vibe_github
import vibe_storage
import vibe_tickets

ISSUE_STATES = ("draft", "ready", "in-progress", "open")

# GH-Kennung eines importierten Tickets (``GH-<n>``).
_GH_ID = re.compile(r"^GH-(\d+)$")


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
    """Normalisierter ``GH-<n>``-Datensatz inkl. Zeitstempel."""
    record = vibe_tickets.normalize({
        "id": "GH-" + str(number),
        "title": _sanitize_title(title, number),
        "type": typ,
        "state": state,
        "github": number,
        "description": str(description or ""),
    })
    now = vibe_tickets._now_utc()
    record["created"] = now
    record["updated"] = now
    return record


def sync_issues(project_path, config):
    """Zentrale Dienstfunktion: Pull + Push + Close in einem Aufruf.

    Liefert die Statistik ``{"created", "updated", "closed", "pushed"}``.
    Wirft bei einem Konflikt der Storage-Schicht ``ValueError`` (nie stilles
    Überschreiben) und bei REST-Fehlern ``vibe_github.GitHubError``.

    Bewusste Entscheidung: Ein lokal bereits erledigtes Ticket bleibt
    erledigt, auch wenn das zugehörige Issue auf GitHub wieder geöffnet
    wurde. Im Offen-Zweig wird es übersprungen (kein Titel-/Zustandsupdate,
    kein Abbruch durch den Done-Schutz von ``vibe_tickets.update``); das
    Issue bleibt remote offen.
    """
    project = str(project_path)
    in_progress = config["issues_in_progress_label"]
    ready = config["issues_ready_label"]
    assignee = str(config.get("issues_assignee") or "").strip()

    stats = {"created": 0, "updated": 0, "closed": 0, "pushed": 0}

    remote = list_issues(config, project, state="all")

    tickets = vibe_tickets.load(project)
    by_github = {}
    for record in tickets:
        number = record.get("github")
        if number is not None:
            by_github[int(number)] = record

    # Phase A (Pull): bestehende Tickets aktualisieren/schließen, neue anlegen.
    for issue in remote:
        number = int(issue.get("number") or 0)
        if not number:
            continue
        issue_state = str(issue.get("state") or "")
        labels = _label_names(issue)
        remote_state = _state_from_labels(labels, in_progress, ready)
        located = by_github.get(number)
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
                # wenn das Issue remote wieder geöffnet wurde. Der
                # Done-Schutz von update würde den gesamten Sync abbrechen;
                # deshalb hier überspringen (kein Update, kein Crash).
                continue
            new_title = _sanitize_title(issue.get("title"), number)
            if located.get("title") != new_title \
                    or located.get("state") != remote_state:
                vibe_tickets.update(project, tid, title=new_title,
                                    state=remote_state, github=number)
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
        created = create_issue(
            config, project, record.get("title") or tid,
            record.get("description") or "", labels=labels,
            assignees=([assignee] if assignee else ()))
        number = int(created.get("number") or 0)
        if not number:
            continue
        vibe_tickets.update(project, tid, github=number)
        stats["pushed"] += 1

    return stats


def _state_labels(config, project_path, number, state):
    """Neue Label-Liste eines Issues für eine State-Aktion."""
    issue = get_issue(config, project_path, number)
    current = _label_names(issue)
    in_progress = config["issues_in_progress_label"]
    ready = config["issues_ready_label"]
    labels = [name for name in current if name not in (in_progress, ready)]
    if state == "ready":
        labels.append(ready)
    elif state == "in-progress":
        if ready in current:
            labels.append(ready)
        labels.append(in_progress)
    # draft/open: ready und in-progress sind bereits entfernt
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


def add_ticket_connected(project_path, config, title, description, category,
                         draft):
    """Legt im verbundenen Projekt zuerst das Issue an, dann das Speicher-Ticket.

    ``category`` ist ``bug``/``feature``; ``draft`` (Standard True) lässt das
    Ready-Label weg und legt das Ticket als ``state=draft`` an. Schlägt die
    Issue-Anlage fehl, bleibt der Ticketspeicher unverändert (wirft).
    """
    project = str(project_path)
    title = " ".join(str(title or "").split())
    if not title:
        raise ValueError("Titel fehlt")
    labels = []
    if category in ("bug", "feature"):
        labels.append(category)
    if not draft:
        labels.append(config["issues_ready_label"])
    assignee = str(config.get("issues_assignee") or "").strip()
    created = create_issue(
        config, project, title, str(description or ""), labels=labels,
        assignees=([assignee] if assignee else ()))
    number = int(created.get("number") or 0)
    if not number:
        raise vibe_github.GitHubError("Issue-Anlage lieferte keine Nummer.")

    typ = "bug" if category == "bug" else (
        "feature" if category == "feature" else "task")
    state = "draft" if draft else "open"
    vibe_tickets._insert(project, _gh_ticket(
        number, title, description, typ, state))
    return "GH-" + str(number)
