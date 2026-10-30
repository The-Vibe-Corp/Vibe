"""vibe_mcp — MCP-Server aus opencode-Konfigurationen anzeigen, anlegen, bearbeiten, testen (nur Standardbibliothek)."""
import os, re, json, sys, time, queue, threading, subprocess, shutil, signal, socket, ssl
import urllib.request, urllib.error
import vibe
import vibe_storage
import vibe_opencode

SECRET_MASK = "***"
NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# ---------- JSONC: lesen und gezielt schreiben (Kommentare außerhalb des mcp-Blocks bleiben erhalten) ----------
def _skip_ws(t, i):
    n = len(t)
    while i < n:
        if t[i] in " \t\r\n": i += 1
        elif t.startswith("//", i):
            j = t.find("\n", i); i = n if j < 0 else j + 1
        elif t.startswith("/*", i):
            j = t.find("*/", i + 2); i = n if j < 0 else j + 2
        else: break
    return i

def _string_end(t, i):
    i += 1
    while i < len(t):
        if t[i] == "\\": i += 2; continue
        if t[i] == '"': return i + 1
        i += 1
    raise ValueError("Nicht beendeter String in der Konfiguration")

def _skip_value(t, i):
    n = len(t)
    if i >= n: raise ValueError("Unerwartetes Ende der Konfiguration")
    c = t[i]
    if c == '"': return _string_end(t, i)
    if c in "{[":
        close = "}" if c == "{" else "]"; i += 1
        while True:
            i = _skip_ws(t, i)
            if i >= n: raise ValueError("Klammer nicht geschlossen")
            if t[i] == close: return i + 1
            if t[i] == ",": i += 1; continue
            if c == "{":
                i = _string_end(t, i); i = _skip_ws(t, i)
                if t[i] != ":": raise ValueError("':' erwartet")
                i = _skip_ws(t, i + 1)
            i = _skip_value(t, i)
    j = i
    while j < n and t[j] not in ",}] \t\r\n" and not t.startswith(("//", "/*"), j): j += 1
    return j

def jsonc_loads(text):
    out, i, n = [], 0, len(text)
    def strip_trailing(i):
        j = _skip_ws(text, i)
        return j < n and text[j] in "}]"
    while i < n:
        c = text[i]
        if c == '"':
            j = _string_end(text, i); out.append(text[i:j]); i = j
        elif text.startswith("//", i) or text.startswith("/*", i):
            i = _skip_ws(text, i)
        elif c == ",":
            if not strip_trailing(i + 1): out.append(c)
            i += 1
        else: out.append(c); i += 1
    s = "".join(out)
    return json.loads(s) if s.strip() else {}

def _object_members(t, start):
    """Liest die Mitglieder eines Objekts ab ``start`` (Index der öffnenden Klammer).

    Liefert ``(members, close, last_end)``. ``members`` ordnet jedem Schlüssel
    ``(key_start, value_start, value_end)`` zu. Kommentare und Formatierung
    werden dabei nur übersprungen, nicht verändert.
    """
    i = _skip_ws(t, start)
    if i >= len(t) or t[i] != "{": raise ValueError("Objekt erwartet.")
    i += 1; members, last_end = {}, None
    while True:
        i = _skip_ws(t, i)
        if i >= len(t): raise ValueError("Objekt nicht geschlossen")
        if t[i] == "}": return members, i, last_end
        if t[i] == ",": i += 1; continue
        key_start = i
        ke = _string_end(t, i); key = json.loads(t[i:ke]); i = _skip_ws(t, ke)
        if i >= len(t) or t[i] != ":": raise ValueError("':' erwartet")
        vs = _skip_ws(t, i + 1); ve = _skip_value(t, vs)
        members[key] = (key_start, vs, ve); last_end = ve; i = ve

def _root_members(t):
    return _object_members(t, 0)

def _line_indent(t, position):
    """Führender Leerraum der Zeile, in der ``position`` liegt."""
    line_start = t.rfind("\n", 0, position) + 1
    prefix = t[line_start:position]
    return prefix[:len(prefix) - len(prefix.lstrip(" \t"))]

def _dump(obj, base_indent="  "):
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    return s.replace("\n", "\n" + base_indent)

def jsonc_set_member(text, obj_start, key, value):
    """Setzt/ersetzt ein Mitglied eines JSONC-Objekts; der Rest bleibt unverändert."""
    members, close, last_end = _object_members(text, obj_start)
    if key in members:
        key_start, vs, ve = members[key]
        return text[:vs] + _dump(value, _line_indent(text, key_start)) + text[ve:]
    close_indent = _line_indent(text, close)
    member_indent = close_indent + "  "
    member = json.dumps(key) + ": " + _dump(value, member_indent)
    pre = text[:close].rstrip(" \t\r\n")
    if last_end is None:
        return pre + "\n" + member_indent + member + "\n" + close_indent + text[close:]
    after = _skip_ws(text, last_end)
    if after < len(text) and text[after] == ",":
        return pre + "\n" + member_indent + member + "\n" + close_indent + text[close:]
    return (text[:last_end] + "," + text[last_end:close].rstrip(" \t\r\n") + "\n"
            + member_indent + member + "\n" + close_indent + text[close:])

def jsonc_delete_member(text, obj_start, key):
    """Entfernt ein Mitglied eines JSONC-Objekts samt einem Trennkomma."""
    members, close, last_end = _object_members(text, obj_start)
    if key not in members: return text
    key_start, vs, ve = members[key]
    after = _skip_ws(text, ve)
    if after < len(text) and text[after] == ",":
        return text[:key_start] + text[after + 1:]
    ordered = list(members.items())
    index = [name for name, _span in ordered].index(key)
    if index > 0:
        previous = ordered[index - 1][1]
        comma = _skip_ws(text, previous[2])
        if comma < len(text) and text[comma] == ",":
            return text[:comma] + text[comma + 1:key_start] + text[ve:]
    return text[:key_start] + text[ve:]

def jsonc_sync_member(text, obj_start, key, old_value, new_value):
    """Aktualisiert ein Mitglied und steigt bei Objekten rekursiv hinein."""
    members, _close, _last_end = _object_members(text, obj_start)
    if key in members:
        _key_start, value_start, _value_end = members[key]
        start = _skip_ws(text, value_start)
        if (isinstance(old_value, dict) and isinstance(new_value, dict)
                and start < len(text) and text[start] == "{"):
            return jsonc_sync_object(text, start, old_value, new_value)
    return jsonc_set_member(text, obj_start, key, new_value)

