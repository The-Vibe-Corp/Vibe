#!/usr/bin/env python3
"""Gemeinsame Storage-Schicht für Konfigurationen und Agenten (V-005).

Die Dateien von vibe (Agenten, MCP-Konfigurationen, Projektlisten, Profile)
werden über eine einzige Schicht geschrieben:

* Schreiben über eine temporäre Datei im Zielordner, ``fsync`` und
  ``os.replace``. Ein abgebrochener Schreibvorgang hinterlässt höchstens eine
  temporäre Datei, nie eine halb geschriebene Zieldatei.
* Eine Sperrdatei (``flock``) serialisiert Schreibvorgänge. Zusätzlich wird
  eine erwartete Prüfsumme geprüft, sodass eine Änderung zwischen Lesen und
  Schreiben als Konflikt erkannt wird statt still überschrieben zu werden.
* Sicherungen erhalten Namen aus Zeitstempel, Mikrosekunden, Zufallsteil und
  einem Zähler und werden mit ``O_EXCL`` angelegt. Zwei Sicherungen im selben
  Augenblick können sich daher nicht überschreiben.
* Wiederherstellung schreibt die Sicherung atomar zurück und legt vorher eine
  Sicherung des aktuellen Stands an.

Wichtig: Auf FUSE-/NTFS-/Netz-Dateisystemen sind atomare Ersetzungen und
Unix-Dateirechte nicht garantiert. ``filesystem_notes()`` liefert den
tatsächlichen Dateisystemtyp und eine ehrliche Einordnung; die Schicht
verspricht dort weder Atomarität noch Rechtewirkung. Die gleiche Vorsicht
gilt für ``flock``: Fehlt es, bleibt die Prüfsummenkontrolle, aber keine
gegenseitige Ausschließung.
"""
import contextlib
import hashlib
import os
import re
import secrets
import stat
import tempfile
import time

TMP_PREFIX = ".vibe-"
TMP_SUFFIX = ".tmp"
LOCK_DIR_ENV = "VIBE_STORAGE_LOCK_DIR"

# Dateisysteme, bei denen eine Ersetzung im selben Ordner als atomar gilt und
# Unix-Dateirechte wirken (lokale Linux-Dateisysteme).
ATOMIC_FILESYSTEMS = {
    "ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs", "jfs", "reiserfs",
    "tmpfs", "ramfs", "zfs", "overlay", "bcachefs", "nilfs2",
}
# Dateisysteme ohne verlässliche Unix-Rechte bzw. ohne garantierte Atomarität.
UNSAFE_PREFIXES = (
    "fuse", "ntfs", "cifs", "smb", "nfs", "vfat", "exfat", "9p", "sshfs",
    "davfs", "afs", "ceph", "glusterfs", "lustre", "webdav",
)


class StorageError(Exception):
    """Basisfehler der Storage-Schicht."""


class ConcurrentChangeError(StorageError, ValueError):
    """Die Datei wurde seit dem Lesen verändert (oder entfernt/angelegt)."""


class BackupError(StorageError):
    """Eine Sicherung konnte nicht gelesen oder angelegt werden."""


class _Missing:
    """Sentinel: Die Datei darf zum Schreibzeitpunkt nicht existieren."""

    def __repr__(self):
        return "MISSING"

    def __bool__(self):
        return False


MISSING = _Missing()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def digest_bytes(data):
    """SHA-256 über Rohbytes."""
    return _sha(bytes(data))


