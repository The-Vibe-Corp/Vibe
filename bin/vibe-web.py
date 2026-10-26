#!/usr/bin/env python3
"""vibe-web — lokales Dashboard (nur Standardbibliothek). Start über: vibe ui"""
import os, sys, json, re, time, secrets, threading, subprocess, io, contextlib
import importlib.util, importlib.machinery
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("VIBE_NO_CONTAINER", "1")
_loader = importlib.machinery.SourceFileLoader("vibe", os.path.join(HERE, "vibe"))
_spec = importlib.util.spec_from_loader("vibe", _loader)
vibe = importlib.util.module_from_spec(_spec); sys.modules["vibe"] = vibe; _loader.exec_module(vibe)
import vibe_mcp

PORT = int(os.environ.get("VIBE_UI_PORT", vibe.UI_PORT))
os.makedirs(vibe.LOGS, exist_ok=True)
TOKFILE = os.path.join(vibe.LOGS, "web.token")
TOKEN = secrets.token_urlsafe(24)
open(TOKFILE, "w").write(TOKEN)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SRV = None

def call(fn, *a, **k):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            fn(*a, **k)
        return True, ANSI.sub("", buf.getvalue()).strip()
    except SystemExit as e:
        return False, (str(e.code) if e.code not in (None, 0) else ANSI.sub("", buf.getvalue()).strip())
    except Exception as e:
        return False, str(e)

def known(n):
    if n not in vibe.projects(): raise AssertionError("Unbekanntes Projekt: " + n)
    return n

def known_scope(s):
    if s != "global": known(s)
    return s

def tail(path, n=120):
    if not os.path.exists(path): return []
    with open(path, "rb") as f:
        data = f.read()[-60000:]
    return ANSI.sub("", data.decode("utf-8", "replace")).splitlines()[-n:]

def project_row(n):
    br, dirty, last = vibe.git_info(n); items = vibe.open_items(n)
    return {"name": n, "type": vibe.ptype(n), "branch": br, "dirty": dirty, "last": last, "open": len(items), "path": vibe.ppath(n),
            "running": vibe.tmux_has(n), "init": vibe.is_init(n), "log": os.path.exists(vibe.logpath(n)),
            "pause_after": vibe.pause_after_active(n)}

def project_detail(n):
    d = project_row(n)
    d["items"] = [{"id": i, "title": t, "state": s} for i, t, s in vibe.open_items(n)]
    d["feedback"] = vibe.feedback_items(n)
    d["tail"] = tail(vibe.logpath(n), 80)
    d["verify_cmd"] = bool(vibe.verify_command(n, "quick"))
    d["env"] = vibe.penv(n)
    try:
        d["write_dirs"] = vibe.write_dirs(n)
        d["write_dirs_error"] = None
    except ValueError as e:
        d["write_dirs"] = []
        d["write_dirs_error"] = str(e)
    d["write_dirs_default"] = vibe.write_dirs_default(n)
    d["write_dirs_custom"] = vibe.write_dirs_custom(n)
    try:
        d["sandbox"] = vibe.sandbox_status(n)
    except Exception as e:
        d["sandbox"] = {"enabled": False, "tools": [], "write_dirs": [], "tool_caches": [],
                        "missing_tools": [], "bwrap": "", "state_dir": "", "error": str(e)}
    return d

def roots_info():
    pm = vibe.project_map(); out = []
    for r in vibe.roots():
        out.append({"path": r, "fixed": r == vibe.VIBE, "projects": [k for k, v in pm.items() if os.path.dirname(v) == r]})
    return out

def agents_info():
    info = vibe.models_info()
    ps = vibe.projects()
    write_dirs, write_dirs_errors = {}, {}
    for p in ps:
        try:
            write_dirs[p] = vibe.write_dirs(p)
        except ValueError as e:
            write_dirs[p] = []
            write_dirs_errors[p] = str(e)
    return {"agents": vibe.agents_all(), "projects": ps, "models": vibe.models_list(),
            "info": {m["id"]: m for m in info.get("models", [])}, "stand": info.get("stand", ""), "hinweis": info.get("hinweis", ""),
            "perms": vibe.PERM_LABELS, "perms_project": vibe.PERM_LABELS_PROJECT,
            "write_dirs": write_dirs, "write_dirs_errors": write_dirs_errors, "profiles": vibe.profiles_load()}

