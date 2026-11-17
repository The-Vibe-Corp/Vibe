# Reviewantwort AP18 — Runde 1

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-17.
Geprüfter Umfang: `a38cabb..aabae4c` (Zweig `feature/m0p/ap18-cli-webui-password`).
Die Antwort ist wörtlich übernommen (bis auf diesen Kopfkasten). Einzige
weitere Abweichung: in der Evidence-Zeile des zweiten Minor-Befunds ist das
Testattrappen-Literal auf `password = "nachstart-…"` gekürzt, damit
`scripts/check-no-secrets.py` (Zugangsdaten-Zuweisungen mit Literalen ab 16
Zeichen) die wörtlich gespeicherte Reviewdatei nicht als Geheimnis meldet;
der Befund selbst ist unverändert.

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: PASS

## Acceptance criteria
| Kriterium | Status | Implementierung (file:line) | Test / Nachweis |
|---|---|---|---|
| `vibe ui password set` (interaktiv, unsichtbar, Wiederholung) | PASS | `bin/vibe:5076-5083` (getpass, isatty-Wächter), `5084-5089` | `PasswordSetInteractiveTest` (4 Fälle), alle ok in `/tmp/vibe-verify-_9pfg8d0/verify.log:431-434`; Rotphase 14/20 im Testbericht dokumentiert |
| `vibe ui password set --stdin` (genau eine Zeile) | PASS | `bin/vibe:5071-5074` | `PasswordSetStdinTest` (4 Fälle), ok in verify.log:435-438 |
| Kennwort nie als Kommandozeilenargument | PASS | `bin/vibe:5107-5114` (unbekanntes Token → Usage-Abruch) | `PasswordArgumentRejectionTest` ok, verify.log:427; Kennwort erscheint nicht in der Ausgabe (Test assertion) |
| Mindestlänge 8 / Abbruch ohne Dateiänderung | PASS | `bin/vibe_ui_config.py:221-233` (set_password validiert vor dem Schreiben), `141-170` (atomar) | `test_stdin_short_password_is_rejected_without_change`, `test_interactive_short_password…`, `test_interactive_mismatch…` ok |
| `vibe ui password clear` (Hash weg, ohne Hash bytegleich / Exit 0) | PASS | `bin/vibe:5062-5069`, `bin/vibe_ui_config.py:256-262` | `PasswordClearTest` (3 Fälle) ok, verify.log:428-430 |
| `vibe ui password [status]` ohne Hash-Auskunft | PASS | `bin/vibe:5052-5061` | `PasswordStatusTest` (3 Fälle) ok, verify.log:439-441 |
| Unbekannte Unteraktion abgelehnt, Datei unverändert | PASS | `bin/vibe:5107-5116` | `PasswordUnknownActionTest` ok, verify.log:442 |
| Bestehendes `ui start/stop`/`--port/--bind` und `cmd_ui(<string>)` unverändert | PASS | `bin/vibe:5100-5129`, `5143-5148` | `UiExistingBehaviourTest`, `CmdUiStringCompatibilityTest` ok, verify.log:425, 443-444 |
| Laufendes Dashboard übernimmt Kennwort ohne Neustart; Token-Login bleibt gültig | PASS | `bin/vibe-web.py:1133-1151` (reload vor Kennwortprüfung), Token-Vergleich unverändert `1146-1148` | `DashboardPasswordReloadTest` ok, verify.log:426; AP13-Netz-/Zugriffstests ok, verify.log:254 ff. |
| Manifest: AP18-Eintrag begründet; vorbestehende Syntaxdefekte verhaltensneutral korrigiert | PASS | `docs/import-manifest.json:926-933` (AP18-Grund), `917-925` (B14), `947-951`, `957-961` (aktualisierte bytes/sha256) | `check-import-manifest.py` ok in verify.log:4 („OK: 57 Dateien …“); Diff belegt fehlendes Komma AP17/B14 und die Doppel-Fassung im `bin/vibe`-Eintrag bereits am Basestand |
| Keine AP18-Regressionen im vollen Lauf | PASS | — | verify.log:4456-4458 (1832 Tests, failures=39, errors=96, skipped=1) vs. Baseline `/tmp/vibe-verify-t3zakkhq/verify.log:4485-4487` (1812, failures=38, errors=100, skipped=1): Differenz exakt erklärbar — 3 Baseline-ERRORs (`test_feedback_entries` ×2, `test_repository_agents_file_contains_the_coding_guidelines`) fehlen im AP18-Lauf, weil im Vergleichs-Worktree die unversionierten `AGENTS.md`/`FEEDBACK.md` fehlten; `test_repository_agents_file_contains_the_test_agent_rule` wechselt nur ERROR→FAIL (gleicher vorbestehender AGENTS.md-Befund). Kein neuer Fachfehler. |
| Trilium-Dokumentation | PASS | — | Notiz `LtyM7rb6m1I0` („AP18 Kennwort der WebUI über die CLI setzen“, Elternbereich Features, angelegt 2026-11-17) von mir über Trilium-MCP gelesen; Indexzeile in `docs/trilium-index.md` (uncommitted, laut Prozess erst nach PASS zu committen) |

