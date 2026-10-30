"""vibe_mcp — MCP-Server aus opencode-Konfigurationen anzeigen, anlegen, bearbeiten, testen (nur Standardbibliothek)."""
import os, re, json, sys, time, queue, threading, subprocess, shutil
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
def _resolve(v):
    def env(m): return os.environ.get(m.group(1), "")
    def fil(m):
        try: return open(os.path.expanduser(m.group(1)), encoding="utf-8").read().strip()
        except Exception: return ""
    return re.sub(r"\{file:([^}]+)\}", fil, re.sub(r"\{env:([^}]+)\}", env, v))

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTO, "capabilities": {}, "clientInfo": {"name": "vibe", "version": "1.0"}}}

def _tools_from(msgs):
    return [{"name": t.get("name", "?"), "description": (t.get("description") or "")[:160]} for t in (msgs.get("result", {}).get("tools") or [])]

def test_local(entry, cwd):
    res = {"ok": False, "steps": [], "tools": [], "server": {}, "error": "", "hint": ""}
    cmd = [_resolve(x) for x in entry["command"]]
    env = dict(os.environ); env.update({k: _resolve(v) for k, v in (entry.get("environment") or {}).items()})
    timeout = max(5, min((entry.get("timeout") or 30000) / 1000.0, 90))
    wd = entry.get("cwd") or cwd
    if wd and not os.path.isabs(wd): wd = os.path.join(cwd, wd)
    if wd and not os.path.isdir(wd):
        res["error"] = f"Arbeitsordner nicht gefunden: {wd}"
        res["hint"] = "Der Arbeitsordner muss existieren; 'cwd' prüfen oder leer lassen."
        return res
    try: proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=wd or None, env=env, text=True, bufsize=1)
    except FileNotFoundError:
        res["error"] = f"Programm nicht gefunden: {cmd[0]}"; res["hint"] = "Ist es im Container installiert (z. B. npx über nodejs/npm)? Pfad oder Installation prüfen."; return res
    except Exception as ex:
        res["error"] = f"Start fehlgeschlagen: {ex}"; return res
    q, errbuf = queue.Queue(), []
    threading.Thread(target=lambda: [q.put(l) for l in proc.stdout], daemon=True).start()
    threading.Thread(target=lambda: [errbuf.append(l) for l in proc.stderr], daemon=True).start()
    def send(o):
        proc.stdin.write(json.dumps(o) + "\n"); proc.stdin.flush()
    def wait(id_):
        end = time.time() + timeout
        while time.time() < end:
            if proc.poll() is not None and q.empty(): return None
            try: line = q.get(timeout=0.5)
            except queue.Empty: continue
            try: m = json.loads(line)
            except Exception: continue
            if m.get("id") == id_: return m
        return None
    try:
        res["steps"].append("Prozess gestartet: " + " ".join(cmd)[:120])
        send(INIT); r = wait(1)
        if not r:
            res["error"] = "Keine Antwort auf 'initialize'" + (f" (Prozess beendet, Code {proc.poll()})" if proc.poll() is not None else f" innerhalb von {int(timeout)} s")
            res["hint"] = "Beim ersten Start lädt npx Pakete nach, das kann länger dauern: einmal manuell starten oder 'timeout' erhöhen. " + ("Letzte Fehlerausgabe: " + "".join(errbuf)[-300:] if errbuf else ""); return res
        if "error" in r: res["error"] = "initialize abgelehnt: " + json.dumps(r["error"])[:200]; return res
        res["server"] = r.get("result", {}).get("serverInfo", {}); res["steps"].append("initialize ok")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}); r2 = wait(2)
        if not r2: res["error"] = "Keine Antwort auf 'tools/list'"; return res
        if "error" in r2: res["error"] = "tools/list abgelehnt: " + json.dumps(r2["error"])[:200]; return res
        res["tools"] = _tools_from(r2); res["steps"].append(f"tools/list ok: {len(res['tools'])} Werkzeuge"); res["ok"] = True
    except BrokenPipeError:
        res["error"] = "Prozess hat die Verbindung geschlossen"; res["hint"] = "".join(errbuf)[-300:]
    finally:
        try: proc.kill()
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try: stream.close()
            except Exception: pass
    return res

