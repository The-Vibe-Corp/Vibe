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
aktualisiert Titel und Zustand lokaler Blöcke, legt neue Blöcke als
``- [ ] GH-<n> <Titel>`` an und schließt lokale Blöcke, deren Issue auf
GitHub geschlossen wurde. Offene lokale Pakete ohne GitHub-Bezug werden als
Issue angelegt und erhalten die Verweiszeile ``GitHub: #<n>``. Zustände sind
mindestens Open, In Progress (Label) und Closed; Entwürfe
(``Status: draft``) bleiben offen ohne Ready-Label und werden vom Läufer
übersprungen. TICKETS.md wird ausschließlich über die atomare Storage-Schicht
geschrieben (erwartete Prüfsumme); kollidierende Änderungen werden als
Konflikt gemeldet, nie still überschrieben.
"""
import os
import re
import urllib.parse

import vibe_github
import vibe_storage

# ---- Block-/Zeilenstruktur, deckungsgleich mit dem Parser in bin/vibe ----
_ENTRY_HEAD = re.compile(r"^- (?P<box>\[[^\]]*\])[ \t]*(?P<rest>.*)$")
_GH_ID = re.compile(r"^GH-(\d+)$")
_STATUS_LINE = re.compile(r"^[ \t]+Status:[ \t]?(.*)$")
_GITHUB_REF = re.compile(r"^[ \t]*GitHub:[ \t]*#\s*(\d+)\b")
_ART_LINE = re.compile(r"^[ \t]+Art:[ \t]?(.*)$")
_DESC_LINE = re.compile(r"^[ \t]+Beschreibung:[ \t]?(.*)$")
# Schlüsselwörter, die als Metadaten-/Markerzeile gelesen werden; deckungsgleich
# mit dem Parser in bin/vibe (_FEEDBACK_LABEL).
_META_KEYS = (
    "Beschreibung", "Erwartet", "Schritte", "Ist", "Commit", "BLOCKIERT",
    "WARTET AUF MERGE", "Art", "Priorität", "Abhängigkeiten", "Umfang",
    "Akzeptanz", "Tests", "Prüfungen", "Review", "Dokumentation", "Doku",
    "Status", "GitHub",
)
_META_LINE = re.compile(r"^[ \t]+(?:" + "|".join(_META_KEYS) + r"):[ \t]?")
# Erkennung einer Steuerzeile beim Schreiben: Schlüsselwort plus Doppelpunkt
# (auch mit Leerraum davor und unabhängig von Groß-/Kleinschreibung), damit
# auch Substring-Marker (BLOCKIERT:, WARTET AUF MERGE:, Priorität:,
# Abhängigkeiten:, Commit:) und der Draft-/Status-Abgleich entschärft werden.
_CONTROL_LINE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>" + "|".join(_META_KEYS)
    + r")[ \t]*:[ \t]?(?P<rest>.*)$", re.IGNORECASE)

ISSUE_STATES = ("draft", "ready", "in-progress", "open")


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


# ---------------------------------------------------------------- Blöcke
def _scan_blocks(lines):
    """(start, end)-Bereiche der Ticketblöcke (Kopfzeilen ``- [...] ...``)."""
    spans, cur = [], None
    for index, line in enumerate(lines):
        if _ENTRY_HEAD.match(line):
            if cur is not None:
                spans.append(cur)
            cur = [index, index + 1]
        elif cur is not None and (line.startswith((" ", "\t")) or not line.strip()):
            if line.strip():
                cur[1] = index + 1
        else:
            if cur is not None:
                spans.append(cur)
            cur = None
    if cur is not None:
        spans.append(cur)
    return spans


def _split_header(header):
    """Zerlegt eine Kopfzeile in ID, Titel, Checkbox und Prefix."""
    match = _ENTRY_HEAD.match(header)
    if not match:
        return None
    rest = match.group("rest")
    parts = rest.strip().split(None, 1)
    if not parts:
        return None
    ident = parts[0]
    ident_at = rest.find(ident)
    if ident_at < 0:
        return None
    prefix_end = match.start("rest") + ident_at + len(ident)
    prefix = header[:prefix_end]
    if not prefix.endswith((" ", "\t")):
        prefix += " "
    return {"id": ident, "title": (parts[1] if len(parts) > 1 else "").strip(),
            "checked": header.startswith("- [x]"), "prefix": prefix}


def _block_description(lines, start, end):
    """Beschreibungstext eines Blocks (``Beschreibung:`` samt Folgezeilen)."""
    desc, in_desc = [], False
    for line in lines[start:end]:
        match = _DESC_LINE.match(line)
        if match:
            in_desc = True
            first = match.group(1).strip()
            if first:
                desc.append(first)
            continue
        if in_desc:
            if _META_LINE.match(line):
                break
            if line.strip():
                desc.append(line.strip())
    return "\n".join(desc)


def _parse_block(lines, start, end):
    """Liest die für den Sync nötigen Felder eines Blocks."""
    header = _split_header(lines[start])
    status, github, art = None, None, ""
    for line in lines[start + 1:end]:
        match = _STATUS_LINE.match(line)
        if match:
            if status is None:
                value = match.group(1).strip().lower()
                if "progress" in value.replace("-", " "):
                    status = "in-progress"
                elif value in ("draft", "entwurf"):
                    status = "draft"
            continue
        match = _GITHUB_REF.match(line)
        if match and github is None:
            try:
                github = int(match.group(1))
            except ValueError:
                github = None
            continue
        match = _ART_LINE.match(line)
        if match and not art:
            art = match.group(1).strip().lower()
    if github is None and header:
        gh = _GH_ID.match(header["id"])
        if gh:
            github = int(gh.group(1))
    return {
        "id": header["id"], "checked": header["checked"],
        "title": header["title"], "status": status, "github": github,
        "art": art,
        "description": _block_description(lines, start, end),
    }


def _sanitize_title(value, number):
    """Einzeiliger Issue-Titel (Fallback mit Nummer)."""
    text = " ".join(str(value or "").split())
    return text or ("Issue " + str(number))


def _remote_status(labels, in_progress, ready):
    """Remote-Zustand: In-Progress-Label schlägt Ready-Label schlägt Draft."""
    if in_progress in labels:
        return "in-progress"
    if ready in labels:
        return "ready"
    return "draft"


def _local_status_value(remote_status):
    """Remote-Zustand -> Wert der lokalen ``Status:``-Zeile (leer = keine)."""
    return {"in-progress": "in-progress", "draft": "draft"}.get(remote_status, "")


def _replace_title(header, new_title):
    """Ersetzt den Titel einer Kopfzeile; Checkbox und ID bleiben unverändert."""
    parsed = _split_header(header)
    if not parsed:
        return header
    return parsed["prefix"] + new_title


def _apply_open_state(block_lines, new_title, status_value):
    """Neue Blockzeilen: Titel gesetzt, Statuszeile gesetzt/entfernt."""
    out = list(block_lines)
    out[0] = _replace_title(out[0], new_title)
    out = [line for line in out if not _STATUS_LINE.match(line)]
    if status_value:
        out.insert(1, "  Status: " + status_value)
    return out


def _apply_close(block_lines, number):
    """Hakt einen Block ab und hängt die Nachweiszeile an (idempotent)."""
    out = list(block_lines)
    if not out[0].startswith("- [x]"):
        out[0] = re.sub(r"^(- )\[[^\]]*\]", r"\1[x]", out[0], count=1)
    if not any(("geschlossen" in line.lower() and "#" + str(number) in line)
               for line in out):
        out.append("  GitHub: Issue #" + str(number) + " auf GitHub geschlossen")
    return out


def _neutralize_description_line(line):
    """Escaped eine Beschreibungs-Folgezeile, die als Metadaten-/Markerzeile
    gelesen würde; harmlose Zeilen bleiben unverändert lesbar.

    ``> `` markiert die Zeile als Freitext und unterbricht den Doppelpunkt
    nach dem Schlüsselwort, sodass weder Parser (_META_LINE/_FEEDBACK_LABEL)
    noch Läufer-Marker (is_draft, is_blocked, is_waiting_merge, priority,
    dependencies, proof_commits) auf Freitext anschlagen.
    """
    match = _CONTROL_LINE.match(line)
    if not match:
        return line
    rest = match.group("rest").strip()
    text = match.group("key") + (" " + rest if rest else "")
    return match.group("indent") + "> " + text


def _build_block(number, title, body, art, status_value):
    """Neuer Block ``- [ ] GH-<n> <Titel>`` aus einem Issue."""
    block = ["- [ ] GH-" + str(number) + " " + title,
             "  GitHub: #" + str(number)]
    if art == "bug":
        block.append("  Art: Bug")
    if status_value:
        block.append("  Status: " + status_value)
    desc = (body or "").strip().splitlines() or [""]
    block.append("  Beschreibung:" + (" " + desc[0] if desc[0] else ""))
    for extra in desc[1:]:
        block.append(_neutralize_description_line("  " + extra))
    return block


def _insert_github_ref(lines, start, number):
    """Fügt ``  GitHub: #<n>`` direkt hinter die Kopfzeile eines Blocks."""
    lines.insert(start + 1, "  GitHub: #" + str(number))


