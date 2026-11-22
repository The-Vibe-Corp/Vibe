# AP6-Korbat — Unit-Tests aufräumen (Test-Hygiene)

Stand: 2026-11-22
Branch: `feature/korbat/ap6-korbat` (Ausgangscommit `4db1b78`)
Spezifikation: TICKETS.md AP6-Korbat; Audit-Dokument `AP10.md`
(`/opt/custom/vibe-dev/workspaces/vibe-audit/docs/features/AP10.md`).
Umfang: Abarbeitung der Test-Tickets T-BR1 bis T-BR8 aus AP10 §7.
Nutzerentscheidungen: **T-BR3 = A** (Tests bereinigen, nicht
`ensure_test_agent` wiederherstellen) und **T-BR7 = A** (Vorlagen um
`node`/`docker` ergänzen, `openwrt` bleibt entfernt).

---

## 1. Zusammenfassung

Die Audit-Befunde wurden am Ausgangscommit nachgeprüft. Produktivseitig
waren fünf Punkte zu ändern:

1. **T-BR1:** `VIBE_CLEAN_ENV` im Paket-Läufer entfernt zusätzlich
   `VIBE_UI_BIND`, `VIBE_UI_PORT` und `GITHUB_AUTO_MERGE`. `VIBE_RUNTIME`
   war bereits enthalten. `HOME` bleibt bewusst gesetzt.
2. **T-BR2:** Jeder Sandbox-Start setzt `VIBE_SANDBOX_ACTIVE=1`; die
   Endprüfung kann damit eine verschachtelte Sandbox erkennen, statt
   bwrap-Fälle pauschal zu überspringen.
3. **T-BR4:** Die zehn fehlenden API-Routen stehen mit Fachbeschreibung und
   Testbeleg in `docs/baseline.md`.
4. **T-BR5:** Persönliche Home-Pfade des vormaligen Benutzers
   (`/home/<name>/…`) sind in 33 Stellen von 11 getrackten Dokumenten durch
   den Platzhalter `/home/nutzer/…` ersetzt.
5. **T-BR7 (Vorlagen-Teil):** `templates/web` und `templates/docker` führen
   wieder ihre dokumentierten Standardwerkzeuge.

Hinzu kommen zwei Nachträge aus der Test-Diagnose: der F27-Produktbefund
(ff-Merge scheitert an der beim Paketstart kopierten, schmutzigen
`AGENTS.md`) ist nach Nutzerentscheidung **Variante A** behoben — auf der
Kopierseite (`copy_work_notes` adoptiert keine dirty `AGENTS.md`) und als
allgemeine Absicherung im `merge_package`; die F6-Dokumentation nennt
wieder den aktuellen Windows-Startbefehl.

Die reinen Test-Tickets T-BR3, T-BR6 und T-BR8 sowie die
Harness-Isolation für `HOME` werden laut Auftragsteilung vom unabhängigen
Test-Agenten umgesetzt; dieses Dokument beschreibt nur die Produktions-
und Dokumentationsanteile.

## 2. Befund, Entscheidung und Umsetzung je Ticket

### T-BR1 — Test-Isolation vervollständigen (`VIBE_UI_BIND`, `VIBE_UI_PORT`, `GITHUB_AUTO_MERGE`)

- **Befund (verifiziert am Start-Commit):** `bin/vibe-run.sh:41` entfernte
  nur `VIBE`, `VIBE_PROFILE`, `VIBE_INSTALL`, `VIBE_STATE`, `VIBE_RUNTIME`,
  `VIBE_CONFIG_FILE` und `VIBE_AGENTS_DIR`. Über `ui.json` →
  `vibe_paths` gelangten `VIBE_UI_BIND`/`VIBE_UI_PORT` in Kindprozesse,
  über `set -a` der Projektdatei zusätzlich `GITHUB_AUTO_MERGE`. Folge
  laut AP10 §3/§5: Testserver banden an die produktive LAN-Adresse
  („vibe-web ist nicht erreichbar“, Portkollisionen) und PR-only-Tests
  liefen im Auto-Merge-Modus.
- **Entscheidung:** Die drei Variablen in `VIBE_CLEAN_ENV` aufnehmen.
  `HOME` wird **nicht** aufgenommen (siehe §3.2).
