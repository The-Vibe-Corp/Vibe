# Review AP4-Korbat — Runde 1

- **Ticket:** AP4-Korbat — Work package closing process rework for GitHub-connected projects
- **Ausgangscommit:** `212d97d` (auf Branch `feature/korbat/ap4-korbat`)
- **Geprüfter Änderungssatz:** 16 geänderte Dateien (`bin/vibe`, `bin/vibe-run.sh`, `bin/vibe-web.py`, `bin/vibe_github.py`, `bin/vibe_packages.py`, `bin/vibe_runs.py`, `bin/web/app.js`, `bin/web/nova-project.js`, `SPEC.md`, `docs/baseline.md`, `docs/import-manifest.json`, `templates/{android,docker,generic,rebuild,web}/AGENTS.md`, `tests/unit/test_b16_runner_wiring.py`, `tests/unit/test_ap9_runner_wiring.py`) sowie 6 unversionierte Neudateien (`tests/unit/test_ap4_korbat_github.py`, `tests/unit/test_ap4_korbat_worktrees_sessions.py`, `tests/unit/test_ap4_korbat_rules.py`, `tests/unit/test_ap4_korbat_gui.py`, `docs/features/AP4-Korbat.md`, `docs/reviews/AP4-Korbat-test-agent-report.md`).
- **Datum:** 2026-11-21
- **Reviewer:** Unabhängiger Review-Agent (Read-only)

---

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3 (Low)
- Verdict: PASS

---

## Acceptance criteria / Konformitätsurteil je Unterticket

