# Review F31 — Runde 6 (unabhängiger code-reviewer, 2026-11-17)

Review zu FEEDBACK.md F31 „Full test suite kostet zeit" (dieser Zyklus; die
Kennung F31 war im vorigen Zyklus für das AGENTS.md-Paket vergeben, siehe
docs/features/F31.md). Arbeitskopie vibe-F31-3rRbm8, Branch
vibe/vibe-F31-1794952034093847392-2175, Basis b7fb398. Der Review-Text
wurde vom Koordinator unverändert aus der Reviewer-Antwort persistiert
(die Dateianlage war dem Reviewer in dieser Sitzung verweigert).

## Summary
- Critical: 0
- High: 1
- Medium: 6
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| `package` führt ausschließlich `VERIFY_PACKAGE` aus, verlangt einen Testnachweis nur bei gesetztem `VERIFY_TESTS` und startet keinen opencode-Dienst | PASS | `scripts/verify.py:401-465`, insbesondere `:403-405`, `:435-437` | `tests/unit/test_verify_script.py:450-603`; geliefert: 11/11 OK (nicht selbst ausgeführt) |
| `package` ist über CLI-Menü/Help, API und UI erreichbar | PASS | `bin/vibe:2199-2246`, `bin/vibe:5512-5523`; `bin/vibe-web.py:1232-1239`; `bin/web/app.js:137-141` | Geliefert: `CommandBoundaryTest` 4/4, API-Paketfall 1/1; nicht selbst ausgeführt |
| Unbekannte Prüfmodi werden in CLI und API abgewiesen | FAIL | `bin/vibe-web.py:1234-1237` (Implementierung vorhanden) | Kein Test für den Fehlerpfad; `tests/unit/test_verify_api_package.py:177-203` prüft nur den Erfolgsfall |
| Gestufte Prüfregeln stehen in `GENERAL_RULES` und allen fünf `templates/*/AGENTS.md`, ohne Abschwächung des Abnahmeumfangs | NOT VERIFIED | `bin/vibe:115-119`; `templates/{android,docker,generic,rebuild,web}/AGENTS.md` (Abschnitt „Effizienz der Prüfungen“) | Geliefert: `TemplateRulesTest` 2/3 — die Suite ist rot; zusätzlich fehlt die Rotphase |
| Paralleler Läufer führt Module parallel aus, berichtet deterministisch, verliert keine Tests und setzt Exitcodes korrekt | FAIL | `scripts/run-tests-parallel.py:54-145` | Geliefert: 6/6 OK für flache Module; die nicht-rekursive Suche (`:63`) verletzt den zugesicherten Schutz vor stillem Testverlust bei verschachtelten Modulen |
| Der Effizienzgewinn ist auf der realen Suite belegt, ohne Qualitätsverlust | NOT VERIFIED | `scripts/run-tests-parallel.py` | Kein Parallel-Lauf der realen 1790-Tests-Suite, keine Vorher-/Nachher-Messung; geliefert ist nur ein sequenzieller Lauf mit 1044 s |
| Browserabnahme inklusive Screenshot ist ausgeführt | FAIL | `tests/browser/test_f31_verify_package_ui.py:152-184` | Kein Browserlauf geliefert; `docs/features/F31-paketpruefung.png` existiert nicht (Verzeichnis enthält nur `F31.md` und `F31-agents-file.png`) |
| Manifest und Dokumentation sind synchron und nachvollziehbar | NOT VERIFIED | `docs/import-manifest.json:936-948` | Manifest-Check Exit 0 nur agentenseitig; Hashes konnte ich nicht nachrechnen. `docs/features/F31.md:1-10` beschreibt weiterhin das frühere AGENTS.md-Paket; der neue Zyklus beginnt erst `:199` |

## Findings

- [High] `tests/unit/test_run_tests_parallel.py:1-248` (und weitere neue Tests) — Rotphase für die neuen Tests nicht belegt
  - Evidence: Für die neuen Tests (`test_run_tests_parallel.py`, die `package`-Fälle in `test_verify_script.py`, `test_verify_api_package.py`, `test_f31_verify_package_ui.py`) liegt keine Ausgabe eines fehlschlagenden Laufs am Ausgangsstand vor. `docs/reviews/F31-test-agent-report.md` ist vom 2026-11-14 und behandelt ausschließlich das frühere AGENTS.md-Paket. Damit ist weder die Unabhängigkeit der Testableitung noch das beobachtete Rot belegt; die globale AGENTS.md-Regel (§5, „Use red–green–refactor“) und die Test-Integritätsregel verlangen genau diesen Nachweis.
  - Required fix: Vom Test-Agenten pro Testfall Vorbedingung, Aktion und Erwartung sowie die tatsächliche Fehlschlagausgabe am Basisstand `b7fb398` nachliefern, danach den Grünlauf am Endstand. Ohne diesen Nachweis dürfen die Tests nicht als Abnahmeevidenz gelten.

