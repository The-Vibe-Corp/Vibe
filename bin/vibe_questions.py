#!/usr/bin/env python3
"""Rückfragen von Agenten an den Nutzer (F16).

Ein Agent darf den Nutzer unterbrechen, wenn eine fachliche Entscheidung offen
ist. Die Rückfrage liegt als kleine JSON-Datei im Laufzeitordner
``$VIBE_RUNTIME/questions``; das Dashboard liest sie und schreibt die Antwort
als eigene Datei zurück. Beide Seiten brauchen dafür keine Netzverbindung und
keine laufende Gegenstelle: Eine Frage bleibt sichtbar, bis sie beantwortet
ist — auch wenn das Dashboard erst später geöffnet wird.

Aufbau je Rückfrage:

* ``<id>.json`` — unveränderliche Frage mit Projekt, Agent, Text, den
  angebotenen Auswahlmöglichkeiten und der Angabe, ob eine freie Antwort
  erlaubt ist.
* ``<id>.answer.json`` — Antwort. Sie wird mit ``O_EXCL``-Semantik angelegt
  (``vibe_storage.MISSING``); eine zweite Antwort kann die erste deshalb nicht
  überschreiben.

Dateien werden über die gemeinsame Storage-Schicht geschrieben. Auf
FUSE-/NTFS-Dateisystemen sind Atomarität und Unix-Rechte nicht garantiert;
die Rückfrage-ID ist auf ein enges Muster begrenzt, damit kein Pfad aus einer
Eingabe entsteht. Inhalte werden vor dem Schreiben begrenzt und geprüft.
"""
import json
import os
import re
import secrets
import time

import vibe_storage

MAX_TEXT = 4000
MAX_OPTION = 200
MAX_OPTIONS = 10
MAX_ANSWER = 4000
MAX_LABEL = 120
ID_RE = re.compile(r"^q[0-9a-f]{12}$")
ANSWER_SUFFIX = ".answer.json"
WAIT_INTERVAL = 0.25


def question_dir(runtime):
    """Ordner aller Rückfragen im Laufzeitbereich."""
    return os.path.join(os.fspath(runtime), "questions")


def _path(runtime, qid, suffix=""):
    """Pfad einer Rückfrage; die ID wird vor jeder Pfadbildung geprüft."""
    if not isinstance(qid, str) or not ID_RE.match(qid):
        raise ValueError("Ungültige Rückfrage-ID: " + str(qid)[:60])
    return os.path.join(question_dir(runtime), qid + suffix)


def _clean_label(value, name):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(name + " muss Text sein")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValueError(name + " enthält ein Steuerzeichen")
    text = value.strip()
    if len(text) > MAX_LABEL:
        raise ValueError(name + " ist länger als " + str(MAX_LABEL) + " Zeichen")
    return text


def _clean_text(value, name, limit):
    if not isinstance(value, str):
        raise ValueError(name + " muss Text sein")
    if "\x00" in value:
        raise ValueError(name + " enthält ein Steuerzeichen")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(name + " ist länger als " + str(limit) + " Zeichen")
    return text


def normalize_options(options):
    """Prüft die angebotenen Auswahlmöglichkeiten und entfernt Rand-Leerzeichen."""
    if options is None:
        options = []
    if isinstance(options, str) or not isinstance(options, (list, tuple)):
        raise ValueError("Auswahlmöglichkeiten müssen eine Liste sein")
    if len(options) > MAX_OPTIONS:
        raise ValueError(
            "Höchstens " + str(MAX_OPTIONS) + " Auswahlmöglichkeiten sind erlaubt"
        )
    result = []
    for option in options:
        text = _clean_text(option, "Auswahlmöglichkeit", MAX_OPTION)
        if not text:
            raise ValueError("Auswahlmöglichkeit ist leer")
        if text in result:
            raise ValueError("Auswahlmöglichkeit ist doppelt: " + text)
        result.append(text)
    return result


def _stamp(now=None):
    return time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now)
    )


def create(runtime, project="", agent="", text="", options=None, free_text=True,
           now=None):
    """Legt eine offene Rückfrage an und liefert ihre ID."""
    text = _clean_text(text, "Frage", MAX_TEXT)
    if not text:
        raise ValueError("Frage fehlt")
    project = _clean_label(project, "Projekt")
    agent = _clean_label(agent, "Agent")
    options = normalize_options(options)
    folder = question_dir(runtime)
    os.makedirs(folder, exist_ok=True)
    created = _stamp(now)
    for _attempt in range(8):
        qid = "q" + secrets.token_hex(6)
        record = {
            "id": qid,
            "project": project,
            "agent": agent,
            "text": text,
            "options": options,
            "free_text": bool(free_text),
            "created": created,
        }
        payload = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
        try:
            vibe_storage.write_text(
                os.path.join(folder, qid + ".json"),
                payload,
                expected=vibe_storage.MISSING,
                mode=0o600,
            )
        except vibe_storage.ConcurrentChangeError:
            continue
        return qid
    raise RuntimeError("Keine freie Rückfrage-ID gefunden")