| Criterion / Unterticket | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **T-G0**: Per-project auto-merge checkbox (`GITHUB_AUTO_MERGE`) + runner merge path (AP3 §3.3, §4.5, §4.6, §5 Schritt 9) | **erfüllt (PASS)** | `bin/vibe_github.py:455,796,1298-1367` (`read_config`, `status`, `merge_pull_request` via `PUT /pulls/<n>/merge` mit `merge_method: squash`); `bin/vibe_packages.py:1607-1623` (`command_github_merge`); `bin/vibe-run.sh:1662-1702` (Verzweigung nach `GITHUB_AUTO_MERGE=1`); `bin/vibe-web.py:1753-1755`; `bin/web/app.js:998-1002,1029,1084`; `bin/web/nova-project.js:581-586,759` | `tests/unit/test_ap4_korbat_github.py` (`AutoMergeConfigTest`, `PrOnlyRunnerTest`, `AutoMergeRunnerTest`) + `tests/unit/test_ap4_korbat_gui.py` (`ClassicSurfaceTest`, `NovaSurfaceTest`, `WebApiBehaviourTest`) — alle grün im gelieferten Prüfnachweis |
| **T-G7**: Ensure PR mergeability before close (fetch base, `git merge --no-ff`, conflict repair, gate; AP3 §3.2, §4.1–4.2, §5 Schritt 7) | **erfüllt (PASS)** | `bin/vibe_github.py:1370-1442` (`_ensure_mergeable`, `ensure_mergeable` mit `fetch --prune`, `merge-base --is-ancestor`, `merge --no-ff --no-edit`, kein Push); `bin/vibe_packages.py:1626-1651` (`command_ensure_mergeable`, `--abort`, Exit 0/2/1, `KONFLIKT:`-Pfade); `bin/vibe-run.sh:787-810,1628-1633` (`ensure_mergeable_package` mit Reparaturrunde und `--abort` bei zweitem Konflikt) | `tests/unit/test_ap4_korbat_github.py` (`EnsureMergeableTest`: 4 Fälle inkl. Merge-Commit ohne Push, Konflikt-Erhalt im Baum, Reparatur-Nachlauf) — grün im gelieferten Prüfnachweis |
| **T-G1**: Decouple local merge from GitHub squash merge (no local feature commits on integration branch; two-phase close `vibe package close`; AP2 §5, AP3 §3.4, §5) | **erfüllt (PASS)** | `bin/vibe-run.sh:1369-1399,1662-1702` (`pr_only_fallback` ohne lokalen Merge, Auto-Merge nutzt `github-pull` + `finish_closed_package` statt `merge_package`); `bin/vibe:2400-2467,6226` (`package_close`, `cmd_package_close`, Dispatch `package`); `bin/vibe_github.py:1191-1204,1236-1295` (idempotentes `complete_package`, `merged_pull_request`); `bin/vibe_packages.py:224-226,243-273` (`sync_proof(..., require_commit=False)`, Entfernen von `BLOCKIERT:`); `bin/vibe-web.py:1475,1484-1494` (`/api/package`) | `tests/unit/test_ap4_korbat_github.py` (`PrOnlyRunnerTest`, `AutoMergeRunnerTest`), `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`PackageCloseCliTest`: 3 Fälle), `tests/unit/test_b16_runner_wiring.py` (`PrOnlyClosureTest`), `tests/unit/test_ap9_runner_wiring.py` — grün im gelieferten Prüfnachweis |
| **T-W2**: Worktree registry + reconnect (RECONNECT mode; AP2 G1, AP3 §4.4, §5 Schritt 3) | **erfüllt (PASS)** | `bin/vibe_runs.py:1162-1280,1523-1549,1611-1629` (`WorktreeRegistry` mit `<runtime>/worktrees.json`, `worktrees.lock`, atomarem Write, CLI `worktree-get/-register/-unregister`); `bin/vibe-run.sh:538-568,1514-1518,1529-1531,1656-1661` (RECONNECT-Prüfung auf Verzeichnis + `git worktree list --porcelain` + Branch-Ref, Skip von `copy-notes` bei Reconnect) | `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`WorktreeRegistryTest`: 6 Fälle, `ReconnectTest`: 2 Fälle) — grün im gelieferten Prüfnachweis |
| **T-W1**: Session ↔ worktree attachment (attach to same workspace until ticket closed; AP2 §4, AP3 §4.4) | **erfüllt (PASS)** | `bin/vibe_runs.py:666-669,716-721,1035-1073,1124-1143,1504-1506,1516-1521` (`SessionRegistry.observe` + `forget_worktree`, `stream` CLI-Optionen); `bin/vibe-run.sh:314-317,497-498,1495-1497,1521-1523,1690-1692` (`VIBE_RESUME_PACKAGE`, `select --prefer`, protokollierter Rückfall, `sessions-forget-worktree`); `bin/vibe_packages.py:593,638-640,1665` (`select_package(..., prefer=...)`); `bin/vibe:1946-1959,2068-2075,2337-2343,2451`; `bin/vibe-web.py:671-677` | `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`SessionWorktreeAttachmentTest`: 4 Fälle, `SessionResumeHintsTest`: 2 Fälle, `PackageCloseCliTest`) + `tests/unit/test_ap4_korbat_gui.py` — grün im gelieferten Prüfnachweis |
| **T-G2**: Pruning fetch everywhere (`--prune`; AP2 G4, AP3 §5 Schritt 2) | **erfüllt (PASS)** | `bin/vibe_github.py:880` (`fetch`: `--prune`), `bin/vibe_github.py:1063` (`pull_integration`: `--prune`), `bin/vibe_github.py:1097` (`integration_state`: `--prune`), `bin/vibe_github.py:1380` (`_ensure_mergeable`: `--prune`) | `tests/unit/test_ap4_korbat_github.py` (`PruneFetchTest`: 4 Fälle) — grün im gelieferten Prüfnachweis |
| **T-G3**: Upstream on GitHub link (AP2 G6) | **erfüllt (PASS)** | `bin/vibe:1070-1093` (`github_link`: iteriert über `refs/heads`, prüft `refs/remotes/origin/<branch>` und setzt `branch --set-upstream-to` best-effort, nicht-fatal mit Warnung auf stderr) | `tests/unit/test_ap4_korbat_github.py` (`GithubLinkUpstreamTest`: 2 Fälle) — grün im gelieferten Prüfnachweis |
| **T-G4**: Worktree-aware branch deletion (AP2 G7, AP3 §5 Schritt 11) | **erfüllt (PASS)** | `bin/vibe_github.py:898-916,941-947` (`_worktrees_by_branch`, `checkout_branch` verweigert in fremder Arbeitskopie ausgecheckten Branch); `bin/vibe-run.sh:835-862` (`cleanup_worktree`: entfernt erst Worktree inkl. `worktree prune`-Retry, prüft `worktree list --porcelain`, löscht mit `branch -d` und nutzt `-D` nur bei `VERIFIED_SQUASH=1`); `bin/vibe:2385-2397,2443-2449` (`package_close`) | `tests/unit/test_ap4_korbat_github.py` (`WorktreeCheckoutTest`) + `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`CleanupWiringTest`, `PackageCloseCliTest`) — grün im gelieferten Prüfnachweis |
| **T-G5**: Branch collision check includes worktrees + remotes (AP2 G8) | **erfüllt (PASS)** | `bin/vibe_packages.py:551-576` (`package_branch_name` prüft `refs/heads/<candidate>`, `refs/remotes/origin/<candidate>` und `worktree_branches` aus `git worktree list --porcelain`) | `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`BranchCollisionTest`: 2 Fälle) — grün im gelieferten Prüfnachweis |
| **T-I1**: Single canonical rules/SPEC source + marker-count invariant (AP2 G3, AP3 §6.1, §6.2, §7.3) | **erfüllt (PASS)** | `SPEC.md:330,343-372` (beide alten „Strictly Enforced“-Blöcke durch den einzigen kanonischen Abschnitt `## Git & work-package closing (runner-owned)` ersetzt; Zeile 330 um `GITHUB_AUTO_MERGE` ergänzt); `bin/vibe:101-144` (`GENERAL_RULES` mit genau einem Markerpaar und aktualisierter Abschlusszeile Zeile 118); `bin/vibe_github.py:14-17` (Modul-Docstring aktualisiert) | `tests/unit/test_ap4_korbat_rules.py` (`GeneralRulesTest`, `SpecCanonicalTest`: 11 Methoden / 15 Subtests) — grün im gelieferten Prüfnachweis |
| **T-I2**: De-duplicate "Laufende Instanz nicht verändern" block (3× → 1×; AP2 G3) | **erfüllt (PASS)** | `bin/vibe:120-122` (`GENERAL_RULES` enthält den Block genau 1×); `templates/{android,docker,generic,rebuild,web}/AGENTS.md` (alle 5 Vorlagen enthalten `GENERAL_RULES` bytengleich und den Block genau 1×) | `tests/unit/test_ap4_korbat_rules.py` (`test_rules_contain_exactly_one_running_instance_block`, `test_every_template_contains_the_rules_exactly_once`) — grün im gelieferten Prüfnachweis |
| **T-S1**: Session state persisted on completion + age-based prune (AP2 B5) | **erfüllt (PASS)** | `bin/vibe_runs.py:74,1091-1123,1336-1343,1508-1514,1605-1607` (`SessionRegistry.finish_for_run` persistiert `state` und entfernt Einträge > 30 Tage ohne existierenden `worktree_path`; `session_overview` gibt Laufregister Vorrang und nutzt sonst den persistierten Zustand); `bin/vibe-run.sh:450-451` (`register_finish` ruft `sessions-finish` auf) | `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`SessionStatePersistTest`: 5 Fälle, `RunnerSessionPersistTest`: 1 Fall) — grün im gelieferten Prüfnachweis |
| **Nutzerentscheidung Option B (Nova-GUI)** & **Descoping T-G6** | **erfüllt (PASS)** | `bin/web/nova-settings.js` unverändert (Feature-Defaults bleiben aus); `tests/browser/test_ap22_settings_ui.py` unverändert; `bin/web/nova-project.js:135-151,524-527,581-586,681-701,759-761` ergänzt nur `link`/`unlink`/`fetch`, Auto-Merge-Checkbox, Session-Anhang und „Paket abschließen“. Keine versteckte Teilimplementierung von T-G6. | `tests/unit/test_ap4_korbat_gui.py` (12 Fälle) + statische Diff-Prüfung |

---

## Findings

- [Minor] `bin/vibe-web.py:1573-1575` und `bin/web/nova-project.js:1004-1012` — Web-API `POST /api/sessions` (`action: "continue"`) reicht `resume_package` nicht an `vibe.cmd_run` weiter und der Nova-Überblicks-Tab zeigt den Worktree-Anhang nicht an
  - Evidence: In `bin/vibe-web.py:671-677` (`start_continue`, aufgerufen über `POST /api/continue`) sowie in `bin/vibe:2337-2343` (`vibe sessions resume`) wird der Session-Eintrag aus `SessionRegistry` gelesen und `resume_package` (bzw. `resume_worktree`/`resume_branch`) an `vibe.cmd_run` übergeben. Beim zeilenweisen „Fortsetzen“-Knopf einer konkreten Session in der Sessions-Karte (`POST /api/sessions` mit `action: "continue"`, `bin/vibe-web.py:1573-1575`) wird dagegen `vibe.cmd_run(name, continue_session=session)` ohne `resume_package=entry.get("package_id") or None` aufgerufen. Wenn das Ticket im PR-only-Modus mit `BLOCKIERT:` markiert ist, wählt der so gestartete Lauf mangels `--prefer <id>` das blockierte Paket nicht aus (`_ready` überspringt blockierte Pakete ohne `prefer`). Zudem zeigt `nvpSessionsSection` in den Nova-Projekteinstellungen (`bin/web/nova-project.js:524-527`) den Paket-/Worktree-Anhang an, während die kompakte Sitzungsliste im Nova-Überblicks-Tab (`bin/web/nova-project.js:1004-1012`) nur die Session-ID rendert.
  - Required fix: In `bin/vibe-web.py:1573-1575` analog zu `start_continue` `resume_package=str(entry.get("package_id") or "").strip() or None` (und optional `resume_worktree`/`resume_branch`) an `vibe.cmd_run` übergeben; optional in `bin/web/nova-project.js:1006-1011` ebenfalls den Paket-/Worktree-Anhang wie in Zeile 524–527 einblenden.

- [Minor] `bin/vibe:2068-2075` — `resume_worktree` und `resume_branch` werden beim Aufbau des `tmux`-Startbefehls ohne `shlex.quote` interpoliert
  - Evidence: In `bin/vibe:1953-1959` werden `continue_session` und `resume_package` strikt gegen `r"[A-Za-z0-9_-]+"` validiert. `resume_worktree` und `resume_branch` stammen aus `sessions.json` und werden in `bin/vibe:2069-2074` direkt per String-Verkettung (`" export VIBE_RESUME_WORKTREE=" + resume_worktree + ";"`) in `inner` (`bash -lc`) eingesetzt (der Läufer `bin/vibe-run.sh` wertet ohnehin nur `VIBE_RESUME_PACKAGE` aus und löst Pfad/Branch sicher über `WorktreeRegistry` auf). Sollte ein Pfad Leerzeichen oder Sonderzeichen enthalten, bricht der `export`-Befehl in der Shell. (Hinweis: `SessionResumeHintsTest.exports` in `tests/unit/test_ap4_korbat_worktrees_sessions.py:779` parst `r"%s=([^\s;\"']+)"`, was einfache Anführungszeichen von `shlex.quote` bei Pfaden ohne Sonderzeichen unberührt lässt, da `shlex.quote` für `[A-Za-z0-9_./-]` keine Quotes setzt.)
  - Required fix: `resume_branch` vor dem Export gegen `vibe_github.BRANCH_RE` / `_clean_registry_branch` prüfen oder beide Werte über `shlex.quote(...)` absichern.

- [Minor] `bin/vibe:1170-1185` vs. `docs/features/AP4-Korbat.md:113` — Dokumentationsabweichung zu `vibe github <projekt> status`
  - Evidence: `docs/features/AP4-Korbat.md:113` dokumentiert unter „Geänderte Schnittstellen“: „`vibe github … status` zeigt Auto-Merge“. Während `vibe_github.status()` (`bin/vibe_github.py:796`) das Feld `auto_merge` im Rückgabe-Dict liefert, gibt die CLI-Formatierung in `cmd_github` (`bin/vibe:1170-1185`) `st["auto_merge"]` nicht als Textzeile auf stdout aus.
  - Required fix: Entweder in `bin/vibe:1173` die Ausgabe von `Auto-Merge: ja/nein` ergänzen oder die Formulierung in `docs/features/AP4-Korbat.md:113` auf `vibe_github.status()` präzisieren.

---

## Detailprüfung der Prüfpunkte 1–9

1. **AP3-Konformität je Unterticket (T-G0, T-G7, T-G1, T-W2, T-W1, T-G2, T-G3, T-G4, T-G5, T-I1, T-I2, T-S1):**
   Alle 12 Untertickets sind vollständig im Code realisiert und mit konkreten Datei-/Zeilenbelegen in der obigen Tabelle nachgewiesen.
2. **Widerspruchsfreiheit (SPEC.md, GENERAL_RULES, Vorlagen):**
   - `SPEC.md` enthält genau einen kanonischen Git-Abschnitt (`## Git & work-package closing (runner-owned)`, Zeilen 343–372), der wortgetreu AP3 §6.1 entspricht. Beide alten `Strictly Enforced`-Abschnitte, `gh pr merge --squash --delete-branch` und `git branch -D` im Agentenauftrag sind entfernt. Zeile 330 unter „Nicht im Umfang“ entspricht AP3 §6.2.
   - `GENERAL_RULES` in `bin/vibe:101-144` enthält genau ein Markerpaar `<!-- vibe:general-rules -->` / `<!-- /vibe:general-rules -->`, den Abschnitt `## Laufende Instanz nicht verändern (verbindlich)` genau 1× (Zeilen 120–122) und in Zeile 118 die aktualisierte GitHub-Abschlussregel nach AP3 §7.3 unter Erhalt der B16-Marker (`Push`, `Merge-Request`, `aktivier`).
   - Alle fünf Vorlagen (`templates/{android,docker,generic,rebuild,web}/AGENTS.md`) enthalten `GENERAL_RULES` bytengleich und genau 1×.
   - Der Modul-Docstring in `bin/vibe_github.py:14-17` beschreibt das Merge-Verhalten mit `GITHUB_AUTO_MERGE="1"`.
