# Review GH-46 — Runde 1

Reviewer: unabhängiger Review-Agent (vibe-reviewer), read-only.
Gegenstand: Arbeitspaket GH-46 im Branch feature/korbat/gh-46, Ausgangscommit `5b9e018`, Änderungssatz `5b9e018..working tree`.
Datum: 2026-11-23.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| 1. `GENERAL_RULES` in `bin/vibe` von projektspezifischen Test-Implementierungen befreien (generisch, präzise, gültig für jedes Projekt, kein Widerspruch zum Arbeitsmodell des vibe-Projekts); verwaltete Blöcke in allen 5 Vorlagen und der Root-`AGENTS.md` bytengleich synchronisieren; Vorschläge für weitere Anpassungen der projekt-eigenen `AGENTS.md`-Abschnitte ausweisen | PASS | `bin/vibe:102-153` (`Effizienz der Prüfungen (verbindlich)` in `bin/vibe:125-137`, Entfernung von `Baseline-Disziplin (verbindlich)`); `templates/generic/AGENTS.md:6-57`; `templates/docker/AGENTS.md:8-59`; `templates/web/AGENTS.md:9-60`; `templates/rebuild/AGENTS.md:59-110`; `templates/android/AGENTS.md:12-63`; `AGENTS.md:85-136`; Vorschläge in `docs/features/GH-46.md:87-95` | Direkt gegengelesen (Diff & Volltext aller 5 Vorlagen + Root-`AGENTS.md`); Testvertrag in `tests/unit/test_ap7_korbat_rules.py:120-204` und `tests/unit/test_project_management.py:445-462`; vorgelegtes Ergebnis (vom Coding-Agenten berichtet + im Abnahme-Volllaufprotokoll `gh46-acceptance-full-2.log` enthalten): `test_ap7_korbat_rules` OK, `verify.sh quick` Exit 0 |
| 2. Transport der lokalen Baseline (`.vibe/verify-baseline`) bei Worktree-Erzeugung (`copy-notes`) und zugehörigen Hash-Wächter im Runner entfernen, während `.vibe/project.env`-Transport und -Wächter (AP5/T-V21) unangetastet bleiben | PASS | `bin/vibe_packages.py:102-110` (`TRANSPORTED_PATHS = (PROJECT_ENV_REL,)`, `VERIFY_BASELINE_REL` entfernt), `bin/vibe_packages.py:252-270`, `bin/vibe_packages.py:1696-1700`; `bin/vibe-run.sh:57-93` (`guard_transported_files`), `bin/vibe-run.sh:1608-1613`, `bin/vibe-run.sh:1662-1670`; `docs/features/AP7-Korbat.md:169-183` | Repo-weite Suche (`grep`) bestätigt 0 verbleibende aktive Referenzen auf `VERIFY_BASELINE_REL` oder `PKG_HASH_BASELINE`; Testverträge in `tests/unit/test_ap5_korbat_project_env_transport.py:295-369` und `tests/unit/test_ap7_korbat_runner.py:223-342`; vorgelegtes Ergebnis + `gh46-acceptance-full-2.log`: `test_ap5_korbat_project_env_transport` und `test_ap7_korbat_runner` grün |
| 3. Einmaliger autorisierter Baseline-Bootstrap für Umgebung `pi-aarch64-py3.14-namespaces`, Vergleich der Defekte mit dokumentierten Vorbeständen, Review und erste committete Version (`tests/verify-baseline.json`) inkl. Behebung des Signatur-Quoting-Defekts in `scripts/verify_engine.py` | PASS | `tests/verify-baseline.json:1-85` (`version: 1`, `min_tests: 2500`, 15 Einträge unter `pi-aarch64-py3.14-namespaces`); `scripts/verify_engine.py:506-515` (`normalize_message`: `(?:^|[\s"'])/[A-Za-z0-9_./\-]+`); Vorbestandsvergleich in `docs/features/GH-46.md:63-80` | Vorgelegte Rohprotokolle direkt geprüft: `gh46-bootstrap-full.log` (Zeilen 2591-2611: 2637 Tests, 15 Module, Mismatch/Exit 7), `gh46-acceptance-full.log` (Zeilen 2591-2609: Exit 7 wegen `test_sandbox`-Temp-Pfad in JSON-Quotes), `gh46-acceptance-full-2.log` (Zeilen 2591-2611: `BASELINE-OK`, 2637 Tests, 15 bekannte Module, Exit 0); `.vibe`-Verzeichnis enthält nur noch `project.env` (lokaler Vorschlag gelöscht); `SignatureNormalizationTest` in `tests/unit/test_ap7_korbat_baseline.py:662-808` |

