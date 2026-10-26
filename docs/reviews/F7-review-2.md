All material is reviewed. Let me compile the final review.

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Shell-Befehle der Agenten auf eine echte Sandbox begrenzen (nur Schreibrechte-Verzeichnisse, MCP, Build-Tools) | PASS | `bin/vibe_sandbox.py:368-464` (ro-bind `/`, `--bind` nur erlaubte Ziele, privates `/tmp` + `--remount-ro`, `.vibe` ro-bind, XDG/TMPDIR-Umleitung), `bin/vibe-run.sh:43-54,75` | `tests/unit/test_sandbox.py:420-468,487-505,507-527` echte bwrap-Läufe (PROJEKT_OK/ERLAUBT_OK/DENIED/HOME_DENIED/TMP_DENIED/ENV_DENIED); von mir nicht erneut ausgeführt |
| MCP bleibt nutzbar (Caches, Netzwerk) | PASS | `bin/vibe_sandbox.py:82-87` (MCP_CACHES unabhängig von SANDBOX_TOOLS), kein `--unshare-net` in `bwrap_argv` | `tests/unit/test_sandbox.py:177-208`; echter MCP-Aufruf in der Sandbox nicht getestet (dokumentierte Restgrenze, F7.md:411-413) |
| Notwendige Build-Tools inkl. Caches erlaubt (Cargo-Datei-Cache behoben) | PASS | `bin/vibe_sandbox.py:48-102` (`cargo`/`rustc` → `~/.cargo` als Verzeichnis), `:200-217` | `tests/unit/test_sandbox.py:294-313` (`.package-cache` als Datei + Fake-cargo), rote Phase laut F7.md:315-344 und Sitzungsangaben |
| Build-Tools je Projekt konfigurierbar (`SANDBOX_TOOLS`) | PASS | `bin/vibe:389-444` (`set_env_values`, `sandbox_set`, `sandbox_tools`), `bin/vibe-web.py:198-214`, `bin/vibe_sandbox.py:128-151` | `tests/unit/test_sandbox.py:133-175` (on/off/tools, Steuerzeichen ohne Dateiänderung), API-Tests `:765-813` |
| Templates liefern Vorauswahl mit | PASS | `templates/{generic,web,android,docker,openwrt}/.vibe/project.env:4-5` | `tests/unit/test_sandbox.py:123-131` |
| Sandbox-Umgehung über dokumentierte SANDBOX-Werte verhindert (Round-1-High behoben) | PASS | `bin/vibe-run.sh:31-42` (`--enabled` als einzige Quelle, Abbruch bei Exit ≠ 0/1), `bin/vibe_sandbox.py:552-553`, Missing-Module-Abbruch `bin/vibe-run.sh:39-41` | `tests/unit/test_sandbox.py:274-292` (`--enabled` 0/1 je Wert), `:545-559` (echter Läufer mit on/TRUE/yes/1), `:561-570` (fehlendes Modul → Abbruch); rote Phase laut Sitzungsangaben (Exit 2, „ESCAPED“ vorher) |
| Bestehende Projekte ohne Einstellung bleiben aus; F3-Verhalten unverändert | PASS | `bin/vibe_sandbox.py:224-229,252-254`, `bin/vibe:328-344` (Delegation, keine zweite Kopie) | `tests/unit/test_sandbox.py:112-121,315-341` (Gleichheit CLI/Sandbox-Normalisierung inkl. Symlink/Fehlerfälle) |
| Dashboard: Karte, API mit Tokenpflicht | PASS | `bin/vibe-web.py:143` (Token vor allen POST-Zweigen), `:198-214`, `:403,444-459` | `tests/unit/test_sandbox.py:815-823` (403 ohne Token, Datei unverändert), `tests/browser/test_sandbox_ui.py:144-207` (Chromium, inkl. Konfigurationstext und Screenshot) |

## Findings