def jsonc_sync_object(text, obj_start, old, new):
    """Gleicht ein JSONC-Objekt an ``new`` an, ohne unveränderte Einträge neu zu schreiben."""
    for key, value in new.items():
        if key in old and old[key] != value:
            text = jsonc_sync_member(text, obj_start, key, old[key], value)
    for key in old:
        if key not in new:
            text = jsonc_delete_member(text, obj_start, key)
    for key, value in new.items():
        if key not in old:
            text = jsonc_set_member(text, obj_start, key, value)
    return text

def jsonc_set_top(text, key, value):
    """Setzt/ersetzt den Wert eines Schlüssels der obersten Ebene; alles andere (auch Kommentare) bleibt unverändert."""
    if not text.strip(): return "{\n  " + json.dumps(key) + ": " + _dump(value) + "\n}\n"
    return jsonc_set_member(text, 0, key, value)

# ---------- Konfigurationsdateien ----------
CONFIG_NAMES = ("opencode.json", "opencode.jsonc")

def cfg_candidates(scope):
    """Konfigurationsdateien in der Reihenfolge, die opencode 2.1.4 verwendet.

    ``opencode mcp add`` sucht zuerst ``opencode.json``, dann
    ``opencode.jsonc``, danach dieselben Namen unter ``.opencode/`` und legt
    ohne Treffer ``opencode.json`` an. vibe bearbeitet genau die Datei, die
    opencode tatsächlich zuerst liest.
    """
    base = os.path.expanduser("~/.config/opencode") if scope == "global" else vibe.ppath(scope)
    return ([os.path.join(base, name) for name in CONFIG_NAMES]
            + [os.path.join(base, ".opencode", name) for name in CONFIG_NAMES])

def cfg_path(scope):
    candidates = cfg_candidates(scope)
    for path in candidates:
        if os.path.exists(path): return path
    return candidates[0]

def load(scope):
    p = cfg_path(scope)
    snapshot = vibe_storage.read_snapshot(p)
    text = snapshot.text if snapshot.exists else ""
    data = jsonc_loads(text)
    # Das Schema wird aus der vorhandenen Konfiguration erkannt. Nur für eine
    # geprüfte opencode-Version darf eine leere Datei das geprüfte Schema
    # verwenden; sonst bleibt das Schema unbekannt und Schreibvorgänge werden
    # abgelehnt (V-007).
    layout_info = vibe_opencode.detect_mcp_layout(data)
    layout, servers = layout_info["layout"], layout_info["servers"]
    digest = snapshot.digest if snapshot.exists else vibe_storage.MISSING
    return p, text, data, layout, servers, digest

def _require_known_layout(layout):
    if layout == vibe_opencode.LAYOUT_UNKNOWN:
        raise ValueError(
            "MCP-Schema nicht feststellbar; die installierte opencode-Version ist nicht geprüft. "
            f"Geprüft ist opencode {vibe_opencode.TESTED_VERSION}. Die Konfiguration wird nicht verändert."
        )

def backup_dir():
    return os.path.join(vibe.PATHS.state, "config-backups")

def backup_label(scope, p):
    base = os.path.expanduser("~/.config/opencode") if scope == "global" else vibe.ppath(scope)
    relative = os.path.relpath(p, base)
    name = os.path.basename(p) if os.path.dirname(relative) in ("", ".") else relative.replace(os.sep, "_")
    return f"{vibe.safe(scope)}-{name}"

def backups(scope):
    """Vorhandene Sicherungen der Konfiguration, älteste zuerst."""
    p = cfg_path(scope)
    return vibe_storage.list_backups(backup_dir(), label=backup_label(scope, p))

def restore(scope, backup=None):
    """Stellt eine Sicherung der Konfiguration wieder her; ohne Angabe die neueste."""
    p = cfg_path(scope)
    items = backups(scope)
    if not items:
        raise ValueError("Keine Sicherung für " + p + " in " + backup_dir())
    chosen = backup or items[-1]
    if chosen not in items:
        raise ValueError("Sicherung gehört nicht zu dieser Konfiguration: " + chosen)
    snapshot = vibe_storage.read_snapshot(p)
    expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
    return vibe_storage.restore_backup(backup_dir(), chosen, p, expected=expected,
                                      label=backup_label(scope, p))

def _mcp_object_start(text):
    """Index des ``mcp``-Objekts oder ``None``, wenn kein ``mcp``-Block existiert."""
    if not text.strip(): return None
    members, _close, _last_end = _root_members(text)
    if "mcp" not in members: return None
    start = _skip_ws(text, members["mcp"][1])
    if text.startswith("null", start): return None
    if start >= len(text) or text[start] != "{":
        raise ValueError("Der 'mcp'-Block ist kein Objekt; die Konfiguration wird nicht verändert.")
    return start

def _store(scope, p, text, data, layout, servers, expected=None, old_servers=None):
    _require_known_layout(layout)
    if old_servers is None:
        mcp = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
        if layout == vibe_opencode.LAYOUT_SERVERS:
            old_servers = mcp.get("servers") if isinstance(mcp.get("servers"), dict) else {}
        else:
            old_servers = {k: v for k, v in mcp.items() if vibe_opencode.is_mcp_server(v)}
    if layout == vibe_opencode.LAYOUT_SERVERS:
        mcp_start = _mcp_object_start(text)
        if mcp_start is None:
            new_text = jsonc_set_top(text, "mcp", {"servers": servers})
        else:
            mcp_members, _close, _last_end = _object_members(text, mcp_start)
            if "servers" not in mcp_members:
                new_text = jsonc_set_member(text, mcp_start, "servers", servers)
            else:
                servers_start = _skip_ws(text, mcp_members["servers"][1])
                if servers_start >= len(text) or text[servers_start] != "{":
                    raise ValueError("'mcp.servers' ist kein Objekt; die Konfiguration wird nicht verändert.")
                new_text = jsonc_sync_object(text, servers_start, old_servers, servers)
    elif layout == vibe_opencode.LAYOUT_CLASSIC:
        mcp_start = _mcp_object_start(text)
        if mcp_start is None:
            raise ValueError("Der 'mcp'-Block fehlt; die Konfiguration wird nicht verändert.")
        new_text = jsonc_sync_object(text, mcp_start, old_servers, servers)
    else:
        raise ValueError("Unbekanntes MCP-Schema: " + str(layout))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    vibe_storage.write_text_with_backup(
        p, new_text, backup_dir(),
        label=backup_label(scope, p), expected=expected)