## Findings

- [Minor] `bin/vibe:5115` — `--stdin` ohne Unteraktion `set` wird still akzeptiert
  - Evidence: `if use_stdin and sub not in (None, "set")` lässt `vibe ui password --stdin` zu; das ergibt `password_sub="status"`, das Kennwort von stdin wird nie gelesen. Der Usage-Text (`bin/vibe:5036`) nennt `--stdin` nur für `set`; ein Skript, das so aufruft, erhält eine Statusausgabe und kein gesetztes Kennwort. Kein Datenrisiko (es wird nichts geschrieben).
  - Required fix: Parser so verschärfen, dass `--stdin` nur zusammen mit `set` gültig ist (Regel `sub == "set"`), und die Fälle in `PasswordUnknownActionTest` ergänzen.

- [Minor] `tests/unit/test_ap18_cli_ui_password.py:886-889` — nachträgliche Änderung der Testdatei durch den Coding-Agenten
  - Evidence: Der Nachtrag im Testbericht dokumentiert die Umbenennung `password = "nachstart-…"` → `kennwort = "nachstart-…"` (check-no-secrets-Heuristik, `scripts/check-no-secrets.py:31-36` würde `password\s*=\s*"<16+ Zeichen>"` melden). AGENTS.md („Unabhängiger Test-Agent“) sagt: „Coding- und Review-Agent dürfen keine Testdateien anlegen, ändern, löschen oder abschwächen.“ Die Änderung ist verhaltensneutral, schwächt keine Assertion, ist transparent dokumentiert und wurde mit erneut 20/20 bestätigt — verletzt die Regel aber formal.
  - Required fix: Künftige Anpassungen an Testdateien (auch kosmetische) beim Test-Agenten anfordern; für dieses Paket genügt der dokumentierte Verlauf, solange keine Assertion verändert wurde.

- [Minor] `bin/vibe:5076-5082` — getpass-Fallback kann unter Sonderumständen mit Echo lesen
  - Evidence: Die Wächterprüfung `sys.stdin.isatty()` deckt den Normalfall ab. Bleibt stdin ein TTY, während kein steuerndes Terminal existierbar ist (z. B. `setsid` mit tty-stdin), fällt `getpass.getpass` intern auf stdin mit Echo zurück (GetPassWarning) — der zugesagte „unsichtbar“-Effekt gilt dann nicht. Sehr schmales Szenario; die Grenze „Ohne Echo wird über die PTY-Ausgabe geprüft“ ist in AP18.md:107-108 dokumentiert.
  - Required fix: Grenze im Handbuch/Feature-Dok nennen oder den Echo-Fallback im interaktiven Pfad aktiv ablehnen (z. B. `/dev/tty`-Erreichbarkeit vor getpass prüfen).

