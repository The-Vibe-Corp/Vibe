"""vibe_mcp — MCP-Server aus opencode-Konfigurationen anzeigen, anlegen, bearbeiten, testen (nur Standardbibliothek)."""
import os, re, json, sys, time, queue, threading, subprocess, shutil
import urllib.request, urllib.error
import vibe

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

def _root_members(t):
    i = _skip_ws(t, 0)
    if i >= len(t) or t[i] != "{": raise ValueError("Die Konfiguration muss ein JSON-Objekt sein.")
    i += 1; members, last_end = {}, None
    while True:
        i = _skip_ws(t, i)
        if i >= len(t): raise ValueError("Objekt nicht geschlossen")
        if t[i] == "}": return members, i, last_end
        if t[i] == ",": i += 1; continue
        ke = _string_end(t, i); key = json.loads(t[i:ke]); i = _skip_ws(t, ke)
        if t[i] != ":": raise ValueError("':' erwartet")
        vs = _skip_ws(t, i + 1); ve = _skip_value(t, vs)
        members[key] = (vs, ve); last_end = ve; i = ve

def _dump(obj, base_indent="  "):
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    return s.replace("\n", "\n" + base_indent)

def jsonc_set_top(text, key, value):
    """Setzt/ersetzt den Wert eines Schlüssels der obersten Ebene; alles andere (auch Kommentare) bleibt unverändert."""
    if not text.strip(): return "{\n  " + json.dumps(key) + ": " + _dump(value) + "\n}\n"
    members, close, last_end = _root_members(text)
    new = _dump(value)
    if key in members:
        vs, ve = members[key]; return text[:vs] + new + text[ve:]
    pre = text[:close].rstrip()
    sep = ""
    if last_end is not None:
        nxt = _skip_ws(text, last_end)
        if not (nxt < len(text) and text[nxt] == ","): sep = ","
        pre = text[:last_end] + sep + text[last_end:close].rstrip()
    return pre + ("\n  " + json.dumps(key) + ": " + new + "\n") + text[close:]

# ---------- Konfigurationsdateien ----------
def oc_major():
    rc, out = vibe.sh("opencode --version", timeout=15)
    m = re.search(r"(\d+)\.\d+", out or "")
    return int(m.group(1)) if m else 0

def cfg_path(scope):
    base = os.path.expanduser("~/.config/opencode") if scope == "global" else vibe.ppath(scope)
    for n in ("opencode.jsonc", "opencode.json"):
        p = os.path.join(base, n)
        if os.path.exists(p): return p
    return os.path.join(base, "opencode.json")

def load(scope):
    p = cfg_path(scope)
    text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    data = jsonc_loads(text)
    mcp = data.get("mcp")
    if isinstance(mcp, dict) and isinstance(mcp.get("servers"), dict): layout, servers = "v2", mcp["servers"]
    elif isinstance(mcp, dict) and mcp: layout, servers = "klassisch", {k: v for k, v in mcp.items() if isinstance(v, dict)}
    else: layout, servers = ("v2" if oc_major() >= 2 else "klassisch"), {}
    return p, text, data, layout, servers

def _store(scope, p, text, data, layout, servers):
    if os.path.exists(p):
        d = os.path.join(vibe.TOOLS, "config-backups"); os.makedirs(d, exist_ok=True)
        shutil.copy2(p, os.path.join(d, f"{vibe.safe(scope)}-{os.path.basename(p)}-{time.strftime('%Y%m%d-%H%M%S')}"))
    mcp = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
    if layout == "v2":
        mcp = dict(mcp); mcp["servers"] = servers
    else:
        mcp = {k: v for k, v in mcp.items() if not isinstance(v, dict)}; mcp.update(servers)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(jsonc_set_top(text, "mcp", mcp))

# ---------- Schutz von Geheimnissen ----------
URL_SECRET = re.compile(r"((?:token|key|secret|password|auth|apikey|api_key)=)[^&#\s]+", re.I)
SECRET_KEY = re.compile(r"token|key|secret|pass|auth|bearer|credential|cookie", re.I)
def _is_secret(k, v):
    v = str(v)
    return v != "" and "{env:" not in v and "{file:" not in v and bool(SECRET_KEY.search(k))

def mask_entry(e):
    e = json.loads(json.dumps(e))
    for k in ("environment", "headers"):
        if isinstance(e.get(k), dict): e[k] = {a: (SECRET_MASK if _is_secret(a, b) else b) for a, b in e[k].items()}
    if isinstance(e.get("url"), str): e["url"] = URL_SECRET.sub(r"\1" + SECRET_MASK, e["url"])
    if isinstance(e.get("oauth"), dict): e["oauth"] = {a: (SECRET_MASK if a.lower() in ("clientsecret",) else b) for a, b in e["oauth"].items()}
    return e