3. **Runner-Abschlussfolge in `bin/vibe-run.sh`:**
   - Die Reihenfolge entspricht AP3 §5 und §4.6: Pakettests (`run_package_tests`) + Schranke (`gate_ok`, Zeilen 1585–1599) → `ensure_mergeable_package` (Zeilen 1628–1633) → `github-complete` (Zeilen 1637–1650) → `worktree-register` Upsert mit `--pr-url` und `--session` (Zeilen 1656–1661) → Verzweigung anhand `PR_URL` und `GITHUB_AUTO_MERGE`:
     - **PR-only (`GITHUB_AUTO_MERGE` leer/ungleich `"1"`):** `pr_only_fallback` (Zeilen 1369–1378, 1700) setzt `mark-blocked`, protokolliert `WARTET AUF MERGE: … danach: vibe package close …`, setzt `STOP=1`, führt **keinen** lokalen Merge, **kein** `sync_work_notes` und **kein** `cleanup_worktree` aus.
     - **Auto-Merge (`GITHUB_AUTO_MERGE="1"`):** ruft `github-merge` auf (Zeile 1666); bei Konflikt (`GH_MERGE_RC = 2`) läuft **genau ein** begrenzter Reparaturdurchlauf (`ensure_mergeable_package` → `github-push` → `github-merge`, Zeilen 1670–1680, keine Schleife); bei Erfolg (`GH_MERGE_RC = 0`): `VERIFIED_SQUASH=1`, `github-pull`, `finish_closed_package` (`sync_work_notes`, `cleanup_worktree`, `worktree-unregister`), `sessions-forget-worktree` (Zeilen 1681–1693); bei bleibendem Fehlschlag: sauberer Rückfall auf `pr_only_fallback` (Zeile 1697).
     - **Lokal-ohne-GitHub (`PR_URL` leer):** Bestandsweg `merge_package` → `VERIFIED_SQUASH=0` → `finish_closed_package` (Zeilen 1704–1714).
   - Alle Aufrufe von `$RUNS_PY` sind mit `[ -f "$RUNS_PY" ]` abgesichert; fehlt `$PACKAGES_PY`, bricht der Läufer bereits in Zeile 278 kontrolliert mit Exit 2 ab.
