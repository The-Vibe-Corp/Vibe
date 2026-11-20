# Reviewantwort AP1 — Runde 2

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-20.
Geprüfter Umfang: Revalidierung von AP1 im Arbeitsbaum `/var/log/custom/vibe-dev/worktrees/vibe-AP1-nme5yF` auf Branch `feature/korbat/ap1`, Basis `8f26a85` (beinhaltet unverändert den Squash-Commit `976228b` des bereits in Runde 1 mit `Verdict: PASS` abgenommenen AP1-Commits `4e89a6e`), einschließlich des Revalidierungsanhangs in `docs/features/AP1.md:216-283` sowie der dokumentierten Nutzerentscheidungen `qace263c176a1`, `qfc1fe3f5fc77` und `q419e128a8b14`.

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
| (1) Privater `opencode serve` startet neu, sobald sich das Zielverzeichnis (`--chdir`/`--write-dir`) von `$P` (Preflight-Integration) zu `$WT` (Paket-Worktree) oder zwischen Paketen ändert; `write_dir` (realpath) wird in `<log>.server.json` gespeichert und in `private_server_healthy "$dir"` geprüft | PASS | `bin/vibe-run.sh:121-146` (`private_server_healthy "$dir"` prüft `/api/info` und `os.path.realpath(recorded) == os.path.realpath(sys.argv[2])`), `bin/vibe-run.sh:156-176` (`private_server_file_write`), `bin/vibe-run.sh:245-266` (`ensure_private_server`: `stop_private_server` + `start_private_server "$dir"`) | `tests/unit/test_b13_private_server_runner.py:721-798` (`PreflightWriteDirChangeTest`); Supplied Output in `docs/features/AP1.md:142-153,168-181,229-245` (`1/1 Test OK`, `verify.sh package` `11/11 OK`) |
| (1b) Sandbox-Projektargument bleibt `$P` (Zustandsordner `state_dir($P)` bleibt pro Integrationsprojekt erhalten, keine doppelten Sitzungs-Logs pro Worktree) | PASS | `bin/vibe-run.sh:202` (`start_private_server`), `bin/vibe-run.sh:565` (`run_agent_in`), Aufrufer `:951` (`"$P"`) und `:610,651` (`"$WT"`) | `tests/unit/test_b13_private_server_runner.py:589-719` (`SandboxPrivateServerTest`, `:700-710` prüft `state_dir(self.project)`) |
| (2) & (3) `opencode-go`-Zugangsdaten in der Sandbox verfügbar gemäß Nutzerentscheidung `qace263c176a1` = Antwort A (Kopie nur der Zugangsdaten in `<state>/data/opencode/opencode.db`, `mode=ro&immutable=1`, `0o600`, atomare Anlage, transaktionales Upgrade ohne Überschreiben bestehender Credentials/Sessions, keine geteilte beschreibbare Host-DB) | PASS | `bin/vibe_sandbox.py:374-376` (`AUTH_TABLES`), `bin/vibe_sandbox.py:384-392` (`_opencode_source_db`), `bin/vibe_sandbox.py:417-510` (`_seed_opencode_credentials`), `bin/vibe_sandbox.py:676` (`bwrap_argv`), `bin/vibe_sandbox.py:738-744` (`auth.json` `--ro-bind`) | `tests/unit/test_ap1_sandbox_credentials.py:73-307` (AK1–AK6); `/var/log/custom/vibe-dev/questions/qace263c176a1.answer.json:1-7`; Supplied Output in `docs/features/AP1.md:155-181,229-245` (`6/6 Tests OK`, `test_b17_sandbox_argv` `4/4 OK`) |
| (4) Revalidierungs- und Dokumentations-Delta ohne Produktionscode-Änderung gemäß Nutzerentscheidungen `qfc1fe3f5fc77` und `q419e128a8b14` (lokale Ausnahme ohne Trilium/Push/PR/Integrationsmerge und ohne erneuten Vollsuite-Lauf) | PASS | `docs/features/AP1.md:1-283` (inkl. Revalidierungsanhang `:216-283`), `docs/reviews/AP1-review-1.md:1-64`, `docs/import-manifest.json:1035-1046,1065-1068,1139-1143`, `/var/log/custom/vibe-dev/questions/qfc1fe3f5fc77.answer.json:1-7`, `/var/log/custom/vibe-dev/questions/q419e128a8b14.answer.json:1-7` | Supplied Output in `docs/features/AP1.md:229-245` (`verify.sh quick` Exit 0: 58 Manifest-Dateien, 195 Python/8 Bash/3 JSON, Secret-Scan; `verify.sh package` Exit 0: 11/11 Tests OK; Fokus-Kombilauf 19/20 OK); ausdrückliche Nutzerfreigabe in `qfc1fe3f5fc77` und `q419e128a8b14` |