def merge_masked(new, old):
    new = json.loads(json.dumps(new)); old = old or {}
    for k in ("environment", "headers"):
        if isinstance(new.get(k), dict):
            for a, b in list(new[k].items()):
                if b == SECRET_MASK: new[k][a] = (old.get(k) or {}).get(a, "")
    if isinstance(new.get("url"), str) and SECRET_MASK in new["url"] and isinstance(old.get("url"), str):
        new["url"] = old["url"] if URL_SECRET.sub(r"\1" + SECRET_MASK, old["url"]) == new["url"] else new["url"]
    if isinstance(new.get("oauth"), dict) and new["oauth"].get("clientSecret") == SECRET_MASK:
        new["oauth"]["clientSecret"] = (old.get("oauth") or {}).get("clientSecret", "")
    return new

# ---------- Anzeigen, anlegen, bearbeiten ----------
def list_all():
    out = []
    for scope in ["global"] + vibe.projects():
        try: p, _, _, layout, servers = load(scope)
        except Exception as ex:
            out.append({"scope": scope, "name": "(Konfiguration nicht lesbar)", "error": str(ex), "path": cfg_path(scope)}); continue
        for name, e in servers.items():
            me = mask_entry(e)
            target = " ".join(me.get("command", [])) if me.get("type") == "local" else me.get("url", "")
            out.append({"scope": scope, "name": name, "type": me.get("type", "?"), "enabled": me.get("enabled", True) is not False, "target": target, "layout": layout, "path": p})
    return out

def get_entry(scope, name):
    _, _, _, layout, servers = load(scope)
    if name not in servers: raise ValueError("MCP-Server nicht gefunden: " + name)
    return {"entry": mask_entry(servers[name]), "layout": layout, "path": cfg_path(scope)}

def validate(entry):
    if not isinstance(entry, dict): raise ValueError("Eintrag ungültig")
    t = entry.get("type")
    if t == "local":
        c = entry.get("command")
        if not (isinstance(c, list) and c and all(isinstance(x, str) and x for x in c)): raise ValueError("Lokal: 'command' braucht mindestens ein Element (Programm, dann Argumente).")
    elif t == "remote":
        u = entry.get("url")
        if not (isinstance(u, str) and re.match(r"^https?://\S+$", u)): raise ValueError("Remote: 'url' muss mit http:// oder https:// beginnen.")
    else: raise ValueError("type muss 'local' oder 'remote' sein.")
    for k in ("environment", "headers"):
        if k in entry and not (isinstance(entry[k], dict) and all(isinstance(a, str) and isinstance(b, str) for a, b in entry[k].items())): raise ValueError(f"'{k}' muss ein Objekt aus Text-Paaren sein.")
    if "enabled" in entry and not isinstance(entry["enabled"], bool): raise ValueError("'enabled' muss true oder false sein.")
    if "timeout" in entry and not isinstance(entry["timeout"], int): raise ValueError("'timeout' muss eine Zahl (Millisekunden) sein.")
    return entry

def save(scope, name, entry, old_name=None, create=False):
    if not NAME_OK.match(name or ""): raise ValueError("Name: Buchstaben, Ziffern, _ und - (Werkzeuge werden mit dem Namen als Präfix angeboten).")
    p, text, data, layout, servers = load(scope)
    old = servers.get(old_name or name)
    entry = validate(merge_masked(entry, old))
    if old_name and old_name != name:
        if name in servers: raise ValueError(f"'{name}' existiert schon.")
        servers.pop(old_name, None)
    elif create and name in servers: raise ValueError(f"'{name}' existiert schon. Zum Ändern bearbeiten statt neu anlegen.")
    servers[name] = entry
    _store(scope, p, text, data, layout, servers)
    return p

def delete(scope, name):
    p, text, data, layout, servers = load(scope)
    if name not in servers: raise ValueError("MCP-Server nicht gefunden: " + name)
    servers.pop(name); _store(scope, p, text, data, layout, servers)

def toggle(scope, name, enabled=None):
    p, text, data, layout, servers = load(scope)
    if name not in servers: raise ValueError("MCP-Server nicht gefunden: " + name)
    e = servers[name]; e["enabled"] = (not (e.get("enabled", True) is not False)) if enabled is None else bool(enabled)
    _store(scope, p, text, data, layout, servers); return e["enabled"]

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
    try: proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=wd if wd and os.path.isdir(wd) else None, env=env, text=True, bufsize=1)
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
    if entry is None: entry = load(scope)[4].get(name)
    else: entry = merge_masked(entry, load(scope)[4].get(name) if name else None)
    if not entry: raise ValueError("MCP-Server nicht gefunden")
    validate(entry)
    cwd = vibe.ppath(scope) if scope != "global" else os.path.expanduser("~")
    return test_local(entry, cwd) if entry["type"] == "local" else test_remote(entry, name)

# ---------- Terminal ----------
def cli(action="list", name=None, scope="global"):
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
        else: sys.exit("vibe mcp list|show|test|on|off|rm [name] [global|<projekt>]")
    except ValueError as e:
        sys.exit(str(e))