4. **Sicherheit & Datenintegrität:**
   - `/api/package` liegt in `bin/vibe-web.py:1475,1487` hinter IP-Allowlist (`_client_allowed`), Host-/Origin-/Sec-Fetch-Site-Guard (`_guard(True)`), Token-/Session-Authentisierung (`_authorized()`) und prüft das Projekt über `known(body.get("name", ""))`.
   - Tokens erscheinen weder im DOM (`app.js`, `nova-project.js` zeigen nur `auth.source`), noch in REST-URLs, Logs oder Fehlermeldungen (`redact()`, `mask_url()`, `mask_embedded_credentials()`).
   - Alle Git- und Subprozessaufrufe in `vibe_github.py`, `vibe_packages.py` und `vibe_runs.py` verwenden Argumentlisten ohne Shell.
   - `VIBE_CONTINUE_SESSION` und `VIBE_RESUME_PACKAGE` werden in `bin/vibe:1953-1959` und `bin/vibe-run.sh:307-317` gegen `[!A-Za-z0-9_-]` geprüft; `GITHUB_AUTO_MERGE` wird strikt binär gegen `"1"` geprüft (`bin/vibe_github.py:455`, `bin/vibe-run.sh:1665`).
   - `WorktreeRegistry` und `SessionRegistry` schreiben unter `fcntl.flock`-Sperrdateien (`worktrees.lock`, `sessions.lock`) atomar über `_atomic_write` + `vibe_storage.fsync_dir`.
