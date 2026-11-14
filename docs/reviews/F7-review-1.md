# Review result

## Summary
- Critical: 0
- High: 1
- Medium: 2
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Shell-Befehle werden auf die konfigurierten Schreibverzeichnisse begrenzt | PASS | `bin/vibe_sandbox.py:401-461` (ro-bind /, --bind nur erlaubte Verzeichnisse, remount-ro /tmp, ro-bind .vibe), `bin/vibe-run.sh:26-36,55` | `tests/unit/test_sandbox.py:351-451` echte bwrap-Läufe (DENIED/PROJEKT_OK/TMP_DENIED/ENV_DENIED), `:457-545` echter Läufer mit `--standalone`; laut gelieferten Prüfergebnissen 24/24 OK (von mir nicht erneut ausgeführt) |
| MCP bleibt nutzbar (Netzwerk, MCP-Caches) | PASS | `bin/vibe_sandbox.py:81-86` (MCP_CACHES, unabhängig von SANDBOX_TOOLS), Netzwerk wird nicht unshared (Doku `docs/features/F7.md:66-71`) | Caches in `test_effective_write_dirs_contain_project_permissions_and_tool_caches` (test_sandbox.py:171) geprüft; echter MCP-Aufruf in der Sandbox ist nicht getestet (Restrisiko, in F7.md nicht beansprucht) |
| Notwendige Build-Tools (Caches) erlaubt | PASS mit Befund | `bin/vibe_sandbox.py:47-101,199-216` | `tests/unit/test_sandbox.py:171-208`; aber Cargo-Eintrag fehlerhaft (siehe Befund 2) |
| Build-Tools je Projekt konfigurierbar (`SANDBOX_TOOLS`) | PASS | `bin/vibe:404-455` (`set_env_values`, `sandbox_set`, `sandbox_tools`, `cmd_sandbox`), `bin/vibe-web.py:198-211` | `tests/unit/test_sandbox.py:127-169` (on/off/tools, Ablehnung von Steuerzeichen), API-Tests `:653-711` |
| Templates liefern Vorauswahl mit | PASS | `templates/{generic,web,android,docker,openwrt}/.vibe/project.env:4-5` | `tests/unit/test_sandbox.py:117-125` |
| Tokenpflicht für `POST /api/sandbox` | PASS | `bin/vibe-web.py:143` (`_ok()` vor allen POST-Zweigen), `:198-211` | `tests/unit/test_sandbox.py:703-711` (403 ohne Token, Datei unverändert) |
| Fail-closed bei fehlendem bwrap | PASS | `bin/vibe_sandbox.py:374-379,476-484`, `bin/vibe:726-729` (Vorprüfung in `cmd_run`) | `tests/unit/test_sandbox.py:288-312` |

## Findings

- [High] `bin/vibe-run.sh:28` — Sandbox-Zustand wird im Läufer anders ausgewertet als in Status/CLI/UI (fail-open-Divergenz)
  - Evidence: `bin/vibe_sandbox.py:223-228` wertet `SANDBOX` nach `.strip().lower()` als `on|1|true|yes` aus; `docs/features/F7.md:80-82` dokumentiert genau diese Wertemenge. Der Läufer prüft hingegen exakt `[ "${SANDBOX:-off}" = "on" ]` (auch Groß-/Kleinschreibung und Anführungszeichen). Bei `SANDBOX=TRUE`, `SANDBOX=yes`, `SANDBOX=1` oder `SANDBOX=ON` zeigt CLI, Dashboard (`Sandbox: an`) und `vibe status` die Sandbox als aktiv an, `sandbox_check` meldet „bereit“ — aber `SANDBOX_WRAP` bleibt leer und der Agentenlauf läuft ohne bubblewrap. Eine dokumentiert gültige Einstellung hebt die Sicherheitsgrenze still auf; die Logzeile (`Sandbox: yes`) ist die einzigeWARNUNG.
  - Required fix: Eine einzige Auswertungsquelle definieren. Entweder `status()` nur `on` akzeptieren lassen (Doku und Tests anpassen) oder `vibe-run.sh` den Zustand über `bin/vibe_sandbox.py` ermitteln lassen (z. B. `--check --json` bzw. Status-JSON statt Stringvergleich). Zusätzlich einen Test ergänzen, der für jeden als aktiv geltenden Wert tatsächlich umschlossene Ausführung belegt.