def _parse_http(resp_text, ctype, id_):
    if "text/event-stream" in (ctype or ""):
        for line in resp_text.splitlines():
            if line.startswith("data:"):
                try:
                    m = json.loads(line[5:].strip())
                    if m.get("id") == id_: return m
                except Exception: pass
        return None
    try:
        m = json.loads(resp_text)
        if isinstance(m, list): m = next((x for x in m if x.get("id") == id_), None)
        return m
    except Exception: return None

def test_remote(entry, name):
    res = {"ok": False, "steps": [], "tools": [], "server": {}, "error": "", "hint": ""}
    url = _resolve(entry["url"]); headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    headers.update({k: _resolve(v) for k, v in (entry.get("headers") or {}).items()})
    timeout = max(5, min((entry.get("timeout") or 30000) / 1000.0, 60)); sid = None
    def post(body, h2=None):
        h = dict(headers); h.update(h2 or {})
        rq = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
        with urllib.request.urlopen(rq, timeout=timeout) as r: return r.status, r.headers, r.read().decode("utf-8", "replace")
    try:
        st, hd, body = post(INIT); sid = hd.get("Mcp-Session-Id") or hd.get("mcp-session-id")
        m = _parse_http(body, hd.get("Content-Type"), 1)
        if not m or "result" not in m: res["error"] = "Unerwartete Antwort auf 'initialize' (kein MCP-Streamable-HTTP-Server?)"; res["hint"] = body[:200]; return res
        res["server"] = m["result"].get("serverInfo", {}); res["steps"].append(f"initialize ok (HTTP {st})")
        h2 = {"Mcp-Session-Id": sid} if sid else {}; h2["MCP-Protocol-Version"] = m["result"].get("protocolVersion", PROTO)
        try: post({"jsonrpc": "2.0", "method": "notifications/initialized"}, h2)
        except urllib.error.HTTPError: pass
        st, hd, body = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, h2)
        m2 = _parse_http(body, hd.get("Content-Type"), 2)
        if not m2 or "result" not in m2: res["error"] = "Keine Werkzeugliste erhalten"; res["hint"] = body[:200]; return res
        res["tools"] = _tools_from(m2); res["steps"].append(f"tools/list ok: {len(res['tools'])} Werkzeuge"); res["ok"] = True
    except urllib.error.HTTPError as ex:
        res["error"] = f"HTTP {ex.code} {ex.reason}"
        if ex.code in (401, 403): res["hint"] = f"Anmeldung nötig. Mit OAuth: 'opencode mcp auth {name or '<name>'}'. Mit Schlüssel: 'headers' (z. B. Authorization) setzen und 'oauth': false."
        elif ex.code == 404: res["hint"] = "URL prüfen (Pfad, z. B. /mcp)."
    except Exception as ex:
        res["error"] = f"{type(ex).__name__}: {ex}"; res["hint"] = "Erreichbarkeit, Proxy und URL prüfen."
    return res

def test(scope, name=None, entry=None):
    old = load(scope)[4].get(name) if name else None
    if entry is None: entry = old
    else: entry = merge_masked(entry, old)
    if not entry: raise ValueError("MCP-Server nicht gefunden")
    validate(entry, extra_keys=_unknown_old_fields(old))
    cwd = vibe.ppath(scope) if scope != "global" else os.path.expanduser("~")
    return test_local(entry, cwd) if entry["type"] == "local" else test_remote(entry, name)

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
            r = test(scope, name); print((vibe.col("g", "OK") if r["ok"] else vibe.col("r", "FEHLER")), name, r.get("server") or "")
            for s in r["steps"]: print("  ", s)
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