# ---------- Schutz von Geheimnissen ----------
URL_SECRET = re.compile(r"((?:^|[?&])(?:token|key|secret|password|auth|apikey|api_key)=)[^&#\s]+", re.I)
SECRET_KEY = re.compile(r"token|key|secret|pass|auth|bearer|credential|cookie", re.I)
def _is_secret(k, v):
    v = str(v)
    return v != "" and "{env:" not in v and "{file:" not in v and bool(SECRET_KEY.search(k))

def _mask_url(url):
    def repl(match):
        value = match.group(0)[len(match.group(1)):]
        if value.startswith(("{env:", "{file:")):
            return match.group(0)
        return match.group(1) + SECRET_MASK
    return URL_SECRET.sub(repl, url)

def mask_entry(e):
    e = json.loads(json.dumps(e))
    for k in ("environment", "headers"):
        if isinstance(e.get(k), dict): e[k] = {a: (SECRET_MASK if _is_secret(a, b) else b) for a, b in e[k].items()}
    if isinstance(e.get("url"), str): e["url"] = _mask_url(e["url"])
    if isinstance(e.get("oauth"), dict): e["oauth"] = {a: (SECRET_MASK if a.lower() in ("clientsecret",) else b) for a, b in e["oauth"].items()}
    return e

def _restore_url(new, old):
    def masked_names(text):
        return [
            match.group(1)[:-1].lstrip("?&")
            for match in URL_SECRET.finditer(text)
            if match.group(0)[len(match.group(1)):] == SECRET_MASK
        ]

    names = masked_names(new)
    if not names: return new
    if not isinstance(old, str):
        raise ValueError("Maskiertes Geheimnis in der URL kann nicht wiederhergestellt werden: der bisherige Eintrag fehlt.")
    # Ein maskierter Parameter lässt sich nur eindeutig zuordnen, wenn er in
    # der neuen und in der bisherigen URL genau einmal vorkommt. Sonst würde
    # ein Geheimnis still durch ein anderes ersetzt.
    lowered = [name.lower() for name in names]
    for name in sorted(set(lowered)):
        if lowered.count(name) > 1:
            raise ValueError(
                f"Geheimnis im URL-Parameter '{name}' kann nicht wiederhergestellt werden: "
                "der Parameter kommt in der neuen URL mehrfach vor."
            )
        previous = re.findall(r"(?i)(?:[?&]|^)" + re.escape(name) + r"=", old)
        if not previous:
            raise ValueError(
                f"Geheimnis im URL-Parameter '{name}' kann nicht wiederhergestellt werden: "
                "der bisherige Eintrag enthält diesen Parameter nicht."
            )
        if len(previous) > 1:
            raise ValueError(
                f"Geheimnis im URL-Parameter '{name}' kann nicht wiederhergestellt werden: "
                "der bisherige Eintrag enthält diesen Parameter mehrfach."
            )
    def repl(match):
        prefix = match.group(1)
        value = match.group(0)[len(prefix):]
        if value != SECRET_MASK: return match.group(0)
        name = prefix[:-1].lstrip("?&")
        found = re.search(r"(?i)(?:[?&]|^)" + re.escape(name) + r"=([^&#\s]*)", old)
        if not found:
            raise ValueError(
                f"Geheimnis im URL-Parameter '{name}' kann nicht wiederhergestellt werden: "
                "der bisherige Eintrag enthält diesen Parameter nicht."
            )
        return prefix + found.group(1)
    restored = URL_SECRET.sub(repl, new)
    if masked_names(restored):
        raise ValueError(
            "Maskiertes Geheimnis in der URL kann nicht zugeordnet werden. "
            "Bitte den vollständigen neuen Wert eintragen."
        )
    return restored

def merge_masked(new, old):
    new = json.loads(json.dumps(new)); old = old or {}
    for k in ("environment", "headers"):
        if isinstance(new.get(k), dict):
            previous = old.get(k) if isinstance(old.get(k), dict) else {}
            for a, b in list(new[k].items()):
                if b == SECRET_MASK:
                    if a not in previous:
                        raise ValueError(
                            f"Geheimnis '{a}' in '{k}' kann nicht wiederhergestellt werden: "
                            "der bisherige Eintrag enthält diesen Schlüssel nicht."
                        )
                    new[k][a] = previous[a]
    if isinstance(new.get("url"), str):
        new["url"] = _restore_url(new["url"], old.get("url"))
    if isinstance(new.get("oauth"), dict) and new["oauth"].get("clientSecret") == SECRET_MASK:
        previous = old.get("oauth") if isinstance(old.get("oauth"), dict) else {}
        if "clientSecret" not in previous:
            raise ValueError(
                "Das maskierte OAuth-Clientsecret kann nicht wiederhergestellt werden: "
                "der bisherige Eintrag enthält es nicht."
            )
        new["oauth"]["clientSecret"] = previous["clientSecret"]
    return new

# ---------- Anzeigen, anlegen, bearbeiten ----------
def list_all():
    out = []
    for scope in ["global"] + vibe.projects():
        try: p, _, _, layout, servers, _digest = load(scope)
        except Exception as ex:
            out.append({"scope": scope, "name": "(Konfiguration nicht lesbar)", "error": str(ex), "path": cfg_path(scope)}); continue
        for name, e in servers.items():
            me = mask_entry(e)
            target = " ".join(me.get("command", [])) if me.get("type") == "local" else me.get("url", "")
            out.append({"scope": scope, "name": name, "type": me.get("type", "?"), "enabled": me.get("enabled", True) is not False, "target": target, "layout": layout, "path": p})
    return out

def get_entry(scope, name):
    _, _, _, layout, servers, digest = load(scope)
    if name not in servers: raise ValueError("MCP-Server nicht gefunden: " + name)
    return {"entry": mask_entry(servers[name]), "layout": layout, "path": cfg_path(scope),
            "digest": None if digest is vibe_storage.MISSING else digest}

