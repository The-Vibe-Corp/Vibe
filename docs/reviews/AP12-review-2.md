# Review AP12 — Runde 2

Datum: 2026-11-12
Reviewer: code-reviewer (unabhängig, read-only)
Umfang: `bf53999..092d133` (Umsetzung der Runde-1-Befunde; vorheriger Umfang `e872577..bf53999` siehe docs/reviews/AP12-review-1.md)
Der Bericht wurde unverändert aus der Review-Antwort übernommen.

## Review result (AP12 — Zweitreview, Runde 2)

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Umsetzung der vier Runde-1-Befunde

**Medium (Test-Portabilität, `tests/unit/test_ap12_github_readiness.py`)** — umgesetzt, keine Abschwächung:
- Umbenennung und Umwandlung durchgeführt: `test_local_config_files_still_exist_locally` → `test_local_test_agent_preserved_when_environment_established` (`tests/unit/test_ap12_github_readiness.py:242`).
- Skip ist begründet und kein Standardausblend-Mechanismus: `vibe_environment_established()` (`:133-143`) prüft `.vibe/project.env` als filebasiertes Signal; der Skip-Text (`:270-276`) nennt Grund und verweist auf die weiterhin vollen AK3-Tests. Die Prüfbegründung ist faktenhaltig und von mir verifiziert: `scripts/setup-vibe.py:1156` (`register_projects` erzeugt `.vibe/project.env`) und `:1131-1168` (`ensure_project_test_agent` legt den Test-Agenten aus der Toolchain-Vorlage an) existieren; kein Setup-/init-Schritt legt ein Root-`opencode.json` an (grep in `scripts/setup-vibe.py` und `bin/vibe`: 0 Treffer; Erzeugung nur `bin/vibe_mcp.py:220-227`).
- Der frisch-Klon-taugliche Kern bleibt volle Abnahme-Assertion: `test_local_config_files_are_untracked_but_present` (`:214`), `test_no_opencode_or_vibe_paths_are_tracked` (`:228`), `test_local_settings_are_ignored` (`:149`).
- Runde-2-Bericht stimmt mit dem Testcode überein (Signal, Umbenennung, `opencode.json`-Limitation, Skip-Begründung, Grenzen-Abschnitt decken sich vollständig mit `:133-143` und `:242-283`).
- Coverage-Erhalt ist belegt: Vorher FAILED (failures=1) genau am beanstandeten Test im Frisch-Klon, nachher OK (skipped=1), Gegenprobe mit simuliertem `.vibe/project.env` ohne Agent-Datei → FAILED mit Bestand-Erhalt-Meldung (Assertion kann weiterhin scheitern), Worktree-Ausführung real (`.vibe/project.env` und `.opencode/agents/test-agent.md` von mir im Arbeitsbaum vorhanden gefunden — der bedingte Test lief tatsächlich, nicht nur als Skip). Die Nachweise sind gelieferte Ausgaben des Test-Agenten bzw. Koordinators; die Umgebungsbedingungen habe ich selbst verifiziert, die Läufe nicht erneut ausgeführt (Read-only).

**Minor 1 (Distanzangabe)** — korrekt: `docs/features/AP12.md:134-137` nennt „8 Commits (Stand `bf53999`)" und erklärt die Fast-Forward-Eigenschaft „0 dahinter" als stabil. Von mir verifiziert: `git log origin/main..092d133` = 9 Commits, `git log 092d133..origin/main` = leer (0 dahinter), `origin/main` @ `c6b2a6c`.

**Minor 2 (Benutzernamen)** — korrekt: `AP12.md:105-107`, `:123-125`, `:164` neutralisiert; grep „marc" in `docs/features/AP12.md` und `docs/reviews/AP12-test-agent-report.md` → 0 Treffer; `AP10-review-3.md:16` als Folgearbeit vermerkt (`AP12.md:260-262`).

**Minor 3 (Archiv-Hinweis)** — korrekt: `AP12.md:115-122` dokumentiert die nachträgliche Ersetzung inkl. betroffener Archive.

Der Reviewnachweis Runde 1 liegt unverändert unter `docs/reviews/AP12-review-1.md` (Inhalt mit gelieferter Runde-1-Antwort deckungsgleich). Der Diff `bf53999..092d133` berührt ausschließlich die vier Nachweis-/Testdateien — `bin/`, `scripts/`, `templates/` sind unangetastet (`git diff --name-only` geprüft), die Runde-1-Prüfbatterie bleibt damit kraft Diff-Befund gültig.

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Medium-Fix: AK3 portabel, frisch-Klon-taugliche Suite | PASS | `tests/unit/test_ap12_github_readiness.py:133-143,242-283` | Bericht Runde 2 (`AP12-test-agent-report.md:121-216`) konsistent zum Code; geliefert: Klon vorher FAILED (failures=1, exakt der beanstandete Test), nachher OK (skipped=1), Gegenproben FAILED/OK; Worktree-Umgebung von mir verifiziert, Läufe nicht selbst ausgeführt |
| Minor-Fix: Distanzangabe standbezogen | PASS | `docs/features/AP12.md:134-137` | `git log origin/main..092d133` (9), `git log 092d133..origin/main` (leer), `origin/main` @ `c6b2a6c` — selbst verifiziert |
| Minor-Fix: keine persönlichen Benutzernamen in paketeigenen Dokumenten | PASS | `AP12.md:105-107,123-125,164`, `AP12-test-agent-report.md:58` (neutralisiert) | grep „marc" in beiden Dateien: 0 Treffer (selbst ausgeführt); Restbestand als Folgearbeit vermerkt (`AP12.md:260-262`) |
| Minor-Fix: Archiv-Ersetzung nachträglich dokumentiert | PASS | `AP12.md:115-122` | Vollständig gelesen; benennt betroffene Archive und die fachliche Unverändertheit |
| Reviewnachweis Runde 1 unverändert gespeichert | PASS | `docs/reviews/AP12-review-1.md` (neu, 50 Zeilen im Diff) | Inhalt deckungsgleich mit der Runde-1-Antwort |
| Keine Produktcodeänderung in 092d133 | PASS | `git diff --name-only` | Nur die 4 Dokument-/Testdateien; Runde-1-Prüfbatterie bleibt gültig |