# ---------------------------------------------------------------- Sync
def sync_issues(project_path, config):
    """Zentrale Dienstfunktion: Pull + Push + Close in einem Aufruf.

    Liefert die Statistik ``{"created", "updated", "closed", "pushed"}``.
    Wirft bei einem Konflikt der Storage-Schicht ``ValueError`` (nie stilles
    Überschreiben) und bei REST-Fehlern ``vibe_github.GitHubError``.
    """
    project = str(project_path)
    path = os.path.join(project, "TICKETS.md")
    snapshot = vibe_storage.read_snapshot(path)
    if not snapshot.exists:
        raise ValueError("Keine TICKETS.md vorhanden: " + path)
    text = snapshot.text
    newline = "\r\n" if "\r\n" in text else "\n"
    ended = text.endswith(("\n", "\r"))
    lines = text.splitlines()

    stats = {"created": 0, "updated": 0, "closed": 0, "pushed": 0}
    in_progress = config["issues_in_progress_label"]
    ready = config["issues_ready_label"]
    assignee = str(config.get("issues_assignee") or "").strip()

    remote = list_issues(config, project, state="all")
    by_number = {}
    for issue in remote:
        number = issue.get("number")
        if number is not None:
            by_number[int(number)] = issue

    spans = _scan_blocks(lines)
    blocks = [_parse_block(lines, start, end) for start, end in spans]
    by_ref, by_ghid = {}, {}
    for (start, end), block in zip(spans, blocks):
        if block["github"] is not None:
            by_ref[block["github"]] = (start, end, block)
        match = _GH_ID.match(block["id"])
        if match:
            by_ghid[int(match.group(1))] = (start, end, block)

    # Phase A (Pull): bestehende Blöcke aktualisieren/schließen, neue anlegen.
    replacements = {}  # start -> (end, neue Zeilen)
    appended = []      # neue Blöcke (Listen von Zeilen)
    for issue in remote:
        number = int(issue.get("number") or 0)
        if not number:
            continue
        state = str(issue.get("state") or "")
        labels = _label_names(issue)
        located = by_ref.get(number) or by_ghid.get(number)
        if located is not None:
            start, end, block = located
            title = _sanitize_title(issue.get("title"), number)
            if state == "closed":
                new_block = _apply_close(lines[start:end], number)
                if new_block != lines[start:end]:
                    stats["closed"] += 1
                    replacements[start] = (end, new_block)
            else:
                status_value = _local_status_value(
                    _remote_status(labels, in_progress, ready))
                new_block = _apply_open_state(lines[start:end], title, status_value)
                if new_block != lines[start:end]:
                    stats["updated"] += 1
                    replacements[start] = (end, new_block)
        elif state != "closed":
            art = "bug" if "bug" in labels else ""
            appended.append(_build_block(
                number, _sanitize_title(issue.get("title"), number),
                str(issue.get("body") or ""), art,
                _local_status_value(_remote_status(labels, in_progress, ready))))
            stats["created"] += 1

    for start in sorted(replacements, reverse=True):
        end, new_block = replacements[start]
        lines[start:end] = new_block
    if appended:
        if lines and lines[-1].strip():
            lines.append("")
        for block in appended:
            lines.extend(block)
            lines.append("")

    # Phase B (Push): offene lokale Pakete ohne GitHub-Bezug als Issue anlegen.
    spans = _scan_blocks(lines)
    blocks = [_parse_block(lines, start, end) for start, end in spans]
    for start in range(len(spans) - 1, -1, -1):
        block = blocks[start]
        if block["github"] is not None or block["checked"]:
            continue
        if block["id"].startswith("GH-"):
            continue  # GH-Block ohne Referenz: nicht erneut pushen
        labels = ["bug"] if block["art"] == "bug" else []
        # Zustandstreue: ohne Statuszeile -> Ready-Label, Entwurf -> ohne.
        if block["status"] != "draft":
            labels.append(ready)
        created = create_issue(
            config, project, block["title"], block["description"],
            labels=labels, assignees=([assignee] if assignee else ()))
        number = int(created.get("number") or 0)
        if not number:
            continue
        _insert_github_ref(lines, spans[start][0], number)
        stats["pushed"] += 1

    result = newline.join(lines)
    if ended:
        result += newline
    try:
        vibe_storage.write_text(path, result, expected=snapshot.digest)
    except vibe_storage.ConcurrentChangeError as error:
        raise ValueError(
            "TICKETS.md wurde zwischenzeitlich geändert — Sync wiederholen ("
            + str(error) + ").") from None
    return stats