5. **API-Vertrag:**
   - `POST /api/github` (`action: "settings"`) speichert `auto_merge` als `GITHUB_AUTO_MERGE="1"`/`""` und gibt `github.auto_merge` (bool) zurück.
   - `vibe_github.status()` enthält `"auto_merge": config["auto_merge"]`.
   - `session_overview` reicht `worktree_path`, `package_id`, `branch` sowie den persistierten `state`/`state_label` durch.
6. **Tests & Test-Integrität:**
   - Alle 66 neuen Testfälle in den 4 neuen Testmodulen (`test_ap4_korbat_github.py`: 17, `test_ap4_korbat_worktrees_sessions.py`: 26, `test_ap4_korbat_rules.py`: 11, `test_ap4_korbat_gui.py`: 12) stammen vom unabhängigen Test-Agenten, besitzen aussagekräftige Assertions und prüfen beobachtbares Verhalten (echte Git-Repositories mit lokalen `file://`-Bare-Remotes, Loopback-REST-Fakes, isolierter `vibe-web`-Server).
   - Die Rotphase vor der Implementierung sowie die drei vom Test-Agenten selbst vorgenommenen Testaufbau-Korrekturen (`EnsureMergeableTest` Dateiname `remote.txt` statt `shared.txt`, `AP9WiringFixture.worktrees`-Hilfsmethode, `PackageCloseCliTest.write_github_env` gegen echte Netzaufrufe) sind in `docs/reviews/AP4-Korbat-test-agent-report.md` (§4, §8, §9) nachvollziehbar und regelkonform dokumentiert.
   - Die Anpassungen an `tests/unit/test_b16_runner_wiring.py` und `tests/unit/test_ap9_runner_wiring.py` sind sachgerechte Fortschreibungen auf das neue AP4-Sollverhalten (PR-only als Standard statt sofortigem lokalem Merge), keine Abschwächungen.