- [Medium] `bin/vibe_sandbox.py:69` — Cargo-Cache-Eintrag `~/.cargo/.package-cache` ist eine Lockdatei und wird wie ein Verzeichnis behandelt
  - Evidence: `_ensure_dir` (`:272-277`) legt jeden Schreibpfad mit `os.makedirs` an; `check()` (`:306-310`) und `bwrap_argv()` (`:388-391`) erzwingen das für alle Cache-Pfade. Existiert `~/.cargo/.package-cache` bereits als Datei (normal nach jeder Cargo-Nutzung), wirft `makedirs` FileExistsError → `check()` meldet „Verzeichnis nicht anlegbar“ und die Sandbox ist für Cargo-Projekte unstartbar. Existiert sie nicht, wird ein Verzeichnis erzeugt, das `cargo` als Lockdatei erwartet und daher likely bricht (in und außerhalb der Sandbox).
  - Required fix: Dateiartige Cache-Einträge (`~/.cargo/.package-cache`) aus `TOOL_CACHES` entfernen oder Cache-Einträge vor dem Binden unterscheiden (existierende Dateien nur mit `--bind-try` einbinden, nicht anlegen) und mit einem Cargo-Projektfall testen.

- [Medium] `bin/vibe_sandbox.py:170-189` — F3-Schreibrechte-Regel ist doppelt implementiert und kann stumm auseinanderdriften
  - Evidence: `project_write_dirs`/`_norm_dir`/`WRITE_DIRS_DEFAULT` (`bin/vibe_sandbox.py:42,153-189`) sind inhaltlich Kopien von `_norm_write_dir`/`write_dirs`/`WRITE_DIRS_DEFAULT` (`bin/vibe:326-360`), inklusive identischer Fehlermeldungen. Die Sandbox erzwingt die Liste, die CLI/UI anzeigen aber aus der zweiten Kopie stammen. Driftet eine Kopie (F3-Änderung an Normalisierung oder Standard), gilt im Dashboard eine andere Grenze als erzwungen wird — ohne Fehlermeldung.
  - Required fix: Eine Quelle wählen: entweder `bin/vibe` delegiert das Parsen an `vibe_sandbox.project_write_dirs` (Richtung CLI → Sandbox-Modul, kein neues Install-File), oder die Regel in ein gemeinsames Modul auslagern. Mindestens einen Test ergänzen, der für Grenzfälle (`~`, Trailing-Slash, Symlink) beide Implementierungen auf identische Ergebnisse prüft.

- [Minor] `bin/vibe_sandbox.py:313-333` — `check()`-Probe testet nicht die tatsächlich verwendeten erweiterten Optionen
  - Evidence: Die Probe startet bwrap ohne `--remount-ro /tmp` (und ohne die Bind-Struktur). `--remount-ro` ist ein neueres bubblewrap-Feature; mit älterem bwrap meldet `check` „bereit“, der erste Lauf scheitert dann an der unbekannten Option (fail closed, aber unnötig spät). F7.md nennt keine Mindestversion.
  - Required fix: Mindest-bwrap-Version dokumentieren und die Probe um `--remount-ro /tmp` (bzw. die Argumentliste aus `bwrap_argv` ohne Befehl) ergänzen.

- [Minor] `FEEDBACK.md:65-66` — Eintrag F8 liegt im selben uncommitteten Arbeitsstand wie F7
  - Evidence: AGENTS.md verlangt „Commit enthält ausschließlich dieses Arbeitspaket und dessen Nachweise“ und „Fremde oder vorbestehende Änderungen nicht … mitcommitten“. Die F8-Zeile wurde in dieser Sitzung nicht vom F7-Paket bearbeitet und ist im Diff enthalten; ob sie vom Nutzer (z. B. über die UI) stammt, ist nicht belegt.
  - Required fix: Herkunft klären; beim Commit nur die F7-relevanten Zeilen von FEEDBACK.md stagen bzw. den F8-Eintrag aus dem F7-Commit herauslassen.

