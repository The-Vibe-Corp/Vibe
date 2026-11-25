# AP5-Korbat — Bestehende Bugs und Artefakte aufräumen, Prüfsetup verbessern

Stand: 2026-11-21
Branch: `feature/korbat/ap5-korbat` (Ausgangscommit `1048210`, auf `dev`)
Spezifikation: TICKETS.md AP5-Korbat; Audit-Dokumente `AP5.md` und `AP6.md`
des Audit-Arbeitsbereichs (`/opt/custom/vibe-dev/workspaces/vibe-audit/docs/features/`).
Umfang: Fehlerbild C1–C5 (init/adopt), read-only-Einwegtransport von
`.vibe/project.env`, T-V1 (`VERIFY_PACKAGE_TESTS`), T-V2 (kurzer
Verify-Tempfpfad) sowie 4a/4b/4c (GUI-Abschluss, Zustand „wartet auf Merge“,
Credential-Auflösung für `ensure-mergeable`). Verbindlich laut Ticket:
Lösungsvariante B aus AP6.md §4.2 für die Prüf-Entkopplung und Option A aus
AP6.md §4.5 für vorbestehend rote Tickets (dokumentierte Baseline statt
Reparatur im Paket).

---

## 1. Zusammenfassung

Vier unabhängige Defekte des Bestands wurden behoben, ohne fachliche
Verträge zu schwächen:

1. **C1–C5:** `vibe init` und die Checkout-Übernahme (`vibe clone` bzw.
   `_adopt_checked_out_project`) brachen mit `NameError` ab, weil Commit
   `35233ff` („removed hardcoded test agent requirements“) die Funktionen
   `ensure_test_agent`/`_ensure_local_test_agent` entfernte, aber zwei
   Bedingungen auf die nun undefinierten Namen `agent`/`agent_note`
   zurückließ. Die Meldungen waren tot. Jetzt wird explizit verfolgt, ob
   eine Vorlage die Datei `.opencode/agents/test-agent.md` über `copy_tree`
   **neu angelegt** hat (`_test_agent_created`); nur dann erscheinen
   Meldung (init) und Notiz (adopt). Ohne solche Vorlage bleiben beide
   still — kein false Success. Bewusst NICHT wieder eingeführt: hardcoded
   Anlegen eines Test-Agents oder ein `TESTER=`-Schreiben.
2. **project.env-Transport:** `.vibe/` ist gitignored und die
   Haupt-Arbeitskopie ist für Agenten read-only — daher hatten
   Paket-Arbeitskopien nie die realen `VERIFY_*`-Befehle, und Agenten
   fabrizierten sich eigene `project.env` (im Audit beobachtet). Der
   Runner-Schritt `copy-notes` transportiert jetzt
   `<project>/.vibe/project.env` **read-only und einwegig** in die
   Arbeitskopie (Modus 0444 best effort, idempotenter Git-Exclude-Eintrag).
   Zurückgeschrieben wird nie; die Datei des Hauptprojekts bleibt
   autoritativ; `.vibe/_secrets.env` wird nie transportiert.
3. **T-V1 (Variante B):** `verify.py` koppelte den Testnachweis des
   Paketmoduls an dieselbe Variable wie den Vollmodus (`VERIFY_TESTS`).
   Ein Projekt mit Vollmodus konnte so keine statische Paketprüfung haben.
   Neu steuert `VERIFY_PACKAGE_TESTS` (Default: leer) den
   Paket-Nachweiszwang; `VERIFY_TESTS` gilt ausschließlich für `full`
   (unverändert, inklusive Fehlermeldung und Zählung).
4. **T-V2:** Der Verify-Tempfpad war mit dem Präfix `vibe-verify-` auf
   beengten Hosts zu lang für tmux-Sockets („File name too long“, 36+
   Scheinfehler laut Audit). Der Präfix ist jetzt `vv-`; mit
   `$VIBE_VERIFY_TMP` lässt sich ein eigener Elternordner vorgeben.
   Aufräumen/`--keep` und TMPDIR-Respekt bleiben unverändert.