7. **Dokumentation, Baseline & Import-Manifest:**
   - `docs/features/AP4-Korbat.md` dokumentiert Zusammenfassung, Untertickets, getroffene Design-Entscheidungen, Schnittstellen, Prüfnachweise, Grenzen und die vom Nutzer selbst vorzunehmenden Schritte (insb. manuelle Anpassung der nutzereigenen Abschnitte in `AGENTS.md`) vollständig und wahrheitsgemäß.
   - `docs/baseline.md` ergänzt `CLI | vibe package` (Zeile 161) und `API | POST /api/package` (Zeile 268) mit dem erlaubten Statuswert `vorhanden und automatisiert geprüft`.
   - `docs/import-manifest.json` dokumentiert das Arbeitspaket `AP4-Korbat` mit allen 13 geänderten Programm-/Vorlagendateien und aktualisierten Größen/SHA-256-Prüfsummen.
8. **Nutzerentscheidung Option B (Nova-GUI):**
   - `bin/web/nova-settings.js` und `tests/browser/test_ap22_settings_ui.py` wurden nicht verändert; alle Nova-Feature-Defaults bleiben standardmäßig aus.
   - `bin/web/nova-project.js` ergänzt ausschließlich `link`/`unlink`/`fetch`, die Auto-Merge-Checkbox, den Session-Anhang in `nvpSessionsSection` und die Aktion „Paket abschließen“ an blockierten Tickets.
