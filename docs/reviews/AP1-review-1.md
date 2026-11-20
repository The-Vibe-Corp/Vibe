# Reviewantwort AP1 — Runde 1

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-20.
Geprüfter Umfang: Commit `4e89a6e` gegenuber Basis `1de016b` im Paket-Worktree
`vibe-AP1-2k1t6P`, Branch `feature/korbat-vibe-dev-bot/ap1-3`. Der Reviewer
konnte die Datei wegen seiner read-only-Werkzeugbeschrankung nicht selbst
anlegen; der Text ist wortlich ubernommen (bis auf diesen Kopfkasten).

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| Bug 1: Reuse nur bei HTTP-Gesundheit **und** passendem `write_dir` (realpath); fehlendes/abweichendes Feld ⇒ Neustart | PASS | `bin/vibe-run.sh:121-146` (`private_server_healthy "$dir"` prüft curl `/api/info` **und** realpath-Vergleich; `write_dir` muss nichtleerer String sein), `bin/vibe-run.sh:245-266` (`ensure_private_server`: bei `return 1` → `stop_private_server` + `start_private_server "$dir"`) | `tests/unit/test_b13_private_server_runner.py:721-797` (`PreflightWriteDirChangeTest`: zwei `listening` mit `cwd=$P` → `cwd=$WT`, `term` dazwischen); Supplied Output in `docs/features/AP1.md:142-153,171-177,191-192` (red: 2≠1; grün: OK) |
| Bug 1: `write_dir` (realpath) in `<log>.server.json`; `url`/`port`/`password_file` kompatibel | PASS | `bin/vibe-run.sh:156-176` (`private_server_file_write` schreibt `url`, `port`, `password_file`, `write_dir=os.path.realpath(directory)`); `bin/vibe-run.sh:101-116` (`private_server_url` unverändert kompatibel) | `tests/unit/test_b13_private_server_runner.py:419-433` prüft `url`/`port`/`password_file` aus der zur Laufzeit eingefangenen Serverdatei; Regressionsgrün `docs/features/AP1.md:186-187` |
| Bug 1: Sandbox-Projektargument bleibt `$P`; nur `--chdir`/`--write-dir` wechseln | PASS | `bin/vibe-run.sh:202` (`start_private_server`), `bin/vibe-run.sh:565` (`run_agent_in`) — beide mit `"$P"` als erstem Argument und `--chdir "$dir" --write-dir "$dir"`; Aufrufer `$P` bei `bin/vibe-run.sh:951`, `$WT` bei `bin/vibe-run.sh:610` | `tests/unit/test_b13_private_server_runner.py:589-718`, speziell `:706-710` (`expected_state = sandbox.state_dir(self.project)`, d. h. `$P`, nicht `$WT`). Ausführung der echten bwrap-Variante in dieser Umgebung nicht möglich (siehe Verification) |
| Bug 2: Sandbox-lokale DB `<state>/data/opencode/opencode.db` mit Schema + NUR Zugangsdaten (`credential`, `account`, `account_state`, `control_account`, `migration`), keine Sitzungen/Nachrichten/Blobs/kv | PASS | `bin/vibe_sandbox.py:371-376` (`AUTH_TABLES`), `:417-468` (nur diese Tabellen gelesen), `:666,676` (`data_home`, Aufruf vor bwrap-Aufbau), `:395-400,470-505` (Schema und Rows) | `tests/unit/test_ap1_sandbox_credentials.py:191-221` (AK1: Schema, 0600, alle 5 Tabellen befüllt, `session_v2`/`session_message`/`kv` leer); Supplied Output `docs/features/AP1.md:155-176` (red: 2 Failures; grün: 6/6 OK) |
| Bug 2: Quelle nur lesend `mode=ro&immutable=1`; Host-DB nie beschrieben | PASS | `bin/vibe_sandbox.py:384-392,436-440` (`file:`-URI mit `?mode=ro&immutable=1`, `uri=True`) | Code-Inspektion; `tests/unit/test_ap1_sandbox_credentials.py:114-121,123-171` isoliert HOME/XDG_DATA_HOME, sodass echte Host-DB unberührt bleibt; kein Test mutiert die Quelle |
| Bug 2: Neu anlegen atomar + 0600 | PASS | `bin/vibe_sandbox.py:488-505` (`mkstemp`, `chmod 0o600`, `BEGIN`/`commit`, `os.replace`, `finally unlink`) | `tests/unit/test_ap1_sandbox_credentials.py:199-202` (AK1 prüft `stat.S_IMODE == 0o600`) |
| Bug 2: Vorhandene DB mit `credential`-Zeilen bleibt unberührt; leere `credential`-Tabelle wird transaktional nachgezogen, Sitzungsdaten bleiben | PASS | `bin/vibe_sandbox.py:470-477` (Early Return bei vorhandenen credential-Zeilen), `:478-486` (`BEGIN`, `_apply_auth_schema` überspringt vorhandene Objekte, `_apply_auth_rows` mit `INSERT OR IGNORE`, `commit`/`rollback`) | `tests/unit/test_ap1_sandbox_credentials.py:223-239` (AK2 byte-identisch), `:241-269` (AK3: credential gefüllt, `session_v2`/`session_message`/`kv` unverändert) |
| Bug 2: Fehler ⇒ Warnung auf stderr, kein Abbruch; Legacy-`auth.json`-Bindung unverändert | PASS | `bin/vibe_sandbox.py:426-431,506-509` (broad `except Exception`, `print(..., file=sys.stderr)`), `:738-744` (`--ro-bind auth.json` unverändert) | `tests/unit/test_ap1_sandbox_credentials.py:271-290` (AK4/AK5 kein Abbruch), `:292-306` (AK6 Bindung geprüft) |
| Tests/Doku/Nachweise: `PreflightWriteDirChangeTest`, `test_ap1_sandbox_credentials` (AK1–AK6), `SandboxPrivateServerTest`-Korrektur, `docs/features/AP1.md`, TICKETS `[x]` mit Commit/Test, aktualisiertes Manifest | PASS | `tests/unit/test_b13_private_server_runner.py:721-797`; `tests/unit/test_ap1_sandbox_credentials.py:73-306`; `tests/unit/test_b13_private_server_runner.py:696-710`; `docs/features/AP1.md:1-212`; `TICKETS.md:6-105`; `docs/import-manifest.json:1026-1035` (Eintrag), `:1054-1057,1129-1132` (files-Hashes) | `docs/reviews/AP1-review-1.md` existiert noch nicht (wird vom Koordinator abgelegt); alle übrigen Artefakte direkt gelesen und vorhanden |