def _check_oauth(oauth):
    if oauth is False: return
    if not isinstance(oauth, dict):
        raise ValueError("'oauth' muss false oder ein Objekt sein.")
    allowed = set(vibe_opencode.mcp_oauth_fields())
    unknown = sorted(set(oauth) - allowed)
    if unknown:
        raise ValueError(
            "OAuth-Feld wird von opencode " + vibe_opencode.TESTED_VERSION
            + " nicht unterstützt: " + ", ".join(unknown) + "."
        )
    for key in ("clientId", "clientSecret", "scope", "redirectUri"):
        if key in oauth and not isinstance(oauth[key], str):
            raise ValueError(f"'oauth.{key}' muss Text sein.")
    if "callbackPort" in oauth:
        port = oauth["callbackPort"]
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("'oauth.callbackPort' muss eine Portnummer zwischen 1 und 65535 sein.")

def validate(entry, extra_keys=()):
    if not isinstance(entry, dict): raise ValueError("Eintrag ungültig")
    t = entry.get("type")
    if t not in ("local", "remote"): raise ValueError("type muss 'local' oder 'remote' sein.")
    allowed = set(vibe_opencode.mcp_entry_fields(t))
    unknown = sorted(set(entry) - allowed - set(extra_keys))
    if unknown:
        raise ValueError(
            "Feld wird von opencode " + vibe_opencode.TESTED_VERSION
            + " für " + t + " nicht unterstützt: " + ", ".join(unknown)
            + ". Die Konfiguration wird nicht verändert."
        )
    if t == "local":
        c = entry.get("command")
        if not (isinstance(c, list) and c and all(isinstance(x, str) and x for x in c)): raise ValueError("Lokal: 'command' braucht mindestens ein Element (Programm, dann Argumente).")
        if "cwd" in entry and not isinstance(entry["cwd"], str): raise ValueError("'cwd' muss Text sein.")
    else:
        u = entry.get("url")
        if not (isinstance(u, str) and re.match(r"^https?://\S+$", u)): raise ValueError("Remote: 'url' muss mit http:// oder https:// beginnen.")
        if "oauth" in entry: _check_oauth(entry["oauth"])
    for k in ("environment", "headers"):
        if k in entry and not (isinstance(entry[k], dict) and all(isinstance(a, str) and isinstance(b, str) for a, b in entry[k].items())): raise ValueError(f"'{k}' muss ein Objekt aus Text-Paaren sein.")
    if "enabled" in entry and not isinstance(entry["enabled"], bool): raise ValueError("'enabled' muss true oder false sein.")
    if "timeout" in entry and (isinstance(entry["timeout"], bool) or not isinstance(entry["timeout"], int) or entry["timeout"] < 1): raise ValueError("'timeout' muss eine positive Zahl (Millisekunden) sein.")
    return entry

def _unknown_old_fields(old):
    if not isinstance(old, dict): return set()
    return set(old) - set(vibe_opencode.mcp_entry_fields(old.get("type")))

def save(scope, name, entry, old_name=None, create=False, expected=None):
    if not NAME_OK.match(name or ""): raise ValueError("Name: Buchstaben, Ziffern, _ und - (Werkzeuge werden mit dem Namen als Präfix angeboten).")
    if not isinstance(entry, dict): raise ValueError("Eintrag ungültig")
    p, text, data, layout, servers, digest = load(scope)
    _require_known_layout(layout)
    old_servers = json.loads(json.dumps(servers))
    old = servers.get(old_name or name)
    if old_name and old_name != name:
        if old_name not in servers: raise ValueError("MCP-Server nicht gefunden: " + old_name)
        if name in servers: raise ValueError(f"'{name}' existiert schon.")
    elif create and name in servers: raise ValueError(f"'{name}' existiert schon. Zum Ändern bearbeiten statt neu anlegen.")
    entry = merge_masked(entry, old)
    # Unbekannte Felder eines bestehenden Eintrags sind Teil der Datei und
    # werden beim Bearbeiten erhalten. Neue, vom Schema nicht unterstützte
    # Felder werden dagegen abgelehnt.
    preserved = set()
    if old and old.get("type") == entry.get("type"):
        for key in _unknown_old_fields(old):
            preserved.add(key)
            if key not in entry:
                entry[key] = old[key]
            elif entry[key] != old[key]:
                raise ValueError(
                    f"Unbekanntes Feld '{key}' kann nicht geändert werden; "
                    "die Konfiguration wird nicht verändert."
                )
    entry = validate(entry, extra_keys=preserved)
    if old_name and old_name != name:
        servers.pop(old_name)
    servers[name] = entry
    _store(scope, p, text, data, layout, servers,
           expected=expected if expected is not None else digest,
           old_servers=old_servers)
    return p

def delete(scope, name, expected=None):
    p, text, data, layout, servers, digest = load(scope)
    _require_known_layout(layout)
    if name not in servers: raise ValueError("MCP-Server nicht gefunden: " + name)
    old_servers = json.loads(json.dumps(servers))
    servers.pop(name)
    _store(scope, p, text, data, layout, servers,
           expected=expected if expected is not None else digest,
           old_servers=old_servers)

def toggle(scope, name, enabled=None, expected=None):
    p, text, data, layout, servers, digest = load(scope)
    _require_known_layout(layout)
    if name not in servers: raise ValueError("MCP-Server nicht gefunden: " + name)
    old_servers = json.loads(json.dumps(servers))
    e = servers[name]; e["enabled"] = (not (e.get("enabled", True) is not False)) if enabled is None else bool(enabled)
    _store(scope, p, text, data, layout, servers,
           expected=expected if expected is not None else digest,
           old_servers=old_servers)
    return e["enabled"]

# ---------- Testen: MCP-Handshake (initialize, tools/list) ----------
PROTO = "2025-03-26"
MIN_TIMEOUT = 5
MAX_TIMEOUT_LOCAL = 90
MAX_TIMEOUT_REMOTE = 60
MAX_TOOLS = 200
MAX_TOOL_NAME = 120
MAX_TOOL_DESCRIPTION = 160
MAX_STDIO_BYTES = 4 * 1024 * 1024
MAX_STDERR_CHARS = 4000
MAX_HTTP_BYTES = 1024 * 1024