## Findings
- [Minor] `docs/features/AP12.md:78` — veraltete Test-AK-Angabe „untracked *und* existent"
  - Evidence: Der Absatz „Lokales Git aufbereiten" behauptet weiterhin, der Test-AK decke „untracked und existent" ab; seit Runde 2 ist die Existenz nur noch bedingt (Test-Agent) geprüft und die `opencode.json`-Existenz bewusst nicht mehr Assertion (dokumentiert in `AP12.md:184-206,251-259` und im Bericht). Der Absatz wurde bei der Fix-Umsetzung nicht mitgezogen — örtlicher Widerspruch innerhalb derselben Datei.
  - Required fix: In `docs/features/AP12.md:76-78` die Klammer auf den neuen Prüfumfang anpassen (unversioniert + ignore-geprüft voll, Bestand-Erhalt bedingt), ohne fachliche Aussage zu ändern.
- [Minor] `docs/reviews/AP12-review-1.md:35,38` — neue „marc"-Nennungen durch den unverändert gespeicherten Reviewnachweis, nicht als Folgearbeit vermerkt
  - Evidence: Der in 092d133 neu versionierte Runde-1-Reviewnachweis enthält „`/home/marc`" (2×) und die bare Nennung „marc" — als einziges in diesem Commit neu aufgenommenes Dokument. Die Pfadform ohne abschließenden `/` löst `HOME_PATH_RE` (`scripts/build-release.py:73`) nicht aus, daher korrekt kein Prüffehlschlag; aber `AP12.md:105-107` („alle Fundstellen ... ersetzt") und die Folgearbeitenliste (`AP12.md:260-262`, nur `AP10-review-3.md:16`) bilden diesen neuen Bestand nicht ab. Die unveränderte Speicherung selbst ist regelkonform (AGENTS Schritt 10).
  - Required fix: In `docs/features/AP12.md` (Grenzen und Folgearbeiten) die Nennungen in `AP12-review-1.md` neben `AP10-review-3.md:16` als Folgearbeit aufnehmen oder die Aussage „alle Fundstellen" auf die Release-Regel-Definition beziehen.

## Verification
- Change set reviewed: `bf53999..092d133` (Arbeitsbaum sauber laut `git status --short`; Commit 092d133 vollständig gelesen, alle 4 geänderte Dateien im vollständigen Diff).
- Git commands run by me: `git status --short`, `git log --oneline -8`, `git diff --stat bf53999..092d133`, `git diff bf53999..092d133 -- <Testdatei, AP12.md, Test-Agent-Bericht>`, `git diff bf53999..092d133 --name-only`, `git log --oneline origin/main..092d133`, `git log --oneline 092d133..origin/main`, `git log --oneline origin/main -1`; darüber hinaus `grep`/`read`/`glob` im Arbeitsbaum.
- Checks with supplied output (vom Koordinator/Test-Agenten geliefert, nicht von mir ausgeführt): `python3 -m unittest tests.unit.test_ap12_github_readiness -v` im Worktree 11/11 OK; verify.sh quick Exit 0; Test-Agent-Runde-2-Nachweise (Frisch-Klon vorher FAILED (failures=1) am beanstandeten Test, nachher OK (skipped=1); Gegenprobe 1 FAILED, Gegenprobe 2 11/11 OK; Worktree 11/11 OK, bedingter Test real ausgeführt). Runde-1-Batterie (verify full mit 1 vorbestehend belegtem Fehlschlag, check-no-secrets, manifest, test_release 14/14, fsck) unverändert gültig — von mir am Diff verifiziert, dass `bin/`, `scripts/`, `templates/` in 092d133 unberührt bleiben.
- Checks not independently run: alle unittest-, `verify.sh`- und Skriptprüfungen (Read-only-Regel); compound-Befehle (`ls`-Kette) durch Berechtigungen verwehrt — Verzeichniszustand stattdessen per `read`/`glob` geprüft.
- Important areas inspected: vollständiger Diff `bf53999..092d133`, `tests/unit/test_ap12_github_readiness.py` (Zeilen 100-299), `docs/reviews/AP12-test-agent-report.md` (komplett, inkl. Runde-2-Abschnitt), `docs/features/AP12.md` (komplett), `docs/reviews/AP12-review-1.md`, Arbeitsbaumzustand `.vibe/` (project.env vorhanden) und `.opencode/agents/test-agent.md` (vorhanden), `scripts/setup-vibe.py:1131-1183`, `bin/vibe_mcp.py:220-227`, `scripts/build-release.py:73`, grep-Ausschlüsse in `scripts/setup-vibe.py` und `bin/vibe` für `opencode.json`.
- Remaining risks: Merge in den Integrationsstand und Push nach `M0P/Vibe` stehen weiterhin aus (freigabepflichtig, Plan unverändert regelkonform); die gelieferten Prüfergebnisse wurden von mir nicht erneut ausgeführt; die beiden Minor-Befunde (veraltete Klammer `AP12.md:78`, Folgearbeiten-Vermerk für die Reviewarchiv-Nennungen) sind nicht blockierend.

Verdict: PASS