## Findings

- No findings.

## Bewertung der Sicherheit

- **Host-DB bleibt readonly:** Die Quelle wird ausschließlich über `sqlite3.connect(..., uri=True)` mit `file:<realpath>?mode=ro&immutable=1` geöffnet (`bin/vibe_sandbox.py:436-440`). Es gibt keinen Schreibpfad zur Host-DB; `os.path.isfile(source)` ist die einzige weitere Operation. Die Kopie liegt unter `state_dir($P)/data/opencode` (`bin/vibe_sandbox.py:666`), also im beschreibbaren Sandbox-Zustand, nicht im Projekt/d Integrationsrepo.
- **Keine Cross-Projekt-Daten in der Kopie:** Befüllt werden ausschließlich die fünf explizit gelisteten Auth-Tabellen (`bin/vibe_sandbox.py:374-376,452-468`); Sitzungs-, Nachrichten-, Blob- und kv-Zeilen werden nicht gelesen. Der Zustandsordner wird aus dem realpath des **Integrationsprojekts** berechnet (`bin/vibe_sandbox.py:251-257`), und das Sandbox-Projektargument bleibt `$P` (`bin/vibe-run.sh:202,565`), sodass alle Arbeitskopien eines Projekts dieselbe, von anderen Projekten getrennte DB nutzen (keine doppelten Sitzungslogs, kein Austausch von Sitzungsverläufen).
- **Keine Token-Werte in Logs:** Warnungen enthalten nur Pfad-/Problem- bzw. SQLite-Fehlerstrings (`bin/vibe_sandbox.py:429-430,508-509`), keine Zeilenwerte. Die Serverdatei enthält nur `url`, `port`, `password_file`, `write_dir` (`bin/vibe-run.sh:166-175`), nie das Kennwort selbst; `tests/unit/test_b13_private_server_runner.py:306-311,435-442` prüft explizit gegen Kennwortleaks. Das Sandbox-`--print-command` gibt Pfade, keine Token aus.

## Bewertung der Rückfallrichtung

- **Alte Serverdatei ohne `write_dir`:** `private_server_healthy` verlangt einen nichtleeren String und realpath-Gleichheit (`bin/vibe-run.sh:140-144`); ein fehlendes Feld führt zu `return 1`, damit `stop_private_server` + Neustart mit neu geschriebener `write_dir` (`:252-253`, `:226`). Kompatibilität zu `url`/`port`/`password_file` bleibt erhalten.
- **Fehlende Host-DB:** `bin/vibe_sandbox.py:433-435` gibt ohne Zieldatei und ohne Warnung/Abbruch zurück; die Sandbox läuft mit den zuvor vorhandenen Zugangsdaten (oder ohne) weiter (AK4).
- **Quelle ohne `credential`-Tabelle:** Die Tabelle wird übersprungen (`bin/vibe_sandbox.py:454-455`); es gibt keinen Abbruch und keine eingefügten Zugangszeilen (AK5). Bei bereits vorhandener Sandbox-DB bleibt eine bestehende leere `credential`-Tabelle erhalten.