## Findings
- No findings.

## Detailprüfung der Review-Schwerpunkte

1. **Regelblock (`bin/vibe:102-153`, `AGENTS.md:26-136`)**:
   - Die Sektion `## Effizienz der Prüfungen (verbindlich)` (`bin/vibe:125-137`) benennt jetzt ausschließlich die Prüfbefehle in `.vibe/project.env` (`VERIFY_QUICK`, `VERIFY_PACKAGE`, `VERIFY_FULL`) als gemeinsame Prüfschnittstelle für Agenten und Läufer, hält die Stufung (gezielte Aufrufe betroffener Testmodule + `VERIFY_PACKAGE` während der Arbeit; `VERIFY_FULL` genau einmal vor der Abnahme und erneut nur nach echten Änderungen an Code oder Tests) fest und enthält keinerlei vibe-spezifische Implementierungsdetails (`verify.sh`, Exitcodes 3/6/7, `--write-baseline`, `VERIFY_MIN_TESTS`, `Baseline-Disziplin`).
   - Abgleich mit den projekt-eigenen Abschnitten in `AGENTS.md:32-38` (Ticket workflow, Schritt 5): Dort sind `bash scripts/verify.sh quick|package|full`, die Exitcode-Semantik (`0`, `3`, `6`, `7`), der autorisierte `Baseline bootstrap` (`--env <label> --write-baseline`), die review-gated `Baseline progression` über `tests/verify-baseline.json` (inkl. Monotonie von `min_tests`, Löschpflicht lokaler Vorschläge wegen D1-Exklusivität, Rückbau grüner Module) sowie die Abgrenzung zum Runner-Endgate vollständig vorhanden.
   - Ausnahme „keine Umgebungsangaben in Baseline-Dateien": Der generische Grundsatz (`Laufzeitdaten, persönliche Konfiguration und Geheimnisse gehören nicht ins Repository.`) steht weiterhin in `## Projektordner sauber halten` (`bin/vibe:107`). Die baseline-spezifische Konkretisierung (keine IP-Adressen, Hostnamen, Geheimnisse, absoluten Pfade in Baseline-Dateien) nicht eigenmächtig in den nutzergepflegten Teil der `AGENTS.md` zu schreiben, sondern als expliziten Vorschlag in `docs/features/GH-46.md:90` (§5.2) auszuweisen, entspricht exakt der Projektvorgabe („AGENTS.md should be adapted by the user, not by an agent") und der F27/T-I1-Architektur (Agenten ändern nur den verwalteten Markerblock via `ensure_general_rules`).

2. **Vorlagen-Sync (`templates/{generic,docker,web,rebuild,android}/AGENTS.md`, `AGENTS.md`)**:
   - In allen fünf Vorlagen und in der Root-`AGENTS.md` existiert genau ein Markerpaar `<!-- vibe:general-rules -->` … `<!-- /vibe:general-rules -->`.
   - Der Blockinhalt ist in allen sechs Dateien bytengleich mit `GENERAL_RULES` in `bin/vibe:102-153`.
   - `git diff 5b9e018` bestätigt, dass außerhalb der Marker in keiner Vorlage und auch nicht in `AGENTS.md` Nutzerteile verändert wurden.

3. **Transport- und Wächter-Entfernung (`bin/vibe_packages.py`, `bin/vibe-run.sh`)**:
   - `VERIFY_BASELINE_REL` und `PKG_HASH_BASELINE` sind im gesamten Repository entfernt (einzige Fundstellen in historischen Review-Berichten `docs/reviews/AP7-Korbat-review-{1,2}.md` und im Änderungsbericht `docs/features/GH-46.md`).
   - `TRANSPORTED_PATHS = (PROJECT_ENV_REL,)` in `bin/vibe_packages.py:109` transportiert weiterhin `.vibe/project.env` read-only (`0444` best effort) und trägt sie idempotent in `.git/info/exclude` ein.
   - `guard_transported_files` in `bin/vibe-run.sh:78-93` prüft weiterhin unverändert auf Veränderung oder Löschung einer beim Paketstart vorhandenen `.vibe/project.env` und bricht bei Manipulation ohne Reparaturrunde ab (`bin/vibe-run.sh:1666-1670`).
   - Kommentare und Docstrings in `bin/vibe_packages.py:102-108,252-270,1696` und `bin/vibe-run.sh:57-77,1608,1662-1665` sowie die Ablösungs-Nachträge in `docs/features/AP7-Korbat.md:169-183` beschreiben das neue Verhalten konsistent.