- **Umsetzung:** `bin/vibe-run.sh` — Array um
  `-u VIBE_UI_BIND -u VIBE_UI_PORT -u GITHUB_AUTO_MERGE` erweitert und
  Begründung im vorhandenen B17-Kommentarblock ergänzt. Das Array wird
  unverändert an allen vier Verwendungsstellen weitergereicht
  (privater Server, `verify_run`, Agentenstart); keine weitere Stelle
  nötig.
- **Nachweise:** `bash -n bin/vibe-run.sh` Exit 0. Die
  Runner-Umgebungsprüfung liefert der unabhängige Test-Agent.

### T-BR2 — bwrap-Verschachtelung sauber erkennen

- **Befund:** Die Endprüfung läuft bei `SANDBOX=on` selbst in
  `vibe_sandbox.py`; ein verschachtelter bwrap-Prozess kann keine weitere
  Benutzernamensraum anlegen (AP10 §6). Ohne Marker mussten
  bwrap-abhängige Fälle pauschal per `skipUnless` übersprungen werden.
- **Entscheidung:** Vertrag mit dem Test-Agenten: Wert exakt `"1"`, gesetzt
  über `--setenv` für **jeden** in der Sandbox gestarteten Prozess; nur
  innerhalb der Sandbox, keine Änderung des übrigen Verhaltens.
- **Umsetzung:** `bin/vibe_sandbox.py` — im vorhandenen `--setenv`-Block
  vor den XDG-/TMPDIR-Einträgen steht jetzt
  `--setenv VIBE_SANDBOX_ACTIVE 1` (also vor dem `--`-Trenner und damit im
  argv jedes Sandbox-Starts, auch des privaten Servers). Die Variable wird
  nie in `os.environ` des Aufrufers geschrieben.
- **Nachweise:** `tests.unit.test_b17_sandbox_argv` (4 Fälle) OK; eine
  Nachbildung der argv-Erzeugung (Testmodus, `VIBE_BWRAP`-Attrappe) zeigt
  genau ein `('--setenv', 'VIBE_SANDBOX_ACTIVE', '1')` vor dem
  Kommandotrenner `--`.

### T-BR3 — entferntes `ensure_test_agent` bereinigen

- **Befund:** Commit `35233ff` entfernte die Funktion bewusst; sieben
  Testmodule prüfen weiterhin ihre Existenz bzw. ihr Verhalten (AP10
  §4.2).
- **Entscheidung (Nutzer, Variante A):** Tests bereinigen; die Funktion
  wird nicht wiederhergestellt.
- **Umsetzung:** ausschließlich Testseite — Aufgabe des unabhängigen
  Test-Agenten. Keine Produktionsänderung in diesem Paket.

### T-BR4 — undokumentierte API-Routen in der Baseline

- **Befund:** `tests.unit.test_baseline_inventory` war am Start-Commit rot
  und nannte exakt zehn Routen: `GET/POST /api/gates`,
  `GET/POST /api/language`, `GET/POST /api/limits`, `GET /api/paths`,
  `GET/POST /api/runs`, `POST /api/emu`. Sie stammen aus AP21 v2
  (Sprache) und AP22 (Paritäts-Endpunkte).
- **Entscheidung:** Die Routen wie die übrigen Tabellenzeilen dokumentieren,
  mit dem tatsächlichen Handlerverhalten und dem vorhandenen Testmodul als
  Beleg; keine erfundenen Routen, keine Statusaufwertung ohne Test.
- **Umsetzung:** `docs/baseline.md` §6 — zehn Zeilen am Ende der API-Tabelle
  (`do_GET`/`do_POST` mit `_limits_view`/`_limits_set`,
  `_gates_view`/`_gates_set`, `_runs_view`/`_runs_prune`, `_emu`,
  `language_data`, `PATHS.as_dict()`). Die Routen sind durch
  `tests/unit/test_ap22_web_routes.py` (`LimitsApiTest`, `GatesApiTest`,
  `RunsApiTest`, `EmuApiTest`, `PathsApiTest`) und
  `tests/unit/test_ap21_i18n.py` (`GlobalLanguageServerTest`) gedeckt.
- **Nachweise:** `tests.unit.test_baseline_inventory` 8 Fälle OK;
  `test_ap22_web_routes` (fünf Klassen) 14 Fälle OK;
  `test_ap21_i18n.GlobalLanguageServerTest` 9 Fälle OK.

### T-BR5 — persönliche Home-Pfade aus getrackten Dateien