5. **4a (GUI-Abschluss, Antwort an den Nutzer):** Der Button
   **„Paket abschließen“** existierte bereits — im Projekt-Detail unter
   „Arbeit“ auf der Ticketkarte in der Spalte „Blockiert“ (ruft
   `/api/package` mit `action=close`, Backend `vibe.package_close`).
   Er ist jetzt zusätzlich in der neuen Spalte „Wartet auf Merge“
   verfügbar. Voraussetzung bleibt ein registrierter Worktree und ein per
   REST verifizierter, gemergter Merge-Request (gleiche Logik wie
   `vibe package close <projekt> <id>`).
6. **4b:** Ein PR-only-Paket (Merge-Request offen, wartet auf den
   Eigentümer) wurde bisher wie jedes andere gesperrte Paket als BLOCKIERT
   (rot) vermerkt und angezeigt. Neu gibt es den eigenen Zustand
   **WARTET AUF MERGE** (gelb): eigene Marke `WARTET AUF MERGE:`,
   eigener CLI-Unterbefehl `mark-waiting`, eigene Board-Spalte und Kachel
   in beiden Oberflächen. Alte BLOCKIERT-Vermerke aus früheren Läufen
   bleiben unverändert blockiert (kein Umschreiben von Bestandsmarken).
7. **4c:** Der Runner meldete „FEHLT: Abruf fehlgeschlagen … could not read
   Username“ plus Token-Hinweis, obwohl Push und Merge-Request danach
   funktionierten. Ursache: `ensure_mergeable` führt `git fetch origin` in
   der **Arbeitskopie** aus, der verschlüsselte Projekt-Token wird aber
   über den **Pfad** des Projekts aufgelöst (Digest) — der Worktree-Pfad
   löst ihn nicht auf. `ensure_mergeable` löst das Credential jetzt einmal
   aus dem Projektkonfigurationspfad und reicht es für alle Git-Aufrufe
   der Arbeitskopie durch (`_credential_passdown`); der Token bleibt
   ausschließlich in der Prozessumgebung, nie in argv/Logs.

## 2. Umsetzung je Punkt

| Punkt | Umsetzung (Kurzform) |
|---|---|
| C1/C3 | `bin/vibe` `cmd_init`: `if _test_agent_created(created):` ersetzt die tote `agent`-Bedingung; Print-Wortlaut unverändert („Unabhängiger Test-Agent ergänzt; …“). |
| C2/C4 | `bin/vibe` `_adopt_checked_out_project`: `notes.append("Unabhängiger Test-Agent ergänzt (" + TEST_AGENT_REL + ")")` ersetzt den toten `agent_note`-Block. |
| C5 | `TEST_AGENT_REL`-Konstante + `_test_agent_created(created)` (Pfadvergleich gegen die `created`-Liste von `copy_tree`, plattformneutral über `os.path`). |
| Transport | `bin/vibe_packages.py`: `PROJECT_ENV_REL`, `transport_project_env(project, worktree) → (transported, exclude_ok)` und `_exclude_project_env(worktree)` (git `rev-parse --git-path info/exclude`, idempotent, relative Pfade gegen den Worktree aufgelöst); `command_copy_notes` druckt eine eigene `OK:`-Zeile bzw. `WARNUNG:` nur bei Exclude-Fehler (Exit 0 bleibt). `sync_proof` unangetastet (schreibt nur Arbeitsnotizen zurück). |
| T-V1 | `scripts/verify.py`: `package_specs = VERIFY_PACKAGE_TESTS`; `requires_proof = full or (package and package_specs)`; `proof_specs`/`proof_key` steuern Datei-, Minimum- und Fehlermeldung; USAGE/Docstring/Exitcode-6-Text aktualisiert. |
| T-V2 | `scripts/verify.py`: `TEMP_PREFIX = "vv-"`; `VIBE_VERIFY_TMP` als Elternordner (`dir=` an `mkdtemp`, Anlage best effort, Fehler → Exit 3); ohne die Variable unverändertes `mkdtemp` (ehrt TMPDIR). |
| 4a | Bestandsbutton bestätigt (keine Neuimplementierung nötig); `nova-project.js`: `closeAction` jetzt für `blocked` **und** `waiting`, weiterhin nur für Pakete (`!isFeedback`). |
| 4b (Kern) | `bin/vibe_packages.py`: `WAITING_MARKER`, `is_waiting_merge`, `mark_waiting_merge`, `command_mark_waiting` + Subparser `mark-waiting`; `_apply_proof` entfernt auch WARTET-Zeilen beim Nachweis-Sync; `select_package._ready` überspringt wartende Pakete (`prefer`-Reattach bleibt möglich); `status_report["waiting"]` (Reihenfolge blocked → waiting → done → open); `priority_view`-Status „wartet auf Merge“ (order + standard). |
| 4b (CLI/Status) | `bin/vibe`: `open_items` und `_parse_entry` liefern den Status `WARTET AUF MERGE`; hat ein Block beide Marken, gewinnt BLOCKIERT. |
| 4b (Runner) | `bin/vibe-run.sh` `pr_only_fallback`: ruft `mark-waiting` statt `mark-blocked`; Logzeile „WARTET AUF MERGE: …“ bleibt; `record_block`/`WAITING_MERGE` unverändert. |
| 4b (GUI) | `bin/web/nova-project.js`: Spalte `waiting` zwischen `open` und `blocked` (Board, Kachel, Label „Wartet auf Merge“, Pille `nv-warn` gelb); `bin/web/i18n.js`: EN „Waiting for merge“; `bin/web/app.js`: Statuspille WARTET → `warn` (BLOCKIERT bleibt `bad`). |
| 4c | `bin/vibe_github.py` `ensure_mergeable`: `with _credential_passdown(credential_for_git(project)):` um `remotes(wt)` und `_ensure_mergeable(wt, …)`. Ohne Token unverändertes Fehlverhalten mit verständlicher Guidance. |

