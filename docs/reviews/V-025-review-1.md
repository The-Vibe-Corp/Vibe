# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Nicht vorhandener oder im Projekt nicht aktiver `AGENT` verhindert den Start nicht (Vibe-Agent gültig und aktiv) | PASS | `bin/vibe:1660-1675` (Pufferung gegen `project_agent_inventory` + aktive Liste, Rückfall auf `status["name"]`) | `test_missing_agent_falls_back_to_vibe_and_repairs_project_env`, `test_global_but_inactive_agent_is_repaired` (test_v025_agent_start_repair.py); Bericht: 8 Tests OK, Exit 0 |
| Vibe verwendet den Vibe-Agenten und schreibt ihn als `AGENT` in `.vibe/project.env`; alle anderen Zeilen unverändert | PASS | `bin/vibe:1671` + `repair_project_agent` `bin/vibe:2926-2952` (nur erste `AGENT`-Zeile, count=1, `vibe_storage.write_text` mit erwarteter Prüfsumme) | `test_repair_preserves_other_lines_verbatim` (bytegleiche Erwartung), `test_write_error_still_starts_with_vibe_and_reports_error` (nachweislich schreibender Pfad) |
| Gültiger, aktiver `AGENT` bleibt unverändert und wird verwendet | PASS | `bin/vibe:1666` (Bedingung trifft nicht zu → kein Schreiben, kein修缮) | `test_active_agent_is_used_and_env_stays_unchanged` (Datei bytegleich, Start mit `tester`) |
| Ausdrücklich übergebener, nicht aktiver Agent weiterhin abgelehnt; Projektdatei unverändert | PASS | `bin/vibe:1661` (Repair nur bei `agent is None`), `bin/vibe:1689-1691` (`sys.exit` aus `run_agent_selection`); Interaktionspfade liefern `None` (`bin/vibe:4575, 4623`) | `test_explicit_inactive_agent_is_rejected_without_writing` |
| Schreibfehler bei der Korrektur verhindert den Start nicht; Fehler gemeldet | PASS | `bin/vibe:1670-1673` (`except (OSError, ValueError, vibe_storage.StorageError)`; `ConcurrentChangeError` ist `StorageError`-Unterklasse, `vibe_storage.py:52-57`) | `test_write_error_still_starts_with_vibe_and_reports_error` mit `failing_writes`-Simulation |
| Vorlagen ohne fest eingebauten `AGENT`-Namen | PASS | `templates/{android,docker,generic,openwrt,rebuild,web}/.vibe/project.env` (Zeile entfernt); Byte-Delta je 28 = `AGENT=coding-agent_deepseek\n`, konsistent mit Manifest | `test_shipped_project_templates_contain_no_agent_entry`; Rot-Nachweis von mir direkt gegen `ee20120` verifiziert (`git show ee20120:templates/web/.vibe/project.env` enthält die Zeile) |
| Ausgabe nennt alten und neuen Agenten | PASS | `bin/vibe:1669` | `test_repair_message_names_old_and_new_agent` |

## Findings
- [Minor] `bin/vibe:2926-2952` — `repair_project_agent` schreibt den Agentennamen ohne Namensprüfung in die Projektdatei
  - Evidence: Der Wert `replacement` kommt aus `profiles.json` (`vibe_agent_name`, `bin/vibe:2222-2227`) und wird erst **nach** dem Repair an `bin/vibe:1680` gegen `NAME_RE` geprüft. `agent_role_set` validiert Namen beim Setzen der Rolle (`bin/vibe:2192`), aber eine von Hand editierte `profiles.json` mit ungültigem Rollennamen würde dauerhaft einen ungültigen `AGENT=` in `project.env` schreiben; jeder weitere Start bricht dann an `bin/vibe:1680` mit „Agentenname: nur a-z, 0-9, _ und -" ab. Keine Shell-Injektion (tmux-Aufruf als Argumentliste `bin/vibe:1715-1718`), kein Sicherheitsproblem — nur eine selbstverschuldete Dauersperre in einem bewusst streng gesicherten Pfad.
  - Required fix: Die Funktion (oder der Aufrufer vor dem Schreiben) soll dieselbe Namensprüfung anwenden, die an `bin/vibe:1680`/`agent_role_set` gilt, und bei ungültigem Namen auf den bisherigen Speicherwert zurückfallen bzw. den Repair mit verständlicher Meldung überspringen.