- **Befund:** Der Home-Pfad-Scan (`scripts/build-release.py`,
  `HOME_PATH_RE` mit Platzhalterliste) fand 34 Treffer mit dem Benutzer
  `vibe`: 33 Stellen in 11 Dokumenten unter `docs/` und eine Stelle in
  `tests/browser/test_b18_harness_ui.py`.
- **Entscheidung:** In den Dokumenten wird nur der Benutzername
  neutralisiert (`/home/<name>/…` → `/home/nutzer/…`); Aussagen, Befehle und
  Ergebnisse der historischen Berichte bleiben unverändert. `nutzer` ist
  ein bereits anerkannter Platzhalter in `build-release.py`; die Logik
  selbst bleibt unangetastet.
- **Umsetzung:** `docs/features/AP21.md` (3), `docs/reviews/AP20-review-1.md`
  (1), `AP20-test-agent-report.md` (3), `AP21-review-6.md` (3),
  `AP21-test-agent-report.md` (10), `AP22-test-agent-report-mc.md` (2),
  `AP22-test-agent-report.md` (5), `B17-test-agent-report.md` (5),
  `B18-review-1.md` (1), `F32-review-1.md` (1), `F32-review-2.md` (1).
  Die Testdatei gehört dem Test-Agenten und wurde nicht angefasst.
- **Nachweise:** Derselbe Scan über alle getrackten Textdateien liefert nach
  der Änderung genau einen Treffer: `tests/browser/test_b18_harness_ui.py:84`.
  `tests.unit.test_release` bleibt deshalb mit genau diesem einen Befund
  rot (Baseline, Testseite); `test_ap12_github_readiness` meldet daneben
  nur noch den vorbestehenden Test-Agent-Befund.

### T-BR6 — Git-Meldungs-Assertion in `ap06`

- **Befund:** Die Assertion prüft den Substring `"Remote"` in der
  Git-Ausgabe; Git meldet stattdessen „origin does not appear to be a git
  repository“.
- **Entscheidung/Umsetzung:** reine Teständerung (robustere Prüfung), laut
  Auftragsteilung beim unabhängigen Test-Agenten. Keine
  Produktionsänderung in diesem Paket.

### T-BR7 — Vorlagen: fehlende Werkzeuge und Signaturdrift

- **Befund (verifiziert am Start-Commit):** `templates/web/.vibe/project.env`
  enthielt `SANDBOX_TOOLS="git python3 git npm"` (kein `node`, doppeltes
  `git`), `templates/docker/.vibe/project.env` enthielt
  `SANDBOX_TOOLS="git python3 git"` (kein `docker`). Beide Listen sind
  Merge-Artefakte der `generic`-Liste; `vibe_sandbox.TOOL_DEFAULTS` und
  `docs/features/F7.md` nennen für web `git node npm` und für docker
  `git docker`.
- **Entscheidung (Nutzer, Variante A):** `node`/`npm` bzw. `docker`
  ergänzen, `openwrt` bleibt entfernt.
- **Umsetzung:** `templates/web/.vibe/project.env` →
  `SANDBOX_TOOLS="git node npm"`; `templates/docker/.vibe/project.env` →
  `SANDBOX_TOOLS="git docker"`. Das doppelte `git` und das versehentlich
  aus `generic` übernommene `python3` entfallen, weil beide Listen damit
  exakt den Code-Defaults und der Dokumentation in F7 §„Projektvorlagen“
  entsprechen; `python3` bleibt im Sandbox-Wurzeldateisystem ausführbar,
  die Liste steuert nur Werkzeugprüfung und Gerätefreigaben.
  `docs/import-manifest.json` führt Größe und SHA-256 beider Dateien nach.
- **Nachweise:** Subset-Prüfung der Vorlagen inline: web
  `['git', 'node', 'npm']`, docker `['git', 'docker']`, jeweils
  `SANDBOX=on` und erwartete Werkzeuge enthalten.
  `tests.unit.test_sandbox.SandboxConfigTest.test_templates_preselect_sandbox_and_build_tools`
  läuft am Start-Commit und nach der Änderung im Subtest `openwrt` rot, weil
  der Test noch die entfernte Vorlage erwartet (Baseline, Testseite); die
  Subtests `web` und `docker` erfüllen den Vertrag.
- **Nicht in diesem Paket:** die übrigen T-BR7-Befunde
  (`register_projects()`-Signatur in `test_setup_vibe`,
  `install_program_files`-Pfad in `test_install_lifecycle`, `BLOCKED`-
  Auswertung in `test_ticket_feedback_processing`) betreffen
  Test-Erwartungen und Installationslogik außerhalb des Vorlagen-Teils und
  bleiben als Bestandsbefund dokumentiert.