SUPPORTED_TRANSPORTS = {
    "local": "local – Standard-Ein-/Ausgabe (stdio), JSON-RPC je Zeile",
    "remote": "remote – Streamable HTTP (JSON oder Server-Sent Events)",
}
TEST_WARNING = (
    "Der Verbindungstest startet bei 'local' ein Programm und stellt bei "
    "'remote' eine Netzverbindung her; das ist nicht garantiert "
    "nebenwirkungsfrei. Geprüft werden nur initialize und tools/list."
)

def _resolve(v):
    def env(m): return os.environ.get(m.group(1), "")
    def fil(m):
        try: return open(os.path.expanduser(m.group(1)), encoding="utf-8").read().strip()
        except Exception: return ""
    return re.sub(r"\{file:([^}]+)\}", fil, re.sub(r"\{env:([^}]+)\}", env, v))

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTO, "capabilities": {}, "clientInfo": {"name": "vibe", "version": "1.0"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

def _result(transport):
    """Gemeinsames Ergebnis mit Transportauskunft, Warnung und Limits."""
    return {
        "ok": False, "steps": [], "tools": [], "server": {}, "error": "", "hint": "",
        "transport": transport or "?", "warning": TEST_WARNING, "category": "",
        "notes": ["Es werden nur initialize und tools/list aufgerufen; "
                  "keine fachlichen Werkzeuge (tools/call)."],
        "limits": {"tools": MAX_TOOLS, "http_bytes": MAX_HTTP_BYTES,
                   "stdio_bytes": MAX_STDIO_BYTES},
        "supported_transports": dict(SUPPORTED_TRANSPORTS),
    }

def _fail(res, category, error, hint=""):
    res["category"] = category
    res["error"] = error
    if hint:
        res["hint"] = hint
    return res

def _timeout_for(entry, maximum):
    return max(MIN_TIMEOUT, min((entry.get("timeout") or 30000) / 1000.0, maximum))

def _payload(message):
    """result-Objekt einer JSON-RPC-Antwort; None bei fehlender oder falscher Form."""
    if not isinstance(message, dict):
        return None
    result = message.get("result")
    return result if isinstance(result, dict) else None

def _server_info(payload):
    info = payload.get("serverInfo")
    return info if isinstance(info, dict) else {}

def _tools_from(msgs):
    payload = _payload(msgs) or {}
    tools = []
    raw = payload.get("tools")
    for item in (raw if isinstance(raw, list) else [])[:MAX_TOOLS]:
        if not isinstance(item, dict):
            continue
        tools.append({
            "name": str(item.get("name", "?"))[:MAX_TOOL_NAME],
            "description": str(item.get("description") or "")[:MAX_TOOL_DESCRIPTION],
        })
    return tools

def _secret_values(entry):
    """Konkrete Geheimwerte, die in Diagnosetexten nicht erscheinen dürfen."""
    values = set()
    def add(value, minimum=4):
        if not isinstance(value, str):
            return
        value = _resolve(value).strip()
        if len(value) >= minimum:
            values.add(value)
    for value in (entry.get("environment") or {}).values():
        add(value)
    for key, value in (entry.get("headers") or {}).items():
        if _is_secret(key, value) or re.search(r"(?i)auth", key):
            add(value)
            match = re.match(r"(?i)^\s*(?:bearer|basic|token)\s+(\S+)", _resolve(value))
            if match:
                add(match.group(1), 6)
    url = entry.get("url")
    if isinstance(url, str):
        for match in URL_SECRET.finditer(_resolve(url)):
            add(match.group(0)[len(match.group(1)):], 3)
    oauth = entry.get("oauth")
    if isinstance(oauth, dict):
        add(oauth.get("clientSecret"), 3)
    arguments = [str(argument) for argument in entry.get("command") or []]
    for index, argument in enumerate(arguments):
        match = re.match(r"(?i)^[^=]*(?:token|key|secret|password|auth)=(.+)$", argument)
        if match:
            add(match.group(1), 3)
        if (re.match(r"(?i)^--?(?:token|api[_-]?key|secret|password|auth)$", argument)
                and index + 1 < len(arguments)):
            add(arguments[index + 1], 3)
    return sorted(values, key=len, reverse=True)

_ASSIGN_SECRET = re.compile(r"(?i)\b(token|api[_-]?key|secret|password|authorization|auth)=([^&\s\"']+)")
_CREDENTIAL = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}")

def _redact_text(text, secrets):
    if not isinstance(text, str):
        return text
    for value in secrets:
        text = text.replace(value, SECRET_MASK)
    text = _ASSIGN_SECRET.sub(lambda m: m.group(1) + "=" + SECRET_MASK, text)
    return _CREDENTIAL.sub(lambda m: m.group(1) + " " + SECRET_MASK, text)

def _redact_value(value, secrets):
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if isinstance(value, list):
        return [_redact_value(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, secrets) for key, item in value.items()}
    return value

def _finish(res, secrets):
    """Entfernt Geheimnisse und begrenzt die Diagnoseausgabe."""
    res = _redact_value(res, secrets)
    res["error"] = res["error"][:1000]
    res["hint"] = res["hint"][:2000]
    res["steps"] = res["steps"][:40]
    return res

def _stderr_tail(error_lines):
    text = "".join(error_lines).strip()
    return text[-MAX_STDERR_CHARS:] if text else ""

def _close_process(proc, pgid):
    """Beendet den Testprozess samt Kindprozessen und schließt die Rohre."""
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    elif proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:
            pass