## 3. Getroffene Entscheidungen

1. **Kein Re-Ship der Test-Agent-Vorlage.** Der Audit-Text (C5) ging davon
   aus, `templates/common/.opencode/agents/test-agent.md` existiere — das
   tut es in diesem Repository nicht (auch nicht in der Installation).
   Da Commit `35233ff` das hardcoded Test-Agent-Requirement bewusst
   entfernte, wird keine Vorlage nachgeliefert; die Meldung erscheint
   genau dann, wenn eine projekt- oder installationseigene Vorlage die
   Datei mitliefert. Damit ist die Bedingung echt, still ohne Vorlage, und
   die frühere Produktentscheidung bleibt unangetastet (Ticket bot beide
   Wege an: „Replace with a real condition … or remove the block“).
2. **Marke/Status-Namen.** `WARTET AUF MERGE:` analog zu `BLOCKIERT:`;
   Statusstring „WARTET AUF MERGE“; CLI-Ausgabe „… als wartend vermerkt.“
   Bestandsblockierungen werden nicht migriert (rückwärtsschonend);
   `package close` räumt beide Marken ab.
3. **Exclude-Ziel in Linked-Worktrees.** `git rev-parse --git-path
   info/exclude` liefert in angehängten Arbeitskopien den **gemeinsamen**
   `info/exclude` des Haupt-Repositorys, keinen per-Worktree-Pfad. Der
   Eintrag `.vibe/project.env` ist dort unproblematisch und nützlich (die
   Datei ist überall unversionierter Laufzeitstand); mehrfach anlegen
   verhindert die Idempotenz-Prüfung.
4. **Statt JEDER `.vibe/`-Datei nur exakt `project.env`.** Der Transport
   kopiert bewusst nur diese eine Datei und liest sie als Text —
   `_secrets.env` und alle anderen `.vibe/`-Einträge werden nie
   transportiert (Ticket-Forderung 5).
5. **`GITHUB_AUTO_MERGE`-Umgebung.** Die Runner-Umgebung dieses Laufs
   exportiert `GITHUB_AUTO_MERGE=1`; der PR-only-Bestandstest
   (`PrOnlyRunnerTest`) erwartet eine ungesetzte Variable und wird daher
   unter `env -u GITHUB_AUTO_MERGE` ausgeführt (Umgebungsisolation, kein
   Codefehler; der Runner liest den Schalter ohnehin aus der
   project.env des Projekts).
6. **Manifest.** Geänderte Dateien im Manifest-Bereich (`bin/**`) wurden
   in `docs/import-manifest.json` aktualisiert (Bytes + SHA-256);
   `scripts/verify.py` liegt nicht im Manifest-Bereich und bleibt
   bewusst unverzeichnet.