### T-BR8 — `test_feedback_entries` entkoppeln

- **Befund:** Der Test liest den lokalen, nicht versionierten
  `FEEDBACK.md`-Ledger.
- **Entscheidung/Umsetzung:** reine Teständerung (Fixture bzw. isolierte
  Datei), laut Auftragsteilung beim unabhängigen Test-Agenten. Keine
  Produktionsänderung in diesem Paket.

### F27 — dirty `AGENTS.md`: Kopierseite und ff-Merge (Nachtrag, Variante A)

- **Befund (durch Test-Diagnose bestätigt):** `copy_work_notes`
  (`bin/vibe_packages.py`, `WORK_COPY_FILES = TICKETS.md, FEEDBACK.md,
  AGENTS.md`) kopierte beim Paketstart auch eine lokal geänderte
  `AGENTS.md` in die Arbeitskopie; der Agent committete sie im Paketbranch.
  `merge_package` verwarf bisher nur uncommittete Änderungen an
  `TICKETS.md`/`FEEDBACK.md`; die schmutzige `AGENTS.md` blockierte
  `git merge --ff-only` mit „Your local changes to the following files
  would be overwritten by merge“ und der Lauf endete mit
  „FEHLT: Merge von <branch> nach <base> fehlgeschlagen“ (beobachtet in
  `tests/unit/test_f27_keep_changes.py`,
  `test_keep_changes_starts_a_package_and_preserves_changes`).
  F27 verlangt dagegen ausdrücklich, dass eine uncommittet geänderte
  `AGENTS.md` weder überschrieben noch committet wird und byte-gleich im
  Arbeitsbaum bleibt (`docs/features/F27.md`, Abschnitte
  „Abgedeckte Fälle“ und „Nachweise und Arbeitsstand“).
- **Entscheidung (Nutzer, Variante A):** Beide Seiten des Problems
  schließen — den Merge-Mechanismus auf genau die überschriebene
  Differenzmenge begrenzen **und** verhindern, dass eine dirty `AGENTS.md`
  überhaupt in den Paketbranch gelangt. Nur so bleibt der F27-Vertrag
  (Byte-Gleichheit und unveränderter Status) erfüllbar; der Merge-Verwurf
  bleibt als allgemeine Absicherung für andere dirty Dateien.
- **Umsetzung Kopierseite (`bin/vibe_packages.py`, `copy_work_notes`):**
  `AGENTS.md` (`PROJECT_RULES_FILE`) wird übersprungen, wenn sie im Projekt
  uncommittete Änderungen hat (gestagt oder ungestagt über
  `git diff --name-only [--cached]`). Sie wird nicht kopiert, bleibt aus
  der `copied`-Liste und wird in einer zweiten Rückgabeliste `skipped`
  gemeldet; `command_copy_notes` gibt dafür je Datei
  „HINWEIS: AGENTS.md hat nicht committete Änderungen; sie wurden nicht in
  die Arbeitskopie übernommen.“ aus (kein `FEHLT`, kein Fehler). Der
  Paketbranch arbeitet mit dem committeten Stand, weil die Arbeitskopie
  ohnehin aus `HEAD` entsteht. Kommentar im Code verweist auf F27.
- **Umsetzung Merge-Seite (`bin/vibe-run.sh`, `merge_package`):**
  - `merge_files` = `git -C "$P" diff --name-only HEAD "$BRANCH"`; bei
    `--ff-only` ist das exakt die Menge, die der Merge in den Arbeitsbaum
    schreibt.
  - `dirty_files` = unstaged (`git diff --name-only`) plus gestagt
    (`git diff --name-only --cached`).
  - Für jede Schnittmenge wird mit `git checkout -q HEAD -- <datei>`
    Arbeitsbaum **und** Index auf `HEAD` zurückgesetzt (deckt auch gestagte
    Änderungen ab) und der Verwurf gesammelt.
  - Eine `WARNUNG`-Zeile nennt die verworfenen Dateien; sind es
    ausschließlich Arbeitsnotizen (`TICKETS.md`, `FEEDBACK.md`,
    `AGENTS.md`), lautet sie wie bisher „WARNUNG: Uncommittete Änderungen
    an Arbeitsnotizen werden für den Merge verworfen: …“, sonst
    „… an Dateien …“. Nicht versionierte Dateien werden nie gelöscht.
  - Dirty Notizen, die der Branch **nicht** ändert, bleiben jetzt
    unangetastet (bisher wurden `TICKETS.md`/`FEEDBACK.md` pauschal
    verworfen); das ist der gewollte, kleinere Eingriff.