def test_local(entry, cwd):
    res = _result(SUPPORTED_TRANSPORTS["local"])
    secrets = _secret_values(entry)
    timeout = _timeout_for(entry, MAX_TIMEOUT_LOCAL)
    res["limits"]["timeout_s"] = timeout
    cmd = [_resolve(x) for x in entry["command"]]
    env = dict(os.environ); env.update({k: _resolve(v) for k, v in (entry.get("environment") or {}).items()})
    wd = entry.get("cwd") or cwd
    if wd and not os.path.isabs(wd): wd = os.path.join(cwd, wd)
    if wd and not os.path.isdir(wd):
        _fail(res, "config", f"Arbeitsordner nicht gefunden: {wd}",
              "Der Arbeitsordner muss existieren; 'cwd' prüfen oder leer lassen.")
        return _finish(res, secrets)
    kwargs = {"start_new_session": True} if os.name == "posix" else {}
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=wd or None, env=env,
                                text=True, bufsize=1, **kwargs)
    except FileNotFoundError:
        _fail(res, "program", f"Programm nicht gefunden: {cmd[0]}",
              "Ist es im Container installiert (z. B. npx über nodejs/npm)? Pfad oder Installation prüfen.")
        return _finish(res, secrets)
    except Exception as ex:
        _fail(res, "program", f"Start fehlgeschlagen: {ex}")
        return _finish(res, secrets)
    try:
        pgid = os.getpgid(proc.pid) if os.name == "posix" else None
    except OSError:
        pgid = None
    q, errbuf = queue.Queue(maxsize=1000), []
    state = {"stdout": 0, "stderr": 0, "truncated": False}
    def read_stdout():
        for line in proc.stdout:
            state["stdout"] += len(line)
            if state["stdout"] > MAX_STDIO_BYTES or len(line) > MAX_STDIO_BYTES:
                state["truncated"] = True
                continue
            if not line.lstrip().startswith("{"):
                continue
            try:
                q.put_nowait(line)
            except queue.Full:
                state["truncated"] = True
    def read_stderr():
        for line in proc.stderr:
            room = MAX_STDERR_CHARS - state["stderr"]
            if room > 0:
                piece = line[:room]
                errbuf.append(piece)
                state["stderr"] += len(piece)
            if len(line) > max(room, 0):
                state["truncated"] = True
    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    def send(o):
        proc.stdin.write(json.dumps(o) + "\n"); proc.stdin.flush()
    def wait(id_):
        end = time.time() + timeout
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return None
            if proc.poll() is not None:
                # Dem Lesethread kurz Zeit geben, die letzte Zeile einzuordnen.
                try:
                    line = q.get(timeout=min(0.2, remaining))
                except queue.Empty:
                    return None
            else:
                try:
                    line = q.get(timeout=min(0.5, remaining))
                except queue.Empty:
                    continue
            try:
                message = json.loads(line)
            except Exception:
                continue
            if message.get("id") == id_:
                return message
    try:
        res["steps"].append("Transport: " + SUPPORTED_TRANSPORTS["local"])
        res["steps"].append("Prozess gestartet: " + " ".join(cmd)[:120])
        send(INIT); message = wait(1)
        if not message:
            tail = _stderr_tail(errbuf)
            if proc.poll() is not None:
                _fail(res, "protocol",
                      f"Keine Antwort auf 'initialize' (Prozess beendet, Code {proc.poll()})",
                      "Der Server hat den Handshake nicht beantwortet." + (" Letzte Fehlerausgabe: " + tail if tail else ""))
            else:
                hint = ("Beim ersten Start lädt npx Pakete nach, das kann länger dauern: einmal manuell starten oder 'timeout' erhöhen."
                        + (" Letzte Fehlerausgabe: " + tail if tail else ""))
                if state["truncated"]:
                    hint += (f" Die Ausgabe überschritt das Ausgabelimit von {MAX_STDIO_BYTES} Byte;"
                             " weitere Zeilen wurden verworfen.")
                _fail(res, "timeout",
                      f"Keine Antwort auf 'initialize' innerhalb von {int(timeout)} s (Zeitlimit)",
                      hint)
            return _finish(res, secrets)
        if "error" in message:
            _fail(res, "protocol", "initialize abgelehnt: " + json.dumps(message["error"])[:200],
                  "Der Server lehnt den MCP-Handshake ab; Konfiguration und Serverversion prüfen.")
            return _finish(res, secrets)
        payload = _payload(message)
        if payload is None:
            _fail(res, "protocol",
                  "initialize liefert kein gültiges Ergebnis (result fehlt oder ist kein Objekt)",
                  "Der Server antwortet nicht nach MCP; Serverversion und Protokoll prüfen.")
            return _finish(res, secrets)
        res["server"] = _server_info(payload)
        res["steps"].append("initialize ok")
        send(INITIALIZED)
        send(TOOLS_LIST); message = wait(2)
        if not message:
            tail = _stderr_tail(errbuf)
            if proc.poll() is not None:
                _fail(res, "protocol",
                      f"Keine Antwort auf 'tools/list' (Prozess beendet, Code {proc.poll()})",
                      "Der Server beendet sich nach dem Handshake ohne Werkzeugliste."
                      + (" Letzte Fehlerausgabe: " + tail if tail else ""))
            else:
                hint = (f"Der Server beantwortet den Handshake, aber nicht die Werkzeugliste "
                        f"innerhalb von {int(timeout)} s."
                        + (" Letzte Fehlerausgabe: " + tail if tail else ""))
                if state["truncated"]:
                    hint += (f" Die Ausgabe überschritt das Ausgabelimit von {MAX_STDIO_BYTES} Byte;"
                             " weitere Zeilen wurden verworfen.")
                _fail(res, "timeout",
                      f"Keine Antwort auf 'tools/list' innerhalb von {int(timeout)} s (Zeitlimit)",
                      hint)
            return _finish(res, secrets)
        if "error" in message:
            _fail(res, "protocol", "tools/list abgelehnt: " + json.dumps(message["error"])[:200],
                  "Der Server verweigert die Werkzeugliste; Rechte oder Serverversion prüfen.")
            return _finish(res, secrets)
        payload = _payload(message)
        if payload is None:
            _fail(res, "protocol",
                  "tools/list liefert kein gültiges Ergebnis (result fehlt oder ist kein Objekt)",
                  "Der Server beantwortet den Handshake, liefert aber keine Werkzeugliste.")
            return _finish(res, secrets)
        all_tools = payload.get("tools") or []
        res["tools"] = _tools_from(message)
        res["steps"].append(f"tools/list ok: {len(res['tools'])} Werkzeuge")
        if len(all_tools) > MAX_TOOLS:
            res["steps"].append(
                f"Werkzeugliste auf {MAX_TOOLS} von {len(all_tools)} Einträgen begrenzt.")
        if state["truncated"]:
            res["steps"].append(
                f"Ausgabe wurde auf {MAX_STDIO_BYTES} Byte stdout "
                f"und {MAX_STDERR_CHARS} Zeichen stderr begrenzt.")
        res["ok"] = True
    except BrokenPipeError:
        _fail(res, "protocol", "Prozess hat die Verbindung geschlossen",
              "".join(errbuf)[-300:])
    finally:
        _close_process(proc, pgid)
    return _finish(res, secrets)