- [Minor] `tests/unit/test_v025_agent_start_repair.py` — CRLF-Erhaltung und Quoted-Format nicht abgedeckt
  - Evidence: `repair_project_agent` verspricht CRLF- und Format-Erhaltung (`bin/vibe:2938, 2942-2949`; Doku `docs/features/V-025.md:72-73`), aber kein Testfall prüft eine CRLF-Projektdatei oder `AGENT="name"`. Der Test-Agent benennt diese Lücke selbst im Bericht („Verbleibende Lücken"). Keine verletzte Akzeptanzkriterium — die Kriterien sprechen von „Zeilen", die `(LF-)Tests` decken sie ab.
  - Required fix: Nächstes Test-Paket des Test-Agenten: je ein Fall CRLF-Datei und gequotter `AGENT`-Wert ergänzen; Implementierung gegebenenfalls nachbessern.

Positive Feststellungen aus eigener Prüfung (nicht nur Bericht):
- Die zwei `verify.sh full`-Fehlschläge sind plausibel vorbestehend: die Home-Pfad-Verstöße liegen in **unveränderten, getrackten** Dateien (`docs/features/B5.md:218`, `docs/features/F23.md:114`, `docs/features/B4.md:15,36`, `FEEDBACK.md:325,339` — von mir selbst per Grep geprüft); keines der drei neuen V-025-Dokumente enthält `/home/…`- oder `/Users/…`-Treffer. `tests/unit/test_release.py` und `tests/unit/test_ap04_setup_harness.py` sind nicht im Paket-Diff.
- Die Testzahl 1169 = 1161 (V-024-Nachweis in TICKETS.md:620) + 8 neue Tests ist konsistent.
- Manifest-Bytezahlen aller sechs Vorlagen differieren um exakt die Länge der entfernten Zeile (28 Byte), `grund`-Eintrag V-025 entspricht dem bestehenden Eintragsformat (`docs/import-manifest.json:851-865`).
-entials Templates-Änderung ist durch SPEC.md:120 („Keine fest eit eingebauten Agentennamen für die Produktlogik") fachlich gedeckt und für neue Projekte sinnvoll (kein Repair beim Erststart nötig).
- Keine Geheimnisse, keine persönlichen Pfade, keine verifizierenden Prüfwerkzeuge (`scripts/verify.sh`, `check-import-manifest.py` …) im Diff; Arbeitsbaum enthält nur die Paketdateien (`git status`).
- Die Tests mocken nur externe Grenzen (`run`, tmux, Registry, Kennwortdatei), nicht das geprüfte Verhalten (Repair-, Auswahl- und Schreiblogik bleiben real); alle 8 Tests haben echte, nicht-triviale Assertions; kein Skip, keine leerer Tests.

## Verification
- Change set reviewed: `ee20120..working tree` (voller `git diff ee20120`, zusätzlich die drei unversionierten Dateien vollständig gelesen: `tests/unit/test_v025_agent_start_repair.py` (8 Tests), `docs/features/V-025.md`, `docs/reviews/V-025-test-agent-report.md`).
- Git commands run by me: `git status --short`, `git diff ee20120 -- bin/vibe`, `git diff ee20120 -- templates/ docs/import-manifest.json`, `git diff ee20120 --stat`, `git show ee20120:templates/web/.vibe/project.env`, `git diff --no-index --numstat /dev/null /dev/null`. (Branch/Log-Bestätigung und `git branch --show-current` scheiterten an den Freigabeberechtigungen der Umgebung; der Branchname ist angegeben, aber **did** von mir nicht eigenständig verifiziert.)

Notiz zur Umgebung: Alle Nicht-Git-Befehle (`grep`, `sed`, `sha256sum`, `python3`) wurden in dieser Sitzung durch die Werkzeugfreigaben verweigert; der oben als „eigene Prüfung" bezeichnete Grep-Anteil lief über das Grep-Werkzeug, die Git-Belege über `git show`/`git diff`.

- Checks with supplied output (vom Coding/ Test-Agent übergeben, nicht von mir ausgeführt): `python3 -m unittest tests.unit.test_v025_agent_start_repair -v` → 8 Tests, OK, Exit 0; 91 gerahmte Agent-Tests OK, Exit 0; `bash scripts/verify.sh quick` → Exit 0; `bash scripts/verify.sh full` → Exit 5, 1169 Tests, exakt die zwei vorbestehenden Fehlschläge. Rot-Anteil laut Bericht: `Ran 7 tests, FAILED (errors=5)` vor der Implementierung; Regressionsfälle AK3/AK4 waren dort bereits grün.
- Checks not independently run: alle Test- und Verify-Läufe (für einen Reviewer verboten); unabhängige SHA-256-Bestätigung der Manifesteinträge (nur Byte-Konsistenz und `verify quick`-Bericht vorhanden).
- Important areas inspected: `cmd_run`-Agentenauflösung (`bin/vibe:1654-1680`), `repair_project_agent` (`bin/vibe:2926-2952`), `run_agent_selection` (`bin/vibe:2908-2923`), `vibe_agent_status/name` (`bin/vibe:2222-2243`), `vibe_storage.read_snapshot/write_text/check_expected` (`bin/vibe_storage.py:98-114, 278-331`), `read_env` (`bin/vibe:443-449`), Freistaht der `require_agent`-Wall, import-Mmanifest-Adapterformat, alle drei neuen Dateien vollständig.
- Remaining risks: sha256-Prüfsummen im Manifest wurden nur indirekt (Bytezahlen, `verify quick`-Bericht) plausibilisiert; die im Bericht genannten Lücken (CRLF, Quoted-`AGENT`, `agents.json`-Unveränderlichkeit beim Repair) sind ungetestet; Trilium- und Review-Nachtrag (V-025.md:132-133: „wird nach dem Review ergänzt") stehen aus und sind gemäß Arbeitsablauf nach diesem Review zu erledigen.