- **Verifikation:**
  - `tests.unit.test_f27_keep_changes` → **Ran 14, OK**; der zuvor rote
    Treiber `RunnerKeepChangesTest.test_keep_changes_starts_a_package_and_preserves_changes`
    ist grün: Paket wird geschlossen, `AGENTS.md` und `unfertig.txt`
    bleiben byte-gleich und uncommittet, Status unverändert (Kombinationsfix).
  - Mini-Repository-Diagnose der Merge-Seite (kein Repo-Inhalt, `/tmp`) mit
    alter und neuer Funktion: alte Fassung → `rc=1`, Log „Your local
    changes … AGENTS.md … FEHLT: Merge …“; neue Fassung → `rc=0`,
    `WARNUNG: … AGENTS.md`, Fast-Forward, Arbeitsbaum sauber. Der
    Notizen-Fall (`TICKETS.md`) bleibt vor und nach dem Fix grün.
  - Bestehende Verträge: `tests.unit.test_ap10_gates.RunnerGateWiringTest`
    (9 Fälle, OK), `tests.unit.test_ap4_korbat_github` (21, OK),
    `tests.unit.test_worknotes_sync` + `tests.unit.test_ap5_korbat_project_env_transport`
    (zusammen 24, OK), `tests.unit.test_b16_runner_wiring` (6, OK),
    `tests.unit.test_ap9_runner_wiring` (3, OK).
  - Die Merge-Seite bleibt als Sicherheitsnetz für andere Dateien der
    Merge-Differenz bestehen; im F27-Szenario greift sie nicht mehr, weil
    die dirty `AGENTS.md` den Paketbranch nicht mehr erreicht.

### F6 — Doku-Drift Windows-Startbefehl

- **Befund:** `docs/features/F6.md` beschrieb den Windows-Startbefehl noch
  als `py -3 "%~dp0_toolchain\bin\vibe" %*`. Seit `67d53bc`
  (Installationsordner getrennt vom Arbeitsbereich) liegt `vibe.cmd` im
  Installationsordner selbst; `install_launcher` in `scripts/setup-vibe.py`
  erzeugt `py -3 "%~dp0bin\vibe" %*`.
- **Umsetzung:** Der Abschnitt „Startbefehl und Projekte“ nennt jetzt
  `vibe.cmd` im Installationsordner (neben `bin/`) mit
  `py -3 "%~dp0bin\vibe" %*` und verweist auf `install_launcher`. Kein
  weiterer Umbau; die POSIX-Zeile (Symlink auf `<install>/bin/vibe`) bleibt
  unverändert.
- **Verifikation:** Abgleich mit `install_launcher`
  (`scripts/setup-vibe.py:1212-1222`) und der Test-Erwartung
  `tests/unit/test_setup_vibe.LauncherTest`
  (`test_windows_launcher_starts_the_python_program`,
  `test_windows_launcher_is_not_rewritten_on_a_second_run`) — 4 Fälle grün.

## 3. Getroffene Entscheidungen

1. **Nur Produktions-/Dokumentationsanteile in diesem Paket.** T-BR3,
   T-BR6, T-BR8 sowie die `HOME`-Isolation der Harnesses sind
   Teständerungen und liegen beim unabhängigen Test-Agenten.
2. **`HOME` bleibt in `VIBE_CLEAN_ENV`.** Agenten und Prüfbefehle brauchen
   `HOME` (Git-Identität, opencode-Daten). Eine pauschale Entfernung würde
   diese Funktionen brechen; die Leckagen werden stattdessen in den
   Test-Harnesses isoliert.
3. **`VIBE_SANDBOX_ACTIVE` nur im Sandbox-argv.** Der Marker ist kein
   Prozess-Export des Aufrufers; außerhalb der Sandbox bleibt die Variable
   ungesetzt und unverändert.
4. **Home-Pfade:** Platzhalter `/home/nutzer/` statt `~/`/`~vibe/`, damit
   absolute Pfade in Befehlen und Zitaten lesbar bleiben und der
   bestehende Scan sie anerkennt.
5. **Vorlagen:** exakte Ausrichtung an `TOOL_DEFAULTS`/F7 statt nur
   additives Ergänzen; damit verschwinden auch die Merge-Artefakte.