## Verification

- Change set reviewed: `1de016b..4e89a6e` — **inhaltlich geprüft über die Arbeitsbaum-Dateien am HEAD** (`4e89a6e206ef9d5ec73fe8e0d0b2e08391a42542`, bestätigt aus `.git`-Ref; `ORIG_HEAD` = `1de016b923f151da2e6c5f4c7d06883f0c5f3920`). Zusätzlicher Vorher-Nachher-Vergleich gegen die installierte Standkopie `/opt/custom/vibe-dev/app/bin/{vibe-run.sh,vibe_sandbox.py}` (dort noch ohne `write_dir`-Logik und ohne `_seed_opencode_credentials`); diese Kopie ist nicht hash-verifiziert gegen `1de016b`.
- Git commands run by me: **keine** — mein read-only-Werkzeugkatalog enthält keine Shell; `git show`, `git diff`, `git status` konnten nicht ausgeführt werden. `fetch(file://…)` ist in der Code-Mode-Laufzeit gesperrt. Der Change Set war jedoch über die Dateien am HEAD vollständig lesbar.
- Checks evidenced by supplied raw output: `docs/features/AP1.md:142-192` enthält dokumentierte Ausgaben (Red: `PreflightWriteDirChangeTest` 2≠1; `test_ap1_sandbox_credentials` 2 Failures; Grün: 1/1 bzw. 6/6 OK; `bash -n` Exit 0; `test_b17_sandbox_argv` 4/4; Manifest-/Syntax-/Secret-Checks OK; Gesamtlauf 20 Tests, 19 OK, 1 Failure). Ich habe diese Ausgaben **nicht selbst reproduziert**.
- Checks reported only by the coding agent: sämtliche oben genannten Test-/Prüfaufrufe; zusätzlich der Commit-Text in `TICKETS.md:105` und im `COMMIT_EDITMSG`.
- Checks not independently run: alle Build-, Test-, Lint-, Syntax-, Manifest- und Secret-Prüfungen (read-only-Rolle; keine Testausführung erlaubt).
- Important areas inspected: `bin/vibe-run.sh` (Server-Datei, Health-Check, Wrap-Kette, Preflight-/Paket-Aufrufer), `bin/vibe_sandbox.py` (`AUTH_TABLES`, `_opencode_source_db`, `_seed_opencode_credentials`, `bwrap_argv`, Legacy-Bindung), `tests/unit/test_ap1_sandbox_credentials.py`, `tests/unit/test_b13_private_server_runner.py`, `tests/unit/runner_support.py`, `tests/unit/test_b17_sandbox_argv.py`, `docs/features/AP1.md`, `docs/import-manifest.json`, `TICKETS.md`, `SPEC.md`, `qace263c176a1.answer.json`.
- Remaining risks: (1) `immutable=1` liest nur die Hauptdatei; WAL-Inhalte der Host-DB werden nicht übernommen — in `docs/features/AP1.md:55,202-205` ausdrücklich als bekanntes Limit dokumentiert und von der AK gefordert. (2) Der echte bwrap-Lauf konnte in dieser Umgebung nicht verifiziert werden (User-Namespaces nicht erlaubt); der vorbestehende `SandboxPrivateServerTest` bleibt deshalb laut Doku rot, seine **Korrektur** auf `state_dir($P)` ist jedoch im Code vorhanden (`tests/unit/test_b13_private_server_runner.py:696-710`) und durch einen Nachweisdatei-Eintrag abgedeckt. (3) Die `Test:`-Zeile in `TICKETS.md:105` nennt einen Gesamtlauf mit 1 dokumentiertem Umgebungs-Failure; das Ticket ist über die Nachweisdatei `docs/features/AP1.md` abgedeckt, nicht über einen vollständig grünen Lauf. (4) Manifest-Hashes/SHA-256 wurden nicht selbst nachgerechnet.

**Hinweis zur Rolle:** Ich bin ausschließlich lesend tätig und durfte keine Dateien ändern, nicht committen, den Branch nicht wechseln und keine Tests ausführen. Die im Code/Commit dokumentierten Testergebnisse wurden als Nachweis gewertet, nicht als selbst reproduzierte Evidenz.

## Verdict rules

Verdict: **PASS** — der change set war inhaltlich verfügbar und wurde vollständig geprüft; es gibt keine Critical-/High-/Medium-Befunde, und alle Akzeptanzkriterien sind mit Implementation und Nachweis belegt (mit den oben genannten, transparent dokumentierten Verifikationsgrenzen).