- [Medium] `bin/vibe-run.sh:31-38` — Exit-Code 1 ist mehrdeutig: Crash des Sandbox-Moduls schaltet die Sandbox still ab (Rest-fail-open)
  - Evidence: Der Läufer behandelt Exit 1 von `--enabled` als „Sandbox aus“ und Exit ≠ 0/1 als Abbruch. Python beendet sich aber bei jedem unbehandelten Fehler — inklusive `SyntaxError`/`ImportError` des Modul­skripts selbst — mit Exit-Code 1. Die Existenzprüfung `[ -f "$BIN/vibe_sandbox.py" ]` (`bin/vibe-run.sh:31`) fängt nur fehlende Dateien ab; eine unvollständig kopierte, korrupte oder uneditierbar geänderte Moduldatei existiert, liefert Exit 1 und der Lauf startet in Zeile 75 ohne `SANDBOX_WRAP` ungeschützt — genau der Still-fail-open-Fall, den der Round-1-Fix schließen sollte. `F7.md:139-140` beansprucht „ein Exit-Code ungleich 0/1 … führt zum Abbruch“; Crashes landen aber auf 1 und werden nicht unterschieden. Der `vibe run`-Pfad (`bin/vibe:710-713`) scheitert bei demselben Defekt dagegen laut mit Fehler (Import-Exception, kein stiller Fallback) — der direkte Läuferpfad ist die offene Lücke.
  - Required fix: Das Verfahren so definieren, dass „aus“ nur bei einem ausdrücklich bestätigten Urteil gilt: `--enabled` muss ein maschinenlesbares Urteil ausgeben (z. B. „an“/„aus“ auf stdout), das der Läufer zusätzlich zum Exit-Code verifiziert, oder das Modul muss interne Fehler abfangen und einen vom „aus“-Code getrennten Exit-Code liefern. Dazu einen Test ergänzen, der eine korrupte/nicht importierbare `vibe_sandbox.py` im Toolchain simuliert und belegt, dass der Läufer abbricht statt ungeschützt zu starten. F7.md den tatsächlichen Verhaltensvertrag korrekt dokumentieren.

- [Minor] `docs/features/F7.md:194,202-228` — Testtabelle unvollständig (28 von 29 Tests)
  - Evidence: F7.md nennt „29 Tests“, listet in der Tabelle aber nur 28; `test_gradle_user_home_is_writable_when_configured` (`tests/unit/test_sandbox.py:198-208`) fehlt, obwohl genau dieser Fall (GRADLE_USER_HOME außerhalb `~/.gradle`) in F7.md:96-98 als Motivation für `TOOL_ENV_CACHES` beschrieben wird.
  - Required fix: Tabellenzeile für den Gradle-Umgebungsvariablen-Test ergänzen.

- [Minor] `docs/baseline.md:168` — Zeilenangabe für `vibe sandbox` weicht um ~45 Zeilen ab
  - Evidence: Angegeben ist `bin/vibe:433-491`; tatsächlich liegen die Sandbox-CLI-Teile bei `bin/vibe:388-472` (`set_env_values` 389, `cmd_sandbox` 446-472), Zeile 491 liegt bereits in `pause_after_request`. Benachbarte Zeilen (`bin/vibe:441-457` für `vibe agent`, tatsächlich 554 ff.) sind ebenfalls verschoben; die neuen Einträge erben und erhöhen die Drift.
  - Required fix: Zeilenangaben der F7-Zeilen (und der unmittelbaren Nachbarn) auf den aktuellen Stand korrigieren.

- [Minor] `bin/vibe:404-411` — `set_env_values` ersetzt den ersten Treffer, die Leserichtung gewinnt die letzte Zeile
  - Evidence: Beim Ersetzen wird der erste auf `^\s*KEY\s*=` passende Treffer geändert (`break` in Zeile 411); `read_env` (`bin/vibe:120-127`) und `read_env_file` (`bin/vibe_sandbox.py:113-125`) überschreiben bei Wiederholungen dagegen mit dem letzten Wert. Enthält `project.env` (nur durch manuelle Bearbeitung möglich) zwei SANDBOX-Zeilen, meldet das UI „Sandbox ausgeschaltet“, der Status bleibt aber „an“, weil die zweite Zeile weiterzählt.
  - Required fix: Ersetzungsregel an die Leserichtung angleichen (letzten Treffer ersetzen) oder Duplikate beim Schreiben erkennbar ablehnen; den Fall mit einem Test sichern.