6. **`merge_package`-Politik (F27, Variante A):** Vor dem ff-Merge werden
   ausschließlich die lokal geänderten Dateien verworfen, die in der
   Merge-Differenz `HEAD..$BRANCH` liegen (Arbeitsbaum und Index), mit
   sichtbarer `WARNUNG`. Der Merge gewinnt, die Laufzeitkopie verliert nur
   dort, wo sie ohnehin überschrieben würde; nicht versionierte Dateien
   werden nie gelöscht. `TICKETS.md`/`FEEDBACK.md` sind ein Spezialfall
   dieser Regel, kein Sonderweg mehr.
7. **Kopierseite (F27, Root Cause):** Eine dirty `AGENTS.md` gehört dem
   Nutzer und wird von `copy_work_notes` nicht adoptiert — weder in den
   Paketbranch noch in den Abschluss-Merge. Der Paketbranch arbeitet mit
   dem committeten Stand; `command_copy_notes` meldet die Auslassung als
   `HINWEIS`. Zusammen mit Punkt 6 bleibt der F27-Vertrag (Byte-Gleichheit,
   unveränderter Status) erfüllt.

## 4. Test-Nachweise (tatsächlich ausgeführt)

Alle Läufe in der Arbeitskopie mit bereinigter Umgebung
(`env -u SANDBOX`, isolierte Pfade der Tests).

| Befehl | Ergebnis |
|---|---|
| `bash -n bin/vibe-run.sh` | Exit 0 |
| `env -u SANDBOX bash scripts/verify.sh quick --project .` | Exit 0 (Manifest 68 Dateien, Syntax 221 Python/8 Bash/3 JSON, keine Geheimnisse) |
| `python3 scripts/check-syntax.py` | Exit 0 |
| `python3 scripts/check-no-secrets.py` | Exit 0 |
| `python3 scripts/check-import-manifest.py` | Exit 0 (68 Dateien) |
| `env -u SANDBOX python3 -m unittest tests.unit.test_baseline_inventory tests.unit.test_b17_sandbox_argv -v` | Ran 12, OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_ap22_web_routes.{LimitsApiTest,GatesApiTest,RunsApiTest,EmuApiTest,PathsApiTest} -v` | Ran 14, OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_ap21_i18n.GlobalLanguageServerTest -v` | Ran 9, OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_sandbox.SandboxConfigTest.test_templates_preselect_sandbox_and_build_tools -v` | Ran 1, FAILED — nur Subtest `openwrt` (Baseline, Testseite); `web`/`docker` separat bestätigt |
| `env -u SANDBOX python3 -m unittest tests.unit.test_ap12_github_readiness -v` | Ran 11, FAILED (1) — nur `UntrackedLocalSettingsTest.test_local_test_agent_preserved_when_environment_established` (bekannter Test-Agent-Vorlagenbefund); Home-Pfad-Fall grün |
| `env -u SANDBOX python3 -m unittest tests.unit.test_release -v` | Ran 14, OK |
| Marker-Nachbildung `bwrap_argv` (Inline-Skript, Attrappe) | genau ein `--setenv VIBE_SANDBOX_ACTIVE 1` vor `--` |
| Home-Pfad-Scan (Inline-Skript, `git ls-files` + `HOME_PATH_RE`) | 0 Treffer über alle getrackten Textdateien |
| `env -u SANDBOX python3 -m unittest tests.unit.test_f27_keep_changes -v` | Ran 14, OK (Kombinationsfix; zuvor rot an der Merge-Blockade bzw. Status-Gleichheit) |
| K7-Mini-Repository (Inline-Skript, alte/neue `merge_package`-Funktion) | alt: rc=1 „FEHLT: Merge …“; neu: rc=0, WARNUNG, Fast-Forward, Arbeitsbaum sauber |
| `env -u SANDBOX python3 -m unittest tests.unit.test_ap10_gates.RunnerGateWiringTest -v` | Ran 9, OK |
| `env -u SANDBOX -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap4_korbat_github -v` | Ran 21, OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_worknotes_sync tests.unit.test_ap5_korbat_project_env_transport -v` | Ran 24, OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_b16_runner_wiring` / `tests.unit.test_ap9_runner_wiring` | Ran 6 OK / Ran 3 OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_setup_vibe.LauncherTest -v` | Ran 4, OK |
| `env -u SANDBOX -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap06_github` | Ran 54, OK |
| `env -u SANDBOX python3 -m unittest tests.unit.test_runner_package_gates` | Ran 12, OK (206 s; Läufer-Gates über echtes `bin/vibe-run.sh`) |