## Findings

- No findings.

## Verification
- Change set reviewed: Arbeitsbaum auf Branch `feature/korbat/ap1` (`HEAD = 8f26a85243ae9de406a035f138057df3163c4052`, enthält unverändert den Squash-Merge `976228b` von AP1 aus `4e89a6e`) sowie das reine Dokumentations-/Revalidierungs-Delta in `docs/features/AP1.md:216-283`. Es gab seit dem bereits abgenommenen AP1-Stand (`4e89a6e` / `976228b`) keinerlei Änderungen an Produktionscode (`bin/vibe-run.sh`, `bin/vibe_sandbox.py`) oder Testdateien (`tests/unit/test_ap1_sandbox_credentials.py`, `tests/unit/test_b13_private_server_runner.py`).
- Git commands run by me: keine (read-only Reviewer ohne Shell-/Git-Werkzeug; Git-Metadaten direkt über `.git/worktrees/vibe-AP1-nme5yF/HEAD`, `ORIG_HEAD`, `refs/heads/feature/korbat/ap1` und `logs/HEAD` geprüft).
- Checks evidenced by supplied raw output: `docs/features/AP1.md:142-194,229-245` (`test_ap1_sandbox_credentials` 6/6 OK; `PreflightWriteDirChangeTest` 1/1 OK; `test_b17_sandbox_argv` 4/4 OK; kombinierter Lauf 19/20 OK mit vorbestehendem Kernel-User-Namespace-Fehler im echten `bwrap`-Test; `verify.sh quick` Exit 0 mit 58 Manifest-Dateien, 195 Python/8 Bash/3 JSON und Secret-Scan; `verify.sh package` Exit 0 mit 11/11 OK).
- Checks reported only by the coding agent: alle in `docs/features/AP1.md` dokumentierten Test- und Prüfskriptläufe sowie der Abbruch des Hintergrund-Vollsuite-Laufs (`verify.sh full`) mit `SIGTERM` / Exit 143 infolge von Server-/Tool-Unterbrechungen (nur Header im Log, nicht abgeschlossen, keine Wiederholung gemäß Nutzerentscheidung `q419e128a8b14` und Projektregel `bin/vibe:135`, da Code und Tests seit `976228b` unverändert blieben).
- Checks not independently run: alle Build-, Test- und sonstigen Nicht-Git-Prüfungen (read-only-Rolle).
- Important areas inspected: `bin/vibe-run.sh`, `bin/vibe_sandbox.py`, `bin/vibe_packages.py`, `bin/vibe-web.py`, `bin/vibe`, `tests/unit/test_ap1_sandbox_credentials.py`, `tests/unit/test_b13_private_server_runner.py`, `tests/unit/test_b17_sandbox_argv.py`, `tests/unit/runner_support.py`, `docs/features/AP1.md`, `docs/reviews/AP1-review-1.md`, `docs/import-manifest.json`, `TICKETS.md`, `SPEC.md`, `/var/log/custom/vibe-dev/questions/qace263c176a1*.json`, `/var/log/custom/vibe-dev/questions/qfc1fe3f5fc77*.json`, `/var/log/custom/vibe-dev/questions/q419e128a8b14*.json`.
- Remaining risks: (1) `immutable=1` liest nur die Hauptdatei der Host-DB ohne uncheckpointete WAL-Seiten und überschreibt keine bereits befüllte Sandbox-DB (dokumentierte Grenze von Antwort A in `docs/features/AP1.md:57,204-207,266-270`). (2) `bwrap` kann in dieser Container-Umgebung mangels User-Namespace-Rechten nicht direkt ausgeführt werden (`docs/features/AP1.md:198-203,237-240`). (3) Der Hintergrund-Vollsuite-Lauf (`verify.sh full`) wurde in dieser Revalidierungsrunde durch `SIGTERM` (Exit 143) abgebrochen und nicht abgeschlossen; dies ist durch die unveränderte Code-/Testbasis seit `976228b`, die grünen `quick`-/Fokus-/`package`-Prüfungen und die ausdrückliche Nutzerfreigabe in `qfc1fe3f5fc77` / `q419e128a8b14` als dokumentierte Abnahmegrenze abgedeckt.
