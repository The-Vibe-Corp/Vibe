# Review B5 — Runde 1

Reviewer: unabhängiger Review-Agent (`code-reviewer`), Session `ses_e457b62d4ffeFyxXoU0C6dAJ4g`
Datum: 2026-11-08
Bewerteter Stand: Arbeitsbaum nach Ausgangscommit `8d08490` (noch kein Paket-Commit)

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 3
- Minor: 4
- Verdict: FAIL

## Akzeptanzkriterien

| Kriterium | Status | Implementierung (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Ohne ausdrückliche Freigabe darf `/dev/shm` nicht das Host-Verzeichnis zeigen (Escape-Fix) | PASS | `bin/vibe_sandbox.py:512-520` (`--tmpfs /dev/shm` vor allen `--bind`), Doku `docs/features/B5.md:35-58` | `tests/unit/test_b5_sandbox.py:127-149` (Argumentebene), `:156-185` (echte bwrap-Läufe, isoliert/schreibbar). Ergebnisgrün „Ran 9 tests … OK“ nur vom Coding-Agenten geliefert, nicht von mir gelaufen |
| Mit Freigabe bindet die Schleife `/dev/shm` wie jede Freigabe | PASS | `bin/vibe_sandbox.py:528-537` (`directories`-Schleife, Freigabe unterdrückt `--tmpfs`) | `ShmArgumentTest` legt `permissions.json` mit `/dev/shm` an und prüft Abwesenheit des tmpfs-Paars (`test_b5_sandbox.py:139-149`) |
| Zustands-/Socket-Pfade bleiben unter AF_UNIX-limit; Rückfall `/tmp/opencode/vsb/<sha256[:10]>` mit Projektzuordnung | PASS | `bin/vibe_sandbox.py:53-58` (`STATE_PATH_LIMIT=100`, `SHORT_STATE_ROOT`), `:217-233` (`state_dir()` Rückfall) | `StateDirTest` (`:191-251`), `SetEnvTest.test_setenv_paths_stay_under_96_chars` (`:258-279`), `tests/unit/test_costs_refresh.py:341-384` (`SandboxDbPathRuleTest`). Ergebnisse agent-geliefert; rote Phase („10 failures“) nur in `docs/features/B5.md:126-139` zitiert |
| Bestandsverhalten (F7) bricht nicht zurück: write_dirs, setenv-Belegungen, bestehende Sandbox-Tests | NOT VERIFIED | `bin/vibe_sandbox.py` unverändertes Verhalten laut Lektüre; `test_sandbox.py:216-218` assertion unverändert (kurze Pfad-Variante) | 31 Ergebnisse von `test_sandbox.SandboxCommandTest/-RunnerTest` nur agent-geliefert. Pflichtprüfung `verify.sh full` nach agenteneigener Aussage noch nicht abgeschlossen → Pflichtnachweis fehlt |
| Manifest-Konsistenz (`bin/vibe_sandbox.py` 73cfd524…, 25885 Bytes) | NOT VERIFIED | `docs/import-manifest.json:92-94` enthält behauptete Werte | `verify.sh quick` Exit 0 nur agent-geliefert; independently nicht nachprüfbar (Hash nicht berechenbar ohne Shell) |
| Doku-Deckung (`docs/features/B5.md`) | FAIL | `docs/features/B5.md` vorhanden; deckt beide Fixes ab | Enthält aber scheinbare Nachweise auf nicht vorhandene Artefakte (siehe M2) |

## Befunde

- [Medium] `docs/features/B5.md:170-173, 189-192` — Pflichtnachweis „verify full“ als erledigt behauptet, Ergebnis nicht verfügbar
  - Evidence: Der Coding-Agent selbst teilt mit: „`bash scripts/verify.sh full` läuft aktuell im tmpfs-Klon … Ergebnis noch ausstehend.“ Zugleich behauptet `B5.md:170-173`, „Protokoll und Testzahlen stehen … in `docs/reviews/B5-review-1.md`“ — diese Datei existiert im Arbeitsbaum nicht (glob `docs/reviews/B5*` leer, auch im Projektordner `/var/mnt/.../vibe/docs/reviews/`摩羯). AGENTS.md nennt `verify.sh full` verbindlich; der Definition of Done („Relevante automatisierte Prüfungen grün“) ist ohne Ergebnis nicht erfüllbar.
  - Required fix: Vollständigen `verify.sh full` auf dem endgültigen Paketstand im kurzen tmpfs-Klon abschließen, Ergebnisprotokoll als zugreifbaren Nachweis sichern und die Dokumentation erstdanach auf die tatsächliche Datei verweisen.
- [Medium] `docs/features/B5.md:109, 141-148, 171-173` — Doku referenziert nicht vorhandene Artefakte und wiederspricht FEEDBACK.md
  - Evidence: Änderungstabelle sagt „`FEEDBACK.md` | Eintrag B5 abgeschlossen mit Nachweis“, tatsächlich ist FEEDBACK.md (Zeile 239) weiterhin `- [ ] B5` ohne `Commit:`/`Test:`-Zeilen. Außerdem ist der Abschnitt „Interpretationsabsicherung durch Rückfragen (F16)“ doppelt vorhanden (Zeilen 81-86 und 141-148). Die B5.md gibt damit Nachweise vor, die im vorgelegten Stand nicht existieren.
  - Required fix: B5.md nur auf zum Commit-Zeitpunkt vorhandene Artefakte verweisen lassen, doppelten Abschnitt entfernen; FEEDBACK-Eintrag erst nach echtem Commit/Nachweis abhaken.
- [Medium] `tests/unit/test_b5_sandbox.py:127-149, 152-185` — Runde-1-Defekt (Mount-Reihenfolge) ist regressionsseitig nicht gesichert
  - Evidence: Der Schatten über `/dev/shm`-Unterpfade (Trennung: tmpfs nach den Bindungen) war exakt der in Runde 1 gefundene Fehler. Der Test prüft nur Paarvorhandensein/Zählung, nicht die positionelle Reihenfolge gegenüber `--bind`; die echten Lauf-Tests (`ShmIsolationTest`) starten ein Projekt unter `/tmp`, nicht unter `/dev/shm` — der aufgetretene Fall (Prüfprojekt/Klon unter `/dev/shm`) ist verhaltensseitig ungetestet. Ohne dass eine Assertion diese Reihenfolge prüft, kann der Defekt unentdeckt zurückkehren.
  - Required fix: Dem Test-Agenten zwei Ergänzungen übergeben: (a) Assertion, dass `("--tmpfs","/dev/shm")` vor allen `--bind`-Paaren steht; (b) idealerweise ein echter Lauf mit Projekt unter `/dev/shm`, der Bindungen auf `/dev/shm`-Unterpfade nach der Privatisierung verifiziert.
- [Minor] `bin/vibe_sandbox.py:54-58, 231` — Argumentation zum Puffer von `STATE_PATH_LIMIT = 100` für nachgelagerte Pfad-Suffixe ist nicht vollständig getragen
  - Evidence: Bei `state` ≤ 100 wird kein Rückfall getätigt. Der Satz „die Unterpfade (z. B. TMPDIR mit kurzem Suffix) erreichen die Grenze nicht“ stimmt generell nicht: `TMPDIR = state + "/tmp"` erreicht bis zu 104 Zeichen, tmux legt Folgepfade wie `TMPDIR/tmux-<uid>/default` an — bei state zwischen ca. 91 und 100 Zeichen überschreiten solche Werkzeugpfade erneut 108 Zeichen (Fehlerklasse des Tickets). Kein Testfall deckt dieses Band und dieses auch nicht zeigte den Fehler.
  - Required fix: Im Hack der Sandbox nachschärfen: Kisseswechsel (Limit weiter senken, z.B. auf ~80) oder die berschränkt gültigeäsicherung (dokumentierte Restgrenze) in `docstring`/B5.md korrigiert nachweisen; ggf. Testkorrektur an den Test-Agenten weitergeben.
- [Minor] `tests/unit/test_b5_sandbox.py:104-117, 262-279` — Tests hinterlassen Zustandsordner ohne Aufräum-Lauf
  - Evidence: Tests, die realen `bwrap_argv`-Aufruf erzeugen (z. B. mit `VIBE_SANDBOX_ROOT="/tmp/opencode/yz*80"`), erzeugen `/tmp/opencode/vibe-sandbox/…`/ bzw. `/tmp/opencode/vsb/<digest>`-Verzeichnisse, die nach Testende bestehen bleiben und nicht geräumt werden.
  - Required fix: Test-Agent： `addCleanup(shutil.rmtree, …, ignore_errors=True)` für die erzeugten Zustandsordner ergänzen.
- [Minor] `tmp4zf4q5fh/` (Wurzel des Arbeitsbaums) — Leeres möglicher Laufzeitartefakt, nicht in `.gitignore`
  - Evidence: Im Arbeitsbaum liegt ein leeres Verzeichnis `tmp4zf4q5fh/pX/` (10-Zeichen-Zufallsname, Muster von `mkdtemp`), nicht von der `.gitignore` umfasst. Zuordnung ohne `git status` nicht möglich (mir war der Shell-Zugriff verweigert). Konflikt zur AGENTS-Regel „Projektordner sauber halten“.
  - Required fix: Vor dem Commit über `git status` verifizieren, dass es nicht zum Paket gehört; dann entfernen und nicht committen.
- [Minor] `docs/features/B5.md:191-194` — Trilium-Dokumentation noch offen
  - Evidence: B5.md nennt den Trilium-Eintrag erstdanach erzeugt zu werden; nach AGENTS ist die Trilium-Spirosphäre Bestandteil der DoD, aktuell nicht nachweisbar.
  - Required fix: Nach Commit Trilium-Eintrag schreiben und die Referenz im FEEDBACK-Eintrag B5 festhalten.

## Prüfnachweis
- Change set bewertet: `8d08490c…` → Arbeitsbaum (vom Coding-Agenten berichteter Umfang; `git diff`/`git status` konnten mangels erlaubter Git-Zugriffe nicht ausgeführt werden — Shell für diese Reviewer-Sitzung komplett mit „permission.rejected“ abgelehnt; bewertet wurde der vollständige aktuelle Inhalt aller Paketdateien: `bin/vibe_sandbox.py`, `tests/unit/test_b5_sandbox.py`, `tests/unit/test_costs_refresh.py`, `docs/features/B5.md`, `docs/import-manifest.json`, `.vibe/project.env`, `FEEDBACK.md`, `.gitignore`).
- Git-Befehle von mir: keine möglich (Shell abgelehnt); diff-zitierbare Zeilennummern dieser Dateien sind als unverifiziert markiert.
- Mitgelieferte Ausgabe (nur agent-geliefert, nicht von mir gelaufen): `verify.sh quick` Exit 0; B5-Tests 9 OK (rote Vorphase „10 failures“ in B5.md:126-139); „31 Tests OK“ für `test_b5_sandbox + test_sandbox.SandboxCommandTest + SandboxRunnerTest` mit gereinigter Umgebung.
- Nicht unabhängig gelaufen: alle Builds/Tests, Manifest-Hash-Verifikation und die Git-diff-Nachprüfung.
- Wichtig inspiziert: Mount-Stapel/Argumentreihenfolge in `bwrap_argv()`, `state_dir()`-Rückfall (Determinismus, Erweiterung/Invalidierung — keine Cache-Logik beteiligt), Konsistenz der Zustandsregel mit allen Verbrauchern (`bin/vibe:3709-3718`, Kostentests), Freigabe-/Bindungs-Logik `/dev/shm`, Testherünfte. „Nur test-agent“-Herkunft ist erkennbar konform konfiguriert (`.vibe/project.env:12` `TESTER=test-agent`, Testdateien mit Unabhängigkeits-Dokumentation) — jedoch nicht unabhängig beweisbar; die Sitzungsnachweise wurden nicht vorgelegt.
- Bekannte Risiken: Mount-Reihenfolge-Defekt ohne regressive Prüfung (M), fehlende Vollprüfung inklusive Kreuzvergleich gegen Baseline (M), fehlende Nachweis-Kette im Dokumentationsartikel (M). Keine Hinweise auf ein neues Loch: Ohne Freigabe bleibt `/dev/shm` ephemeral und host-isoliert; Freigabepfade unter `/dev/shm` werden weiterhin korrekt gebunden; die Zustandsregel steht nur in der Implementierung.

---
Verdict: FAIL