def file_digest(path):
    """SHA-256 der Datei oder ``None``, wenn sie nicht existiert."""
    try:
        with open(path, "rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except FileNotFoundError:
        return None


def read_snapshot(path, encoding="utf-8", errors="replace"):
    """Liest eine Datei unverändert als Bytes und Text mit Prüfsumme.

    ``text`` wird ohne Zeilenenden-Umwandlung dekodiert; ``data`` enthält die
    Rohbytes für Sicherungen. Nicht vorhandene Dateien liefern
    ``exists=False``, ``digest=None`` und ``text=None``.
    """
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        info = os.stat(path)
    except FileNotFoundError:
        return Snapshot(path=os.fspath(path), exists=False, digest=None,
                        size=0, mode=None, data=b"", text=None)
    return Snapshot(path=os.fspath(path), exists=True, digest=_sha(data),
                    size=len(data), mode=stat.S_IMODE(info.st_mode), data=data,
                    text=data.decode(encoding, errors))


class Snapshot:
    """Zustand einer Datei zu einem Zeitpunkt."""

    __slots__ = ("path", "exists", "digest", "size", "mode", "data", "text")

    def __init__(self, path, exists, digest, size, mode, data, text):
        self.path = path
        self.exists = exists
        self.digest = digest
        self.size = size
        self.mode = mode
        self.data = data
        self.text = text

    def __repr__(self):
        return (f"Snapshot(path={self.path!r}, exists={self.exists!r}, "
                f"digest={self.digest!r}, size={self.size!r})")

    def as_dict(self):
        return {"path": self.path, "exists": self.exists,
                "digest": self.digest, "size": self.size}


def expected_digest(value):
    """Normalisiert ``expected`` auf ``None``, ``MISSING`` oder einen Hash."""
    if value is None or value is MISSING:
        return value
    if isinstance(value, Snapshot):
        return value.digest if value.exists else MISSING
    return str(value)


def check_expected(path, current, expected):
    """Prüft eine erwartete Prüfsumme gegen den aktuellen Snapshot."""
    expected = expected_digest(expected)
    if expected is None:
        return
    if expected is MISSING:
        if current.exists:
            raise ConcurrentChangeError(
                "Datei existiert bereits und wurde nicht überschrieben: " + str(path))
        return
    if not current.exists:
        raise ConcurrentChangeError(
            "Datei wurde zwischenzeitlich entfernt: " + str(path))
    if current.digest != expected:
        raise ConcurrentChangeError(
            "Datei wurde zwischenzeitlich geändert: " + str(path))


def lock_dir():
    """Ordner für Sperrdateien; per Umgebung überschreibbar (Tests)."""
    value = os.environ.get(LOCK_DIR_ENV)
    if value:
        return value
    uid = getattr(os, "getuid", lambda: "user")()
    return os.path.join(tempfile.gettempdir(), f"vibe-storage-locks-{uid}")


@contextlib.contextmanager
def locked(path):
    """Serialisiert Schreibvorgänge auf ``path`` (best effort, ohne Shell).

    ``flock`` ist auf lokalen Dateisystemen verfügbar. Fehlt es (z. B. auf
    einem FUSE-Mount), wird ohne Sperre weitergearbeitet; die Prüfsummen-
    kontrolle bleibt bestehen. Es wird niemals Atomarität zugesichert, die das
    Dateisystem nicht bietet.
    """
    directory = lock_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        os.chmod(directory, 0o700)
    except OSError:
        pass
    key = hashlib.sha256(os.path.realpath(path).encode("utf-8", "surrogateescape")).hexdigest()
    lock_path = os.path.join(directory, key + ".lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        yield False
        return
    fcntl = None
    held = False
    try:
        try:
            import fcntl as _fcntl
            fcntl = _fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            held = True
        except (ImportError, OSError):
            held = False
        yield held
    finally:
        if held and fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            os.close(fd)
        except OSError:
            pass


def _fsync_dir(directory):
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _stage_bytes(directory, data, mode):
    fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, suffix=TMP_SUFFIX, dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        return tmp
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stage_bytes(path, data, mode=None):
    """Schreibt Rohbytes in eine temporäre Datei neben ``path`` (ohne Ersetzen).

    Öffentlich, damit ein abgebrochener Schreibvorgang testbar ist: Die
    Zieldatei bleibt unverändert, bis ``commit_staged`` aufgerufen wird.
    """
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    if mode is None:
        current = read_snapshot(path)
        mode = current.mode if current.exists else 0o644
    return _stage_bytes(directory, bytes(data), mode)


def stage_text(path, text, encoding="utf-8", mode=None):
    return stage_bytes(path, text.encode(encoding), mode=mode)


def discard_staged(staged):
    """Entfernt eine nicht übernommene temporäre Datei."""
    try:
        os.unlink(staged)
    except FileNotFoundError:
        pass


def commit_staged(staged, path, expected=None, fsync=True):
    """Ersetzt ``path`` durch eine zuvor geschriebene temporäre Datei."""
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    with locked(path):
        current = read_snapshot(path)
        check_expected(path, current, expected)
        try:
            os.replace(staged, path)
        except BaseException:
            discard_staged(staged)
            raise
        if fsync:
            _fsync_dir(directory)
    return read_snapshot(path)


def _commit_locked(path, data, expected, mode):
    """Ersetzen, während ``locked(path)`` bereits gehalten wird."""
    directory = os.path.dirname(os.path.abspath(path))
    current = read_snapshot(path)
    check_expected(path, current, expected)
    if mode is None:
        mode = current.mode if current.exists else 0o644
    staged = _stage_bytes(directory, bytes(data), mode)
    try:
        # Erneut prüfen: Auch ein Schreiber ohne diese Sperre wird erkannt.
        check_expected(path, read_snapshot(path), expected)
        os.replace(staged, path)
    except BaseException:
        discard_staged(staged)
        raise
    _fsync_dir(directory)
    return read_snapshot(path), current


def write_bytes(path, data, expected=None, mode=None):
    """Schreibt Rohbytes atomar über eine temporäre Datei im Zielordner.

    ``expected`` ist ``None`` (keine Prüfung), ``MISSING`` (Datei darf nicht
    existieren), eine Prüfsumme oder ein :class:`Snapshot`. Bei Abweichung
    wird :class:`ConcurrentChangeError` ausgelöst und die Zieldatei bleibt
    unverändert. Die Rechte einer vorhandenen Datei bleiben erhalten.
    """
    path = os.fspath(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with locked(path):
        snapshot, _ = _commit_locked(path, data, expected, mode)
    return snapshot


def write_text(path, text, expected=None, mode=None, encoding="utf-8"):
    """Wie :func:`write_bytes`, aber für Text (ohne Zeilenenden-Umwandlung)."""
    return write_bytes(path, text.encode(encoding), expected=expected, mode=mode)


def write_text_with_backup(path, text, backup_dir, label=None, expected=None,
                           mode=None, encoding="utf-8"):
    """Sichert den bisherigen Inhalt und ersetzt die Datei atomar.

    Sicherung und Ersetzen liegen unter derselben Sperre, damit die Sicherung
    genau den Inhalt enthält, der ersetzt wurde. Liefert
    ``(neuer_snapshot, sicherungspfad_oder_None)``.
    """
    path = os.fspath(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = text.encode(encoding)
    with locked(path):
        current = read_snapshot(path)
        check_expected(path, current, expected)
        backup = None
        if current.exists:
            backup = backup_bytes(path, current.data, backup_dir, label=label)
        snapshot, _ = _commit_locked(path, data, expected, mode)
    return snapshot, backup


# ---------- Sicherungen ----------
def _backup_stem(target, label):
    base = label or os.path.basename(os.fspath(target)) or "sicherung"
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("._-") or "sicherung"
    ext = os.path.splitext(os.fspath(target))[1] or ".bak"
    if base.endswith(ext) and len(base) > len(ext):
        base = base[:-len(ext)]
    return base, ext


def _stamp(now=None):
    when = time.time() if now is None else float(now)
    return (time.strftime("%Y%m%d-%H%M%S", time.localtime(when)),
            f"{int((when % 1) * 1_000_000):06d}")


def backup_bytes(target, data, backup_dir, label=None, now=None, mode=0o600):
    """Legt eine kollisionsfreie Sicherung der übergebenen Bytes an.

    Der Name enthält Zeitstempel, Mikrosekunden und einen Zufallsteil. Die
    Datei wird mit ``O_CREAT|O_EXCL`` angelegt; bei einer Kollision (gleicher
    Name) wird mit einem Zähler erneut versucht. ``mode=0600`` ist eine
    bestmögliche Einschränkung, keine Garantie auf FUSE/NTFS.
    """
    backup_dir = os.fspath(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    stem, ext = _backup_stem(target, label)
    stamp, micro = _stamp(now)
    for attempt in range(100):
        suffix = f"-{attempt}" if attempt else ""
        name = f"{stem}-{stamp}-{micro}-{secrets.token_hex(2)}{suffix}{ext}"
        candidate = os.path.join(backup_dir, name)
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        except FileExistsError:
            continue
        except OSError as error:
            raise BackupError(f"Sicherung nicht möglich ({backup_dir}): {error}") from error
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(bytes(data))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(candidate, mode)
            except OSError:
                pass
        except BaseException:
            discard_staged(candidate)
            raise
        _fsync_dir(backup_dir)
        return candidate
    raise BackupError(
        "Keine freie Sicherungsdatei nach 100 Versuchen in " + backup_dir)


def backup_file(path, backup_dir, label=None, now=None, mode=0o600):
    """Sichert den aktuellen Inhalt einer vorhandenen Datei."""
    snapshot = read_snapshot(path)
    if not snapshot.exists:
        raise BackupError("Datei nicht gefunden, keine Sicherung möglich: " + str(path))
    return backup_bytes(path, snapshot.data, backup_dir, label=label, now=now, mode=mode)


def backup_text(target, text, backup_dir, label=None, now=None, mode=0o600,
                encoding="utf-8"):
    """Sichert bekannten Text (z. B. den gerade gelesenen Agenteninhalt)."""
    return backup_bytes(target, text.encode(encoding), backup_dir,
                        label=label, now=now, mode=mode)


def list_backups(backup_dir, label=None):
    """Sicherungsnamen im Ordner, aufsteigend (älteste zuerst)."""
    try:
        names = os.listdir(backup_dir)
    except FileNotFoundError:
        return []
    names = [name for name in names
             if not name.startswith(".") and os.path.isfile(os.path.join(backup_dir, name))]
    if label:
        base = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._-")
        prefixes = {base + "-"}
        stem, ext = os.path.splitext(base)
        if ext:
            prefixes.add(stem + "-")
        names = [name for name in names if any(name.startswith(p) for p in prefixes)]
    return sorted(names)


def _resolve_backup(backup_dir, name):
    base = os.path.realpath(backup_dir)
    candidate = os.path.realpath(os.path.join(base, os.fspath(name)))
    if os.path.dirname(candidate) != base:
        raise BackupError("Sicherung liegt nicht im Sicherungsordner: " + str(name))
    if not os.path.isfile(candidate):
        raise BackupError("Sicherung nicht gefunden: " + str(name))
    return candidate


def restore_backup(backup_dir, name, target, expected=None, label=None):
    """Stellt eine Sicherung atomar wieder her.

    Vor dem Zurückschreiben wird der aktuelle Stand als neue Sicherung
    abgelegt, damit die Wiederherstellung selbst rückgängig gemacht werden
    kann. ``expected`` schützt zusätzlich vor einer zwischenzeitlichen
    Änderung der Zieldatei.
    """
    source = _resolve_backup(backup_dir, name)
    with open(source, "rb") as handle:
        data = handle.read()
    # Prüfung, Sicherheitskopie und Zurückschreiben liegen unter derselben
    # Sperre. Eine abgelehnte Wiederherstellung verändert den Zustand daher
    # nicht – auch nicht durch eine zusätzliche Sicherung.
    with locked(target):
        target_snapshot = read_snapshot(target)
        check_expected(target, target_snapshot, expected)
        safety = None
        if target_snapshot.exists:
            safety = backup_bytes(target, target_snapshot.data, backup_dir,
                                  label=label or os.path.basename(os.fspath(target)))
        snapshot, _ = _commit_locked(target, data, expected, None)
    return {"backup": os.path.basename(source), "safety": safety, "snapshot": snapshot}


# ---------- Ehrliche Einordnung des Dateisystems ----------
def _unescape_mount(value):
    def repl(match):
        return chr(int(match.group(1), 8))
    return re.sub(r"\\([0-7]{3})", repl, value)


def _mount_table(mountinfo=None):
    path = mountinfo or "/proc/mounts"
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 3:
                    rows.append((_unescape_mount(parts[1]), parts[2]))
    except OSError:
        return None
    return rows


def _classify(fstype):
    if not fstype:
        return None, None
    name = fstype.lower()
    if name in ATOMIC_FILESYSTEMS:
        return True, True
    if name.startswith(UNSAFE_PREFIXES) or name in UNSAFE_PREFIXES:
        return False, False
    return None, None


def filesystem_notes(path, mountinfo=None):
    """Dateisystemtyp und belastbare Aussage zu Atomarität und Rechten.

    ``atomic``/``posix_permissions`` sind ``True``, ``False`` oder ``None``
    (unbekannt). Es wird nur ``True`` geliefert, wenn das Dateisystem die
    Eigenschaft tatsächlich zusichert. ``warning`` ist ein deutscher Satz für
    Oberfläche und Dokumentation; er ist leer, wenn beides zugesichert ist.
    """
    target = os.path.realpath(os.fspath(path))
    table = _mount_table(mountinfo)
    if table is None:
        fstype = None
        mount = None
    else:
        best = None
        for candidate, kind in table:
            base = candidate.rstrip("/") or "/"
            if target == base or target.startswith(base + "/") or base == "/":
                if best is None or len(base) > len(best[0]):
                    best = (base, kind)
        mount, fstype = best if best else (None, None)
    atomic, permissions = _classify(fstype)
    if atomic is True and permissions is True:
        warning = ""
    elif fstype is None:
        warning = ("Dateisystem unbekannt: atomare Ersetzung und Unix-Dateirechte "
                   "werden von vibe nicht zugesichert.")
    elif atomic is None:
        warning = (f"Dateisystem {fstype} ist unbekannt eingeordnet: atomare "
                   "Ersetzung und Unix-Dateirechte sind nicht garantiert.")
    else:
        warning = (f"Dateisystem {fstype}: atomare Ersetzung und Unix-Dateirechte "
                   "sind nicht garantiert. vibe schreibt über eine temporäre Datei "
                   "im selben Ordner und erkennt konkurrierende Änderungen, kann "
                   "hier aber weder Atomarität noch Rechtewirkung zusichern.")
    return {"path": target, "mount": mount, "fstype": fstype,
            "atomic": atomic, "posix_permissions": permissions,
            "warning": warning}
