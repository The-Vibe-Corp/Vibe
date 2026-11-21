#!/usr/bin/env python3
"""vibe_github — optionale GitHub-Verknüpfung je Projekt (AP6, seit AP9
mit Läufer-Automatik).

GitHub-Funktionen sind pro Projekt einzuschalten (``GITHUB_ENABLED`` in
``.vibe/project.env``). Die Knöpfe in der Oberfläche bleiben bewusste
Nutzerentscheidungen; die aktivierte Verknüpfung gilt seit AP9 als stehende
Freigabe für die Läufer-Automatik: Vor jedem Arbeitspaket zieht der Läufer
den Haupt-Branch (``pull_integration``, nur fetch + ff-only) und nach jedem
abgeschlossenen Paket überträgt er den Paket-Branch automatisch nach origin
und stellt einen Merge-Request (``complete_package``). Seit B16 ist dieser
Abschluss eine echte Schranke: Bei divergiertem/veraltetem Integrationsstand
oder einem fehlgeschlagenen Push/Merge-Request wird das Paket blockiert, ohne
lokal zu mergen. Das Zusammenführen des Merge-Requests übernimmt der Läufer
seit AP4 nur bei ``GITHUB_AUTO_MERGE="1"`` (squash über die REST-API); ohne
den Schalter bleibt der Abschluss PR-only und wartet auf den Eigentümer
(``vibe package close``). Git läuft mit
Argumentlisten (ohne Shell),
GitHub-REST über die
Standardbibliothek (urllib); die API-Basis ist konfigurierbar
(``GITHUB_API``, Standard https://api.github.com), damit Prüfungen gegen
einen lokalen Scheindienst laufen können. Der GitHub-Dienst selbst wird nur
bei einer bewussten Aktion kontaktiert (Issues, Merge-Request); die
Git-Status-Ebene bleibt ohne aktivierte Verknüpfung und in der
Projektansicht (``remote=False``) grundsätzlich fernfrei und liest
Ahead/Behind aus der lokalen ``origin/<branch>``-Referenz. Nur bei
aktivierter Verknüpfung im Fern-Modus liest sie die aktuelle Fern-Referenz
via ls-remote und zieht unbekannte Fern-Objekte nach, ohne etwas
zusammenzuführen.

Der GitHub-Zugangstoken (B7): Standardmäßig kommt er aus der Umgebung
(``GITHUB_TOKEN`` oder ``GH_TOKEN``). Zusätzlich kann er in der Oberfläche
hinterlegt werden. Seit AP9 gilt der Token **je Projekt**: Er liegt
verschlüsselt unter ``<VIBE_STATE>/github-tokens/<Projektkennung>.json``
(Masterschlüssel ``<VIBE_STATE>/github-token.key``, beides 0600 best
effort) und der Zustandsordner bleibt damit außerhalb jedes
Git-Repositorys. Die Verschlüsselung nutzt ausschließlich die
Standardbibliothek: scrypt (salt-abgeleiteter Schlüssel), ein
HMAC-SHA256-Strom als Chiffre und Encrypt-then-MAC (HMAC über salt,
nonce und Chiffrat). Ein manipulierter oder defekter Eintrag liefert beim
Lesen den Leerwert statt einer Ausnahme. Grenze, die ehrlich benannt
wird: Der Masterschlüssel liegt im selben Zustandsordner; die
Verschlüsselung schützt vor beiläufigem Lesen (Backups, Screenshots,
Git-Zuführungen), nicht vor einem Angreifer mit vollem Schreibzugriff auf
den Datenträger. Der alte globale Token (B7) bleibt als Rückfall
lesbar; beim Schreiben gewinnen Projekt-Tokens.

Der Token taucht in keinem Log, keiner Konfiguration im Projekt und
keiner Fehlermeldung auf. Gespeicherte Zugangsdaten werden ausdrücklich
nur GitHub-Endpunkten übergeben: der offiziellen REST-API
(api.github.com) und Git-URLs mit dem Host github.com. Gegenüber
konfigurierbaren anderen Hosts wird niemals der hinterlegte Token
versendet; der Umgebungstoken behält sein bisheriges REST-Verhalten.
"""
import contextlib
import hashlib
import hmac
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

if os.path.dirname(os.path.realpath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
# Bewusste Ausnahme (wrong-import-position): Der sys.path-Zusatz für die
# Skriptausführung liegt bewusst vor dem Import; das Modul wird auch einzeln
# mit unvollständiger Installation aufgerufen (gemeinsame Storage-Schicht, V-005).
import vibe_storage  # pylint: disable=wrong-import-position

OFFICIAL_API = "https://api.github.com"
DEFAULT_LABEL = "vibe"
TOKEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN")
TRUE_VALUES = ("1", "true", "yes", "on")
TIMEOUT_GIT = 120
TIMEOUT_REMOTE_READ = 10
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


TOKEN_FILE = "github-token"
CREDENTIAL_ENV_NAME = "VIBE_GITHUB_CREDENTIAL"
# URL-gültige Konfiguration: Die Zugangsdaten gelten ausschließlich für
# https://github.com von Git-Aufrufen, nie für andere Hosts.
CREDENTIAL_CONFIG_KEY = "credential.https://github.com.helper"
CREDENTIAL_HELPER_VALUE = ("!f() { printf 'username=x-access-token\\n'; "
                           "printf 'password=%s\\n' "
                           "\"$VIBE_GITHUB_CREDENTIAL\"; }; f")

# AP9: Projektbezogene, verschlüsselte Token-Ablage im Zustandsordner.
TOKEN_DIR_NAME = "github-tokens"
KEY_FILE = "github-token.key"
ENC_VERSION = 1
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
MAC_INFO = b"vibe-github-token-mac"

# Gültige Branch-Namen (Git-Refname-Teilmenge): kein führendes "-", keine
# Punkte-Sequenz, kein ".lock"-Ende, keine Leer- oder Steuerzeichen.
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def branch_name(value):
    """Prüft und normalisiert einen Branch-Namen; ungültige Namen werfen."""
    text = str(value or "").strip()
    if (not text or not BRANCH_RE.match(text) or ".." in text
            or text.endswith(".lock") or text.endswith("/")
            or text.endswith(".")):
        raise ValueError("Ungültiger Branch-Name: " + (text[:60] or "(leer)"))
    return text


def _project_digest(project_path):
    """Kollisionsfreie Dateikennung je Projekt aus dem echten Pfad."""
    return hashlib.sha256(
        os.path.realpath(str(project_path)).encode("utf-8", "surrogateescape")
    ).hexdigest()[:16]


def _project_token_path(project_path, environ=None):
    """Pfad des verschlüsselten Token-Eintrags des Projekts."""
    name = _project_digest(project_path) + ".json"
    return os.path.join(token_state_dir(environ), TOKEN_DIR_NAME, name)


def _master_key(environ=None):
    """Liest oder erzeugt den Masterschlüssel (32 Bytes, 0600 best effort).

    Ein einmal erzeugter Schlüssel wird nie gedreht, sonst wären frühere
    Einträge unwiderruflich verloren. Eine Datei falscher Länge gilt als
    beschädigt: Lesen liefert dann den Leerwert, Schreiben wird mit einer
    verständlichen Meldung abgelehnt."""
    path = os.path.join(token_state_dir(environ), KEY_FILE)
    try:
        with open(path, "rb") as handle:
            key = handle.read()
        if len(key) == 32:
            return key
        raise ValueError("Masterschlüsseldatei ist beschädigt (falsche Länge): "
                         + path + " — Datei entfernen und Token neu hinterlegen")
    except FileNotFoundError:
        pass
    key = os.urandom(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        os.chmod(os.path.dirname(path), 0o700)
    except OSError:
        pass  # nicht überall wirksame Rechte (FUSE/NTFS) - kein Fehler
    try:
        vibe_storage.write_bytes(path, key, mode=0o600)
    except OSError as error:
        raise ValueError("Masterschlüssel konnte nicht gespeichert werden: "
                         + str(error)) from None
    return key


def _derive_key(master, salt):
    """Schlüsselerzeugung: scrypt über den Masterschlüssel und das Salz."""
    return hashlib.scrypt(master, salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                          p=SCRYPT_P, dklen=32)


def _keystream(key, nonce, length):
    """HMAC-SHA256-Strom über (nonce, Zähler) — die Chiffre dieses Moduls."""
    blocks = bytearray()
    counter = 0
    while len(blocks) < length:
        blocks.extend(hmac.new(key, nonce + struct.pack(">Q", counter),
                               hashlib.sha256).digest())
        counter += 1
    return bytes(blocks[:length])


def _mac_key(key):
    return hmac.new(key, MAC_INFO, hashlib.sha256).digest()


def _mac(key, salt, nonce, ciphertext):
    return hmac.new(_mac_key(key), salt + nonce + ciphertext,
                    hashlib.sha256).hexdigest()


def _encrypt_token(master, plaintext):
    """Verschlüsselt den Token (Stromchiffre + Encrypt-then-MAC)."""
    salt = os.urandom(16)
    nonce = os.urandom(16)
    key = _derive_key(master, salt)
    data = plaintext.encode("utf-8")
    ciphertext = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce,
                                                             len(data))))
    return {
        "version": ENC_VERSION,
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "chiffrat": ciphertext.hex(),
        "mac": _mac(key, salt, nonce, ciphertext),
    }