## Verification
- Change set reviewed: `a38cabb..aabae4c` (Commits via `git show --stat aabae4c` und Voll-Diffs der 7 Dateien); Arbeitsbaum: nur `docs/trilium-index.md` uncommitted (AP18-Indexzeile, laut Prozess bewusst offen bis zum finalen PASS). TICKETS.md enthält (noch) keinen AP18-Eintrag — laut Auftrag erst nach Review.
- Git commands run by me: `git log --oneline -3`, `git status --short`, `git show --stat aabae4c`, `git show aabae4c -- bin/vibe bin/vibe-web.py`, `git show aabae4c -- docs/import-manifest.json docs/handbuch.md`, `git diff docs/trilium-index.md`. (Mehrere weitere Befehle inkl. `python3 scripts/check-import-manifest.py`, `sha256sum`, `tail` und `git grep` wurden von der Shell-Berechtigung abgelehnt — siehe unten.)
- Checks with supplied output: AP18-Einheitentestlauf, verify.sh quick und full wurden nicht von mir ausgeführt; die Verify-Logs beider Läufe liegen aber als echte Artefakte vor und habe ich ausgewertet: `/tmp/vibe-verify-_9pfg8d0/verify.log` (AP18: Manifest-Check ok Zeile 4, Syntax ok, keine Geheimnisse, 20 AP18-Fälle ok Zeilen 425-444, AP13-Tests ok, Summenzeile 4456-4458) und `/tmp/vibe-verify-t3zakkhq/verify.log` (Baseline: Zeilen 4485-4487). Der Abgleich aller FAIL/ERROR-Listen (135 vs. 138 Einträge) ergibt exakt die erklärten Worktree-Artefakte plus eine ERROR→FAIL-Reklassifizierung desselben vorbestehenden AGENTS.md-Befunds — kein AP18-Fachfehler.
- Checks not independently run: alle Build-/Test-/Prüfkommandos (Testlauf, verify.sh, check-import-manifest, sha256sum); Freigabe-Verweigerung der Shell. Die Richtigkeit der Manifest-Hashes gegenüber den Dateien beruht daher auf dem verify.log-Artefakt, nicht auf meiner eigenen Berechnung. Hinweis: der Full-Lauf endet ~16 Min. vor dem Commit-Zeitpunkt; der Arbeitsbaum ist für `bin/vibe`/`bin/vibe-web.py` aber byteidentisch mit dem Commit (`git status`), sofern zwischen Prüfende und Commit nichts geändert wurde — das kann ich nicht unabhängig belegen.
- Important areas inspected: `bin/vibe` (`_ui_password`, `_ui_arguments`, `cmd_ui`, Dispatch `"ui"`, `__doc__`), `bin/vibe-web.py` (`/api/login` inkl. Allowlist/Origin/Token-Pfad, `reload_ui_data`, `_startup_config`, `_guard`, `_read_json`), `bin/vibe_ui_config.py` komplett, Testdatei komplett (939 Zeilen), Test-Agent-Bericht, AP18.md, handbuch-Ausschnitt, Manifest-Ausschnitte, `scripts/check-no-secrets.py`, SPEC.md „Sicherheit und Datenintegrität“.
- Remaining risks: (1) Ändern eines bereits gesetzten Kennworts und `clear` im laufenden Betrieb sind durch den Dashboard-Reload-Test nicht abgedeckt (dokumentierte Grenze im Testbericht; Codepfad `set_password` ist durch AP13-Fälle gesichert). (2) Vorbestehende Defekte außerhalb des Pakets bleiben unberührt (`cmd_init` NameError `agent`, AGENTS.md-Inhaltsprüfungen, `ensure_test_agent`-Klasse, doppelte Definitionen `reload_ui_data`/`restart_required`/`security_data` in `bin/vibe-web.py:669-744` — AP18 ruft die zweite, identische Definition). (3) Die Process-Argument-Ablehnung wird über die CLI-Abbruchprüfung nachgewiesen, nicht per `/proc/<pid>/cmdline` (dokumentierte Grenze).