- [Minor] `tests/unit/test_sandbox.py:351` — Testname verspricht mehr als er prüft
  - Evidence: `test_real_sandbox_allows_write_dirs_and_denies_home` testet Schreibverbote nur gegen `/var/tmp`; ein Schreibversuch ins (per `XDG_*` umgeleitete) Home bzw. `~/.local/share/opencode` wird nicht Probe. Der Name suggeriert eine Home-Deny-Abnahme.
  - Required fix: Umbenennen oder einen tatsächlichen Schreibversuch auf einen Pfad unter dem echten Home ergänzen, der im Sandbox-Namensraum lesbar, aber nicht beschreibbar sein muss.

## Verification
- Change set reviewed: `32e1a99..working tree` (Branch `feature/f7-sandbox`); alle 15 geänderten Dateien per `git diff` gelesen, alle 5 neuen Dateien vollständig gelesen (`bin/vibe_sandbox.py` 578 Zeilen, `tests/unit/test_sandbox.py` 715, `tests/browser/test_sandbox_ui.py` 211, `docs/features/F7.md` 395, PNG als Bild betrachtet).
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git branch --show-current`, `git diff --stat`, `git diff -- bin/vibe`, `git diff -- bin/vibe-run.sh bin/vibe-web.py`, `git diff -- templates/ scripts/setup-vibe.py tests/unit/test_setup_vibe.py FEEDBACK.md docs/baseline.md docs/features/F3.md docs/trilium-index.md`, `git diff -- docs/import-manifest.json` (ein kombiniertes grep/`head`-Kommando wurde von den Berechtigungen abgelehnt; stattdessen grep/read-Tools genutzt).
- Checks with supplied output: Unit-Suite (211 OK), Browsersuite (11 OK), Syntaxcheck, Geheimnischeck, Importmanifest-Check, rote Phase der Härtung (TMP_OPEN, ENV_OPEN/VIBE_OPEN) — alles vom coding agent geliefert, von mir nicht erneut ausgeführt. Unabhängig von mir verifiziert: Trilium-Notiz `ZzVeElHG2ifr` („F7 Sandbox für Shell und Build-Werkzeuge“, geändert 2026-10-26 16:47 UTC) über den MCP-Zugang gelesen; `docs/features/F7-sandbox.png` existiert und zeigt die beschriebene Karte (Zustand „bereit“, `git python3`, 8 Schreibverzeichnisse).
- Checks not independently run: alle Build- und Testläufe, `bash scripts/verify.sh quick|full` (Skript existiert nicht; `VERIFY_QUICK/VERIFY_FULL` sind `echo TODO` — F7.md weist das nachweislich korrekt aus).
- Important areas inspected: `bin/vibe_sandbox.py` (argv-Reihenfolge, `/tmp`-Remount, `.vibe`-ro-Bind, fail-closed, auth.json-ro-Bind, `TOOL_CACHES`/`MCP_CACHES`/`TOOL_ENV_CACHES`, `normalize_tools`), `bin/vibe-run.sh` (Wrapping, `--standalone`-Erzwingung), `bin/vibe` (Env-Schreibung atomar, Tokenpfad, cmd_run-Vorprüfung), `bin/vibe-web.py` (Tokenprüfung Zeile 143 vor `/api/sandbox`, Nutzlast), Templates, Setup, Manifest, Tests (keine Skips/leeren Assertions, echte bwrap-Läufe, deterministische Temp-Pfade/Ports, keine abgeschwächten Alt-Assertions laut Diff).
- Remaining risks: Befund 1 (Status-Divergenz) ist der einzige fail-open-Pfad; MCP-Serverbetrieb innerhalb der Sandbox ist nicht automatisiert nachgewiesen; bwrap-Mindestversion für `--remount-ro` ist weder geprüft noch dokumentiert; die gelieferten Prüfergebnisse sind plausibel und konsistent (187+24=211 Unit-, 10+1=11 Browser-Tests), aber nicht von mir wiederholt worden.