def _decrypt_token(master, payload):
    """Entschlüsselt nach MAC-Prüfung; jede Abweichung liefert None."""
    try:
        if not isinstance(payload, dict):
            return None
        salt = bytes.fromhex(str(payload["salt"]))
        nonce = bytes.fromhex(str(payload["nonce"]))
        ciphertext = bytes.fromhex(str(payload["chiffrat"]))
        stored_mac = str(payload["mac"])
    except (KeyError, TypeError, ValueError):
        return None
    key = _derive_key(master, salt)
    if not hmac.compare_digest(_mac(key, salt, nonce, ciphertext), stored_mac):
        return None
    data = bytes(a ^ b for a, b in
                 zip(ciphertext, _keystream(key, nonce, len(ciphertext))))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def save_project_token(project_path, token):
    """Hinterlegt einen GitHub-Token verschlüsselt für genau dieses Projekt.

    Ungültige Eingaben werden abgelehnt, bevor irgendetwas geschrieben
    wird; der Inhalt erscheint in keiner Meldung. Die Ablage liegt im
    Zustandsordner außerhalb jedes Git-Repositorys; Datei- und Ordnerrechte
    sind best effort (FUSE/NTFS, siehe SPEC)."""
    value = str(token or "")
    if "\x00" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Token enthält unerlaubte Steuerzeichen")
    value = value.strip()
    if not value:
        raise ValueError("Kein GitHub-Token angegeben: In der Karte einfügen")
    master = _master_key()
    path = _project_token_path(project_path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    payload = json.dumps(_encrypt_token(master, value), ensure_ascii=False,
                         indent=1) + "\n"
    try:
        vibe_storage.write_text(path, payload, mode=0o600)
    except OSError as error:
        raise ValueError("Token konnte nicht gespeichert werden: "
                         + str(error)) from None


def read_project_token(project_path, environ=None):
    """Verschlüsselten Projekt-Token lesen; fehlend/defekt/manipuliert → ""."""
    path = _project_token_path(project_path, environ)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.loads(handle.read())
    except (OSError, ValueError):
        return ""
    try:
        master = _master_key(environ)
    except (ValueError, OSError):
        return ""
    return _decrypt_token(master, payload) or ""


def delete_project_token(project_path, environ=None):
    """Entfernt den Projekt-Token; eine fehlende Datei bleibt kein Fehler."""
    try:
        os.unlink(_project_token_path(project_path, environ))
    except OSError:
        pass


def token_state_dir(environ=None):
    """Zustandsordner für den Token: außerhalb jedes Git-Repositories."""
    env = os.environ if environ is None else environ
    state = str(env.get("VIBE_STATE") or "").strip()
    if state:
        return os.path.abspath(state)
    try:  # CLI-Kontext ohne VIBE_STATE: denselben Zustandsordner auflösen
        # Bewusste Ausnahme (import-outside-toplevel): spät importiert, scheitert
        # die Auflösung, bleibt der Token-Umgang mit dem Ausweichpfad unten.
        import vibe_paths  # pylint: disable=import-outside-toplevel
        return os.path.abspath(vibe_paths.resolve().state)
    # Bewusste Ausnahme (broad-exception-caught): bestandssicherer Ausweichpfad,
    # auch unter isolierten Tests nie stoppend.
    except Exception:  # noqa: BLE001; pylint: disable=broad-exception-caught
        return os.path.join(os.path.expanduser("~"), ".local", "state", "vibe")


def token_state_path(environ=None):
    """Pfad der Token-Datei im Zustandsordner (je Aufruf neu aufgelöst)."""
    return os.path.join(token_state_dir(environ), TOKEN_FILE)


def save_token(token):
    """Hinterlegt einen GitHub-Token im Zustandsordner (0600, best effort).

    Ungültige Eingaben werden abgelehnt, bevor irgendetwas geschrieben
    wird; der Inhalt erscheint in keiner Meldung. Auf Dateisystemen ohne
    wirksame Unix-Rechte (FUSE/NTFS, siehe SPEC) bleibt der Modus best
    effort und die Funktion gibt kein falsches Sicherheitsversprechen."""
    value = str(token or "").strip()
    if not value:
        raise ValueError("Kein GitHub-Token angegeben: In der Karte einfügen")
    if "\x00" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Token enthält unerlaubte Steuerzeichen")
    path = token_state_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass  # nicht überall wirksame Rechte (FUSE/NTFS) - kein Fehler
    handle, tmp = tempfile.mkstemp(prefix=".github-token-", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(value)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except OSError:
        vibe_storage.discard_quiet(tmp)
        raise


def read_stored_token(environ=None):
    """Gespeicherten Token lesen (Leerwert, wenn nicht existiert/lesbar)."""
    try:
        with open(token_state_path(environ), encoding="utf-8") as handle:
            return handle.read().strip()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError,
            PermissionError, OSError):
        return ""


def delete_token(environ=None):
    """Entfernt die gespeicherte Token-Datei; eine fehlende Datei bleibt kein Fehler."""
    try:
        os.unlink(token_state_path(environ))
    except OSError:
        pass


def token_status(project_path=None, environ=None, project_token=None):
    """Token-Kennung ohne Inhalt: {set, source}.

    Reihenfolge: Umgebung, dann verschlüsselter Projekt-Token, dann der
    legacy global gespeicherte Token (B7). Mit ``project_token`` (AP15)
    wird ein bereits gelöstes Credential des Durchgangs geprüft, statt
    den Projekt-Token erneut zu entschlüsseln. Entspricht es dem legacy
    globalen Token, stammt das Credential von dort (der Projekt-Token
    hätte in der Kette Vorrang) und wird als „gespeichert" gemeldet."""
    if token_from_env():
        return {"set": True, "source": "umgebung"}
    stored_global = read_stored_token(environ)
    if project_path is not None:
        if project_token is None:
            project_token = read_project_token(project_path, environ)
        if project_token and project_token != stored_global:
            return {"set": True, "source": "projekt"}
    if stored_global:
        return {"set": True, "source": "gespeichert"}
    return {"set": False, "source": ""}


def credential_for_git(project_path, environ=None):
    """Credential-Kette für Git-Aufrufe: Umgebung > verschlüsselter
    Projekt-Token > legacy globaler Token (dieselbe Reihenfolge wie in
    ``git()``).

    Je Durchgang (z. B. eine Dashboard-Anfrage) einmal aufrufen und das
    Ergebnis an alle ``git()``-Aufrufe des Durchgangs weiterreichen
    (AP15); bewusst kein Cache über Anfragen hinweg — jeder Durchgang
    liest und entschlüsselt die Ablage erneut."""
    return (token_from_env() or read_project_token(project_path, environ)
            or read_stored_token(environ))


# AP15: Durchgangskontext für das einmal gelöste Credential. Kein Cache:
# Er existiert ausschließlich innerhalb des ``_credential_passdown``-
# Kontexts eines Durchgangs (Zustand je Thread, damit parallele
# Dashboard-Anfragen sich nicht vermischen) und wird beim Verlassen auf
# den vorherigen Stand zurückgesetzt; es gibt keine Wiederverwendung über
# Anfragen hinweg. Über einen Kontext statt über ein Schlüsselwort an
# jedem ``git()``-Aufruf wird weitergereicht, damit bestehende Läufer,
# die ``git`` durch einen Stub mit enger Signatur ersetzen (Muster
# test_b8_project_open_without_remote), unverändert funktionieren.
_CREDENTIAL_PASSDOWN = threading.local()


@contextlib.contextmanager
def _credential_passdown(credential):
    """Stellt das Credential des Durchgangs für alle ``git()``-Aufrufe
    bereit und räumt beim Verlassen wieder auf."""
    previous = getattr(_CREDENTIAL_PASSDOWN, "credential", None)
    _CREDENTIAL_PASSDOWN.credential = credential
    try:
        yield
    finally:
        _CREDENTIAL_PASSDOWN.credential = previous


def token_for_rest(api=None, project_path=None):
    """Token für die REST-Ebene: Umgebung gewinnt; hinterlegte Token gehen
    ausdrücklich nur an die offizielle GitHub-API (github.com). Der
    Projekt-Token wird vor dem legacy globalen Token bevorzugt."""
    token = token_from_env()
    if token:
        return token
    api_value = str(api or "").strip().rstrip("/")
    if not api_value or api_value == OFFICIAL_API:
        if project_path is not None:
            token = read_project_token(project_path)
            if token:
                return token
        return read_stored_token()
    return ""


def read_config(env_path):
    """GitHub-Konfiguration des Projekts; ohne Einträge bleibt GitHub aus."""
    values = _read_env_file(env_path)
    enabled = str(values.get("GITHUB_ENABLED", "")).strip().lower() in TRUE_VALUES
    label = str(values.get("GITHUB_LABEL", "")).strip() or DEFAULT_LABEL
    api = str(values.get("GITHUB_API", "")).strip() or OFFICIAL_API
    # AP4: Binärer Schalter — nur exakt "1" aktiviert den Auto-Merge; alles
    # andere (leer, "true", "on", …) bleibt aus (PR-only ist der Standard).
    auto_merge = str(values.get("GITHUB_AUTO_MERGE", "")).strip() == "1"
    return {
        "enabled": enabled,
        "repo": str(values.get("GITHUB_REPO", "")).strip(),
        "label": label,
        "api": api,
        # AP9: Basis-Branch für Merge-Requests (Leerwert = Standard der origin).
        "base": str(values.get("GITHUB_BASE", "")).strip(),
        "auto_merge": auto_merge,
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


def git(project_path, *args, timeout=TIMEOUT_GIT, token=None):
    """Führt Git mit Argumentlisten aus (ohne Shell, mit Zeitlimit).

    Ohne Terminal-Prompt: Eine nicht erreichbare oder nach Zugangsdaten
    fragende Gegenstelle darf das Dashboard nicht anhalten. Die Werte
    werden mit ``setdefault`` gesetzt: Betreiber dürfen die Voreinstellung
    (``GIT_TERMINAL_PROMPT=0``, ``GCM_INTERACTIVE=never``) in ihrer
    Serverumgebung bewusst übersteuern (z. B. Askpass-Setup); ausgeliefert
    wird ohne Übersteuerung stets die promptfreie Voreinstellung.

    Mit verfügbarem GitHub-Token (B7, Umgebung oder je Projekt hinterlegt)
    erhält der Lauf eine URL-gültige Credential-Konfiguration für
    https://github.com. Die Konfiguration (ohne Geheimnis, nur ein
    Verweis auf die Umgebungsvariable) liegt als ``-c``-Argument in argv —
    vor dem festen ``core.fsmonitor=false``, damit fachliche Auswertungen
    den Unterbefehl hinter dem festen Präfix lesen können; der Tokeninhalt
    bleibt ausschließlich in der Prozessumgebung
    (``VIBE_GITHUB_CREDENTIAL``) und niemals in argv, Logs oder der
    Konfiguration. Mit ``token`` (AP15) wird ein bereits gelöstes
    Credential des Durchgangs ungeprüft verwendet; ``None`` löst die
    Kette selbst — zunächst über einen aktiven Durchgangskontext
    (``_credential_passdown``), sonst über ``credential_for_git``."""
    if token is None:
        token = getattr(_CREDENTIAL_PASSDOWN, "credential", None)
    if token is None:
        token = credential_for_git(project_path)
    argv = ["git", "--no-pager",
            *_credential_args(token),
            "-c", "core.fsmonitor=false",
            *[str(a) for a in args]]
    if not all(isinstance(a, str) for a in argv):
        raise ValueError("Argumentliste erwartet: nur Zeichenketten")
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GCM_INTERACTIVE", "never")
    # AP9: Credential-Kette Umgebung > Projekt-Token > legacy globaler Token.
    _apply_credential_env(env, token)
    try:
        result = subprocess.run(argv, cwd=str(project_path), capture_output=True,
                                text=True, timeout=timeout, env=env, check=False)
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return 127, "Programm nicht gefunden: git"
    except subprocess.TimeoutExpired:
        return 124, f"Zeitüberschreitung nach {timeout:g} s: {' '.join(argv)}"
    except OSError as error:
        return 126, f"Programm nicht ausführbar: git: {error}"


def _credential_args(token):
    """URL-gültige Credential-Konfiguration als -c-Argumente (ohne Geheimnis).

    Der Helper selbst enthält nur einen Verweis auf die Umgebungsvariable;
    der Tokeninhalt kommt über ``_apply_credential_env`` in die
    Prozessumgebung und damit nie in argv."""
    if not token:
        return []
    return ["-c", CREDENTIAL_CONFIG_KEY + "=" + CREDENTIAL_HELPER_VALUE]


def _apply_credential_env(env, token):
    """Injiziert den Tokeninhalt über die Prozessumgebung (keine argv).

    Die Credential-Konfiguration selbst liegt als ``-c``-Argument in argv
    (``_credential_args``); hier kommt nur der Tokeninhalt über
    ``VIBE_GITHUB_CREDENTIAL`` in die Prozessumgebung."""
    if not token:
        return env  # Kein Token: Git verhält sich unverändert (kein Prompt)
    env[CREDENTIAL_ENV_NAME] = token
    return env


# Fehlerbilder der Authentifizierung (B7): von diesen Ausgaben wird der
# Nutzer klar zur Token-Hinterlegung geführt, statt einer rohen Meldung.
_TOKEN_GUIDANCE = (
    "Keine gültigen GitHub-Zugangsdaten: In der Karte „Git & GitHub“ einen "
    "Token hinterlegen (Token speichern) oder GITHUB_TOKEN setzen. GitHub "
    "empfiehlt dafür einen Personal Access Token.")
_AUTH_PATTERNS = ("could not read Username", "terminal prompts disabled",
                  "Authentication failed", "cannot exec", "askpass")


def _auth_guidance(message):
    """Ergänzt bei Auth-Fehlern eine verständliche Handlungsanweisung."""
    text = str(message or "")
    if "Zugangsdaten" in text:
        return text
    if any(pattern in text for pattern in _AUTH_PATTERNS):
        return text + "\n" + _TOKEN_GUIDANCE
    return text


def current_branch(project_path):
    """Aktuell ausgecheckter Branch; ohne Branch bleibt der Leerwert."""
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


def mask_embedded_credentials(text):
    """Maskiert Zugangsdaten in allen .git-URLs eines Freitexts.

    Git-Fehlerausgaben wiederholen die Remote-Adresse, einschließlich
    eingebetteter Zugangsdaten (``https://user:token@host/...``). Meldungen
    aus Git-Ausgaben dürfen diese Daten nicht weitergeben (SPEC: keine
    Geheimnisse in Fehlermeldungen oder Logs); ``mask_url`` deckt nur eine
    einzelne Adresse ab, hier geht es um mehrzeilige Ausgaben.
    """
    return re.sub(
        r"([a-zA-Z][a-zA-Z0-9+.-]*)://[^\s/@<>]+@",
        r"\1://***@",
        str(text or ""),
    )


def _local_push_state(project_path, branch):
    """Ahead/Behind gegen die lokale Fern-Referenz, ohne Netzwerk."""
    rc, _ = git(project_path, "rev-parse", "--verify", "--quiet",
                "origin/" + branch)
    if rc != 0:
        return 0, 0
    return _revision_compare_local(project_path, branch, "origin/" + branch)


def _push_state(project_path, branch, remote_sha=None, *, remote=True,
                has_origin=None):
    """Ahead/Behind des Branches gegen origin.

    Mit ``remote=False`` wird ausschließlich die lokale
    ``origin/<branch>``-Referenz gelesen; es findet keine Netzwerkabfrage
    statt. Das Dashboard nutzt diesen Modus, damit ein nicht erreichbares
    Remote das Öffnen eines Projekts nicht blockiert.

    Mit ``remote=True`` wird die aktuelle Fern-Referenz via ls-remote
    gelesen. Es wird nichts ins lokale Fern-Referenzlayout geschrieben und
    nichts zusammengeführt. Der bewusste Abgleich zieht bei unbekanntem
    Fern-Objekt nur dieses Objekt nach (kein Merge, keine verschobenen
    Fern-Referenzen). Ohne Remote-Eintrag oder bei Fehler bleibt der Stand
    bei 0/0 (keine veralteten Referenzen). ``remote_sha`` darf eine bereits
    ermittelte Fern-SHA sein, damit Branchlisten mit einem einzigen
    ls-remote auskommen. ``has_origin`` (AP15) ist das bereits ermittelte
    Ergebnis der Remote-Prüfung des Durchgangs; ``None`` prüft wie bisher
    selbst. Das Credential kommt über den Durchgangskontext
    (``_credential_passdown``), nicht über Aufrufargumente."""
    if not branch:
        return 0, 0
    if has_origin is None:
        has_origin = any(r["name"] == "origin" for r in remotes(project_path))
    if not has_origin:
        return 0, 0
    if not remote:
        return _local_push_state(project_path, branch)
    if remote_sha is None:
        rc, out = git(project_path, "ls-remote", "origin",
                      "refs/heads/" + branch, timeout=TIMEOUT_REMOTE_READ)
        if rc != 0:
            return _local_push_state(project_path, branch)
        remote_sha = _lsremote_sha(out, branch)
        if not remote_sha:
            return 0, 0
    if not _object_present(project_path, remote_sha):
        # Fern-Objekt lokal unbekannt: gezielt das neue Objekt nachziehen,
        # damit rev-list gegen die rohe SHA rechnen kann. Das zieht keine
        # Merge-Kopien und verschiebt keine Fern-Referenzen; scheitert der
        # Nachzug, bleibt der Stand bei 0/0 (keine veralteten Referenzen).
        git(project_path, "fetch", "--quiet", "origin", remote_sha,
            timeout=TIMEOUT_REMOTE_READ)
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


def status(project_path, *, remote=True, token=None):
    """Leseansicht: konfigurierte Verknüpfung und Git-Zustand.

    ``remote=False`` liest Ahead/Behind nur aus lokalen Referenzen und
    vermeidet jede Netzwerkabfrage. Ohne aktivierte GitHub-Verknüpfung
    wird ebenfalls nie eine Fernabfrage ausgelöst. Mit ``token`` (AP15)
    wird das bereits gelöste Credential des Durchgangs über den
    Durchgangskontext an alle ``git()``-Aufrufe weitergereicht; ohne
    ``token`` wird es hier einmal gelöst. ``remotes()`` wird einmal
    geprüft und für Ansichtsfeld und Fernprüfung wiederverwendet.
    """
    project = str(project_path)
    config = read_config(os.path.join(project, ".vibe", "project.env"))
    credential = credential_for_git(project) if token is None else token
    with _credential_passdown(credential):
        remote_rows = remotes(project)
        branch = current_branch(project)
        ahead, behind = _push_state(
            project, branch, remote=remote and config["enabled"],
            has_origin=any(r["name"] == "origin" for r in remote_rows))
        auth = token_status(project, project_token=credential)
    return {
        "enabled": config["enabled"],
        "repo": config["repo"],
        "label": config["label"],
        "api": config["api"],
        "base": config["base"],
        "auto_merge": config["auto_merge"],
        "remotes": remote_rows,
        "branch": branch or "-",
        "ahead": ahead,
        "behind": behind,
        "unpushed": ahead > 0,
        "auth": auth,
    }


def _branch_row(project, name, fields, head, remote_sha, *, use_remote,
                has_origin):
    """Eine Branchzeile: aktuell-Flag und Abstand zum Upstream."""
    ahead, behind = _push_state(project, name, remote_sha, remote=use_remote,
                                has_origin=has_origin)
    return {
        "name": name,
        "current": name == head,
        "last": (fields[1] + " "
                 + (fields[2].strip() if len(fields) > 2 else "")).strip(),
        "ahead": ahead,
        "behind": behind,
    }


def branches(project_path, *, remote=True, token=None):
    """Lokale Branches mit aktuell-Flag und Abstand zum Upstream.

    Ein einziger ls-remote liefert alle Fern-SHA-Werte; der Abstand wird
    je Branch lokal gerechnet. Mit ``remote=False`` oder ohne aktivierte
    GitHub-Verknüpfung bleiben lokale Referenzen die Grundlage und es
    findet keine Netzwerkabfrage statt. Mit ``token`` (AP15) wird das
    bereits gelöste Credential des Durchgangs über den Durchgangskontext
    an alle ``git()``-Aufrufe weitergereicht; ohne ``token`` wird es hier
    einmal gelöst. ``remotes()`` wird einmal geprüft und für alle
    Branches als ``has_origin`` wiederverwendet."""
    project = str(project_path)
    config = read_config(os.path.join(project, ".vibe", "project.env"))
    use_remote = remote and config["enabled"]
    credential = credential_for_git(project) if token is None else token
    with _credential_passdown(credential):
        has_origin = any(r["name"] == "origin" for r in remotes(project))
        head = current_branch(project)
        rc, out = git(
            project, "for-each-ref", "refs/heads",
            "--format=%(refname:short)\t%(objectname:short)"
            "\t%(contents:subject)")
        rows = []
        if rc != 0:
            return rows
        remote_shas = _remote_shas(project) if use_remote else {}
        for line in out.splitlines():
            fields = line.split("\t")
            if not fields or not fields[0]:
                continue
            rows.append(_branch_row(project, fields[0], fields, head,
                                    remote_shas.get(fields[0]),
                                    use_remote=use_remote,
                                    has_origin=has_origin))
        return rows


def _remote_shas(project):
    """Fern-SHA-Werte von origin in einem ls-remote (None bei Fernfehler)."""
    if not any(r["name"] == "origin" for r in remotes(project)):
        return {}
    rc, out = git(project, "ls-remote", "--heads", "origin",
                  timeout=TIMEOUT_REMOTE_READ)
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
    rc, out = git(project_path, "fetch", "--all", "--quiet", "--prune")
    if rc != 0:
        return False, _auth_guidance("Abruf fehlgeschlagen: " + (out or "unbekannter Fehler"))
    return True, f"Abgleich beendet ({count} Remote(s))"


def pull(project_path):
    """Branch aufholen (--ff-only: keine ungewollten Merge-Commits)."""
    project = str(project_path)
    branch = current_branch(project)
    if not branch:
        return False, "Kein Branch ausgecheckt (detached HEAD): Pull verweigert"
    rc, out = git(project, "pull", "--ff-only")
    if rc != 0:
        return False, _auth_guidance("Zusammenführen nicht möglich: " + (out or "unbekannter Fehler"))
    return True, f"Branch {branch} aufgeholt ({out or 'aktuell'})"


def _worktrees_by_branch(project_path):
    """Branch -> Arbeitskopie-Pfade aus ``git worktree list --porcelain``.

    Liefert ein Mapping auf Pfadlisten; bei Git-Fehlern bleibt es leer
    (best effort, keine Ausnahme)."""
    mapping = {}
    rc, out = git(project_path, "worktree", "list", "--porcelain")
    if rc != 0:
        return mapping
    path = ""
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
        elif line.startswith("branch ") and path:
            branch = line[len("branch "):].strip()
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/"):]
            mapping.setdefault(branch, []).append(path)
    return mapping


def checkout_branch(project_path, branch):
    """Checkt einen Branch aus; erzeugt ihn bei Bedarf aus origin/<branch>.

    Schutzregeln: Ein ungültiger Name wird vor jedem Git-Aufruf abgelehnt;
    bei uncommitteten Änderungen wird der Wechsel verweigert, damit keine
    fremden Arbeiten gemischt werden; ein bereits ausgecheckter Branch ist
    Erfolg ohne Aktion; ein Branch, der in einer anderen Arbeitskopie
    ausgecheckt ist, wird verweigert (T-G4). Git läuft mit Argumentlisten
    (ohne Shell)."""
    project = str(project_path)
    branch = branch_name(branch)
    if current_branch(project) == branch:
        return True, f"Branch {branch} ist bereits ausgecheckt"
    rc, out = git(project, "status", "--porcelain", "--untracked-files=no")
    if rc != 0:
        return False, mask_embedded_credentials("Git-Status fehlgeschlagen: "
                                                + (out or "unbekannter Fehler"))
    if out.strip():
        # Ungetrackte Dateien blockieren bewusst nicht: Sie gehören dem
        # Arbeitsbaum und wandern bei einem Wechsel nicht mit.
        raise ValueError("Es gibt uncommittete Änderungen: Erst committen "
                         "oder verwerfen, dann den Branch wechseln.")
    held = [
        path for path in _worktrees_by_branch(project).get(branch, [])
        if os.path.realpath(path) != os.path.realpath(project)
    ]
    if held:
        raise ValueError("Branch ist in einer Arbeitskopie ausgecheckt: "
                         + held[0])
    rc, _ = git(project, "rev-parse", "--verify", "--quiet",
                "refs/heads/" + branch)
    if rc == 0:
        rc, out = git(project, "checkout", branch)
    else:
        rc_remote, _ = git(project, "rev-parse", "--verify", "--quiet",
                           "refs/remotes/origin/" + branch)
        if rc_remote != 0:
            raise ValueError("Branch nicht gefunden (lokal oder als "
                             "origin/<branch>): " + branch)
        rc, out = git(project, "checkout", "-b", branch, "origin/" + branch)
    if rc != 0:
        return False, _auth_guidance(mask_embedded_credentials(
            out or "unbekannter Fehler"))
    return True, f"Branch {branch} ausgecheckt"


def push(project_path, branch="", target=""):
    """Überträgt einen Branch auf origin; setzt dabei den Upstream.

    Mit ``target`` wird der Refspec ``<branch>:<target>`` verwendet: Der
    lokale Branch landet unter dem gewählten Namen auf origin, ohne dass
    ein gleichnamiger Fern-Branch berührt wird."""
    project = str(project_path)
    branch = (branch or current_branch(project)).strip()
    if not branch:
        return False, "Kein Branch ausgecheckt: Push verweigert"
    branch = branch_name(branch)
    refspec = branch
    if str(target or "").strip():
        refspec = branch + ":" + branch_name(target)
    rc, out = git(project, "push", "-u", "origin", refspec)
    if rc != 0:
        return False, _auth_guidance(mask_embedded_credentials(
            out or "unbekannter Fehler"))
    message = f"Branch {branch} nach origin übertragen"
    if refspec != branch:
        message = f"Branch {branch} nach origin/{branch_name(target)} übertragen"
    return True, message


def connection(project_path):
    """Verbindungsprüfung für die Oberfläche (AP9): Fern- und REST-Zustand.

    Die Fernseite wird mit ls-remote gelesen (kein Merge, kurzes Zeitlimit).
    Die REST-Prüfung läuft nur, wenn irgendein Token verfügbar ist; der
    gespeicherte Token geht dabei nur an die offizielle API, gegenüber
    anderen API-Basen wird ohne Anmeldung geprüft und das ehrlich gemeldet.
    Diese Funktion wirft niemals; alle Befunde stehen im Ergebnis."""
    project = str(project_path)
    config = read_config(os.path.join(project, ".vibe", "project.env"))
    view = {"remote": None, "api": None, "ok": False, "message": ""}
    parts = []
    if not any(r["name"] == "origin" for r in remotes(project)):
        view["remote"] = False
        parts.append("Kein Remote origin konfiguriert")
    else:
        rc, out = git(project, "ls-remote", "--heads", "origin",
                      timeout=TIMEOUT_REMOTE_READ)
        view["remote"] = rc == 0
        parts.append("Remote origin: " + ("erreichbar" if rc == 0 else
                     "nicht erreichbar (" + mask_embedded_credentials(
                         (out or "unbekannter Fehler")[:200]) + ")"))
    if config["enabled"] and config["repo"]:
        env_token = token_from_env()
        stored = read_project_token(project) or read_stored_token()
        if not (env_token or stored):
            view["api"] = None
            parts.append("GitHub-REST: nicht geprüft (kein Token hinterlegt — "
                         "Token speichern oder GITHUB_TOKEN setzen)")
        else:
            api_value = (config["api"] or OFFICIAL_API).rstrip("/")
            official = not str(config["api"] or "").strip() \
                or api_value == OFFICIAL_API.rstrip("/")
            # Gespeicherte Token gehören nur zur offiziellen API; der
            # Umgebungstoken behält sein bisheriges REST-Verhalten.
            token = env_token or (stored if official else "")
            note = "" if (token or not stored) else \
                " (ohne Anmeldung: der gespeicherte Token gilt nur für api.github.com)"
            try:
                _http_json("GET", api_value + "/repos/" + quote(config["repo"]),
                           token=token)
                view["api"] = True
                parts.append("GitHub-REST: OK" + note)
            except GitHubError as error:
                view["api"] = False
                parts.append("GitHub-REST: " + str(error) + note)
    view["ok"] = view["remote"] is True and view["api"] is not False
    view["message"] = "; ".join(parts)
    return view


def pull_integration(project_path):
    """Aktualisiert den Integrationsbranch vor einem neuen Arbeitspaket.

    Ohne aktivierte GitHub-Verknüpfung oder ohne origin wird bewusst
    übersprungen (kein Verhalten ohne ausdrückliche Konfiguration). Sonst
    fetch von origin und ff-only Zusammenführung mit ``origin/<branch>``:
    Der Refspec ist ausdrücklich, damit keine Upstream-Konfiguration
    Voraussetzung ist (verlinkte, nicht geklonte Projekte haben keine).
    Es entstehen keine Merge-Commits. Liefert ``(ausgeführt, ok, Meldung)``
    und wirft niemals."""
    project = str(project_path)
    try:
        config = read_config(os.path.join(project, ".vibe", "project.env"))
        if not config["enabled"]:
            return False, True, ("GitHub ist für dieses Projekt nicht aktiv: "
                                 "Aktualisierung übersprungen")
        if not any(r["name"] == "origin" for r in remotes(project)):
            return False, True, ("Kein Remote origin: Aktualisierung "
                                 "übersprungen")
        branch = current_branch(project)
        if not branch:
            return True, False, ("Kein Branch ausgecheckt (detached HEAD): "
                                 "Aktualisierung verweigert")
        rc, out = git(project, "fetch", "--quiet", "--prune", "origin")
        if rc != 0:
            return True, False, _auth_guidance(mask_embedded_credentials(
                "Abruf fehlgeschlagen: " + (out or "unbekannter Fehler")))
        rc, out = git(project, "merge", "--ff-only", "origin/" + branch)
        if rc != 0:
            return True, False, _auth_guidance(mask_embedded_credentials(
                "Zusammenführen nicht möglich: "
                + (out or "unbekannter Fehler")))
        return True, True, f"Branch {branch} aufgeholt ({out or 'aktuell'})"
    except (OSError, ValueError) as error:
        return True, False, "Aktualisierung fehlgeschlagen: " + str(error)


def integration_state(project_path):
    """Prüft vor dem Abschluss die Integrationslage des aktuellen Branches (B16).

    Liefert immer ``{"ok", "message", "ahead", "behind"}`` und wirft niemals.
    Ein fehlgeschlagener Fetch, detached HEAD und ein zurückliegender Stand
    (``behind > 0``) blockieren; eine Erstveröffentlichung ohne Fern-Branch
    ist zulässig.
    """
    state = {"ok": False, "message": "", "ahead": 0, "behind": 0}
    project = str(project_path)
    # Bewusste Ausnahme (broad-exception-caught): Diese Prüfung ist eine
    # Schranke und darf unter keiner Umständen einen Lauf mit einer Exception
    # abbrechen; alle Befunde stehen im Ergebnisdict.
    try:
        branch = current_branch(project)
        if not branch:
            state["message"] = (
                "Kein Branch ausgecheckt (detached HEAD): kein Abschluss "
                "auf veraltetem Stand.")
            return state
        rc, out = git(project, "fetch", "--prune", "origin")
        if rc != 0:
            # Ein Fetch kann auch an Zugangsdaten scheitern; die Guidance
            # steht deshalb immer dabei, die URL bleibt maskiert.
            detail = mask_embedded_credentials(out or "unbekannter Fehler")
            state["message"] = _auth_guidance(
                "Abruf von origin fehlgeschlagen: " + detail + "\n"
                + _TOKEN_GUIDANCE)
            return state
        rc, _ = git(project, "rev-parse", "--verify", "--quiet",
                    "origin/" + branch)
        if rc != 0:
            state["ok"] = True
            state["message"] = (
                "Branch " + branch + " ist noch nicht auf origin vorhanden "
                "(Erstveröffentlichung).")
            return state
        rc, out = git(project, "rev-list", "--left-right", "--count",
                      branch + "...origin/" + branch)
        if rc != 0:
            state["message"] = _auth_guidance(mask_embedded_credentials(
                "Vergleich mit origin/" + branch + " nicht möglich: "
                + (out or "unbekannter Fehler")))
            return state
        parts = out.split()
        ahead, behind = int(parts[0]), int(parts[1])
        state["ahead"], state["behind"] = ahead, behind
        if behind == 0:
            state["ok"] = True
            state["message"] = (
                "Integrationsstand aktuell (" + str(ahead)
                + " ahead, 0 behind).")
            return state
        lage = "divergiert" if ahead > 0 else "veraltet"
        state["message"] = (
            "Integrationsbranch " + branch + " " + lage + " von origin: "
            + str(ahead) + " ahead / " + str(behind) + " behind; "
            "kein Abschluss auf veraltetem Stand.")
        return state
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        state["message"] = ("Integrationsstand nicht prüfbar: "
                            + mask_embedded_credentials(str(error)))
        return state


def complete_package(project_path, branch, package_id=None, title=None):
    """Überträgt einen abgeschlossenen Arbeitspaket-Branch und stellt den
    Merge-Request (AP9, seit B16 eine echte Abschlussschranke): Erst wird die
    Integrationslage geprüft, dann der Branch gepusht und danach der Request
    auf die Basis gestellt (explizit > GITHUB_BASE > Standard der origin).

    Ohne aktivierte Verknüpfung oder ohne origin: bewusster Skip. Sonst
    liefert das 4-Tupel ``(performed, ok, message, result)`` mit ``result``
    als Dict mit ``branch`` und ``pr_url``. Bei einer blockierten Integrations-
    lage wird weder gepusht noch ein Merge-Request gestellt; Push- und
    Request-Fehler melden ``ok=False``. Diese Funktion wirft niemals."""
    project = str(project_path)
    result = {"branch": str(branch or "").strip(), "pr_url": ""}
    # Bewusste Ausnahme (broad-exception-caught): Der Abschluss ist eine
    # Schranke und darf niemals mit einer Exception abbrechen.
    try:
        config = read_config(os.path.join(project, ".vibe", "project.env"))
        if not config["enabled"]:
            return False, True, ("GitHub ist für dieses Projekt nicht aktiv: "
                                 "Übertragung übersprungen"), result
        if not any(r["name"] == "origin" for r in remotes(project)):
            return False, True, "Kein Remote origin: Übertragung übersprungen", result
        branch = branch_name(branch or current_branch(project))
        result["branch"] = branch
        # B16: Vor Push und Merge-Request blockieren, wenn der Integrations-
        # stand zurückliegt oder divergiert — sonst würde ein veralteter Stand
        # trotz Fehlschlag lokal weitergemergt (F32/AP19).
        state = integration_state(project)
        if not state["ok"]:
            return True, False, state["message"], result
        ok, message = push(project, branch)
        if not ok:
            return True, False, message, result
        if not config["base"] and not default_base(project):
            # Bewusster, begrenzter Nachversuch: origin/HEAD versorgen, damit
            # der Merge-Request eine Basis kennt. set_head_default fragt den
            # Remote selbst ab (remote set-head --auto) — ein Fernaufruf.
            set_head_default(project)
        label = f"{package_id}: {branch}" if package_id else f"Merge-Request: {branch}"
        try:
            request = create_pull_request(
                project, config["repo"], branch,
                base=config["base"] or None,
                title=title or label,
                body=("Automatischer Merge-Request des Arbeitspakets "
                      + str(package_id or branch)),
                api=config["api"] or None,
                token=token_for_rest(config["api"], project),
                token_required=False)
        except (GitHubError, ValueError) as error:
            # AP4: Idempotenter Abschluss — ein bereits bestehender offener
            # Merge-Request (422 / "already exists") wird nachgeschlagen und
            # dessen URL als Erfolg übernommen, statt einen zweiten PR zu
            # stellen. Andere Fehler melden wie bisher ``ok=False``.
            existing = _find_open_pull_request(
                project, config["repo"], branch, config["api"] or None,
                token_for_rest(config["api"], project))
            if existing:
                result["pr_url"] = existing.get("url") or ""
                return True, True, ("Branch " + branch + " übertragen; "
                                    "bestehender Merge-Request #"
                                    + str(existing.get("number")) + ": "
                                    + (existing.get("url") or "")), result
            return True, False, ("Branch " + branch + " übertragen; "
                                 "Merge-Request fehlgeschlagen: " + str(error)), result
        result["pr_url"] = request.get("url") or ""
        return True, True, ("Branch " + branch + " übertragen; Merge-Request #"
                            + str(request.get("number")) + ": "
                            + (request.get("url") or "")), result
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        return True, False, ("Übertragung fehlgeschlagen: "
                             + mask_embedded_credentials(str(error))), result


def _first_pr(payload):
    """Erster PR-Datensatz aus einer Liste oder einem einzelnen Objekt.

    GitHub liefert für ``GET /pulls`` eine Liste, für ``GET /pulls/<n>`` ein
    einzelnes Objekt; lokale Fakes bilden gelegentlich nur eine der beiden
    Formen ab. Beide werden gleichwertig gelesen."""
    if isinstance(payload, dict) and payload.get("number"):
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("number"):
                return item
    return None


def _pr_field(payload, field):
    pr = _first_pr(payload)
    return pr.get(field) if pr else None


def _find_open_pull_request(project, repo, branch, api, token):
    """Offener Merge-Request zum Branch; ``None`` ohne Treffer oder Fehler."""
    owner = str(repo or "").split("/", 1)[0]
    url = (api or OFFICIAL_API).rstrip("/") + "/repos/" + quote(repo) + "/pulls"
    query = urllib.parse.urlencode({"head": owner + ":" + branch,
                                    "state": "open"})
    try:
        payload = _http_json("GET", url + "?" + query, token=token)
    except GitHubError:
        return None
    pr = _first_pr(payload)
    if not pr:
        return None
    return {"number": pr.get("number"), "url": pr.get("html_url") or ""}


def merged_pull_request(project_path, branch):
    """Sucht den Merge-Request eines Branches und prüft, ob er gemergt ist.

    Ohne aktivierte Verknüpfung, ohne Repository oder bei Fehlern bleibt
    ``found=False``. Liefert immer ``{found, state, merged, url, number}``
    und wirft niemals. ``merged`` und ``state`` kommen zuverlässig aus der
    Detailabfrage (``GET /pulls/<n>``), wenn diese verfügbar ist."""
    result = {"found": False, "state": "", "merged": False, "url": "",
              "number": None}
    project = str(project_path)
    try:
        config = read_config(os.path.join(project, ".vibe", "project.env"))
        if not config["enabled"] or not config["repo"]:
            return result
        branch = branch_name(branch or current_branch(project))
        api = (config["api"] or OFFICIAL_API).rstrip("/")
        owner = config["repo"].split("/", 1)[0]
        token = token_for_rest(api, project)
        base_url = api + "/repos/" + quote(config["repo"]) + "/pulls"
        query = urllib.parse.urlencode({"head": owner + ":" + branch,
                                        "state": "all"})
        listing = _http_json("GET", base_url + "?" + query, token=token)
        pr = _first_pr(listing)
        if not pr:
            return result
        result.update({
            "found": True,
            "number": pr.get("number"),
            "url": pr.get("html_url") or "",
            "state": str(pr.get("state") or ""),
            "merged": bool(pr.get("merged")),
        })
        try:
            detail = _http_json("GET", base_url + "/" + str(pr.get("number")),
                                token=token)
        except GitHubError:
            detail = None
        if isinstance(detail, dict):
            result["state"] = str(detail.get("state") or result["state"])
            result["merged"] = bool(detail.get("merged"))
            result["url"] = str(detail.get("html_url") or result["url"])
        return result
    except Exception:  # noqa: BLE001; pylint: disable=broad-exception-caught
        return result


def merge_pull_request(project_path, branch, package_id=None):
    """Mergt den offenen Merge-Request des Branches per REST (squash).

    Wirft niemals; liefert ``(ok, message, result)``. ``result`` trägt
    ``branch``, ``number``, ``sha``, ``pr_url`` und bei einem Konflikt
    ``conflict=True`` (405/409 bzw. ``merged=false``), damit der Läufer den
    begrenzten Reparaturpfad erkennt. Ohne Token wird der Versuch trotzdem
    unternommen (``token_for_rest`` mit token_required-Prinzip von
    ``complete_package``); die Ablehnung wird als Befund gemeldet."""
    project = str(project_path)
    result = {"branch": str(branch or "").strip(), "number": None,
              "sha": "", "pr_url": "", "conflict": False}
    try:
        config = read_config(os.path.join(project, ".vibe", "project.env"))
        if not config["enabled"]:
            return False, ("GitHub ist für dieses Projekt nicht aktiv: "
                           "kein automatischer Merge."), result
        if not config["repo"]:
            return False, "Kein Repository verknüpft (GITHUB_REPO fehlt).", result
        branch = branch_name(branch or current_branch(project))
        result["branch"] = branch
        api = (config["api"] or OFFICIAL_API).rstrip("/")
        owner = config["repo"].split("/", 1)[0]
        token = token_for_rest(api, project)
        base_url = api + "/repos/" + quote(config["repo"]) + "/pulls"
        query = urllib.parse.urlencode({"head": owner + ":" + branch,
                                        "state": "open"})
        listing = _http_json("GET", base_url + "?" + query, token=token)
        pr = _first_pr(listing)
        if not pr or not pr.get("number"):
            return False, ("Kein offener Merge-Request für " + branch
                           + " gefunden."), result
        number = pr.get("number")
        result["number"] = number
        result["pr_url"] = pr.get("html_url") or ""
        # Mergeability kurz abfragen; ``mergeable == null`` heißt bei GitHub
        # "noch nicht berechnet" und wird kurz (max. 3×) erneut geprüft.
        for _ in range(3):
            try:
                detail = _http_json("GET", base_url + "/" + str(number),
                                    token=token)
            except GitHubError:
                break
            mergeable = detail.get("mergeable") if isinstance(detail, dict) else None
            if mergeable is not None:
                break
            time.sleep(1)
        try:
            merged = _http_json("PUT", base_url + "/" + str(number) + "/merge",
                                token=token, payload={"merge_method": "squash"})
        except GitHubError as error:
            message = str(error)
            if "GitHub-Fehler 405" in message or "GitHub-Fehler 409" in message:
                result["conflict"] = True
                return False, ("Konflikt beim automatischen Merge von " + branch
                               + ": " + message), result
            raise
        if not isinstance(merged, dict):
            return False, "GitHub-Antwort auf den Merge ist ungewöhnlich.", result
        if merged.get("merged") is False:
            result["conflict"] = True
            return False, ("Merge-Request #" + str(number) + " konnte nicht "
                           "gemergt werden: "
                           + str(merged.get("message") or "")), result
        result["sha"] = str(merged.get("sha") or "")
        return True, ("Merge-Request #" + str(number) + " automatisch gemergt "
                      "(squash)."), result
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        return False, ("Automatischer Merge fehlgeschlagen: "
                       + mask_embedded_credentials(str(error))), result


def _ensure_mergeable(worktree, base_ref):
    """Fetch --prune origin und Merge von ``base_ref`` nach HEAD (--no-ff).

    Niederstufige Operation (T-G7): läuft ausschließlich im ``worktree`` und
    wirft niemals. Liefert ``(ok, message, result)``; ``result`` trägt bei
    einem Konflikt ``conflict=True`` und die konfliktbehafteten ``paths``.
    Ein Push findet nicht statt."""
    result = {"conflict": False, "paths": []}
    wt = str(worktree)
    try:
        rc, out = git(wt, "fetch", "--quiet", "--prune", "origin")
        if rc != 0:
            return False, _auth_guidance(mask_embedded_credentials(
                "Abruf fehlgeschlagen: " + (out or "unbekannter Fehler"))), result
        rc, _ = git(wt, "merge-base", "--is-ancestor", base_ref, "HEAD")
        if rc == 0:
            return True, ("Bereits mergebar (" + base_ref
                          + " ist Vorfahr von HEAD)."), result
        rc, out = git(wt, "merge", "--no-ff", "--no-edit", base_ref)
        if rc == 0:
            return True, "Basis " + base_ref + " gemergt.", result
        rc_conf, conflict_files = git(wt, "diff", "--name-only", "--diff-filter=U")
        if rc_conf == 0 and conflict_files.strip():
            result["conflict"] = True
            result["paths"] = [line.strip() for line in conflict_files.splitlines()
                               if line.strip()]
            return False, ("Merge-Konflikt mit " + base_ref), result
        return False, mask_embedded_credentials(
            "Merge mit " + base_ref + " fehlgeschlagen: "
            + (out or "unbekannter Fehler")), result
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        return False, mask_embedded_credentials(
            "Merge nicht durchführbar: " + str(error)), result


def ensure_mergeable(project_path_config, worktree, base=""):
    """Sichert die Mergeability des Paketbranches vor dem Abschluss (T-G7).

    Die Konfiguration (``enabled``/``base``) kommt aus
    ``project_path_config/.vibe/project.env``; Git läuft ausschließlich im
    ``worktree``. Ohne aktivierte Verknüpfung oder ohne origin wird bewusst
    übersprungen. Ist ``base`` ausdrücklich angegeben (voller Ref, z. B.
    ``origin/main``), gilt er unmittelbar. Liefert ``(ok, message, result)``
    und wirft niemals; ``result`` trägt ``conflict``/``paths`` (Konflikt),
    sonst ``performed``.
    """
    result = {"conflict": False, "paths": []}
    project = str(project_path_config)
    wt = str(worktree)
    try:
        if not str(base or "").strip():
            config = read_config(os.path.join(project, ".vibe", "project.env"))
            if not config["enabled"]:
                result["performed"] = False
                return True, ("GitHub ist für dieses Projekt nicht aktiv: "
                              "Mergeability übersprungen."), result
            base = config["base"] or default_base(wt)
            if not base:
                return False, ("Basis-Branch unbekannt: GITHUB_BASE angeben "
                               "oder origin/HEAD setzen."), result
            base_ref = "origin/" + base
        else:
            base_ref = str(base).strip()
        # AP5 (4c): Das Credential wird einmal aus dem Projektkonfigurations-
        # pfad gelöst und für alle Git-Aufrufe der Arbeitskopie durchgereicht.
        # Der Worktree-Digest unterscheidet sich vom Projekt-Digest; löste
        # ``git()`` das Credential über den Worktree-CWD auf, fehlte der
        # Projekt-Token trotz funktionierendem Push. Der Token bleibt nur in
        # der Prozessumgebung (VIBE_GITHUB_CREDENTIAL), nie in argv/Logs.
        with _credential_passdown(credential_for_git(project)):
            if not any(r["name"] == "origin" for r in remotes(wt)):
                result["performed"] = False
                return True, "Kein Remote origin: Mergeability übersprungen.", result
            ok, message, sub = _ensure_mergeable(wt, base_ref)
        sub["performed"] = True
        result.update(sub)
        return ok, message, result
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        return False, mask_embedded_credentials(
            "Mergeability nicht prüfbar: " + str(error)), result


def clone(url, target_dir, timeout=TIMEOUT_GIT, branch=None):
    """Checkt ein Repository nach target_dir aus (git clone, Argumentliste).

    Mit ``branch`` wird genau dieser Branch ausgecheckt (``git clone
    --branch``); ein ungültiger Name wird vor dem Aufruf abgelehnt.

    Die URL wird als ein einziges Argument übergeben: Eine Shell gibt es
    nicht, versteckte Befehle in der Adresse werden nicht ausgeführt. Ohne
    Terminal-Prompt und mit dem bisherigen Credential-Umfeld (AP6); der
    Tokeninhalt bleibt in der Prozessumgebung. Scheitert das Klonen, wird
    ein vom Aufruf neu erzeugtes Zielverzeichnis vollständig entfernt, damit
    kein halbes Projekt zurückbleibt; ein vorher vorhandener Ordner wird
    niemals angetastet (der Aufrufer hat ihn zuvor abgelehnt).
    """
    target = os.fspath(target_dir)
    if not target or target in (".", ".."):
        raise ValueError("Zielordner fehlt")
    existed = os.path.lexists(target)
    extra = ["--branch", branch_name(branch)] if branch else []
    rc, out = git(os.path.dirname(target) or ".",
                  "clone", "--quiet", *extra, str(url), target, timeout=timeout)
    if rc != 0 and not existed:
        shutil.rmtree(target, ignore_errors=True)
    # Fehlermeldungen von git können die Remote-Adresse samt eingebetteter
    # Zugangsdaten wiederholen; Meldungen verlassen das Modul nur maskiert.
    return rc, mask_embedded_credentials(_auth_guidance(out))


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
            f"GitHub-Fehler {error.code}: {detail or error.reason or 'unbekannt.'}"
        ) from None
    except (urllib.error.URLError, OSError) as error:
        raise GitHubError("GitHub nicht erreichbar: " + str(getattr(error, "reason", error))) from None
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise GitHubError("GitHub-Antwort ist kein JSON.") from None


def list_issues(repo, label=None, api=None, token=None, project=None):
    """Offene GitHub-Issues; Label-Filter (Leerwert = alle Issues).

    Ohne ausdrücklich übergebenen Token: Umgebungs-Token, sonst der
    verschlüsselte Projekt-Token (AP9), sonst der legacy gespeicherte
    Token (B7) — gespeicherte Token nur für die offizielle API."""
    repo = str(repo or "").strip()
    if not RE_REPO.match(repo):
        raise GitHubError("Repository in owner/name angeben")
    api_value = (api or OFFICIAL_API)
    token = token if token is not None else token_for_rest(api_value, project)
    api = api_value.rstrip("/")
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
                        api=None, token=None, token_required=True):
    """Stellt einen Merge-Request über die REST-API; nur mit Token.

    ``token_required=False`` ist der Automatik-Weg des Läufers
    (``complete_package``): Auch ohne Token wird der Versuch unternommen;
    die Ablehnung der API wird dann als verständlicher Befund gemeldet.
    Der Nutzerpfad (CLI/Oberfläche) bleibt bei der Voreinstellung und
    verlangt weiterhin einen Token, bevor irgendetwas gesendet wird."""
    project = str(project_path)
    head = str(head or "").strip()
    if not head or "^" in head or "~" in head:
        raise GitHubError("Quell-Branch (head) fehlt oder ist ungültig")
    title = str(title or "").strip()
    if not title:
        raise GitHubError("Titel für den Merge-Request fehlt")
    token = token if token is not None else token_for_rest(api or OFFICIAL_API,
                                                           project)
    if not token and token_required:
        raise GitHubError("Kein GitHub-Zugangstoken in der Umgebung "
                          "(GITHUB_TOKEN oder GH_TOKEN) gesetzt oder in der "
                          "Karte hinterlegt.")
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
    return text or f"Issue {number}"


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
        entry = f"- [ ] GH-{number} {_sanitize_title(issue.get('title'), number)}"
        existing.add(number)
        block.append(entry)
        added.append(f"GH-{number}")
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