def _load_answer(runtime, qid):
    try:
        with open(_path(runtime, qid, ANSWER_SUFFIX), encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Antwort nicht lesbar: " + qid) from error
    if not isinstance(data, dict):
        raise ValueError("Antwort nicht lesbar: " + qid)
    data.setdefault("option", None)
    data.setdefault("option_text", None)
    data.setdefault("text", "")
    return data


def load(runtime, qid):
    """Liest eine Rückfrage samt Antwort; unbekannte IDs sind ein Fehler."""
    try:
        with open(_path(runtime, qid, ".json"), encoding="utf-8") as handle:
            record = json.load(handle)
    except FileNotFoundError as error:
        raise ValueError("Rückfrage nicht gefunden: " + qid) from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Rückfrage nicht lesbar: " + qid) from error
    if not isinstance(record, dict) or record.get("id") != qid:
        raise ValueError("Rückfrage nicht lesbar: " + qid)
    record.setdefault("project", "")
    record.setdefault("agent", "")
    record.setdefault("text", "")
    record.setdefault("options", [])
    record.setdefault("free_text", True)
    record.setdefault("created", "")
    options = record["options"]
    # Der Rückfrageordner ist für den Agenten beschreibbar. Eine dort
    # manipulierte oder beschädigte Datei darf weder die Anzeige der übrigen
    # Fragen verhindern noch übergroße Werte in die Oberfläche bringen.
    if (
        not isinstance(record["project"], str)
        or not isinstance(record["agent"], str)
        or not isinstance(record["text"], str)
        or not isinstance(record["created"], str)
        or len(record["text"]) > MAX_TEXT
        or len(record["project"]) > MAX_LABEL
        or len(record["agent"]) > MAX_LABEL
        or len(record["created"]) > 40
        or not isinstance(options, list)
        or len(options) > MAX_OPTIONS
        or not all(
            isinstance(option, str) and len(option) <= MAX_OPTION
            for option in options
        )
    ):
        raise ValueError("Rückfrage nicht lesbar: " + qid)
    record["free_text"] = bool(record["free_text"])
    record["answer"] = _load_answer(runtime, qid)
    return record


def open_questions(runtime):
    """Alle noch unbeantworteten Rückfragen, älteste zuerst."""
    folder = question_dir(runtime)
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return []
    result = []
    for name in names:
        if not name.endswith(".json") or name.endswith(ANSWER_SUFFIX):
            continue
        qid = name[: -len(".json")]
        if not ID_RE.match(qid):
            continue
        try:
            record = load(runtime, qid)
        except ValueError:
            # Eine defekte Datei darf die Anzeige der übrigen Fragen nicht
            # verhindern; sie bleibt für die Fehlersuche liegen.
            continue
        if record["answer"] is None:
            result.append(record)
    result.sort(key=lambda entry: (entry.get("created") or "", entry["id"]))
    return result


def answer(runtime, qid, option=None, text="", by="web"):
    """Beantwortet eine offene Rückfrage; eine zweite Antwort ist ein Fehler."""
    record = load(runtime, qid)
    if record["answer"] is not None:
        raise ValueError("Rückfrage ist bereits beantwortet: " + qid)
    options = record.get("options") or []
    free_text = bool(record.get("free_text", True))
    text = _clean_text("" if text is None else text, "Antwort", MAX_ANSWER)
    if option is not None:
        if isinstance(option, bool) or not isinstance(option, int):
            raise ValueError("Auswahl muss eine Zahl sein")
        if not options:
            raise ValueError("Diese Rückfrage bietet keine Auswahlmöglichkeiten")
        if not 0 <= option < len(options):
            raise ValueError("Auswahl liegt außerhalb der angebotenen Möglichkeiten")
        option_text = options[option]
    else:
        option_text = None
        if options and not free_text:
            raise ValueError("Bitte eine der angebotenen Möglichkeiten wählen.")
        if not text:
            raise ValueError("Antwort fehlt")
    answer_record = {
        "option": option,
        "option_text": option_text,
        "text": text,
        "at": _stamp(),
        "by": _clean_label(by, "Quelle") or "web",
    }
    payload = json.dumps(answer_record, ensure_ascii=False, indent=1) + "\n"
    try:
        vibe_storage.write_text(
            _path(runtime, qid, ANSWER_SUFFIX),
            payload,
            expected=vibe_storage.MISSING,
            mode=0o600,
        )
    except vibe_storage.ConcurrentChangeError as error:
        raise ValueError("Rückfrage ist bereits beantwortet: " + qid) from error
    return answer_record


def wait_for(runtime, qid, timeout=90.0, interval=WAIT_INTERVAL, stop=None):
    """Wartet auf eine Antwort und erlaubt einen vorzeitigen Abbruch.

    ``stop`` wird bei jeder Prüfung aufgerufen. Liefert sie einen wahren Wert,
    endet das Warten sofort mit ``("stop", None)`` — so kann der Nutzer den
    autonomen Modus während eines laufenden Laufs einschalten und den Agenten
    von der Antwortpflicht befreien. Sonst: ``("answer", Antwort)`` oder
    ``("timeout", None)``.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        record = load(runtime, qid)
        if record["answer"] is not None:
            return "answer", record["answer"]
        if stop is not None and stop():
            return "stop", None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timeout", None
        time.sleep(min(interval, remaining))


def wait(runtime, qid, timeout=90.0, interval=WAIT_INTERVAL):
    """Wartet auf die Antwort; ``None`` heißt, das Zeitlimit ist abgelaufen."""
    return wait_for(runtime, qid, timeout=timeout, interval=interval)[1]


def project_for_path(path, projects):
    """Projektname, in dessen Ordner ``path`` liegt (längster Treffer)."""
    target = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
    best_name = None
    best_root = ""
    for name, root in sorted(projects.items()):
        if not root:
            continue
        candidate = os.path.realpath(
            os.path.abspath(os.path.expanduser(str(root)))
        )
        if target == candidate or target.startswith(candidate + os.sep):
            if best_name is None or len(candidate) > len(best_root):
                best_name, best_root = name, candidate
    return best_name