- [Medium] `tests/unit/test_project_management.py:477-485` — neuer Test verlangt eine gitignorierte Datei und ist dauerhaft rot
  - Evidence: Der Test fordert `REPO / "AGENTS.md"` als Datei. `.gitignore:23` ignoriert `/AGENTS.md`; im Arbeitsbaum existiert die Datei nicht (von mir geprüft). Damit schlägt der Test in jedem sauberen Clone deterministisch fehl; die gelieferte Ausgabe `TemplateRulesTest 2/3` bestätigt die rote Suite.
  - Required fix: Die Regel an ihrer versionierten Quelle prüfen (`bin/vibe` `GENERAL_RULES` bzw. die Vorlagen) oder `AGENTS.md` versionieren. Keinesfalls durch Skip/Ignore verdecken.

- [Medium] `scripts/run-tests-parallel.py` — zentrale Effizienzbehauptung auf der realen Suite nicht belegt
  - Evidence: Der Läufer ist vorhanden, aber es gibt keinen Lauf der realen Suite über den Läufer, keine Dauer-/Testzahl-Gegenüberstellung und keinen Vergleich der Fehlmengen. Geliefert ist nur der sequenzielle Lauf mit 1790 Tests und 1044 s. Die Frage aus `FEEDBACK.md:605-608` (12+ Minuten, mehrfach pro Paket) ist damit nicht beantwortet.
  - Required fix: Denselben Commit sequenziell und mit dem Läufer ausführen, Testzahlen, Dauer und identische Pass-/Fail-Mengen dokumentieren.

- [Medium] `tests/browser/test_f31_verify_package_ui.py:152-184` — Browserabnahme und Screenshot fehlen
  - Evidence: Der Test schreibt `docs/features/F31-paketpruefung.png` und prüft die drei Prüfbuttons sowie den Paket-Stream. Ein Browserlauf ist nicht geliefert; die Datei fehlt im Verzeichnis `docs/features` (nur `F31.md` und `F31-agents-file.png` vorhanden). Die UI-Abnahme ist damit nicht erbracht.
  - Required fix: Browser-Test ausführen, Ausgabe und Screenshot als Nachweis liefern oder die UI-Abnahme ausdrücklich als nicht verifiziert kennzeichnen.

- [Medium] `bin/vibe-web.py:1234-1237` — Fehlerpfad für unbekannte Prüfmodi ist ungetestet
  - Evidence: Die API weist unbekannte Modi mit `ok=False` und Meldung ab. `tests/unit/test_verify_api_package.py:177-203` sendet ausschließlich `mode="package"` und prüft den Erfolg; ein Test für einen ungültigen oder fehlenden Modus fehlt.
  - Required fix: Einen unabhängigen Test ergänzen, der einen ungültigen Modus postet und `ok=False`, die Modusmeldung und den Nichtstart eines Prüflaufs belegt.

- [Medium] `templates/android/AGENTS.md:1-10`, `templates/docker/AGENTS.md:1-7` — projektspezifische Regelblöcke ohne Begründung entfernt
  - Evidence: Der Diff gegen `b7fb398` entfernt in beiden Vorlagen Regelblöcke, die nicht zum Effizienzthema gehören. Die aktuellen Dateien enthalten nur noch die Projektkopfzeilen und den verwalteten Regelblock. Weder der Manifest-`grund` (`docs/import-manifest.json:936-948`) noch `docs/features/F31.md` begründen die Entfernung; sie ist eine Verhaltensänderung für neu angelegte Projekte außerhalb des Paketumfangs.
  - Required fix: Die entfernten Blöcke wiederherstellen oder die Entfernung ausdrücklich begründen und freigeben lassen; die Vorlageninhalte durch einen Regressionstest absichern.