def _issue_number(block):
    """Issuenummer eines Blocks (Verweiszeile oder GH-Kennung), sonst None."""
    return block["github"]


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
    """State-Aktion: PATCH der Labels und sofortige lokale Statuszeile.

    ``state`` ist draft/ready/in-progress/open. Liefert die Issuenummer; wirft
    bei fehlendem Bezug, unbekanntem Zustand, REST- oder Speicherfehler.
    """
    project = str(project_path)
    if state not in ISSUE_STATES:
        raise ValueError("Unbekannter Issues-Zustand: " + str(state)
                         + " (draft|ready|in-progress|open)")
    path = os.path.join(project, "TICKETS.md")
    snapshot = vibe_storage.read_snapshot(path)
    if not snapshot.exists:
        raise ValueError("Keine TICKETS.md vorhanden: " + path)
    text = snapshot.text
    newline = "\r\n" if "\r\n" in text else "\n"
    ended = text.endswith(("\n", "\r"))
    lines = text.splitlines()

    located = None
    for start, end in _scan_blocks(lines):
        block = _parse_block(lines, start, end)
        if block["id"] == ticket_id:
            located = (start, end, block)
            break
    if located is None:
        raise ValueError("Arbeitspaket nicht gefunden: " + str(ticket_id))
    start, end, block = located
    number = _issue_number(block)
    if number is None:
        raise ValueError("Arbeitspaket hat keinen GitHub-Bezug: " + str(ticket_id))

    labels = _state_labels(config, project, number, state)
    update_issue(config, project, number, {"labels": labels})

    status_value = {"draft": "draft", "in-progress": "in-progress"}.get(state, "")
    out = [line for line in lines[start:end] if not _STATUS_LINE.match(line)]
    if status_value:
        out.insert(1, "  Status: " + status_value)
    lines[start:end] = out

    result = newline.join(lines)
    if ended:
        result += newline
    try:
        vibe_storage.write_text(path, result, expected=snapshot.digest)
    except vibe_storage.ConcurrentChangeError as error:
        raise ValueError(
            "TICKETS.md wurde zwischenzeitlich geändert — Aktion wiederholen ("
            + str(error) + ").") from None
    return number


def add_ticket_connected(project_path, config, title, description, category,
                         draft):
    """Legt im verbundenen Projekt zuerst das Issue an, dann den lokalen Block.

    ``category`` ist ``bug``/``feature`` (Label); ``draft`` (Standard True)
    lässt das Ready-Label weg und markiert den Block als ``Status: draft``.
    Schlägt die Issue-Anlage fehl, bleibt TICKETS.md unverändert (wirft).
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

    status_value = "draft" if draft else ""
    block = _build_block(number, title, str(description or ""),
                         "bug" if category == "bug" else "", status_value)

    path = os.path.join(project, "TICKETS.md")
    snapshot = vibe_storage.read_snapshot(path)
    if not snapshot.exists:
        raise ValueError("Keine TICKETS.md vorhanden: " + path)
    text = snapshot.text
    newline = "\r\n" if "\r\n" in text else "\n"
    ended = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(block)
    result = newline.join(lines)
    if ended:
        result += newline
    try:
        vibe_storage.write_text(path, result, expected=snapshot.digest)
    except vibe_storage.ConcurrentChangeError as error:
        raise ValueError(
            "TICKETS.md wurde zwischenzeitlich geändert — Anlage wiederholen ("
            + str(error) + ").") from None
    return "GH-" + str(number)