Volllauf (Koordinator, einmalig vor Abnahme, `tests/unit` über
`scripts/run-tests-parallel.py --jobs 4` mit `env -u SANDBOX` und
`VIBE_SANDBOX_ACTIVE=1` — das simuliert die verschachtelte Endprüfung des
Läufers, in der bwrap-abhängige Fälle über den T-BR2-Marker skippen):

- **Ergebnis: 2396 Tests, 128/132 Module bestanden, Exit 1** wegen genau
  4 Modulen mit dokumentierten Vorabständen (AP10 §4.2, alle am
  Ausgangscommit `4db1b78` bereits rot):
  `test_ap12_github_readiness` (1: veraltete Test-Agent-Adoptionsprämisse),
  `test_ap8_github_checkout` (1: lokale Adoption der mitgelieferten
  Test-Agent-Vorlage),
  `test_project_management` (5: `TESTER`/Test-Agent-Vorlagen-Drift nach
  35233ff), `test_rebuild_profile` (1: `VERIFY_QUICK="echo TODO"` in
  `templates/rebuild`). Keines dieser Module liegt im T-BR1–T-BR8-Umfang,
  keines wurde durch dieses Paket neu rot.

## 5. Baseline und Grenzen

- **bwrap in dieser Umgebung grundsätzlich nicht verfügbar:** Fälle, die
  eine echte Sandbox starten, sind hier nicht ausführbar; die Argument-
  und Markerprüfung erfolgt ohne bwrap über `VIBE_BWRAP`-Attrappen.
- **`test_baseline_inventory`** war vor diesem Paket rot und ist jetzt grün;
  die zehn nachgetragenen Routen sind die einzige Ursache.
- **`test_sandbox` (Vorlagen):** der `openwrt`-Eintrag in der
  Testdatei-`TOOL_DEFAULTS`-Kopie wurde nach Nutzerentscheidung entfernt
  (Projekttyp existiert seit dem Repo-Cleanup nicht mehr); web/docker
  prüfen die ergänzten Vorlagenwerte. Im Produktivcode gibt es
  `TOOL_DEFAULTS` nur in `bin/vibe_sandbox.py` (Werkzeug-Defaults für
  `vibe sandbox on`; `web` und `docker` sind dort korrekt). Die
  Projekttypen ergeben sich aus den Vorlagenordnern unter `templates/`;
  die `openwrt`-Vorlage bleibt entfernt.
- **Home-Pfad-Hygiene:** Der Scan über alle getrackten Textdateien ist
  vollständig grün (0 Treffer); die letzte Testdatei-Stelle hat der
  Test-Agent neutralisiert. `build-release.py` wurde bewusst nicht
  geändert.
- **F7-Dokumentation:** Die Tabelle „Projektvorlagen“ beschreibt weiterhin
  fünf Vorlagen inklusive `openwrt`; diese Zeile ist vorbestehende Drift
  (Vorlage im Repo-Cleanup entfernt) und wurde nicht umgebaut, weil die
  Werkzeugwerte für `web`/`docker` bereits dem Zielzustand entsprechen.
- **F27-Kopierseite:** Die Auslassung gilt nur für `AGENTS.md`;
  `TICKETS.md`/`FEEDBACK.md` werden weiterhin kopiert (auch dirty), weil der
  Agent sie als Laufzeitnotizen fortschreibt. Der `HINWEIS` erscheint im
  `copy-notes`-Aufruf des Läufers; ein Fehler ist das nicht.
- **Rename-Quellen im Abschluss-Merge (Review-Befund, Doku-Grenze):**
  `merge_package` listet mit `git diff --name-only HEAD "$BRANCH"` die
  Quellpfade von im Paketbranch umbenannten Dateien nicht auf. Ist eine
  solche Datei in `$P` uncommittet geändert, verwirft der Läufer sie nicht
  und der ff-Merge scheitert fail-closed („Your local changes … would be
  overwritten“, `FEHLT: Merge …`) — kein Datenverlust, aber ein seltener
  Blockierfall, der bewusst der Nutzerentscheidung (nur überschriebene
  Dirty-States verwerfen) folgt.
