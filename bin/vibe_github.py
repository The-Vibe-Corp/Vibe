#!/usr/bin/env python3
"""vibe_github — optionale GitHub-Verknüpfung je Projekt (AP6).

GitHub-Funktionen sind pro Projekt einzuschalten (``GITHUB_ENABLED`` in
``.vibe/project.env``) und ändern nie automatisch etwas: Branches, Updates
(fetch/pull) und Pushes/Merge-Requests sind bewusste Nutzerentscheidungen.
Git läuft mit Argumentlisten (ohne Shell), GitHub-REST über die
Standardbibliothek (urllib); die API-Basis ist konfigurierbar
(``GITHUB_API``, Standard https://api.github.com), damit Prüfungen gegen
einen lokalen Scheindienst laufen können. Der GitHub-Dienst selbst wird nur
bei einer bewussten Aktion kontaktiert (Issues, Merge-Request); die
Git-Status-Ebene liest die aktuelle Fern-Referenz bewusst via ls-remote und
zieht unbekannte Fern-Objekte nach, ohne etwas zusammenzuführen.

Der Access-Token kommt ausschließlich aus der Umgebung (``GITHUB_TOKEN``
oder ``GH_TOKEN``) und taucht in keinem Log, keiner Konfiguration und
keiner Fehlermeldung auf.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

if os.path.dirname(os.path.realpath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import vibe_storage  # gemeinsame Storage-Schicht: Kollisionserkennung (V-005)

OFFICIAL_API = "https://api.github.com"
DEFAULT_LABEL = "vibe"
TOKEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN")
TRUE_VALUES = ("1", "true", "yes", "on")
TIMEOUT_GIT = 120
TIMEOUT_HTTP = 30
RE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TICKET_GH_RE = re.compile(r"(?m)^\s*-\s*\[[^\]]*\]\s*GH-(\d+)\b")


class GitHubError(ValueError):
    """Verständlicher Fehler der GitHub-Ebene (enthält nie den Token)."""


def token_from_env():
    """Access-Token nur aus der Umgebung; eine Speicherung bleibt verboten."""
    for key in TOKEN_ENV:
        value = os.environ.get(key)
        if value:
            return value
    return ""


def read_config(env_path):
    """GitHub-Konfiguration des Projekts; ohne Einträge bleibt GitHub aus."""
    values = _read_env_file(env_path)
    enabled = str(values.get("GITHUB_ENABLED", "")).strip().lower() in TRUE_VALUES
    label = str(values.get("GITHUB_LABEL", "")).strip() or DEFAULT_LABEL
    api = str(values.get("GITHUB_API", "")).strip() or OFFICIAL_API
    return {
        "enabled": enabled,
        "repo": str(values.get("GITHUB_REPO", "")).strip(),
        "label": label,
        "api": api,
    }


def _read_env_file(path):
    """Liest KEY=WERT-Zeilen (Anführungszeichen erlaubt, # als Kommentar)."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (FileNotFoundError, NotADirectoryError):
        return {}
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _repo_slug(parts):
    """owner/name aus Pfadabschnitten; endend .git wird entfernt."""
    while parts and parts[0] in ("", ".git"):
        parts.pop(0)
    while len(parts) >= 2 and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    # Punkte im echten Repo-Namen (owner/my.repo) sind zulässig;
    # reine Navigationsabschnitte "."/".." bleiben verständlich abgelehnt.
    if len(parts) < 2 or any(p in (".", "..") for p in parts):
        return None
    slug = parts[-2] + "/" + parts[-1]
    return slug if RE_REPO.match(slug) else None


def parse_remote_url(url):
    """Prüft eine Git-Remote-Adresse; liefert owner/name für GitHub-Hosts.

    github.com-Adressen müssen ein erkennbares owner/name tragen; Datei-,
    SSH- und andere Host-Adressen sind als Git-Remote zulässig (Repository
    bleibt dort unbekannt, GitHub-Funktionen brauchen owner/name).
    """
    raw = str(url or "").strip()
    if not raw:
        raise ValueError("Remote-Adresse fehlt")
    if "\x00" in raw or any(c in raw for c in ("\n", "\r")):
        raise ValueError("Remote-Adresse enthält unerlaubte Steuerzeichen")
    scp = re.match(r"^(?P<user>[^@/]+@)?(?P<host>[^/:\s]+):(?P<path>.+)$", raw)
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme in ("http", "https", "file", "ssh") and parsed.scheme in raw[:8]:
        if parsed.scheme == "file":
            if not os.path.isabs(parsed.path) and parsed.netloc not in ("", "localhost"):
                raise ValueError("file-Remote erwartet: file:///absoluter/pfad")
            return None
        host = (parsed.netloc or "").strip().lower()
        if not host and parsed.scheme == "ssh" and raw.startswith("ssh://"):
            raise ValueError("ssh-Remote erwartet: ssh://user@host/pfad")
        parts = [p for p in parsed.path.split("/") if p]
        if not host and parsed.scheme in ("http", "https"):
            raise ValueError("Remote-Adresse ohne Host")
        if host == "github.com":
            return _require_github_slug(parts)
        return None
    if scp:
        host = scp.group("host").strip().lower()
        parts = [p for p in scp.group("path").split("/") if p]
        if host == "github.com":
            return _require_github_slug(parts)
        return None
    raise ValueError("Remote-Adresse erwartet: https://github.com/owner/name.git, "
                     "git@github.com:owner/name.git oder file:///pfad")


def _require_github_slug(parts):
    slug = _repo_slug(list(parts))
    if not slug:
        raise ValueError("GitHub-Repository: owner/name erwartet (z. B. owner/name.git)")
    return slug


def git(project_path, *args):
    """Führt Git mit Argumentlisten aus (ohne Shell, mit Zeitlimit)."""
    argv = ["git", "--no-pager", "-c", "core.fsmonitor=false", *[str(a) for a in args]]
    if not all(isinstance(a, str) for a in argv):
        raise ValueError("Argumentliste erwartet: nur Zeichenketten")
    try:
        result = subprocess.run(argv, cwd=str(project_path), capture_output=True,
                                text=True, timeout=TIMEOUT_GIT)
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return 127, "Programm nicht gefunden: git"
    except subprocess.TimeoutExpired:
        return 124, f"Zeitüberschreitung nach {TIMEOUT_GIT:g} s: {' '.join(argv)}"
    except OSError as error:
        return 126, f"Programm nicht ausführbar: git: {error}"


def current_branch(project_path):
    rc, out = git(project_path, "symbolic-ref", "--short", "HEAD")
    return out.strip() if rc == 0 and out.strip() else ""


def remotes(project_path):
    """Alle Remotes (Name, maskierte URL); eingebettete Zugangsdaten wie
    ``https://token:geheim@host`` erscheinen als ``scheme://***@host``."""
    rc, out = git(project_path, "remote", "-v")
    rows = []
    if rc == 0:
        seen = set()
        for line in out.splitlines():
            name, _, rest = line.partition("\t")
            url = mask_url(rest.split("(", 1)[0].strip())
            if name and url and (name, url) not in seen:
                seen.add((name, url))
                rows.append({"name": name, "url": url})
    return rows


def mask_url(url):
    """.git-URLs mit Zugangsdaten im Header-Teil ohne diese Daten anzeigen."""
    if "://" not in url or "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    userinfo, _, after = rest.partition("@")
    if not after or not userinfo:
        return url
    return scheme + "://***@" + after


def _push_state(project_path, branch, remote_sha=None):
    """Ahead/Behind des Branches gegen origin (aktuell via ls-remote).

    Es wird nichts ins lokale Fern-Referenzlayout geschrieben und nichts
    zusammengeführt. Der bewusste Abgleich liest die Fern-Referenz und
    zieht bei unbekanntem Fern-Objekt nur dieses Objekt nach (kein Merge,
    keine verschobenen Fern-Referenzen). Ohne Remote-Eintrag oder bei
    Fehler bleibt der Stand bei 0/0 (keine veralteten Referenzen).
    ``remote_sha`` darf eine bereits ermittelte Fern-SHA sein, damit
    Branchlisten mit einem einzigen ls-remote auskommen.
    """
    if not branch:
        return 0, 0
    if not any(r["name"] == "origin" for r in remotes(project_path)):
        return 0, 0
    if remote_sha is None:
        rc, out = git(project_path, "ls-remote", "origin", "refs/heads/" + branch)
        if rc != 0:
            rc, _ = git(project_path, "rev-parse", "--verify", "--quiet",
                        "origin/" + branch)
            if rc != 0:
                return 0, 0
            return _revision_compare_local(project_path, branch, "origin/" + branch)
        remote_sha = _lsremote_sha(out, branch)
        if not remote_sha:
            return 0, 0
    if not _object_present(project_path, remote_sha):
        # Fern-Objekt lokal unbekannt: gezielt das neue Objekt nachziehen,
        # damit rev-list gegen die rohe SHA rechnen kann. Das zieht keine
        # Merge-Kopien und verschiebt keine Fern-Referenzen; scheitert der
        # Nachzug, bleibt der Stand bei 0/0 (keine veralteten Referenzen).
        git(project_path, "fetch", "--quiet", "origin", remote_sha)
    return _revision_compare_local(project_path, branch, remote_sha)


def _lsremote_sha(out, branch):
    for column in out.splitlines():
        sha, _, ref = column.partition("\t")
        if sha and ref.strip() == "refs/heads/" + branch:
            return sha.strip()
    return ""


def _object_present(project_path, sha):
    rc, _ = git(project_path, "rev-parse", "--verify", "--quiet",
                sha + "^{commit}")
    return rc == 0


def _revision_compare_local(project_path, left, right):
    rc, out = git(project_path, "rev-list", "--left-right", "--count",
                  left + "..." + right)
    if rc != 0 or not out.strip():
        return 0, 0
    fields = out.split()
    if len(fields) < 2 or not fields[0].isdigit() or not fields[1].isdigit():
        return 0, 0
    return int(fields[0]), int(fields[1])


def status(project_path):
    """Leseansicht: konfigurierte Verknüpfung und Git-Zustand."""
    project = str(project_path)
    config = read_config(os.path.join(project, ".vibe", "project.env"))
    branch = current_branch(project)
    ahead, behind = _push_state(project, branch)
    return {
        "enabled": config["enabled"],
        "repo": config["repo"],
        "label": config["label"],
        "api": config["api"],
        "remotes": remotes(project),
        "branch": branch or "-",
        "ahead": ahead,
        "behind": behind,
        "unpushed": ahead > 0,
    }


def branches(project_path):
    """Lokale Branches mit aktuell-Flag und Abstand zum Upstream.

    Ein einziger ls-remote liefert alle Fern-SHA-Werte; der Abstand wird
    je Branch lokal gerechnet."""
    project = str(project_path)
    head = current_branch(project)
    rc, out = git(project, "for-each-ref", "refs/heads",
                  "--format=%(refname:short)\t%(objectname:short)\t%(contents:subject)")
    rows = []
    if rc != 0:
        return rows
    remote = _remote_shas(project)
    for line in out.splitlines():
        fields = line.split("\t")
        if not fields or not fields[0]:
            continue
        name = fields[0]
        ahead, behind = _push_state(project, name, remote.get(name))
        rows.append({
            "name": name,
            "current": name == head,
            "last": (fields[1] + " " + (fields[2].strip() if len(fields) > 2 else "")).strip(),
            "ahead": ahead,
            "behind": behind,
        })
    return rows


def _remote_shas(project):
    """Fern-SHA-Werte von origin in einem ls-remote (None bei Fernfehler)."""
    if not any(r["name"] == "origin" for r in remotes(project)):
        return {}
    rc, out = git(project, "ls-remote", "--heads", "origin")
    if rc != 0:
        return {}
    mapping = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if not sha or not ref.startswith("refs/heads/"):
            continue
        mapping[ref.strip()[len("refs/heads/"):]] = sha.strip()
    return mapping


def fetch(project_path):
    """Abgleichen der Remotes (read-write-Fetch, kein Merge)."""
    count = len(remotes(project_path))
    if count == 0:
        return False, "Kein Remote konfiguriert: erst verknüpfen (link)"
    rc, out = git(project_path, "fetch", "--all", "--quiet")
    if rc != 0:
        return False, "Abruf fehlgeschlagen: " + (out or "unbekannter Fehler")
    return True, "Abgleich beendet (%d Remote(s))" % count


def pull(project_path):
    """Branch aufholen (--ff-only: keine ungewollten Merge-Commits)."""
    project = str(project_path)
    branch = current_branch(project)
    if not branch:
        return False, "Kein Branch ausgecheckt (detached HEAD): Pull verweigert"
    rc, out = git(project, "pull", "--ff-only")
    if rc != 0:
        return False, "Zusammenführen nicht möglich: " + (out or "unbekannter Fehler")
    return True, "Branch %s aufgeholt (%s)" % (branch, out or "aktuell")


def push(project_path, branch=""):
    """Überträgt einen Branch auf origin; setzt dabei den Upstream."""
    project = str(project_path)
    branch = (branch or current_branch(project)).strip()
    if not branch:
        return False, "Kein Branch ausgecheckt: Push verweigert"
    rc, out = git(project, "push", "-u", "origin", branch)
    if rc != 0:
        return False, "Push fehlgeschlagen: " + (out or "unbekannter Fehler")
    return True, "Branch %s nach origin übertragen" % branch


def check_api(url):
    """Prüft die GitHub-API-Basis: http/https mit Host, ohne Steuerzeichen."""
    text = str(url or "")
    if "\x00" in text or any(c in text for c in ("\n", "\r", "\t")):
        raise ValueError("GitHub-API-Basis enthält unerlaubte Steuerzeichen")
    raw = text.strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("GitHub-API-Basis erwartet eine http(s)-Adresse "
                         "(z. B. https://api.github.com)")
    if not (parsed.netloc or "").strip():
        raise ValueError("GitHub-API-Basis erwartet einen Host")
    return raw


def _http_json(method, url, *, token="", payload=None, timeout=TIMEOUT_HTTP):
    """Ein GitHub-REST-Aufruf; Fehler werden ohne Token verständlich gemeldet."""
    check_api(url)
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "vibe"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        with error:
            raw = error.read() or b""
        detail = ""
        try:
            detail = str(json.loads(raw.decode("utf-8")).get("message") or "")
        except (ValueError, UnicodeDecodeError):
            detail = ""
        raise GitHubError(
            "GitHub-Fehler %d: %s" % (error.code, detail or error.reason or "unbekannt.")
        ) from None
    except (urllib.error.URLError, OSError) as error:
        raise GitHubError("GitHub nicht erreichbar: " + str(getattr(error, "reason", error))) from None
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise GitHubError("GitHub-Antwort ist kein JSON.") from None


def list_issues(repo, label=None, api=None, token=None):
    """Offene GitHub-Issues; Label-Filter (Leerwert = alle Issues)."""
    repo = str(repo or "").strip()
    if not RE_REPO.match(repo):
        raise GitHubError("Repository in owner/name angeben")
    api = (api or OFFICIAL_API).rstrip("/")
    query = {"state": "open", "per_page": "100"}
    if label:
        query["labels"] = str(label)
    url = api + "/repos/" + quote(repo) + "/issues?" + urllib.parse.urlencode(query)
    results = _http_json("GET", url, token=token)
    if not isinstance(results, list):
        raise GitHubError("GitHub-Antwort für Issues ist ungewöhnlich.")
    issues = []
    wanted = str(label or "").strip()
    for item in results:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue  # Merge-Requests erscheinen auch in der Issue-Liste
        names = [str(l.get("name", "")) for l in item.get("labels", []) if isinstance(l, dict)]
        if wanted and wanted not in names:
            continue
        issues.append({
            "number": int(item.get("number") or 0),
            "title": str(item.get("title") or "").strip(),
            "html_url": str(item.get("html_url") or ""),
            "labels": names,
        })
    return [issue for issue in issues if issue["number"]]


def default_base(project_path):
    """Standard-Branch der origin (origin/HEAD); Leerwert unbekannt."""
    rc, out = git(project_path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if rc != 0:
        return ""
    return out.strip().replace("origin/", "", 1) if out.strip().startswith("origin/") else out.strip()


def set_head_default(project_path):
    """Beste Bemühung: origin/HEAD aus dem Fernstand setzen."""
    rc, _ = git(project_path, "remote", "set-head", "origin", "--auto")
    return rc == 0


def create_pull_request(project_path, repo, head, base=None, title=None, body=None,
                        api=None, token=None):
    """Stellt einen Merge-Request über die REST-API; nur mit Token."""
    project = str(project_path)
    head = str(head or "").strip()
    if not head or "^" in head or "~" in head:
        raise GitHubError("Quell-Branch (head) fehlt oder ist ungültig")
    title = str(title or "").strip()
    if not title:
        raise GitHubError("Titel für den Merge-Request fehlt")
    token = token or token_from_env()
    if not token:
        raise GitHubError("Kein GitHub-Zugangstoken in der Umgebung "
                          "(GITHUB_TOKEN oder GH_TOKEN) gesetzt.")
    api = (api or OFFICIAL_API).rstrip("/")
    base = str(base or "").strip()
    if not base:
        base = default_base(project)
        if not base or not _remote_branch_exists(project, base):
            # Ohne verlässliche Basis keine Rateanfrage: Der Nutzer gibt
            # base an oder setzt origin/HEAD (kein unbeteiligter Fernaufruf).
            raise GitHubError("Basis-Branch (base) unbekannt: angeben "
                              "oder origin/HEAD setzen")
    url = api + "/repos/" + quote(repo) + "/pulls"
    payload = {"title": title, "head": head, "base": base, "body": str(body or "")}
    result = _http_json("POST", url, token=token, payload=payload)
    return {"number": result.get("number"),
            "url": result.get("html_url") or "",
            "base": base}


def _remote_branch_exists(project, branch):
    rc, _ = git(project, "rev-parse", "--verify", "--quiet",
                "refs/remotes/origin/" + branch)
    return rc == 0


def quote(value):
    """Sicherer Pfad-Anteil in GitHub-URLs (owner/name bleibt lesbar)."""
    return urllib.parse.quote(str(value), safe="/")



def _sanitize_title(value, number):
    text = " ".join(str(value or "").split())
    return text or "Issue %s" % number


def import_issues_into_tickets(project_path, issues):
    """Hängt fehlende GitHub-Issues idempotent in TICKETS.md ein.

    Format ``- [ ] GH-<Nummer> <Titel>`` bleibt mit dem Ticket-Parser von
    vibe kompatibel (ID ``GH-<Nummer>``, offen). Vorhandene Nummern werden
    nicht doppelt eingetragen; die Datei wird über die gemeinsame
    Storage-Schicht (V-005) atomar geschrieben und konkurrierende Änderungen
    werden als Konflikt gemeldet, statt sie still zu überschreiben.
    """
    project = str(project_path)
    path = os.path.join(project, "TICKETS.md")
    snapshot = vibe_storage.read_snapshot(path)
    if not snapshot.exists:
        raise ValueError("Keine TICKETS.md vorhanden: " + path)
    text = snapshot.text
    existing = {int(match) for match in TICKET_GH_RE.findall(text)}
    newline = "\r\n" if "\r\n" in text else "\n"
    added = []
    block = []
    for issue in issues:
        number = issue.get("number") if isinstance(issue, dict) else None
        try:
            number = int(number)
        except (TypeError, ValueError):
            continue
        if not number or number in existing:
            continue
        entry = "- [ ] GH-%d %s" % (number, _sanitize_title(issue.get("title"), number))
        existing.add(number)
        block.append(entry)
        added.append("GH-%d" % number)
    if not block:
        return 0
    if text and not text.endswith(("\n", "\r")):
        text += newline
    text += newline.join(block) + newline
    try:
        vibe_storage.write_text(path, text, expected=snapshot.digest)
    except vibe_storage.ConcurrentChangeError as error:
        raise ValueError("TICKETS.md wurde zwischenzeitlich geändert — "
                         "Import wiederholen (" + str(error) + ").") from None
    return len(added)