9. **Descoping T-G6:**
   - T-G6 (In-product working-copy repair) ist wie beauftragt nicht implementiert und in `docs/features/AP4-Korbat.md` ehrlich als descoped ausgewiesen.

---

## Verification

- **Change set reviewed:** `212d97d..working tree` (16 modifizierte Dateien + 6 unversionierte Neudateien vollständig statisch gelesen und gegen `AP3.md`, `AP2.md`, `TICKETS.md` und `SPEC.md` abgeglichen).
- **Git commands run by me:** keine (Review erfolgte rein über direkte Datei-Inspektion aller 22 betroffenen Dateien des Arbeitspakets, da in dieser Subagent-Sitzung kein Bash-/Git-Tool deklariert ist; der vollständige Dateibestand lag im Worktree vor).
- **Checks evidenced by supplied raw output:**
  - Rotphasen- und Nachlauf-Ausgaben des unabhängigen Test-Agenten in `docs/reviews/AP4-Korbat-test-agent-report.md` (`test_ap4_korbat_github`, `test_ap4_korbat_worktrees_sessions`, `test_ap4_korbat_rules`, `test_ap4_korbat_gui`, `test_b16_runner_wiring`, `test_ap9_runner_wiring`).
- **Checks reported only by the coding agent:**
  - `bash scripts/verify.sh quick` → Exit 0 (`check-no-secrets.py` OK, `check-import-manifest.py` OK, `bash -n bin/vibe-run.sh` OK)
  - `bash scripts/verify.sh package` → Ran 403 tests, failures=2 (beide vorbestehend am Ausgangscommit `212d97d`: `test_ap06_github.CliPushTest`, `test_ap9_github` clone `NameError: agent_note`)
  - `bash scripts/verify.sh full` → Ran 2244 tests (= 2178 Basis + 66 neue AP4-Fälle, alle 66 grün), failures=59, errors=100 (identisch zur umgebungsgleichen Baseline am Ausgangscommit `212d97d` nach Bereinigung der dokumentierten Manifest-/Baseline-Einträge)
  - `test_import_manifest` → 8/8 OK; `test_web_api_security` (bereinigte Umgebung) → 22/22 OK.
- **Checks not independently run:** Alle Build-, Test- und Git-Befehle (als Read-only-Reviewer ohne Shell-Werkzeug nicht selbst ausgeführt). Kein Playwright/Browser-Lauf (Playwright fehlt in der Umgebung) und kein Lauf gegen die echte GitHub-API (Tests nutzen lokale Loopback-Fakes und `file://`-Remotes).
- **Important areas inspected:** `bin/vibe-run.sh`, `bin/vibe_github.py`, `bin/vibe_packages.py`, `bin/vibe_runs.py`, `bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `bin/web/nova-project.js`, `bin/web/nova-settings.js`, `SPEC.md`, `templates/*/AGENTS.md`, `docs/baseline.md`, `docs/import-manifest.json`, `docs/features/AP4-Korbat.md`, `docs/reviews/AP4-Korbat-test-agent-report.md`, `tests/unit/test_ap4_korbat_*.py`, `tests/unit/test_b16_runner_wiring.py`, `tests/unit/test_ap9_runner_wiring.py`.
- **Remaining risks:**
  - Wie in `docs/reviews/AP4-Korbat-test-agent-report.md` (§6) und `docs/features/AP4-Korbat.md` (§5) ehrlich ausgewiesen, sind die JavaScript-Änderungen in `app.js` und `nova-project.js` mangels Playwright/Node-Laufzeit nur über Quelltext-/Strukturassertions und Backend-API-Tests abgesichert, und der zweite Konfliktdurchlauf (`--abort`) sowie der Auto-Merge-Reparatur-Retry bei Wettrennungs-Konflikten sind über ihre Einzelbausteine statt als kombinierter End-to-End-Läufertest geprüft.
  - Die drei oben gelisteten Minor-Befunde (insb. fehlendes `resume_package` in `POST /api/sessions` `action: "continue"`) beeinträchtigen die Abnahmekriterien nicht, sollten aber bei Gelegenheit oder in einer Folgerunde bereinigt werden.

Verdict: PASS