def _parse_json_message(text, wanted_id):
    try:
        data = json.loads(text)
    except Exception:
        return None
    if isinstance(data, list):
        data = next((item for item in data
                     if isinstance(item, dict) and item.get("id") == wanted_id), None)
    return data if isinstance(data, dict) else None

def _read_http(resp, wanted_id, deadline):
    """Liest eine HTTP-Antwort begrenzt; bricht bei SSE nach der Antwort ab."""
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "text/event-stream" in ctype:
        lines, total = [], 0
        while True:
            if time.time() > deadline:
                raise TimeoutError("Zeitlimit")
            line = resp.readline()
            if not line:
                return None, "".join(lines), False
            total += len(line)
            if total > MAX_HTTP_BYTES:
                return None, "".join(lines), True
            text = line.decode("utf-8", "replace")
            lines.append(text)
            if text.startswith("data:"):
                message = _parse_json_message(text[5:].strip(), wanted_id)
                if message is not None:
                    return message, "".join(lines), False
    chunks, total = [], 0
    while True:
        if time.time() > deadline:
            raise TimeoutError("Zeitlimit")
        chunk = resp.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_HTTP_BYTES:
            return None, b"".join(chunks).decode("utf-8", "replace"), True
        chunks.append(chunk)
    text = b"".join(chunks).decode("utf-8", "replace")
    return _parse_json_message(text, wanted_id), text, False

def test_remote(entry, name):
    res = _result(SUPPORTED_TRANSPORTS["remote"])
    secrets = _secret_values(entry)
    timeout = _timeout_for(entry, MAX_TIMEOUT_REMOTE)
    res["limits"]["timeout_s"] = timeout
    url = _resolve(entry["url"]); headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    headers.update({k: _resolve(v) for k, v in (entry.get("headers") or {}).items()})
    if entry.get("oauth") is not False:
        res["notes"].append(
            "OAuth: vibe führt keine Anmeldung durch und liest keine Tokens. "
            f"Für OAuth-Server zuerst 'opencode mcp auth {name or '<name>'}' ausführen.")
    def post(body, h2=None, wanted_id=None, max_wait=None):
        h = dict(headers); h.update(h2 or {})
        rq = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
        wait = min(timeout, max_wait) if max_wait else timeout
        deadline = time.time() + wait
        with urllib.request.urlopen(rq, timeout=wait) as response:
            message, text, truncated = _read_http(response, wanted_id, deadline)
            return response.status, response.headers, message, text, truncated
    try:
        res["steps"].append("Transport: " + SUPPORTED_TRANSPORTS["remote"])
        status, response_headers, message, body, truncated = post(INIT, wanted_id=1)
        payload = _payload(message)
        if payload is None:
            _fail(res, "protocol",
                  "initialize liefert kein gültiges Ergebnis (result fehlt oder ist kein Objekt; kein MCP-Streamable-HTTP-Server?)",
                  "Geprüft wird Streamable HTTP (POST mit JSON oder Server-Sent Events). "
                  "Klassische SSE-Transporte (GET /sse) und andere Transporte werden nicht getestet und sind kein Hinweis auf einen defekten Server. "
                  + ("Antwort: " + body[:300] if body else ""))
            return _finish(res, secrets)
        res["server"] = _server_info(payload)
        res["steps"].append(f"initialize ok (HTTP {status})")
        session_id = response_headers.get("Mcp-Session-Id") or response_headers.get("mcp-session-id")
        follow = {"MCP-Protocol-Version": payload.get("protocolVersion", PROTO)}
        if session_id:
            follow["Mcp-Session-Id"] = session_id
            res["steps"].append("Sitzungskennung erhalten")
        try:
            post(INITIALIZED, follow, max_wait=5)
        except (urllib.error.HTTPError, OSError, TimeoutError):
            res["notes"].append("Die initialized-Benachrichtigung wurde nicht bestätigt; tools/list wird dennoch versucht.")
        status, response_headers, message, body, truncated = post(TOOLS_LIST, follow, wanted_id=2)
        payload = _payload(message)
        if payload is None:
            _fail(res, "protocol", "tools/list liefert kein gültiges Ergebnis (result fehlt oder ist kein Objekt)",
                  "Geprüft wird Streamable HTTP (POST mit JSON oder Server-Sent Events). "
                  "Klassische SSE-Transporte (GET /sse) und andere Transporte werden nicht getestet und sind kein Hinweis auf einen defekten Server. "
                  + ("Antwort: " + body[:300] if body else ""))
            return _finish(res, secrets)
        all_tools = payload.get("tools") or []
        res["tools"] = _tools_from(message)
        res["steps"].append(f"tools/list ok: {len(res['tools'])} Werkzeuge")
        if len(all_tools) > MAX_TOOLS:
            res["steps"].append(
                f"Werkzeugliste auf {MAX_TOOLS} von {len(all_tools)} Einträgen begrenzt.")
        if truncated:
            res["steps"].append(
                f"HTTP-Antwort wurde nach {MAX_HTTP_BYTES} Byte begrenzt.")
        res["ok"] = True
    except urllib.error.HTTPError as ex:
        detail = ""
        try:
            detail = ex.read(2048).decode("utf-8", "replace")
        except Exception:
            pass
        finally:
            try:
                ex.close()
            except Exception:
                pass
        _fail(res, "auth" if ex.code in (401, 403) else "http",
              f"HTTP {ex.code} {ex.reason}",
              ("Anmeldung nötig. vibe führt keine Anmeldung durch und liest keine Tokens. "
               f"Mit OAuth zuerst 'opencode mcp auth {name or '<name>'}' ausführen. "
               "Mit Schlüssel: 'headers' (z. B. Authorization) setzen und 'oauth': false.")
              if ex.code in (401, 403)
              else ("URL prüfen (Pfad, z. B. /mcp)." if ex.code == 404
                    else "Der Server antwortet mit einem HTTP-Fehler; URL, Proxy und Serverprotokoll prüfen."))
        if detail:
            res["error"] += " – " + detail[:300]
    except TimeoutError:
        _fail(res, "timeout", f"Zeitlimit von {int(timeout)} s überschritten",
              "Erreichbarkeit, Proxy und URL prüfen oder 'timeout' erhöhen.")
    except urllib.error.URLError as ex:
        reason = getattr(ex, "reason", ex)
        if isinstance(reason, TimeoutError):
            _fail(res, "timeout", f"Zeitlimit von {int(timeout)} s überschritten",
                  "Erreichbarkeit, Proxy und URL prüfen oder 'timeout' erhöhen.")
        elif isinstance(reason, socket.gaierror):
            _fail(res, "dns", f"Name nicht auflösbar: {reason}",
                  "DNS, Netzwerk und Schreibweise der URL prüfen.")
        elif isinstance(reason, ssl.SSLError):
            _fail(res, "tls", f"TLS-Fehler: {reason}",
                  "Zertifikat, Proxy und URL prüfen; vibe prüft Zertifikate.")
        else:
            _fail(res, "network", f"{type(reason).__name__}: {reason}",
                  "Erreichbarkeit, Proxy und URL prüfen.")
    except Exception as ex:
        _fail(res, "protocol", f"{type(ex).__name__}: {ex}",
              "Antwort des Servers prüfen; erwartet wird MCP über Streamable HTTP.")
    return _finish(res, secrets)

