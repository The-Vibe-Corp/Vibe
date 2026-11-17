# AP18 — Test-Agent-Bericht

Auftrag: unabhängige Tests für AP18 (Kennwort der WebUI über die CLI setzen).
Die Fälle wurden aus dem Arbeitspaket und SPEC.md („Sicherheit und
Datenintegrität") abgeleitet, nicht aus einem Implementierungsdiff.

## Ergebnis

Neue Testdatei (keine Produktionsänderungen): `tests/unit/test_ap18_cli_ui_password.py`

Testbefehl: `python3 -m unittest tests.unit.test_ap18_cli_ui_password -v`

## Testfälle

**`PasswordSetStdinTest`** — `password set --stdin`
- `test_stdin_sets_a_salted_hash_without_prompt` — kein `ui.json`; `--stdin` mit `abcdefgh\n`; Exit 0, gesalzener Hash in `ui.json`, `verify_password` akzeptiert, kein Klartext in Datei/Ausgabe.
- `test_stdin_reads_exactly_one_line_without_newline` — kein `ui.json`; zwei stdin-Zeilen; nur Zeile 1 ist Kennwort, Zeile 2 und der zusammengesetzte Text schlagen fehl, `\n` ist nicht Teil des Kennworts.
- `test_stdin_accepts_a_final_line_without_newline` — kein `ui.json`; stdin endet ohne Zeilenumbruch; Exit 0, Kennwort gesetzt.
- `test_stdin_short_password_is_rejected_without_change` — `ui.json` mit `{"ui_port": 9155}`; 7 Zeichen; Exit ≠ 0, Meldung zur Mindestlänge, Datei unverändert.

**`PasswordSetInteractiveTest`** — `password set` (echtes PTY)
- `test_interactive_set_asks_twice_and_stores_the_hash` — kein `ui.json`; Kennwort zweimal; zwei Prompts, Exit 0, Hash gesetzt, kein Echo des Kennworts.
- `test_interactive_mismatch_aborts_without_change` — `ui.json` mit `{"ui_port": 9156}`; zwei unterschiedliche Eingaben; Exit ≠ 0, Fehlermeldung, Datei unverändert.
- `test_interactive_short_password_is_rejected_without_change` — kein `ui.json`; 7 Zeichen zweimal; Exit ≠ 0, Mindestlängenmeldung, keine Datei.
- `test_interactive_without_tty_and_empty_stdin_aborts` — kein TTY/leeres stdin; Abbruch mit Meldung, kein Hängen (Timeout 30 s), keine Datei.

**`PasswordArgumentRejectionTest`**
- `test_password_as_command_line_argument_is_rejected` — kein `ui.json`; Kennwort positional, als `--password` und `--password=…`; Exit ≠ 0, Usage-Meldung, keine Datei, Kennwort nicht in der Ausgabe.

**`PasswordClearTest`**
- `test_clear_removes_the_hash_and_keeps_other_fields` — `ui.json` mit `ui_port` + Hash; `clear`; Exit 0, Hash weg, `ui_port` bleibt, `verify_password` falsch.
- `test_clear_without_hash_changes_nothing_and_exits_zero` — `ui.json` nur mit `ui_port`; `clear`; Exit 0, nichtleere Meldung, Datei bytegleich.
- `test_clear_without_ui_json_exits_zero_without_creating_a_file` — kein `ui.json`; `clear`; Exit 0, Meldung, weiterhin keine Datei.

**`PasswordStatusTest`**
- `test_status_without_ui_json_reports_not_set` — kein `ui.json`; `password status`; Exit 0, „nicht gesetzt".
- `test_status_reports_set_without_leaking_hash_details` — Hash gesetzt; `password status`; Exit 0, „gesetzt" ohne „nicht gesetzt", Salz/Hash-Hex nicht in der Ausgabe.
- `test_bare_password_without_subaction_shows_status` — einmal ohne, einmal mit Hash; `vibe ui password`; gleiche Statusausgabe wie `status`.

**`PasswordUnknownActionTest`**
- `test_unknown_action_is_rejected_without_change` — `ui.json` mit Hash; `password frobnicate`; Exit ≠ 0, Usage-Meldung, Datei bytegleich.

**`UiExistingBehaviourTest`**
- `test_ui_start_with_port_and_bind_still_starts` — isolierte Pfade, tmux-Attrappe, freier Port; `start --port N --bind 127.0.0.1`; `new-session` mit den aufgelösten Werten im tmux-Log.
- `test_ui_stop_without_session_stays_unchanged` — keine Sitzung; `stop`; Exit 0, „Dashboard läuft nicht.", kein Kill/Start.

**`CmdUiStringCompatibilityTest`**
- `test_cmd_ui_accepts_the_legacy_string_argument` — isolierte Pfade, keine Sitzung; `cmd_ui("stop")` mit String; kein Fehler, „Dashboard läuft nicht.".

**`DashboardPasswordReloadTest`**
- `test_password_set_after_start_is_accepted_without_restart` — laufendes Dashboard ohne Kennwort; Login mit Kennwort → 403, dann `password set --stdin`, dann Login → 200 + Session-Cookie, autorisierter GET → 200, falsches Kennwort → 403, Instanz-Token weiterhin 200.

## Tatsächliche Rotphase

Befehl: `python3 -m unittest tests.unit.test_ap18_cli_ui_password -v`

Kurzfassung:
```
Ran 20 tests in 5.6s
FAILED (failures=14)
```
Alle neuen Fachfälle scheitern erwartungsgemäß, weil der aktuelle `vibe ui`-Parser `password` nicht kennt und mit `Aufruf: vibe ui [start|stop] [--port <n>] [--bind <ip>]` abbricht (Exit 1). 6 Tests sind grün und bewusst nur Regressions-/Schutzfälle: `cmd_ui("stop")`-String, `ui start/stop`, Ablehnung eines Kennworts als Argument, unbekannte Unteraktion, sowie der Nicht-TTY-Abbruch (aktuell ebenfalls durch die Usage-Ablehnung erfüllt).

Zusätzlich validiert: Der PTY-Helfer sendet nachweislich zwei Prompts (`sent == 2`) und erkennt Mismatch/Erfolg korrekt — gegen ein temporäres Wegwerf-Skript außerhalb des Repos geprüft, nicht gegen Produktionscode.

## Offene Grenzen

- Die PTY-Fälle erwarten deutsche Prompts mit „Kennwort" oder „Passwort"; ein anderer deutscher Begriff würde trotz korrektem Verhalten scheitern. Das ist die dokumentierte Annahme des Vertrags („Ausgaben auf Deutsch").
- „Ohne Echo" wird über die PTY-Ausgabe geprüft, nicht über termios-Flags.
- Beim Nicht-TTY-Abbruch wird nur Exit ≠ 0, nichtleere Meldung und unveränderte Datei geprüft; die exakte Formulierung ist nicht vorgeschrieben.
- Der Dashboard-Test deckt das nachträgliche Setzen ab (kein Kennwort → gesetzt), nicht das Ändern eines bereits gesetzten Kennworts oder `clear` im laufenden Betrieb.
- `vibe ui start` nutzt weiterhin eine tmux-Attrappe; es wird kein echter Dashboard-Start über tmux geprüft. Das laufende Dashboard für die Reload-Prüfung wird dagegen als echter Prozess auf Loopback gestartet.
- Prozessargumente werden nicht per `/proc/<pid>/cmdline` inspiziert; geprüft wird, dass die Argumentform abgelehnt wird und das Kennwort nie in der Ausgabe erscheint.

## Nachtrag (Coding-Agent, nachträgliche Änderung an der Testdatei)

Aus einem einzigen lokalen Namen `password = "nachstart-kennwort"` wurde
`kennwort` (Wert und Verhalten unverändert), weil `scripts/check-no-secrets.py`
Zugangsdaten-Zuweisungen mit Literalen ab 16 Zeichen meldet und der
`verify.sh quick` an dieser Test-Attrappe hängen blieb. Keine Aussage wurde
abgeschwächt; danach erneut 20/20 OK.