4. **Baseline-Manifest (`tests/verify-baseline.json:1-85`)**:
   - Vollständig gelesen: Schema v1 (`"version": 1`), `"min_tests": 2500` (monotone Anhebung von `2000` auf das operative `VERIFY_MIN_TESTS=2500` aus `.vibe/project.env:8`), Umgebungsschlüssel `"pi-aarch64-py3.14-namespaces"` mit exakt 15 Einträgen.
   - Jeder Eintrag besitzt ausschließlich die Felder `module`, `class`, `signature` (`sha256:<64 hex>`). Es sind keine Hostnamen, IP-Adressen, Pfade oder Geheimnisse enthalten.
   - Direktabgleich gegen die Rohprotokolle `gh46-bootstrap-full.log` (Zeilen 2595-2609) und `gh46-acceptance-full-2.log` (Zeilen 2593-2609): Alle 13 von gequotedten Pfaden nicht betroffenen Signaturen stimmen 1:1 mit dem Bootstrap-Protokoll überein; alle 15 Einträge (inkl. der nach dem Engine-Fix neu berechneten Signaturen für `tests.unit.test_project_management` und `tests.unit.test_sandbox`) matchen im zweiten Abnahme-Volllauf als `BASELINE-OK` (Exit 0).

5. **Engine-Fix (`scripts/verify_engine.py:506-515`)**:
   - Minimale Änderung in Zeile 509: `re.sub(r"(?:^|[\s\"'])/[A-Za-z0-9_./\-]+", " <pfad>", text)` statt `r"(?:^|\s)/[A-Za-z0-9_./\-]+"`.
   - Erfasst führende `/` nach `"` (z. B. JSON-Payloads in `test_sandbox` mit `/tmp/.../vv-<rand>/...`) und nach `'` (z. B. `FileNotFoundError` mit `'/<worktree>/...'` in `test_project_management`), ohne Fehlertexte außerhalb von Pfaden zu verändern.
   - Dass die übrigen 13 Einträge aus dem Bootstrap-Lauf in `gh46-acceptance-full-2.log` mit unveränderter Signatur als `BASELINE-OK` erkannt werden, belegt die Nichtinvasivität des Fixes unmittelbar.

6. **Test-Agent-Regel & Test-Integrität**:
   - Alle fünf geänderten Testdateien (`tests/unit/test_ap7_korbat_rules.py`, `tests/unit/test_ap5_korbat_project_env_transport.py`, `tests/unit/test_ap7_korbat_runner.py`, `tests/unit/test_project_management.py`, `tests/unit/test_ap7_korbat_baseline.py`) enthalten aussagekräftige, scharfe Assertions auf die geänderten Verträge (Verbot projektspezifischer Fragmente im generischen Block, Bytengleichheit über `managed_block`, Nicht-Transport und Nicht-Bewachung von `.vibe/verify-baseline` bei fortbestehendem `project.env`-Schutz, Schema- und Hygieneprüfung des Baseline-Manifests, Signaturstabilität und Nicht-Übernormalisierung in `SignatureNormalizationTest`).
   - Vorbestehende, vom Paket unberührte Testverträge wurden nicht abgeschwächt; die F22-Vorbestände in `test_project_management` bleiben unangetastet.