- [Medium] `scripts/run-tests-parallel.py:63` — nicht-rekursive Modulsuche kann Tests still auslassen
  - Evidence: `discover_modules` verwendet `base.glob("test*.py")` und erfasst nur direkte Kinder. `unittest discover` arbeitet rekursiv. Ein verschachteltes Testpaket würde nicht ausgeführt, der Bericht meldete dennoch Erfolg und Exit 0 — im Widerspruch zum dokumentierten Vertrag „Kein stiller Testverlust“ (`:24-28`).
  - Required fix: Rekursive Suche (`rglob`) oder unittest-discover-kompatible Erfassung implementieren und mit einem verschachtelten Testmodul belegen, dass es ausgeführt wird.

- [Minor] `tests/unit/test_run_tests_parallel.py:134-158` — zeitbasierter Parallelitätsnachweis ist flaky
  - Evidence: Drei Module schlafen je 1,0 s; die Assertion verlangt `elapsed < 2.6`. Auf belasteten CI-Rechnern können Prozessstart und Scheduling den Wert überschreiten, obwohl korrekt parallel gearbeitet wurde.
  - Required fix: Deterministisch auf überlappende Ausführung prüfen (z. B. gemeinsame Marker/Startzeitfenster) statt auf eine knappe Wanduhrschwelle.

- [Minor] `scripts/run-tests-parallel.py:76-82` — kein Timeout und keine robuste Dekodierung pro Modul
  - Evidence: `subprocess.run` hat keinen `timeout`; ein hängendes Modul blockiert den gesamten Lauf unbegrenzt. `text=True` dekodiert mit Locale-Vorgabe und kann bei abweichender Ausgabe eine Exception auslösen, statt das Modul als fehlgeschlagen zu berichten.
  - Required fix: Konfigurierbaren Timeout mit Fehlerergebnis sowie `encoding="utf-8", errors="replace"` setzen und Timeouts namentlich als fehlgeschlagene Module melden.

- [Minor] `docs/features/F31.md:1-10` — Kopf und Stand beschreiben weiterhin das frühere Paket
  - Evidence: Titel und Stand (`2026-11-14`) gehören zum AGENTS.md-Paket; der neue Zyklus „Test-Suite-Effizienz“ beginnt erst `:199`. Der aktuelle Paketstatus, die Prüfergebnisse und die offenen Punkte (Browserlauf, reale Messung) sind damit an der Spitze nicht erkennbar.
  - Required fix: Kopf/Stand auf den aktuellen Zyklus umstellen und Validierungsergebnisse sowie Grenzen im selben Dokument nachvollziehbar festhalten.

## Verification
- Change set reviewed: `b7fb398..working tree` im Worktree `vibe-F31-3rRbm8`, Branch
  `vibe/vibe-F31-1794952034093847392-2175`; 13 geänderte und 4 neue Dateien, alles uncommitted.
- Git commands run by me: `git status --short`, `git log --oneline -8`, `git diff` je Datei bzw. `git show HEAD:<datei>` für `templates/android/AGENTS.md` und `scripts/verify.py`. Spätere Shell-Aufrufe wurden mit `Permission denied: shell` abgewiesen; die Datei `docs/reviews/F31-review-6.md` konnte ich deshalb nicht anlegen.
- Checks with supplied output: `VerifyPackageTest` 11/11, `CommandBoundaryTest` 4/4, API-Paketfall 1/1, `RunTestsParallelTest` 6/6, `TemplateRulesTest` 2/3, Manifest-/Syntax-/Secrets-Check Exit 0, sequenzieller Lauf 1790 Tests/1044 s. Alle Angaben sind agentenseitig und von mir nicht ausgeführt.
- Checks not independently run: sämtliche Build-, Test- und Browserläufe; Hash- und Manifest-Nachrechnung; `bash scripts/verify.sh package`.
- Important areas inspected: `scripts/verify.py`, `scripts/run-tests-parallel.py`, `bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `tests/unit/test_verify_script.py`, `tests/unit/test_run_tests_parallel.py`, `tests/unit/test_verify_api_package.py`, `tests/unit/test_project_management.py`, `tests/browser/test_f31_verify_package_ui.py`, `templates/*/AGENTS.md`, `docs/import-manifest.json`, `docs/features/F31.md`, `.gitignore`.
- Remaining risks: (1) Der Review konnte nicht als Datei persistiert werden. (2) Die Manifest-Prüfsummen sind nicht gegengeprüft. (3) Die reale Effizienz und die UI-Abnahme sind unbelegt; solange diese Nachweise fehlen, ist das Paket nicht abnahmefähig. (4) `.vibe/project.env` fehlt im Worktree, sodass `verify.sh` dort nicht unmittelbar lauffähig ist.