def verify_bg(n, mode):
    argv = vibe.verify_argv(n, mode)
    if not argv: return False, "Keine Prüfbefehle in .vibe/project.env"
    lg = open(vibe.logpath(n, "verify"), "w")
    lg.write(f"$ {vibe.verify_command(n, mode)}\n"); lg.flush()
    subprocess.Popen(argv, cwd=vibe.ppath(n), stdout=lg, stderr=subprocess.STDOUT)
    return True, "Prüfung gestartet"

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else body.encode())
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def _ok(self, q=None):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"): return False
        t = self.headers.get("X-Token") or (q or {}).get("t", [""])[0]
        return secrets.compare_digest(t, TOKEN)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/": return self._send(200, PAGE, "text/html")
        if not self._ok(q): return self._send(403, {"error": "Token fehlt oder falsch"})
        try:
            if u.path == "/api/projects": return self._send(200, [project_row(n) for n in vibe.projects()])
            if u.path == "/api/project": return self._send(200, project_detail(known(q["name"][0])))
            if u.path == "/api/roots": return self._send(200, roots_info())
            if u.path == "/api/agents": return self._send(200, agents_info())
            if u.path == "/api/agent":
                scope = known_scope(q["scope"][0]); return self._send(200, {"text": vibe.agent_read(scope, q["name"][0])})
            if u.path == "/api/mcp": return self._send(200, {"servers": vibe_mcp.list_all(), "projects": vibe.projects()})
            if u.path == "/api/mcp_entry":
                scope = known_scope(q["scope"][0]); return self._send(200, vibe_mcp.get_entry(scope, q["name"][0]))
            if u.path == "/api/types": return self._send(200, vibe.types())
            if u.path == "/api/doctor": return self._send(200, [{"label": a, "ok": b, "hint": c} for a, b, c in vibe.doctor_checks()])
            if u.path == "/api/fritz": return self._send(200, vibe.fritz_status())
            if u.path == "/api/server": h = vibe.server_health(); return self._send(200, {"up": bool(h), "url": vibe.OC_URL, "info": h})
            if u.path == "/api/stream": return self.stream(known(q["name"][0]), q.get("kind", ["run"])[0])
        except (AssertionError, ValueError) as e:
            return self._send(404, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "nicht gefunden"})
    def do_POST(self):
        u = urlparse(self.path)
        if not self._ok(): return self._send(403, {"error": "Token fehlt oder falsch"})
        try:
            n = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(n) or b"{}")
            name = body.get("name", "")
            if u.path in ("/api/run", "/api/stop", "/api/verify", "/api/feedback", "/api/init", "/api/rights", "/api/pause", "/api/sandbox"): known(name)
            extra = {}
            if u.path == "/api/run": ok, msg = call(vibe.cmd_run, name, body.get("agent") or None)
            elif u.path == "/api/stop": ok, msg = call(vibe.cmd_stop, name)
            elif u.path == "/api/verify": ok, msg = verify_bg(name, "full" if body.get("mode") == "full" else "quick")
            elif u.path == "/api/init": ok, msg = call(vibe.cmd_init, name, body.get("type") or None)
            elif u.path == "/api/feedback":
                act = body.get("action") or "add"
                try:
                    if act == "add":
                        t = (body.get("title") or "").strip(); assert t, "Titel fehlt"
                        num = vibe.add_feedback(name, t, body.get("description", "")); ok, msg = True, f"F{num} eingetragen"
                    elif act == "update":
                        fid = (body.get("id") or "").strip(); assert fid, "Feedback-ID fehlt"
                        vibe.feedback_update(name, fid, body.get("title"), body.get("description", "")); ok, msg = True, f"{fid} gespeichert"
                    elif act == "delete":
                        fid = (body.get("id") or "").strip(); assert fid, "Feedback-ID fehlt"
                        vibe.feedback_delete(name, fid); ok, msg = True, f"{fid} gelöscht"
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/new": ok, msg = call(vibe.cmd_new, name, body.get("type", "generic"), body.get("tpl") or None)
            elif u.path == "/api/roots":
                act = body.get("action"); path = body.get("path", "")
                try:
                    if act == "add": p = vibe.root_add(path)
                    elif act == "remove": vibe.root_remove(path); p = path
                    else: vibe._pm.clear(); p = ""
                    pm = vibe.project_map(); found = [k for k, v in pm.items() if p and os.path.dirname(v) == os.path.abspath(os.path.expanduser(p))]
                    ok, msg = True, (f"{len(found)} Projekt(e) in {p}: {', '.join(found) or '-'}" if act == "add" else "OK")
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/rights":
                act = body.get("action"); ok, msg, changed = True, "", None
                try:
                    if act == "add":
                        dirs = vibe.write_dirs_add(name, body.get("path", "")); msg = "Verzeichnis hinzugefügt"
                    elif act in ("remove", "rm"):
                        dirs = vibe.write_dirs_remove(name, body.get("path", "")); msg = "Verzeichnis entfernt"
                    elif act == "reset":
                        dirs = vibe.write_dirs_reset(name); msg = "Standardverzeichnisse wiederhergestellt"
                    elif act == "apply":
                        dirs = vibe.write_dirs(name); changed = vibe.apply_write_dirs_to_project(name)
                        msg = ("Schreibrechte auf " + str(len(changed)) + " Projektagent(en) angewendet: " + ", ".join(changed)) if changed else "Nichts geändert – keine Projektagenten mit Schreibrecht vorhanden"
                    else:
                        ok, msg, dirs = False, "Unbekannte Aktion", None
                    if dirs is not None:
                        extra["write_dirs"] = dirs; extra["custom"] = vibe.write_dirs_custom(name)
                    if changed is not None: extra["changed"] = changed
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/sandbox":
                act = body.get("action"); ok, msg, status = True, "", None
                try:
                    if act == "on":
                        status = vibe.sandbox_set(name, True); msg = "Sandbox eingeschaltet"
                    elif act == "off":
                        status = vibe.sandbox_set(name, False); msg = "Sandbox ausgeschaltet"
                    elif act == "tools":
                        status = vibe.sandbox_tools(name, body.get("tools", "")); msg = "Build-Werkzeuge gespeichert"
                    elif act == "check":
                        checked = vibe.sandbox_check(name); ok, msg = checked["ok"], checked["message"]
                        status = vibe.sandbox_status(name); extra["check"] = checked
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    if status is not None: extra["sandbox"] = status
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/pause":
                act = body.get("action") or "on"; ok, msg = True, ""
                try:
                    if act in ("on", "an", "request"):
                        vibe.pause_after_request(name); msg = "Pause nach dem aktuellen Arbeitspaket angefordert"
                    elif act in ("off", "aus", "cancel"):
                        released = vibe.pause_after_cancel(name)
                        msg = "Pause-Anforderung aufgehoben" if released else "Keine Pause angefordert"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    extra["pause_after"] = vibe.pause_after_active(name)
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/fritz":
                act = body.get("action"); ok, msg = True, ""
                try:
                    if act in ("automation", "on", "off", "set"):
                        enabled = (act == "on") if act in ("on", "off") else body.get("enabled")
                        if not isinstance(enabled, bool):
                            raise ValueError("enabled muss true oder false sein")
                        vibe.fritz_automation_set(enabled)
                        msg = "Fritzbox-Automatik " + ("an" if enabled else "aus")
                    elif act == "reconnect":
                        result = vibe.fritz_reconnect(); extra["result"] = result
                        ok, msg = result["ok"], result["message"]
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
                extra["fritz"] = vibe.fritz_status()
            elif u.path == "/api/agent_template":
                scope = known_scope(body.get("scope", "global"))
                dirs = vibe.write_dirs(scope) if scope != "global" else None
                ok, msg = True, vibe.agent_template(body.get("description", ""), body.get("mode", "subagent"), body.get("model", ""), body.get("temperature", ""), body.get("steps", ""), body.get("perm", "lesen"), body.get("prompt", ""), write_dirs=dirs)
            elif u.path == "/api/agent":
                act = body.get("action"); scope = known_scope(body.get("scope", "global")); an = body.get("name", "")
                try:
                    if act == "save": warn = vibe.agent_write(scope, an, body.get("text", ""), create=bool(body.get("create"))); ok, msg = True, "Gespeichert" + (" – Hinweis: " + " ".join(warn) if warn else "")
                    elif act == "delete": vibe.agent_delete(scope, an); ok, msg = True, "Gelöscht (Sicherung in agent-backups)"
                    elif act == "copy": vibe.agent_copy(scope, an, known_scope(body.get("to", "global"))); ok, msg = True, "Kopiert"
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/mcp":
                act = body.get("action"); scope = known_scope(body.get("scope", "global")); entry = body.get("entry")
                try:
                    if act == "save": p = vibe_mcp.save(scope, name, entry, body.get("old_name") or None, bool(body.get("create"))); ok, msg = True, "Gespeichert in " + p + " (Sicherung in config-backups). opencode liest die Konfiguration beim nächsten Start."
                    elif act == "delete": vibe_mcp.delete(scope, name); ok, msg = True, "Gelöscht (Sicherung in config-backups)"
                    elif act == "toggle": en = vibe_mcp.toggle(scope, name); ok, msg = True, "aktiviert" if en else "deaktiviert"
                    elif act == "test": extra["result"] = vibe_mcp.test(scope, name or None, entry); ok, msg = True, "Test beendet"
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/profiles":
                act = body.get("action")
                try:
                    if act == "save":
                        d = vibe.profiles_load(); data = body.get("data") or {}
                        for k in ("rollen", "profile"):
                            if isinstance(data.get(k), dict): d[k] = data[k]
                        vibe.profiles_save(d); ok, msg = True, "Profile gespeichert"
                    elif act == "use":
                        done, skipped = vibe.profile_apply(body.get("profile", "")); ok, msg = True, "Angewendet: " + "; ".join(done) + (" | übersprungen: " + "; ".join(skipped) if skipped else "")
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/model": ok, msg = call(vibe.cmd_model, body.get("agent", ""), body.get("model", ""), body.get("scope", "global"))
            elif u.path == "/api/server": ok, msg = call(vibe.cmd_server, "start" if body.get("action") == "start" else "stop")
            elif u.path == "/api/shutdown":
                self._send(200, {"ok": True, "message": "Dashboard wird beendet"})
                threading.Thread(target=lambda: (time.sleep(0.5), SRV.shutdown()), daemon=True).start(); return
            else: return self._send(404, {"error": "nicht gefunden"})
            out = {"ok": ok, "message": msg}; out.update(extra)
            self._send(200 if ok else 400, out)
        except AssertionError as e:
            self._send(400, {"ok": False, "message": str(e)})
        except Exception as e:
            self._send(500, {"ok": False, "message": f"{type(e).__name__}: {e}"})
    def stream(self, name, kind):
        path = vibe.logpath(name, "verify" if kind == "verify" else "run")
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store"); self.end_headers()
        def send(lines):
            self.wfile.write(("data: " + json.dumps(lines, ensure_ascii=False) + "\n\n").encode()); self.wfile.flush()
        try:
            pos = os.path.getsize(path) if os.path.exists(path) else 0
            send(tail(path, 80) or ["(noch keine Ausgabe)"])
            while True:
                time.sleep(1)
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    if size < pos: pos = 0
                    if size > pos:
                        with open(path, "rb") as f:
                            f.seek(pos); chunk = f.read(); pos = size
                        send(ANSI.sub("", chunk.decode("utf-8", "replace")).splitlines()); continue
                self.wfile.write(b": ping\n\n"); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