## 4. Verifikation (tatsächlich ausgeführt)

Unabhängiger Test-Agent (vor der Implementierung, Rotphase; Bericht
`docs/reviews/AP5-Korbat-test-agent-report.md`):
`tests/unit/test_ap5_korbat_init_adopt.py` (8 Fälle), `tests/unit/
test_ap5_korbat_project_env_transport.py` (5), `tests/unit/
test_ap5_korbat_waiting_state.py` (20); Vertragsanpassungen in
`test_verify_script.py` (T-V1/T-V2) und `test_ap4_korbat_github.py`
(PR-only-Marker, 4c). Rotphase bestätigt u. a.: 8× `NameError: name
'agent' is not defined` (`bin/vibe:2743`), fehlender Transport, fehlende
`is_waiting_merge`/`mark-waiting`-Befehle, `NameError: name 'agent_note'`
in `test_ap9_github` am Ausgangsstand.

Grünläufe nach Implementierung (Koordinator bestätigt):

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_ap5_korbat_init_adopt tests.unit.test_ap5_korbat_project_env_transport` | Ran 13, OK |
| `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state` | Ran 23, OK (nach Review-Runde 1: drei Minor-Nachtestfälle des Test-Agenten — de-i18n-Symmetrie, Beschreibungsgrenze hinter der Wartemarke, Priorisierungs-Anzeige — ebenfalls grün) |
| `python3 -m unittest tests.unit.test_verify_script` | Ran 34, FAILED (failures=1) — einzig `RepositoryVerifyTest` (umgebungsbedingt, siehe §5) |
| `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap4_korbat_github` | Ran 21, OK |
| `python3 -m unittest tests.unit.test_ap9_github` | Ran 44, OK (der `agent_note`-NameError ist weg) |
| `python3 -m unittest tests.unit.test_project_management` | Ran 36, FAILED (failures=6, errors=1) — ausschließlich die vorbestehende F22-Baseline (siehe §5); alle 14 `NameError`-Errors sind weg |
| `python3 -m unittest tests.unit.test_worknotes_sync` | Ran 19, OK |
| `python3 -m unittest tests.unit.test_ap4_korbat_worktrees_sessions` | Ran 27, OK |
| `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_b16_runner_wiring` | Ran 6, OK (nach Vertragstreffer aus dem Volllauf, siehe unten) |
| `python3 scripts/check-syntax.py` | Exit 0 (214 Python, 8 Bash, 3 JSON) |
| `python3 scripts/check-no-secrets.py` | Exit 0 |
| `python3 scripts/check-import-manifest.py` | Exit 0 (67 Dateien stimmen überein) |

Volllauf (einmal pro Paket, `env -u GITHUB_AUTO_MERGE python3
scripts/run-tests-parallel.py --dir tests/unit --jobs 4`):
**2212 Tests, 91/127 Module bestanden, 36 Module rot.** Der Abgleich ergab
genau EINEN Vertragstreffer außerhalb der dokumentierten Baseline —
`test_b16_runner_wiring.PrOnlyClosureTest` pinnte noch den alten
PR-only-Vermerk `BLOCKIERT` und wurde vom unabhängigen Test-Agenten auf
`WARTET AUF MERGE` (plus `assertNotIn("BLOCKIERT")`, also strenger)
nachgezogen; danach läuft das Modul grün (`env -u GITHUB_AUTO_MERGE
python3 -m unittest tests.unit.test_github_runner` → OK). Alle
übrigen roten Module sind dokumentierte Baseline (Klassifizierung mit
Fehlerursachen in §5): Umgebungsfamilie („vibe-web ist nicht erreichbar“,
bwrap/tmux/Runner-Prozesse), F22-Altschuld (fehlgeschlagene *Modi* durch
die C1/C2-Fixung von NameError auf veraltete Erwartung verschoben),
umgebungsbedingter `RepositoryVerifyTest` sowie vorbestehende Hygiene- und
Dokumentationsdrift. Kein Modul, das vor AP5 grün war, ist durch AP5 rot
geworden.

**Review-Runden:** Runde 1 (`docs/reviews/AP5-Korbat-review-1.md`) endete
mit `Verdict: PASS` und einem Minor (Symmetrie-/Metadatenlücken um den
neuen Zustand): deutsches i18n-Wörterbuch ohne Identitätspaar
„Wartet auf Merge“, `WARTET AUF MERGE` fehlte in `_FEEDBACK_LABEL` (Marke
konnte in die Ticketbeschreibung gesogen werden), `cmd_priority` zeigte
wartende Pakete ohne Statuszusatz, und die Manifest-Chronik (`aenderungen`)
hatte noch keinen AP5-Eintrag. Der unabhängige Test-Agent sicherte die drei
verhaltensrelevanten Punkte vorab mit eigenen Nachtestfällen (Rotphase
belegt: Ran 23, genau die 3 neuen Fälle rot), die Umsetzung erfolgte
anschließend durch den Coding-Agenten (inkl. Chronikeintrag und erneuter
Hash-Aktualisierung); alle betroffenen Prüfungen grün (Ran 23 OK,
Manifest/Syntax/Secrets Exit 0, `test_ap4_korbat_gui` Ran 14 OK). Runde 2
bestätigt den Abschluss (`docs/reviews/AP5-Korbat-review-2.md`).

## 5. Baseline und Grenzen (Option A, laut Ticket)

Volllauf-Klassifizierung (2212 Tests / 36 rote Module, siehe §4):

- **Umgebungsfamilie** (echte Prozesse/Server/Sandbox in der Agenten-
  Umgebung nicht verfügbar): `test_b3_password_auto_setup`,
  `test_b4_pi_agent_dir`, `test_b5_sandbox`, `test_b8_no_remote_block`,
  `test_b13_private_server_runner`, `test_costs`,
  `test_feedback_{capture,completed,edit_delete,entries}`,
  `test_f22_preflight_assist`, `test_fritz_reconnect`,
  `test_install_lifecycle`, `test_lifecycle`, `test_pause_after_package`,
  `test_project_guide`, `test_project_write_dirs`,
  `test_rebuild_profile`, `test_sandbox`, `test_setup_vibe`,
  `test_storage`, `test_ticket_feedback_processing`,
  `test_v025_agent_start_repair`, `test_v026_run_isolation`,
  `test_f27_keep_changes`, `test_web_api_security` — Fehlersignaturen wie
  „vibe-web ist nicht erreichbar“ bzw. bwrap/tmux-Voraussetzungen; keine
  berührt AP5-Codeflächen (keine Route, kein Serververhalten geändert).
  Derselbe Grundumfang ist in den Vollläufen von AP2/AP4 dokumentiert
  („failures=54, errors=113“ bzw. „failures=59, errors=100“).
- **Vorbestehende Drift (nicht AP5):** `test_baseline_inventory`
  (undokumentierte API-Routen aus älteren Paketen),
  `test_ap12_github_readiness`/`test_release` (32 Hygienebefunde, erster
  Treffer `docs/features/AP21.md:166` — unangetasteter Bestand; die neuen
  AP5-Dateien enthalten nach `check-no-secrets.py`/Home-Pfad-Muster keine
  zusätzlichen Befunde), `test_ap06_github` (`CliPushTest`, von AP4 als
  vorbestehend dokumentiert), `test_ap03_agent_management`/
  `test_project_agents` (ensure_test_agent-/F22-Umfeld).
- **F22-Altschuld** (erwartet das in `35233ff` entfernte hardcoded
  Test-Agent-Verhalten; Fehlermodus durch die C1/C2-Fixung von `NameError`
  auf veraltete Erwartung verschoben, kein Fall wurde grün→rot):
  in `test_project_management`:
  `test_init_adds_the_test_agent_and_tester_to_an_existing_project`,
  `test_init_applies_a_new_template_type_without_code_changes`,
  `test_shipped_test_agent_template_is_complete` (ERROR: Vorlage existiert
  bewusst nicht), `test_all_shipped_project_templates_configure_the_tester`,
  `test_all_shipped_project_templates_contain_the_test_agent_rule`,
  `test_general_rules_require_an_independent_test_agent`,
  `test_repository_agents_file_contains_the_test_agent_rule`;
  in `test_ap8_github_checkout`:
  `test_the_shipped_test_agent_is_replaced_by_the_local_template`
  (erwartet das entfernte Ersetzen mitgelieferter Test-Agents; seit AP5
  läuft die Übernahme wieder durch und meldet dann die veraltete
  Erwartung statt `NameError`).
- **`RepositoryVerifyTest.test_repository_quick_check_passes`:**
  umgebungsbedingt rot in jeder Paket-Arbeitskopie, denn `scripts/verify.sh
  quick` verlangt `.vibe/project.env` — genau die Datei, die bis zu diesem
  Paket nicht transportiert wurde. Ab dem nächsten Lauf beliefert der neue
  Transport die Arbeitskopie; hier wurde sie bewusst NICHT fabriziert.
- **AP6-Liste der bekannten Umgebungsmodule:** im Volllauf diesmal grün:
  `test_run_control`, `test_run_autostop`; die übrigen dort genannten
  (`test_sandbox`, `test_fritz_reconnect`, `test_pause_after_package`,
  `test_project_agents`) bleiben in der Umgebungsfamilie oben dokumentiert
  rot. Alle unangetastet von AP5.
- **GUI:** keine Browser-/Playwright-Ausführung möglich (Umgebung);
  Oberflächen-Verträge sind über Quelltext-/Strukturassertions gesichert
  (Bestandsmuster aus AP4).
- **4c:** Nachweis über protokollierenden Git-Stub (Pfad-Auflösung,
  Token-Durchreichung, argv-Freiheit des Geheimnisses); kein echter
  HTTPS-401-Fetch.
- **Trilium-MCP:** nicht konfiguriert/verfügbar — keine Synchronisation
  erfolgt (Ticketregel: meldet, blockiert nicht).
- Der Runner selbst führt die Paket-/Gesamtprüfung mit den autoritativen
  `VERIFY_*`-Befehlen des Integrationsstands aus (runner-owned, unverändert).

## 6. Nutzerhandlungen (nicht vom Paket erledigt)

- **Upgrade/Migration:** keine. Neue Läufe transportieren
  `.vibe/project.env` automatisch in die Arbeitskopie; Bestandsprojekte
  funktionieren unverändert.
- **GUI-Abschluss (4a):** Projekt öffnen → Reiter „Arbeit“ → Ticketkarte
  in der Spalte **„Wartet auf Merge“** (früher: „Blockiert“) → Button
  **„Paket abschließen“**. Gleiche Wirkung wie
  `vibe package close <projekt> <id>`.
- **Optionale Projekt-Konfiguration:** wer zusätzlich zum statischen
  `VERIFY_PACKAGE` einen Testnachweis je Paket will, setzt
  `VERIFY_PACKAGE_TESTS="…"` in der `.vibe/project.env` des Projekts;
  der Vollmodus bleibt über `VERIFY_TESTS` konfiguriert (Variante B).
- **Optionale Host-Konfiguration:** auf Hosts mit langen Tempfpaden
  (tmux-Socket-Limit) `VIBE_VERIFY_TMP` auf einen kurzen Ordner setzen.

## 7. Geänderte Dateien

- `bin/vibe` (C1–C5, 4b-Status), `bin/vibe_packages.py` (Transport, 4b),
  `bin/vibe-run.sh` (`pr_only_fallback`), `bin/vibe_github.py` (4c),
  `scripts/verify.py` (T-V1, T-V2),
  `bin/web/nova-project.js`, `bin/web/i18n.js`, `bin/web/app.js` (4a/4b),
  `docs/import-manifest.json` (Hashes der geänderten `bin/**`-Dateien),
  Tests des unabhängigen Test-Agenten: `tests/unit/test_ap5_korbat_init_adopt.py`,
  `tests/unit/test_ap5_korbat_project_env_transport.py`,
  `tests/unit/test_ap5_korbat_waiting_state.py` (neu), `tests/unit/
  test_verify_script.py`, `tests/unit/test_ap4_korbat_github.py`,
  `tests/unit/test_b16_runner_wiring.py` (Vertragsanpassungen laut
  Ticket, letztere aus dem Volllauf-Fund) sowie
  `docs/reviews/AP5-Korbat-test-agent-report.md`.