- **`register_projects`/`install_lifecycle`/`ticket_feedback_processing`:**
  vom Test-Agenten auf den aktuellen Installationsvertrag (67d53bc) bzw.
  die AP3-Präzedenz nachgezogen; die genannten Module laufen grün
  (`test_install_lifecycle` Ran 43 OK, `test_setup_vibe` Ran 50 OK,
  `test_ticket_feedback_processing` Ran 28 OK).
- **Trilium-MCP:** in dieser Umgebung nicht verfügbar; keine
  Synchronisation (Ticketregel: melden, nicht blockieren).

## 6. Geänderte Dateien

- `bin/vibe-run.sh` (T-BR1; `merge_package` für F27/Variante A)
- `bin/vibe_packages.py` (`copy_work_notes`/`command_copy_notes` für
  F27/Variante A)
- `bin/vibe_sandbox.py` (T-BR2)
- `docs/baseline.md` (T-BR4)
- `docs/features/F6.md` (Windows-Startbefehl, Doku-Drift)
- `templates/web/.vibe/project.env`, `templates/docker/.vibe/project.env`
  (T-BR7)
- `docs/features/AP21.md`, `docs/reviews/AP20-review-1.md`,
  `docs/reviews/AP20-test-agent-report.md`, `docs/reviews/AP21-review-6.md`,
  `docs/reviews/AP21-test-agent-report.md`,
  `docs/reviews/AP22-test-agent-report-mc.md`,
  `docs/reviews/AP22-test-agent-report.md`,
  `docs/reviews/B17-test-agent-report.md`, `docs/reviews/B18-review-1.md`,
  `docs/reviews/F32-review-1.md`, `docs/reviews/F32-review-2.md` (T-BR5)
- `docs/import-manifest.json` (Größe/SHA-256 der geänderten
  Manifest-Dateien, Chronikeintrag AP6-Korbat)
- `docs/features/AP6-Korbat.md` (dieses Dokument, neu)

## 7. Nachtrag: Merge von `origin/dev` und Baseline-Nachschuss (2026-11-22)

Der Abschlusslauf verlangte den Merge von `origin/dev` in den Paketbranch.
Der Konflikt in `docs/import-manifest.json` wurde als echte Vereinigung
aufgelöst (Merge-Commit `5e66e1c`): die beiden F33-Chronikeinträge von
`origin/dev` und der AP6-Korbat-Eintrag stehen alle drei in der `aenderungen`-
Liste; die `files`-Einträge wurden gegen den tatsächlich gemergten Stand
geprüft (`check-import-manifest.py`: OK, 70 Dateien).

**Erbefundung aus F33:** Die mit dem Merge eingereichten Routen
`GET /api/global_agents_file` und `POST /api/global_agents_file`
(`bin/vibe-web.py`, F33) sind in `docs/baseline.md` nicht dokumentiert —
nachweislich bereits auf `origin/dev` selbst (Routen in
`MERGE_HEAD:bin/vibe-web.py`, keine Erwähnung in
`MERGE_HEAD:docs/baseline.md`), sodass
`tests.unit.test_baseline_inventory.test_every_api_route_is_documented`
im gemergten Stand wieder rot war (T-BR4 war bei der Abnahme grün; die
Fehlbergabe der Konfliktauflösung ist ausgeschlossen, da beide Elternseiten
die Diskrepanz enthalten bzw. unverändert übernahmen).

**Entscheidung (Nutzer, Rückfrage `qd6061915a721`, Variante A):** Die zwei
Routen in diesem Paket nachtragen, damit T-BR4 am finalen Stand grün bleibt;
danach Review-Runde 3 und aktualisierter Ticket-Nachweis.

**Umsetzung:** Zwei Zeilen am Ende der API-Tabelle in `docs/baseline.md` §6
im etablierten T-BR4-Stil (Status „vorhanden und automatisiert geprüft“,
Handlervertrag aus `do_GET`/`do_POST`, Testbelege aus
`tests/unit/test_f33_global_agents.py`). `docs/baseline.md` liegt außerhalb
der Manifest-Scopes; keine Manifest-Pflicht.

**Verifikation:** `env -u SANDBOX python3 -m unittest
tests.unit.test_baseline_inventory tests.unit.test_ap24_license
tests.unit.test_f33_global_agents` → Ran 30, OK;
`env -u SANDBOX bash scripts/verify.sh quick --project .` → Exit 0.

**Neue Dateien in diesem Nachtrag:** `docs/baseline.md` (zwei API-Zeilen),
dieses Dokument (§7), `TICKETS.md` (Nachweiszeile ergänzt),
`docs/reviews/AP6-Korbat-review-3.md`.