PAGE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>vibe</title><style>
:root{--bg:#14161a;--card:#1d2026;--line:#2c313a;--tx:#e6e8eb;--mut:#8b93a1;--ac:#5aa9ff;--ok:#4cc38a;--warn:#f2b84b;--bad:#f06a6a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 system-ui,sans-serif}
header{display:flex;gap:16px;align-items:center;padding:10px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:16px;margin:0}nav button{background:none;border:0;color:var(--mut);padding:8px 12px;cursor:pointer;font-size:14px}
nav button.on{color:var(--tx);border-bottom:2px solid var(--ac)}main{padding:18px;max-width:1300px;margin:auto}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mut);font-weight:500}
tr.row{cursor:pointer}tr.row:hover{background:#1a1d23}.pill{padding:2px 8px;border-radius:10px;font-size:12px;background:#2a2f38;white-space:nowrap}
.run{background:#17382a;color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.ok{color:var(--ok)}.mut{color:var(--mut)}
.pill.ok{background:#17382a}.pill.warn{background:#3a3016}.pill.bad{background:#3d1d1d}.pill.mut{background:#2a2f38}
button.b{background:#2a2f38;color:var(--tx);border:1px solid var(--line);padding:6px 12px;border-radius:6px;cursor:pointer}button.b:hover{border-color:var(--ac)}
button.p{background:var(--ac);color:#06121f;border-color:var(--ac)}button.d{border-color:var(--bad);color:var(--bad)}button.quit{background:#5a1d1d;border-color:var(--bad);color:#fff;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px}
pre#log{background:#0d0f12;border:1px solid var(--line);border-radius:6px;padding:10px;height:320px;overflow:auto;white-space:pre-wrap;font:12px/1.4 ui-monospace,monospace;margin:0}
input,textarea,select{background:#0d0f12;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:6px;width:100%}label{display:block;margin:8px 0 2px;color:var(--mut);font-size:12px}
input[type=checkbox]{width:auto}textarea.raw{font:12px/1.4 ui-monospace,monospace;min-height:360px}details summary{cursor:pointer;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.bar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}a{color:var(--ac)}
.err{border-color:var(--bad)}.detail td{background:#181b20}ul.l{margin:4px 0 8px 18px;padding:0}.sep{width:1px;height:22px;background:var(--line)}@media(max-width:900px){.grid,.grid3{grid-template-columns:1fr}}
.logcard{display:flex;flex-direction:column;min-height:0}.logcard.full{position:fixed;inset:8px;z-index:100;margin:0;box-shadow:0 0 0 1px var(--line),0 12px 40px #000a}
.logcard.full pre#log{flex:1 1 auto;height:auto;min-height:0}body.logfull{overflow:hidden}
.fbentry{border-top:1px solid var(--line);padding:8px 0}.fbentry:first-child{border-top:0}.fbdesc{white-space:pre-wrap;margin:2px 0 6px}.fbentry .bar{margin:4px 0 0}
</style></head><body>
<header><h1>vibe</h1><nav id="nav"></nav><span id="srv" style="margin-left:auto;display:flex;gap:8px;align-items:center"></span></header><main id="main"></main>
<script>
const T=(()=>{const m=location.hash.match(/t=([^&]+)/);if(m){sessionStorage.t=m[1];history.replaceState(null,'',location.pathname)}return sessionStorage.t||''})();
async function api(p,body){const o=body?{method:'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:JSON.stringify(body)}:{headers:{'X-Token':T}};
 const r=await fetch(p,o);const j=await r.json().catch(()=>({}));if(!r.ok&&!body)throw new Error(j.error||('HTTP '+r.status));return j}
function el(t,a={},...c){const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='on')for(const[ev,f]of Object.entries(v))e.addEventListener(ev,f);else if(k==='class')e.className=v;else if(k==='value')e.value=v;else e.setAttribute(k,v)}
 for(const x of c.flat())if(x!==null&&x!==undefined&&x!==false)e.append(x.nodeType?x:document.createTextNode(String(x)));return e}
const main=document.getElementById('main'),nav=document.getElementById('nav'),srvbox=document.getElementById('srv');let tab='projects',es=null,timer=null,LOG=null;
function showErr(e){main.replaceChildren(el('div',{class:'card err'},el('b',{class:'bad'},'Fehler: '),String(e&&e.message||e)),el('button',{class:'b',on:{click:()=>setTab('projects')}},'← zur Projektliste'))}
function setTab(t){exitLogFull();LOG=null;tab=t;if(es){es.close();es=null}clearInterval(timer);[...nav.children].forEach(b=>b.classList.toggle('on',b.dataset.t===t));Promise.resolve(({projects,agents,mcp,env}[t])()).catch(showErr);header()}
[['projects','Projekte'],['agents','Agenten & Modelle'],['mcp','MCP-Tools'],['env','Umgebung']].forEach(([k,l])=>nav.append(el('button',{'data-t':k,on:{click:()=>setTab(k)}},l)));
function toast(m){alert(m)}
function setLogFull(on){if(!LOG)return;LOG.card.classList.toggle('full',on);document.body.classList.toggle('logfull',on);LOG.button.textContent=on?'Verkleinern':'Vergrößern';if(on)LOG.pre.style.height='auto';else LOG.fit()}
function exitLogFull(){if(LOG&&LOG.card.classList.contains('full'))setLogFull(false)}
window.addEventListener('keydown',e=>{if(e.key==='Escape')exitLogFull()});
window.addEventListener('resize',()=>{if(LOG)LOG.fit()});
const GOOD=['sehr schnell','schnell','gering','geeignet','gut','ja'],MID=['mittel','bedingt','unklar'],BAD=['langsam','hoch','eingeschränkt','nicht empfohlen','nein'];
function badge(v){v=v||'?';return el('span',{class:'pill '+(GOOD.includes(v)?'ok':MID.includes(v)?'warn':BAD.includes(v)?'bad':'mut')},v)}
async function header(){try{const s=await api('/api/server');srvbox.replaceChildren(el('span',{class:s.up?'ok':'mut'},'opencode-Server: '+(s.up?'an':'aus')),
  el('button',{class:'b',title:'Startet/stoppt nur den gemeinsamen opencode-Server (Weboberfläche), nicht dieses Dashboard',on:{click:async()=>{toast((await api('/api/server',{action:s.up?'stop':'start'})).message);header()}}},s.up?'opencode stoppen':'opencode starten'),el('span',{class:'sep'}),
  el('button',{class:'b quit',title:'Beendet diese App (das Dashboard), nicht opencode',on:{click:async()=>{if(!confirm('Dashboard (diese App) beenden? Laufende Agentenläufe in tmux laufen weiter.'))return;await api('/api/shutdown',{});
   main.replaceChildren(el('div',{class:'card'},'Dashboard beendet. Neu starten im Terminal: vibe ui'));srvbox.replaceChildren()}}},'Dashboard beenden'))}catch(e){}}
async function rootsCard(){const rs=await api('/api/roots');const inp=el('input',{placeholder:'/var/mnt/data/.../mein-entwicklungsordner'});
 const rows=rs.map(r=>el('div',{class:'bar'},el('b',{},r.path),el('span',{class:'mut'},r.projects.length+' Projekt(e)'+(r.projects.length?': '+r.projects.join(', '):'')),
  r.fixed?el('span',{class:'pill'},'Standard'):el('button',{class:'b d',on:{click:async()=>{await api('/api/roots',{action:'remove',path:r.path});setTab('projects')}}},'entfernen')));
 return el('div',{class:'card'},el('b',{},'Entwicklungsordner'),...rows,el('label',{},'Ordner hinzufügen und Projekte darin einlesen (jeder Unterordner mit .git)'),
  el('div',{class:'bar'},inp,el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/roots',{action:'add',path:inp.value});toast(r.message);setTab('projects')}}},'Einlesen'),
   el('button',{class:'b',on:{click:async()=>{await api('/api/roots',{action:'scan'});setTab('projects')}}},'Neu einlesen')))}
async function projects(){
 if(!T){main.replaceChildren(el('div',{class:'card'},'Token fehlt. Dashboard mit "vibe ui" öffnen (der Link enthält das Token).'));return}
 const render=async()=>{const ps=await api('/api/projects');
  const tb=el('table',{},el('tr',{},...['Projekt','Typ','Branch','Offen','Änd.','Lauf','Letzter Commit'].map(h=>el('th',{},h))));
  ps.forEach(p=>tb.append(el('tr',{class:'row',on:{click:()=>detail(p.name).catch(showErr)}},el('td',{},p.name,p.init?null:el('span',{class:'warn'},' ●')),el('td',{},p.type),el('td',{},p.branch),
   el('td',{class:p.open?'warn':'ok'},p.open),el('td',{},p.dirty),el('td',{},el('span',{class:'pill '+(p.running?'run':'')},p.running?'läuft':'-'),p.pause_after?el('span',{class:'pill warn',title:'Nach dem aktuellen Arbeitspaket wird kein neues gestartet'},' Pause'):null),el('td',{class:'mut'},p.last))));
  const rc=await rootsCard();
  main.replaceChildren(el('div',{class:'card'},ps.length?tb:el('span',{class:'mut'},'Keine Projekte gefunden. Entwicklungsordner unten hinzufügen.'),ps.some(p=>!p.init)?el('div',{class:'warn',style:'margin-top:8px'},'● = noch nicht für vibe vorbereitet (Projekt öffnen → „Für vibe vorbereiten“)'):null),rc,newForm())};
 await render();timer=setInterval(()=>{if(tab==='projects'&&!document.activeElement.matches('input,textarea,select'))render().catch(()=>{})},5000)}
function newForm(){const types=el('select',{});api('/api/types').then(t=>t.forEach(x=>types.append(el('option',{},x))));
 const nm=el('input',{placeholder:'projektname (a-z, 0-9, -)'}),tp=el('input',{placeholder:'nur Android: Vorlage aus "android create --list"'});
 return el('div',{class:'card',id:'nf'},el('b',{},'Neues Projekt (im Standardordner)'),el('div',{class:'grid'},el('div',{},el('label',{},'Name'),nm),el('div',{},el('label',{},'Typ'),types)),el('label',{},'Android-Vorlage'),tp,
  el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/new',{name:nm.value,type:types.value,tpl:tp.value});toast(r.message);setTab('projects')}}},'Anlegen')))}
async function detail(name){clearInterval(timer);if(es){es.close();es=null}exitLogFull();LOG=null;window.scrollTo(0,0);
 const d=await api('/api/project?name='+encodeURIComponent(name));const logEl=el('pre',{id:'log'},(d.tail||[]).join('\n')||'(noch keine Ausgabe)');
 const items=el('div',{},d.items.length?d.items.map(i=>el('div',{},el('span',{class:i.state==='BLOCKIERT'?'bad':'warn'},i.state+' '),el('b',{},i.id+' '),i.title)):el('span',{class:'ok'},'Alles abgehakt'));
 const f={t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was soll geändert oder ergänzt werden?'})};
 const act=(p,b)=>async()=>{const r=await api(p,b);toast(r.message);detail(name).catch(showErr)};
 const tsel=el('select',{});api('/api/types').then(t=>t.forEach(x=>{const o=el('option',{},x);if(x===d.type)o.selected=true;tsel.append(o)}));
 const initCard=d.init?null:el('div',{class:'card'},el('b',{class:'warn'},'Noch nicht für vibe vorbereitet'),el('div',{class:'mut'},'Ergänzt fehlende Dateien (FEEDBACK.md, TICKETS.md, AGENTS.md, .vibe/project.env). Vorhandenes wird nie überschrieben, es wird nichts committet.'),
   el('div',{class:'bar'},tsel,el('button',{class:'b p',on:{click:act('/api/init',{name,type:tsel.value})}},'Für vibe vorbereiten')));
 let logPaused=false,logBuf='';
 const pauseBtn=el('button',{class:'b'},'Pause'),fullBtn=el('button',{class:'b'},'Vergrößern');
 const logCard=el('div',{class:'card logcard'});
 const appendLog=t=>{const near=logEl.scrollHeight-logEl.scrollTop-logEl.clientHeight<60;logEl.textContent+=t;if(logEl.textContent.length>80000)logEl.textContent=logEl.textContent.slice(-60000);if(near)logEl.scrollTop=logEl.scrollHeight};
 const fitLog=()=>{if(logCard.classList.contains('full'))return;const h=Math.max(240,window.innerHeight-logEl.getBoundingClientRect().top-18);logEl.style.height=h+'px'};
 pauseBtn.addEventListener('click',()=>{logPaused=!logPaused;pauseBtn.textContent=logPaused?'Fortsetzen':'Pause';pauseBtn.classList.toggle('p',logPaused);if(!logPaused&&logBuf){appendLog(logBuf);logBuf='';logEl.scrollTop=logEl.scrollHeight}});
 fullBtn.addEventListener('click',()=>setLogFull(!logCard.classList.contains('full')));
 LOG={card:logCard,pre:logEl,button:fullBtn,fit:fitLog};
 main.replaceChildren(...[el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>setTab('projects')}},'← zurück'),el('h2',{style:'margin:0'},name),el('span',{class:'pill '+(d.running?'run':'')},d.running?'läuft':'gestoppt'),el('span',{class:'mut'},d.type+' · '+d.branch+' · '+d.dirty+' Änderungen · '+d.path)),
  initCard,
  pauseCard(d,name),
  el('div',{class:'bar'},el('button',{class:'b p',on:{click:act('/api/run',{name})}},'Agentenlauf starten'),el('button',{class:'b',on:{click:act('/api/stop',{name})}},'Stoppen'),
   el('button',{class:'b',on:{click:()=>{act('/api/verify',{name,mode:'quick'})();stream('verify')}}},'Prüfung quick'),el('button',{class:'b',on:{click:()=>{act('/api/verify',{name,mode:'full'})();stream('verify')}}},'Prüfung full'),
   el('button',{class:'b',on:{click:()=>stream('run')}},'Lauf-Log'),el('a',{href:'http://127.0.0.1:4096',target:'_blank'},'opencode-Weboberfläche')),
  el('div',{class:'grid'},el('div',{},el('div',{class:'card'},el('b',{},'Offene Arbeitspakete ('+d.items.length+')'),items),
   feedbackCard(d,name),
   rightsCard(d,name),
   sandboxCard(d,name),
   el('div',{class:'card'},el('b',{},'Feedback eintragen'),el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
    el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/feedback',{name,title:f.t.value,description:f.b.value});toast(r.message);detail(name).catch(showErr)}}},'Eintragen')))),
   logCard)].filter(Boolean));
 logCard.append(el('div',{class:'bar'},el('b',{},'Live-Ausgabe'),pauseBtn,fullBtn),logEl);
 fitLog();
 function stream(kind){if(es)es.close();logEl.textContent='';logPaused=false;logBuf='';pauseBtn.textContent='Pause';pauseBtn.classList.remove('p');es=new EventSource('/api/stream?name='+encodeURIComponent(name)+'&kind='+kind+'&t='+encodeURIComponent(T));
  es.onmessage=ev=>{const chunk=JSON.parse(ev.data).join('\n')+'\n';if(logPaused){logBuf=(logBuf+chunk).slice(-80000);return}appendLog(chunk)}}
 stream('run')}
function pauseCard(d,name){
 const active=!!d.pause_after;
 const btn=el('button',{class:'b'+(active?' p':''),on:{click:async()=>{const r=await api('/api/pause',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Pause aufheben':'Nach aktuellem Paket anhalten');
 return el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Arbeitspaket-Pause'),el('span',{class:'pill '+(active?'warn':'mut')},active?'Pause angefordert':'keine Pause'),btn),
  el('div',{class:'mut'},'Der laufende Agent wird nicht unterbrochen. Nach dem aktuellen Arbeitspaket startet der Läufer kein neues Paket; die Anforderung gilt einmalig und wird beim Anhalten verbraucht.'))}
function feedbackCard(d,name){const list=el('div',{});const cls=s=>s==='erledigt'?'ok':s==='BLOCKIERT'?'bad':'warn';
 const done=d.feedback.filter(i=>i.completed),pending=d.feedback.filter(i=>!i.completed);let showDone=false;
 const toggle=el('button',{class:'b'});
 const delBtn=i=>el('button',{class:'b d',on:{click:async()=>{if(!confirm('Feedback '+i.id+' wirklich löschen?'))return;const r=await api('/api/feedback',{name,action:'delete',id:i.id});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Löschen');
 const rowFor=i=>{const row=el('div',{class:'fbentry','data-id':i.id});
  row.append(el('div',{},el('span',{class:'pill '+cls(i.state)},i.state),el('b',{},' '+i.id+' '+i.title)),
   ...(i.description?[el('div',{class:'mut fbdesc'},i.description)]:[]),
   el('div',{class:'bar'},
    ...(i.completed?[el('span',{class:'mut'},'abgeschlossen – nicht bearbeitbar')]:[el('button',{class:'b',on:{click:()=>edit(i,row)}},'Bearbeiten')]),
    delBtn(i)));
  return row};
 const draw=()=>{const shown=showDone?d.feedback:pending;
  list.replaceChildren(...(shown.length?shown.map(rowFor):[el('span',{class:'mut'},showDone?'Noch kein Feedback vorhanden.':'Keine offenen Feedback-Punkte.')]));
  toggle.textContent=showDone?'Abgeschlossene ausblenden':'Abgeschlossene anzeigen ('+done.length+')';
  toggle.classList.toggle('p',showDone);toggle.setAttribute('aria-expanded',showDone?'true':'false');
  toggle.style.display=done.length?'':'none'};
 const edit=(i,row)=>{const t=el('input',{value:i.title}),b=el('textarea',{rows:4,value:i.description||''});
  const ed=el('div',{class:'fbentry','data-id':i.id},el('label',{},'Titel'),t,el('label',{},'Beschreibung'),b,
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/feedback',{name,action:'update',id:i.id,title:t.value,description:b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:()=>ed.replaceWith(row)}},'Abbrechen')));
  row.replaceWith(ed)};
 toggle.addEventListener('click',()=>{showDone=!showDone;draw()});
 draw();
 return el('div',{class:'card',id:'feedback'},el('div',{class:'bar'},el('b',{},'Feedback ('+d.feedback.length+')'),toggle),list)}
function rightsCard(d,name){const inp=el('input',{placeholder:'/absoluter/pfad','aria-label':'Schreibverzeichnis'});
 const rows=el('div',{},...(d.write_dirs.length?d.write_dirs.map(p=>el('div',{class:'bar'},el('span',{class:'mut'},p),
   el('button',{class:'b d',on:{click:async()=>{const r=await api('/api/rights',{name,action:'remove',path:p});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entfernen'))):[el('span',{class:'mut'},'Keine Verzeichnisse – Schreiben ist gesperrt.')]));
 const sandboxOn=!!(d.sandbox&&d.sandbox.enabled);
 return el('div',{class:'card'},el('b',{},'Schreibrechte (Agenten)'),
  el('div',{class:'mut'},sandboxOn
   ? 'Sandbox aktiv: Schreibwerkzeug (edit) und Shell-Befehle (bash) können nur in diesen Verzeichnissen, den Caches der Build-Werkzeuge und /tmp/opencode schreiben. MCP und Netzwerk bleiben erlaubt; Lesezugriffe werden nicht eingeschränkt.'
   : 'Verzeichnisse für das Schreibwerkzeug (edit) der Projektagenten. Voreingestellt sind /tmp/opencode und das Projektverzeichnis. Agenten ohne Schreibrecht bleiben unverändert. Shell-Befehle (bash) bleiben erlaubt und können Dateien außerhalb dieser Liste ändern – die Liste ist keine Sandbox.'),
  d.write_dirs_error?el('div',{class:'bad'},'Liste nicht lesbar: '+d.write_dirs_error):null,
  rows,
  el('div',{class:'bar'},inp,el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/rights',{name,action:'add',path:inp.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Hinzufügen')),
  el('div',{class:'bar'},el('button',{class:'b',on:{click:async()=>{if(!confirm('Standardverzeichnisse wiederherstellen?'))return;const r=await api('/api/rights',{name,action:'reset'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Standard wiederherstellen'),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/rights',{name,action:'apply'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Auf Projektagenten anwenden')),
  el('div',{class:'mut'},d.write_dirs_custom?'Eigene Liste aktiv.':'Standardliste aktiv.'))}
function sandboxCard(d,name){const s=d.sandbox||{enabled:false,tools:[],write_dirs:[],missing_tools:[],error:null,bwrap:''};
 const active=!!s.enabled,missing=s.missing_tools||[],dirs=s.write_dirs||[],tools=s.tools||[];
 const state=!active?'aus':(s.error?'Fehler':(!s.bwrap?'bubblewrap fehlt':(missing.length?'Werkzeuge fehlen':'bereit')));
 const tone=!active?'mut':(s.error||!s.bwrap||missing.length?'bad':'ok');
 const inp=el('input',{value:tools.join(' '),placeholder:'git node npm','aria-label':'Build-Werkzeuge'});
 return el('div',{class:'card',id:'sandbox'},el('div',{class:'bar'},el('b',{},'Sandbox (Shell und Build-Werkzeuge)'),el('span',{class:'pill '+tone},state),
   el('button',{class:'b'+(active?'':' p'),on:{click:async()=>{const r=await api('/api/sandbox',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Sandbox ausschalten':'Sandbox einschalten'),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/sandbox',{name,action:'check'});toast(r.message)}}},'Prüfen')),
  el('div',{class:'mut'},'Aktiv läuft der Agent mit eigenem opencode-Server in bubblewrap. Schreiben ist nur in den Verzeichnissen unten, in den Caches der Build-Werkzeuge und in einem privaten Temporärordner möglich; /tmp ist sonst schreibgeschützt. MCP und Netzwerk bleiben verfügbar; Lesezugriffe werden nicht eingeschränkt.'),
  el('div',{class:'mut'},'Die Sandbox-Konfiguration (.vibe/project.env, .vibe/permissions.json) ist im Lauf schreibgeschützt.'),
  s.error?el('div',{class:'bad'},'Fehler: '+s.error):null,
  missing.length?el('div',{class:'bad'},'Fehlende Werkzeuge: '+missing.join(', ')):null,
  !active?el('div',{class:'mut'},'Ohne Sandbox bleiben Shell-Befehle (bash) außerhalb der Liste möglich.'):null,
  el('label',{},'Build-Werkzeuge (Leerzeichen oder Komma)'),inp,
  el('div',{class:'bar'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/sandbox',{name,action:'tools',tools:inp.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Werkzeuge speichern')),
  el('details',{},el('summary',{},'Erlaubte Schreibverzeichnisse ('+dirs.length+')'),el('div',{},...dirs.map(p=>el('div',{class:'mut'},p)))))}

/* ---------- Agenten, Modelle, Profile ---------- */
let AG=null,AGFILTER='alle';
function modelLabel(id,info){const m=info[id];return m?`${id} — ${m.preis||'?'} · ${m.tempo}, ${m.aufwand} Aufwand, Daten ${m.daten}`:id}
function modelSelect(models,info,current,blank){const s=el('select',{});if(blank)s.append(el('option',{value:''},blank));const groups={};
 models.forEach(m=>{(groups[m.split('/')[0]]=groups[m.split('/')[0]]||[]).push(m)});if(current&&!models.includes(current))(groups[current.split('/')[0]]=groups[current.split('/')[0]]||[]).push(current);
 Object.entries(groups).forEach(([g,ms])=>{const og=el('optgroup',{label:g});ms.forEach(m=>og.append(el('option',{value:m},modelLabel(m,info))));s.append(og)});if(current)s.value=current;return s}
async function agents(){AG=await api('/api/agents');const d=AG;
 const sel=el('select',{},el('option',{value:'alle'},'Alle'),el('option',{value:'global'},'Nur global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sel.value=AGFILTER;
 sel.addEventListener('change',()=>{AGFILTER=sel.value;agents().catch(showErr)});
 const rows=d.agents.filter(a=>AGFILTER==='alle'||a.scope===AGFILTER);
 const tb=el('table',{},el('tr',{},...['Agent','Geltung','Modus','Modell','Beschreibung',''].map(h=>el('th',{},h))));
 rows.forEach(a=>tb.append(el('tr',{},el('td',{},a.name,a.core?el('span',{class:'pill warn',title:'Kernagent der Manipulationsprüfung'},' ◆ Kern'):null,a.shadow?el('span',{class:'pill warn',title:'Gleicher Name in mehreren Bereichen'},' doppelt'):null,a.valid?null:el('span',{class:'pill bad'},' defekt')),
  el('td',{},a.scope==='global'?el('span',{class:'pill ok'},'global'):el('span',{class:'pill'},'Projekt: '+a.scope)),el('td',{},a.mode),el('td',{class:'mut'},a.model),el('td',{class:'mut'},a.description),
  el('td',{},el('button',{class:'b',on:{click:()=>agentForm(a.scope,a.name).catch(showErr)}},'Bearbeiten')))));
 main.replaceChildren(el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Agenten'),sel,el('button',{class:'b p',on:{click:()=>agentForm(null,null).catch(showErr)}},'Neuer Agent')),
   rows.length?tb:el('span',{class:'mut'},'Keine Agenten in diesem Bereich.'),
   el('div',{class:'mut',style:'margin-top:8px'},'Global = ~/.config/opencode/agents (für alle Projekte). Projekt = <Projekt>/.opencode/agents (nur dort, Teil des Repos). ◆ = von der Abnahme vorausgesetzt.')),profilesCard(d),modelsCard(d))}
function profilesCard(d){const P=JSON.parse(JSON.stringify(d.profiles));const names=Object.keys(P.profile);const cur=el('select',{},...names.map(n=>el('option',{value:n},n+(n===P.aktiv?' (aktiv)':''))));cur.value=P.aktiv;
 const roles=['coder','reviewer'];const body=el('div',{});
 const draw=()=>{const prof=P.profile[cur.value];body.replaceChildren(
   el('table',{},el('tr',{},el('th',{},'Rolle'),el('th',{},'Agenten in dieser Rolle'),el('th',{},'Modell im Profil „'+cur.value+'“')),
    ...roles.map(r=>{const ms=modelSelect(d.models,d.info,prof[r]||'','— nicht ändern —');ms.addEventListener('change',()=>{prof[r]=ms.value});
      return el('tr',{},el('td',{},r),el('td',{class:'mut'},Object.entries(P.rollen).filter(([a,x])=>x===r).map(([a])=>a).join(', ')||'—'),el('td',{},ms))})))};
 cur.addEventListener('change',draw);draw();
 const rol=el('div',{class:'mut'},'Rollenzuordnung (globale Agenten): ',...d.agents.filter(a=>a.scope==='global').map(a=>{const s=el('select',{style:'width:auto;margin:0 8px 0 4px'},el('option',{value:''},'—'),...roles.map(r=>el('option',{value:r},r)));s.value=P.rollen[a.name]||'';
   s.addEventListener('change',()=>{if(s.value)P.rollen[a.name]=s.value;else delete P.rollen[a.name]});return el('span',{},a.name,s)}));
 return el('div',{class:'card'},el('details',{open:'open'},el('summary',{},'Profile – Modelle pro Rolle umschalten (z. B. kostenlos ↔ bezahlt)'),
  el('div',{class:'mut',style:'margin:6px 0'},'Ein Profil legt fest, welches Modell die Rollen Coder und Reviewer nutzen. „Anwenden“ schreibt die model:-Zeile der zugeordneten globalen Agenten (mit Sicherung). Bezahlte Modelle erscheinen erst, wenn der Anbieter verbunden ist (/connect bzw. opencode auth login).'),
  el('div',{class:'bar'},cur,el('button',{class:'b',on:{click:async()=>{const r=await api('/api/profiles',{action:'save',data:P});toast(r.message)}}},'Profile speichern'),
   el('button',{class:'b p',on:{click:async()=>{const sv=await api('/api/profiles',{action:'save',data:P});const r=await api('/api/profiles',{action:'use',profile:cur.value});toast(r.message);if(r.ok)agents().catch(showErr)}}},'Speichern und anwenden')),body,rol))}
function modelsCard(d){const used={};d.agents.forEach(a=>{(used[a.model]=used[a.model]||[]).push(a.name+(a.scope==='global'?'':'@'+a.scope))});
 const ids=d.models.filter(m=>m.startsWith('opencode/')||d.info[m]);Object.keys(d.info).forEach(i=>{if(!ids.includes(i))ids.push(i)});
 const other={};d.models.filter(m=>!m.startsWith('opencode/')&&!d.info[m]).forEach(m=>{other[m.split('/')[0]]=(other[m.split('/')[0]]||0)+1});
 const tb=el('table',{},el('tr',{},...['Modell','Anbieter','Preis je 1M (ein/aus)','Tempo','Aufwand','Daten','Bilder','Coder','Reviewer','in Verwendung'].map(h=>el('th',{},h))));
 ids.forEach(id=>{const m=d.info[id]||{};const gone=!d.models.includes(id);
  const det=el('tr',{class:'detail'},el('td',{colspan:'10'},el('div',{class:'grid3'},
    el('div',{},el('b',{},'Stärken'),el('ul',{class:'l'},(m.staerken||['keine Angaben']).map(x=>el('li',{},x)))),
    el('div',{},el('b',{},'Schwächen'),el('ul',{class:'l'},(m.schwaechen||['keine Angaben']).map(x=>el('li',{},x)))),
    el('div',{},el('b',{},'Details'),el('div',{class:'mut'},'Kontext: '+(m.ctx||'?')),el('div',{class:'mut'},'Daten: '+(m.daten_text||'?')),el('div',{class:'mut'},'Quellen: '+(m.quellen||'—')),gone?el('div',{class:'bad'},'Nicht in „opencode models“ (Anbieter nicht verbunden oder Modell entfernt).'):null))));
  det.style.display='none';
  tb.append(el('tr',{class:'row',on:{click:()=>{det.style.display=det.style.display==='none'?'table-row':'none'}}},el('td',{},'▸ '+(m.name||id),el('div',{class:'mut'},id)),el('td',{class:'mut'},m.lab||'?'),el('td',{},m.preis||'?'),el('td',{},badge(m.tempo)),el('td',{},badge(m.aufwand)),el('td',{},badge(m.daten)),el('td',{},badge(m.vision)),
   el('td',{},badge(m.coder)),el('td',{},badge(m.reviewer)),el('td',{class:'mut'},(used[id]||[]).join(', ')||'—')));tb.append(det)});
 return el('div',{class:'card'},el('details',{},el('summary',{},'Modelle – Einschätzung und Preis (aufklappen, Zeile anklicken für Details)'),
   el('div',{class:'mut',style:'margin:8px 0'},'Stand '+d.stand+'. '+d.hinweis),tb,Object.keys(other).length?el('div',{class:'mut',style:'margin-top:8px'},'Weitere verbundene Anbieter (ohne Einschätzung): '+Object.entries(other).map(([k,v])=>k+' ('+v+' Modelle)').join(', ')):null))}
async function agentForm(scope,name){const d=AG||await api('/api/agents');const isNew=!name;let text='';
 if(!isNew)text=(await api('/api/agent?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name))).text;
 const nm=el('input',{placeholder:'name (a-z, 0-9, -, _)'});if(!isNew){nm.value=name;nm.setAttribute('disabled','disabled')}
 const sc=el('select',{},el('option',{value:'global'},'global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sc.value=scope||'global';if(!isNew)sc.setAttribute('disabled','disabled');
 const ds=el('input',{placeholder:'Wofür ist der Agent da? (Pflicht)'});
 const md=el('select',{},el('option',{value:'subagent'},'subagent (wird von anderen aufgerufen)'),el('option',{value:'primary'},'primary (direkt startbar)'),el('option',{value:'all'},'all'));
 const cur=!isNew&&(/^model:\s*(\S+)/m.exec(text)||[])[1];
 const mo=modelSelect(d.models,d.info,cur||'','— Standardmodell —');
 const tp=el('input',{placeholder:'z. B. 0.1',value:'0.1'}),st=el('input',{placeholder:'z. B. 60'});
 const pm=el('select',{});const perms=()=>sc.value==='global'?d.perms:d.perms_project;
 const setPerms=()=>{const cur=pm.value;pm.replaceChildren(...Object.entries(perms()).map(([k,v])=>el('option',{value:k},v)));pm.value=perms()[cur]?cur:'lesen'};
 setPerms();pm.value='lesen';
 const hint=el('div',{class:'mut'});
 const updHint=()=>{const dirs=sc.value==='global'?null:(d.write_dirs[sc.value]||[]);const err=sc.value==='global'?null:(d.write_dirs_errors||{})[sc.value];
 hint.textContent=err?'Schreibrechte nicht lesbar: '+err:(sc.value==='global'?'Global: volle Schreibrechte ohne Verzeichnisgrenze.':'Schreibrechte (edit, voll) nur in: '+(dirs&&dirs.length?dirs.join(', '):'keine Verzeichnisse – Schreiben gesperrt')+'. Shell (bash) bleibt erlaubt.')};
 updHint();
 const pr=el('textarea',{rows:5,placeholder:'System-Prompt: Rolle, Regeln, Ausgabeformat'});
 const raw=el('textarea',{class:'raw'});raw.value=text;
 const gen=async()=>{const r=await api('/api/agent_template',{description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,perm:pm.value,prompt:pr.value,scope:sc.value});raw.value=r.message};
 sc.addEventListener('change',()=>{setPerms();updHint();if(isNew)gen().catch(showErr)});
 mo.addEventListener('change',()=>{if(!isNew){const v=mo.value;if(!v)return;raw.value=/^model:/m.test(raw.value)?raw.value.replace(/^model:.*$/m,'model: '+v):raw.value.replace(/\n---/,'\nmodel: '+v+'\n---')}else gen()});
 const core=!isNew&&d.agents.some(a=>a.name===name&&a.scope===scope&&a.core);
 const cp=el('select',{},el('option',{value:''},'Kopieren nach …'),...['global',...d.projects].filter(x=>x!==scope).map(x=>el('option',{value:x},x==='global'?'global':'Projekt: '+x)));
 const kopf=isNew?el('div',{},el('div',{class:'grid'},el('div',{},el('label',{},'Name'),nm),el('div',{},el('label',{},'Geltung'),sc)),el('label',{},'Beschreibung'),ds,
   el('div',{class:'grid3'},el('div',{},el('label',{},'Modus'),md),el('div',{},el('label',{},'Modell'),mo),el('div',{},el('label',{},'Rechte'),pm)),
   hint,
   el('div',{class:'grid'},el('div',{},el('label',{},'Temperatur'),tp),el('div',{},el('label',{},'Max. Schritte'),st)),el('label',{},'Prompt'),pr,
   el('div',{class:'bar'},el('button',{class:'b',on:{click:gen}},'Datei aus Eingaben erzeugen'),el('span',{class:'mut'},'Das Ergebnis unten kann vor dem Speichern frei bearbeitet werden.'))):
  el('div',{},el('div',{class:'bar'},el('b',{},name),el('span',{class:'pill'},scope==='global'?'global':'Projekt: '+scope),core?el('span',{class:'pill warn'},'◆ Kernagent: Änderungen können die Manipulationsprüfung schwächen'):null),
   el('label',{},'Modell schnell wechseln (schreibt die model:-Zeile in den Text unten)'),mo,hint);
 if(isNew)setTimeout(gen,0);
 main.replaceChildren(el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>agents().catch(showErr)}},'← zurück'),el('h2',{style:'margin:0'},isNew?'Neuer Agent':'Agent bearbeiten')),
  el('div',{class:'card'},kopf,el('label',{},'Datei (Frontmatter + Prompt)'),raw,
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const n=isNew?nm.value:name,s=isNew?sc.value:scope;const r=await api('/api/agent',{action:'save',scope:s,name:n,text:raw.value,create:isNew});toast(r.message);if(r.ok)agents().catch(showErr)}}},'Speichern'),
    isNew?null:cp,isNew?null:el('button',{class:'b',on:{click:async()=>{if(!cp.value)return toast('Ziel wählen');const r=await api('/api/agent',{action:'copy',scope,name,to:cp.value});toast(r.message)}}},'Kopieren'),
    isNew?null:el('button',{class:'b d',on:{click:async()=>{if(!confirm('Agent „'+name+'“ löschen? Eine Sicherung bleibt in agent-backups.'))return;const r=await api('/api/agent',{action:'delete',scope,name});toast(r.message);if(r.ok)agents().catch(showErr)}}},'Löschen'))))}

/* ---------- MCP-Tools ---------- */
async function mcp(){const d=await api('/api/mcp');
 const tb=el('table',{},el('tr',{},...['Name','Geltung','Typ','Ziel','aktiv',''].map(h=>el('th',{},h))));
 d.servers.forEach(s=>{ if(s.error){tb.append(el('tr',{},el('td',{colspan:'6',class:'bad'},s.scope+': Konfiguration nicht lesbar: '+s.error)));return}
  tb.append(el('tr',{},el('td',{},s.name),el('td',{},s.scope==='global'?el('span',{class:'pill ok'},'global'):el('span',{class:'pill'},'Projekt: '+s.scope)),el('td',{},s.type),el('td',{class:'mut'},s.target),el('td',{},badge(s.enabled?'ja':'nein')),
   el('td',{},el('div',{class:'bar',style:'margin:0'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/mcp',{action:'test',scope:s.scope,name:s.name});mcpResult(r)}}},'Testen'),
    el('button',{class:'b',on:{click:()=>mcpForm(s.scope,s.name).catch(showErr)}},'Bearbeiten'),
    el('button',{class:'b',on:{click:async()=>{const r=await api('/api/mcp',{action:'toggle',scope:s.scope,name:s.name});toast(s.name+' '+r.message);mcp().catch(showErr)}}},s.enabled?'Ausschalten':'Einschalten')))))});
 const layouts=[...new Set(d.servers.filter(s=>s.layout).map(s=>s.scope+': '+s.layout+' → '+s.path))];
 main.replaceChildren(el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'MCP-Server (Model Context Protocol)'),el('button',{class:'b p',on:{click:()=>mcpForm(null,null).catch(showErr)}},'Neuer MCP-Server')),
  d.servers.length?tb:el('span',{class:'mut'},'Keine MCP-Server konfiguriert.'),
  el('div',{class:'mut',style:'margin-top:8px'},'MCP-Server geben dem Agenten zusätzliche Werkzeuge (z. B. Notizen, Datenbanken, Dokumentation). Die Werkzeuge belegen Kontext und kosten dadurch Tokens: nur aktivieren, was gebraucht wird. Geheimnisse (Token, Schlüssel) werden hier maskiert; beim Speichern bleiben sie unverändert.'),
  layouts.length?el('div',{class:'mut'},'Konfigurationsdateien: '+layouts.join(' | ')):null),el('div',{id:'mcpres'}))}
function mcpResult(r,into){const t=r.result;const box=into||document.getElementById('mcpres');if(!box)return toast(r.message);
 box.replaceChildren(el('div',{class:'card '+(t&&t.ok?'':'err')},el('b',{class:t&&t.ok?'ok':'bad'},t?(t.ok?'Test bestanden':'Test fehlgeschlagen'):'Fehler'),r.ok?null:el('div',{class:'bad'},r.message),
  t&&t.server&&t.server.name?el('div',{class:'mut'},'Server: '+t.server.name+' '+(t.server.version||'')):null,...(t?t.steps.map(s=>el('div',{class:'mut'},'✓ '+s)):[]),
  t&&t.error?el('div',{class:'bad'},t.error):null,t&&t.hint?el('div',{class:'warn'},'Hinweis: '+t.hint):null,
  t&&t.tools&&t.tools.length?el('div',{},el('b',{},t.tools.length+' Werkzeuge'),el('ul',{class:'l'},t.tools.map(x=>el('li',{},el('b',{},x.name),x.description?' – '+x.description:'')))):null))}
const lines=s=>s.split('\n').map(x=>x.trim()).filter(Boolean);
const kv=(s,sep)=>{const o={};lines(s).forEach(l=>{const i=l.indexOf(sep);if(i>0)o[l.slice(0,i).trim()]=l.slice(i+1).trim()});return o};
const unkv=(o,sep)=>Object.entries(o||{}).map(([a,b])=>a+sep+b).join('\n');
async function mcpForm(scope,name){const d=await api('/api/mcp');let e={type:'local',command:[],enabled:true};
 if(name)e=(await api('/api/mcp_entry?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name))).entry;
 const isNew=!name;const nm=el('input',{value:name||'',placeholder:'name (Buchstaben, Ziffern, _ -)'});
 const sc=el('select',{},el('option',{value:'global'},'global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sc.value=scope||'global';if(!isNew)sc.setAttribute('disabled','disabled');
 const ty=el('select',{},el('option',{value:'local'},'local (Programm starten, stdio)'),el('option',{value:'remote'},'remote (URL, Streamable HTTP)'));ty.value=e.type||'local';
 const cmd=el('textarea',{rows:4,placeholder:'ein Argument pro Zeile, z. B.\nnpx\n-y\n@modelcontextprotocol/server-everything'});cmd.value=(e.command||[]).join('\n');
 const envv=el('textarea',{rows:3,placeholder:'NAME=Wert (eine pro Zeile; {env:VARIABLE} erlaubt)'});envv.value=unkv(e.environment,'=');
 const cwd=el('input',{value:e.cwd||'',placeholder:'optional'});
 const url=el('input',{value:e.url||'',placeholder:'https://…/mcp'});
 const hdr=el('textarea',{rows:3,placeholder:'Name: Wert (eine pro Zeile, z. B. Authorization: Bearer {env:TOKEN})'});hdr.value=unkv(e.headers,': ');
 const noauth=el('input',{type:'checkbox'});noauth.checked=e.oauth===false;
 const en=el('input',{type:'checkbox'});en.checked=e.enabled!==false;
 const to=el('input',{value:String(e.timeout||''),placeholder:'ms, Standard 30000'});
 const loc=el('div',{},el('label',{},'Befehl (Programm und Argumente)'),cmd,el('label',{},'Umgebungsvariablen'),envv,el('label',{},'Arbeitsordner'),cwd);
 const rem=el('div',{},el('label',{},'URL'),url,el('label',{},'Header'),hdr,el('label',{},el('span',{},'OAuth abschalten (für Server mit Schlüssel im Header) '),noauth));
 const show=()=>{loc.style.display=ty.value==='local'?'block':'none';rem.style.display=ty.value==='remote'?'block':'none'};ty.addEventListener('change',show);show();
 const build=()=>{const o={type:ty.value};if(ty.value==='local'){o.command=lines(cmd.value);const ev=kv(envv.value,'=');if(Object.keys(ev).length)o.environment=ev;if(cwd.value.trim())o.cwd=cwd.value.trim()}
  else{o.url=url.value.trim();const hv=kv(hdr.value,':');if(Object.keys(hv).length)o.headers=hv;if(noauth.checked)o.oauth=false;else if(e.oauth&&typeof e.oauth==='object')o.oauth=e.oauth}
  o.enabled=en.checked;if(to.value.trim())o.timeout=parseInt(to.value,10);return o};
 const res=el('div',{});
 main.replaceChildren(el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>mcp().catch(showErr)}},'← zurück'),el('h2',{style:'margin:0'},isNew?'Neuer MCP-Server':'MCP-Server bearbeiten')),
  el('div',{class:'card'},el('div',{class:'grid'},el('div',{},el('label',{},'Name (Werkzeuge erscheinen mit diesem Präfix)'),nm),el('div',{},el('label',{},'Geltung'),sc)),
   el('div',{class:'grid'},el('div',{},el('label',{},'Typ'),ty),el('div',{},el('label',{},'Timeout (ms)'),to)),loc,rem,el('label',{},el('span',{},'aktiv '),en),
   el('div',{class:'mut',style:'margin-top:6px'},'Maskierte Werte (***) bleiben beim Speichern unverändert. Zum Ändern den ganzen Wert neu eintragen.'),
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/mcp',{action:'save',scope:isNew?sc.value:scope,name:nm.value,old_name:isNew?'':name,create:isNew,entry:build()});toast(r.message);if(r.ok)mcp().catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:async()=>{res.replaceChildren(el('div',{class:'mut'},'Teste … (kann bis zu einer Minute dauern, z. B. wenn npx Pakete lädt)'));const r=await api('/api/mcp',{action:'test',scope:isNew?sc.value:scope,name:isNew?'':name,entry:build()});mcpResult(r,res)}}},'Testen (mit den Werten oben)'),
    isNew?null:el('button',{class:'b d',on:{click:async()=>{if(!confirm('MCP-Server „'+name+'“ löschen?'))return;const r=await api('/api/mcp',{action:'delete',scope,name});toast(r.message);if(r.ok)mcp().catch(showErr)}}},'Löschen'))),res)}
async function env(){const d=await api('/api/doctor');const f=await api('/api/fritz');
 main.replaceChildren(el('div',{class:'card'},el('b',{},'Umgebungsprüfung'),...d.map(c=>el('div',{},el('span',{class:c.ok?'ok':'bad'},c.ok?'OK   ':'FEHL '),c.label,c.ok||!c.hint?null:el('span',{class:'mut'},'  → '+c.hint)))),fritzCard(f))}
function fritzCard(f){
 const cb=el('input',{type:'checkbox'});cb.checked=!!f.automation;
 const state=el('span',{class:'pill '+(f.automation?'warn':'mut')},'Automatik: '+(f.automation?'an':'aus'));
 const ready=el('span',{class:'pill '+(f.ready?'ok':'bad')},f.ready?'bereit':'nicht bereit');
 const resultBox=el('div',{});
 const recon=el('button',{class:'b p'},'Jetzt neu verbinden');
 recon.disabled=!f.ready;
 recon.addEventListener('click',async()=>{if(!confirm('FRITZ!Box neu verbinden? Die Internetverbindung wird kurz getrennt; alle Geräte im Netz sind betroffen.'))return;
  recon.disabled=true;resultBox.replaceChildren(el('div',{class:'mut'},'Reconnect läuft … (die FRITZ!Box prüft bis zu drei Minuten auf eine neue IP)'));
  try{const r=await api('/api/fritz',{action:'reconnect'});
   resultBox.replaceChildren(el('div',{class:'card '+(r.ok?'':'err')},el('b',{class:r.ok?'ok':'bad'},r.ok?'Reconnect erfolgreich':'Reconnect fehlgeschlagen'),
    el('pre',{style:'white-space:pre-wrap;margin:8px 0 0'},(r.result&&r.result.output)||r.message||'')))}catch(e){resultBox.replaceChildren(el('div',{class:'card err'},String(e&&e.message||e)))}finally{recon.disabled=!f.ready}});
 return el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Fritzbox-Reconnect'),state,ready,recon),
  el('div',{class:'mut'},'Optionale Altintegration: Nach einem fehlgeschlagenen Agentenlauf kann eine neue Internet-IP angefordert werden (z. B. nach einem Anbieter-Limit). Ein Reconnect trennt die Internetverbindung der FRITZ!Box kurz; das betrifft alle Geräte im Netz. Die Automatik ist standardmäßig aus und greift nur nach einem Fehler, nie während eines laufenden Pakets.'),
  el('div',{class:'mut'},'Konfiguration: '+f.env+' (nicht im Repository)'+(f.configured?' – vorhanden':' – fehlt oder unvollständig')),
  el('div',{class:'mut'},'Helfer: '+f.script+(f.script_ok?'':' (fehlt)')+' · Python: '+(f.python||'nicht gefunden')+(f.python_ok?'':' (nicht ausführbar)')+' · Voraussetzung: fritzconnection im Python installiert'),
  el('div',{class:'bar'},el('label',{style:'margin:0'},el('span',{},' Automatik nach fehlgeschlagenem Agentenlauf '),cb),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/fritz',{action:'automation',enabled:cb.checked});toast(r.message);if(r.ok)env().catch(showErr)}}},'Automatik übernehmen')),
  resultBox)}
window.addEventListener('unhandledrejection',e=>showErr(e.reason));
setTab('projects');
</script></body></html>"""

if __name__ == "__main__":
    SRV = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    SRV.daemon_threads = True
    print(f"vibe-web läuft auf http://127.0.0.1:{PORT}/  (Token in {TOKFILE})", flush=True)
    SRV.serve_forever()
    print("vibe-web beendet.", flush=True)