## Verification
- Change set reviewed: `32e1a99..working tree` (Branch `feature/f7-sandbox`); alle 15 geänderten Dateien per `git diff` gelesen, alle neuen Dateien vollständig gelesen (`bin/vibe_sandbox.py` 586 Zeilen, `tests/unit/test_sandbox.py` 827, `tests/browser/test_sandbox_ui.py` 211, `docs/features/F7.md` 451, `docs/reviews/F7-review-1.md`), `docs/features/F7-sandbox.png` als Bild geprüft (Karte „bereit“, `git python3`, 8 Schreibverzeichnisse, kein NaN-Artefakt).
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff 32e1a99 --stat`, `git diff 32e1a99 -- bin/vibe-run.sh bin/vibe`, `git diff 32e1a99 -- bin/vibe-web.py FEEDBACK.md templates scripts/setup-vibe.py tests/unit/test_setup_vibe.py docs/trilium-index.md docs/features/F3.md docs/baseline.md`, `git diff 32e1a99 -- docs/import-manifest.json`, `git diff 32e1a99 -- docs/baseline.md`. (Ein erstes kombiniertes Shell-Kommando wurde von den Berechtigungen abgelehnt; danach nur Einzelbefehle. Keine Dateiänderungen.)
- Checks with supplied output (vom coding agent geliefert, von mir nicht erneut ausgeführt): Unit-Suite 216 OK, Browser-Suite 11 OK, Sandbox-Modul 29 OK, `check-syntax.py` OK, `check-no-secrets.py` OK, `check-import-manifest.py` OK (26 Dateien), `bash scripts/verify.sh quick` exit 127 (Skript fehlt; `VERIFY_QUICK/VERIFY_FULL` = `echo TODO` — F7.md:396-401 weist dies nachweislich aus). Rote Nachweise für die Round-1-Fixes (Exit 2 statt 0/1, „ESCAPED“, fehlendes Modul lief Exit 0) wurden geliefert und passen zu den Tests.
- Checks not independently run: alle Build- und Testläufe; die verwendeten Exit-Codes von `python3` (Exit 1 bei unbehandelter Ausnahme) stammen aus Sprachverhalten, nicht aus einem eigenen Lauf.
- Von mir unabhängig verifiziert: Trilium-Notiz `ZzVeElHG2ifr` („F7 Sandbox für Shell und Build-Werkzeuge“, geändert 2026-10-26 16:55 UTC) über den MCP-Zugang gelesen — sie nennt `--enabled`, `vibe-run`, `SANDBOX_TOOLS` und die Vorlagen; `docs/import-manifest.json` führt `bin/vibe_sandbox.py` neu mit aktualisierten Prüfsummen; Tokenprüfung `bin/vibe-web.py:143` liegt vor `/api/sandbox`.
- Wichtig geprüfte Bereiche: Läufer-Steuerfluss (Abbruchpfade, `PIPESTATUS`, `SANDBOX_WRAP`-Wrapping je Durchgang), fehlendes Modul vs. korruptes Modul, `--check` vor dem ersten Paket (Nebeneffekt: legt Schreib-/Zustandsverzeichnisse an, bwrap-Probe mit `--remount-ro`, 15 s Timeout — kein misleading failure, F7.md dokumentiert), Delegation `bin/vibe` → `vibe_sandbox` (kein Zirkelimport; `sys.path`-Insert in `bin/vibe:35`, `read_env`-Parsen identisch zu `read_env_file`), Round-1-Nachbesserungen (Cargo, Probe-Optionen, Testname inkl. HOME-Deny), Tests auf echte Assertions und Fail-Pfade (bwrap-Pflicht assertion statt Skip, eindeutige Temp-Pfade, keine entfernten/abgeschwächten Alt-Assertions laut Diff), Screenshot und Manifest.
- Remaining risks: Der Round-1-High ist für alle dokumentierten Werte geschlossen; die verbleibende Exit-1-Mehrdeutigkeit (Befund 1) ist der offene fail-open-Rest. Kein automatisierter Nachweis, dass echte MCP-Server innerhalb der Sandbox starten (dokumentierte Grenze). Die F8-Zeilen liegen weiterhin uncommitted in FEEDBACK.md — der versprochene partielle Staging-Ausschluss ist erst beim Commit prüfbar und muss dort eingehalten werden. `verify.sh quick/full` existiert weiterhin nicht (projektweiter V-002-Stand, kein F7-Defekt).