7. **Fachdokumentation (`docs/features/GH-46.md`) & Import-Manifest (`docs/import-manifest.json`)**:
   - `docs/features/GH-46.md` dokumentiert Ziel, Änderungen, Vorbestandsvergleich der 15 Module (inkl. präziser Einordnung von `test_ap4_korbat_rules` infolge Merge #54 am Branchpunkt `5b9e018`), Design-Entscheidungen, die 6 Vorschläge für die nutzergepflegten `AGENTS.md`-Abschnitte sowie Verifikation und Grenzen ohne persönliche Pfade oder Geheimnisse.
   - `docs/import-manifest.json` aktualisiert exakt die 8 geänderten Scoped-Dateien (`bin/vibe`, `bin/vibe-run.sh`, `bin/vibe_packages.py`, 5× `templates/*/AGENTS.md`) und begründet sie unter `arbeitspaket: "GH-46"`.

8. **Baseline-Disziplin im Paketverlauf**:
   - Bootstrap war ausdrücklich im Ticket gefordert („Run the baseline bootstrap once on this environment, compare defects to documented past ones, then review and commit the first version for this environment").
   - Die beiden Abnahme-Vollläufe liefen ohne `--write-baseline` (belegt durch die Kopf- und Fußzeilen in `gh46-acceptance-full.log` und `gh46-acceptance-full-2.log`).
   - Das Verzeichnis `.vibe/` enthält nur `project.env`; die temporäre Vorschlagsdatei `.vibe/verify-baseline` ist gelöscht.

## Verification
- Change set reviewed: `5b9e018..working tree` (17 modifizierte getrackte Dateien, 1 unversionierte neue Doku-Datei `docs/features/GH-46.md`, plus Aktualisierung des verwalteten Blocks in der unversionierten Root-`AGENTS.md`).
- Git commands run by me: `git status --short`, `git diff 5b9e018`.
- Checks evidenced by supplied raw output:
  - `/tmp/opencode/vibe-sandbox/vibe-c7188db792/tmp/opencode/gh46-bootstrap-full.log`: `Gesamt: 2637 Tests, 131/146 Module bestanden, 15 fehlgeschlagen`, `VERIFY_RESULT: mode=full tests=2637 failed_modules=15`, Exit 7 (erwarteter Mismatch beim ersten Bootstrap mit `--write-baseline`).
  - `/tmp/opencode/vibe-sandbox/vibe-c7188db792/tmp/opencode/gh46-acceptance-full.log`: `Gesamt: 2631 Tests, 131/146 Module bestanden, 15 fehlgeschlagen`, `Neue Regression: tests.unit.test_sandbox`, 14× `Bekannt rot`, Exit 7 (vor dem Engine-Fix).
  - `/tmp/opencode/vibe-sandbox/vibe-c7188db792/tmp/opencode/gh46-acceptance-full-2.log`: `Gesamt: 2637 Tests, 131/146 Module bestanden, 15 fehlgeschlagen`, `BASELINE-OK` für alle 15 bekannten Module, `VERIFY_RESULT: mode=full tests=2637 failed_modules=15 baseline_ok=1 env=pi-aarch64-py3.14-namespaces`, `OK: Prüfung 'full' erfolgreich. (Exit 0)`.
- Checks reported only by the coding agent: Rotphasen-Läufe des Test-Agenten (21 erwartete Fehler in Rotphase 1; 4 erwartete Fehler in Rotphase 2 für `SignatureNormalizationTest`), Einzel-Grünläufe `python3 -m unittest tests.unit.test_ap7_korbat_rules tests.unit.test_ap5_korbat_project_env_transport tests.unit.test_ap7_korbat_runner -v` (24/24 OK), `python3 -m unittest tests.unit.test_ap7_korbat_baseline -v` (29/29 OK), `bash scripts/verify.sh quick` (Exit 0), `bash scripts/verify.sh package` (Exit 0). (Hinweis: Die Unit-Test-Module sind zusätzlich als Bestandteil des Rohprotokolls `gh46-acceptance-full-2.log` mit `OK` belegt.)
- Checks not independently run: all build, test, and other non-Git checks (read-only review).
- Important areas inspected: `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe-run.sh`, `scripts/verify_engine.py`, `templates/{generic,docker,web,rebuild,android}/AGENTS.md`, `AGENTS.md`, `tests/verify-baseline.json`, `docs/import-manifest.json`, `docs/features/AP7-Korbat.md`, `docs/features/GH-46.md`, `tests/unit/test_ap7_korbat_rules.py`, `tests/unit/test_ap5_korbat_project_env_transport.py`, `tests/unit/test_ap7_korbat_runner.py`, `tests/unit/test_ap7_korbat_baseline.py`, `tests/unit/test_project_management.py`.
- Remaining risks: Die in `docs/features/GH-46.md` §5 aufgeführten Anpassungen der nutzergepflegten Abschnitte in `AGENTS.md` (insb. §5.1 veralteter Halbsatz zum Baseline-Transport/Wächter in Workflow-Schritt 5, §5.2 Hinweis auf keine Umgebungsangaben in Baseline-Dateien, §5.3 Rekursionshinweis für `VERIFY_QUICK`) sowie das Folge-Ticket zum #54-SPEC-Sprachdrift (`test_ap4_korbat_rules`) obliegen vereinbarungsgemäß dem Nutzer bzw. einem separaten Ticket.

Verdict: PASS