def test(scope, name=None, entry=None):
    old = load(scope)[4].get(name) if name else None
    if entry is None: entry = old
    else: entry = merge_masked(entry, old)
    if not entry: raise ValueError("MCP-Server nicht gefunden")
    transport = entry.get("type")
    if transport not in SUPPORTED_TRANSPORTS:
        res = _result(str(transport) if transport else "?")
        _fail(res, "unsupported_transport",
              f"Transport '{transport}' wird nicht unterstützt.",
              "Unterstützt werden: local (Standard-Ein-/Ausgabe/stdio) und remote (Streamable HTTP). "
              "Das ist kein Hinweis auf einen defekten Server; andere Transporte werden von vibe nicht getestet.")
        return _finish(res, _secret_values(entry))
    if transport == "remote" and isinstance(entry.get("url"), str):
        scheme_match = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", entry["url"])
        scheme = scheme_match.group(1).lower() if scheme_match else ""
        if scheme and scheme not in ("http", "https"):
            res = _result(SUPPORTED_TRANSPORTS["remote"])
            _fail(res, "unsupported_transport",
                  f"Transport über '{scheme}://' wird nicht unterstützt.",
                  "Unterstützt wird Streamable HTTP über http:// oder https://. "
                  "WebSocket (ws://, wss://) und andere Transporte werden nicht getestet und sind kein Hinweis auf einen defekten Server.")
            return _finish(res, _secret_values(entry))
    try:
        validate(entry, extra_keys=_unknown_old_fields(old))
    except ValueError as ex:
        res = _result(SUPPORTED_TRANSPORTS.get(transport, transport))
        _fail(res, "config", "Ungültige Konfiguration: " + str(ex),
              "Den Eintrag korrigieren; es wurde nichts verändert oder gestartet.")
        return _finish(res, _secret_values(entry))
    cwd = vibe.ppath(scope) if scope != "global" else os.path.expanduser("~")
    return test_local(entry, cwd) if transport == "local" else test_remote(entry, name)

# ---------- Terminal ----------
def cli(action="list", name=None, scope="global", backup=None):
    try:
        if action == "list":
            rows = list_all()
            if not rows: print("Keine MCP-Server konfiguriert."); return
            print(vibe.col("b", f"{'Name':22}{'Geltung':16}{'Typ':8}{'aktiv':7}Ziel"))
            for r in rows:
                if r.get("error"): print(vibe.col("r", f"{r['scope']}: Konfiguration nicht lesbar: {r['error']}")); continue
                print(f"{r['name'][:21]:22}{('global' if r['scope'] == 'global' else r['scope'])[:15]:16}{r['type']:8}{('ja' if r['enabled'] else 'nein'):7}{r['target'][:60]}")
            print(vibe.col("d", "Echten Status je nach opencode-Version: 'opencode mcp list'. Geheimnisse werden hier maskiert."))
        elif action == "show":
            print(json.dumps(get_entry(scope, name)["entry"], indent=2, ensure_ascii=False))
        elif action in ("backups", "restore"):
            target_scope = name or "global"
            # Aufruf: vibe mcp restore <global|projekt> <sicherung>. Der Bereich
            # steht schon in `name`; das nächste Argument ist die Sicherung.
            chosen = backup if backup is not None else (scope if scope not in (None, "", "global") else None)
            if target_scope != "global": vibe.ppath(target_scope)
            rows = backups(target_scope)
            if action == "backups":
                if not rows: print("Keine Sicherung für Konfiguration von", target_scope); return
                print(vibe.col("b", f"Sicherungen für {cfg_path(target_scope)}:"))
                for row in reversed(rows): print("  " + row)
                print(vibe.col("d", "Wiederherstellen: vibe mcp restore " + target_scope + " <sicherung>"))
                return
            result = restore(target_scope, chosen)
            print(vibe.col("g", "Wiederhergestellt: " + cfg_path(target_scope) + " aus " + result["backup"]))
            if result["safety"]: print("Vorheriger Stand gesichert:", result["safety"])
        elif action == "test":
            print(vibe.col("y", "Hinweis: " + TEST_WARNING))
            r = test(scope, name)
            print((vibe.col("g", "OK") if r["ok"] else vibe.col("r", "FEHLER")), name, r.get("server") or "")
            print("  Transport:", r.get("transport", "?"))
            if r.get("category"): print("  Kategorie:", r["category"])
            for s in r["steps"]: print("  ", s)
            for n in r.get("notes", []): print("  ", n)
            for t in r["tools"]: print(f"   - {t['name']}: {t['description']}")
            if r["error"]: print(vibe.col("r", "  " + r["error"]))
            if r["hint"]: print(vibe.col("y", "  Hinweis: " + r["hint"]))
        elif action in ("on", "off"):
            toggle(scope, name, action == "on"); print(name, "aktiviert" if action == "on" else "deaktiviert")
        elif action == "rm":
            delete(scope, name); print("Gelöscht (Sicherung in config-backups):", name)
        else: sys.exit("vibe mcp list|show|test|on|off|rm [name] [global|<projekt>] | vibe mcp backups|restore <global|projekt> [sicherung]")
    except ValueError as e:
        sys.exit(str(e))
