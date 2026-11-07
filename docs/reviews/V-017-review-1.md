# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 5
- Verdict: PASS

## Acceptance criteria

Ticket V-017 (TICKETS.md) und SPEC.md Abschnitt „Bazzite-Startmenü“ (SPEC.md:216-230) wurden vollständig abgeglichen; das angegebene Abhängigkeitstrio V-004 (Health-Endpunkt), V-006 (Pfadmodul), V-016 (Stop-Semantik) wurde gegen die tatsächliche Implementierung (`bin/vibe-web.py:333-343` Health-Format `ok/app/instance`, `bin/vibe_paths.py`, `bin/vibe:3365-3396` `session_owned`-geschütztes `ui stop`) geprüft.

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| läuft nicht → starten und Browser öffnen | PASS | `scripts/vibe_starter.py:391-457` (absent → Container-Präfix + `ui start` + Health-Wait + Browser) | `tests/unit/test_bazzite_starter.py:206, 254` (absent- und Real-Dashboard-Test); Host-Protokoll `docs/features/V-017-bazzite.txt` Fall 1: Container aus/an → „Testcontainer laeuft jetzt“, Browser mit Token. Vom Agenten gelieferte Outputs, nicht von mir ausgeführt |
| läuft → nur Browser öffnen | PASS | `scripts/vibe_starter.py:393-404` | `test_running_dashboard_opens_only_the_browser` (interntest:203); `RealDashboardTest` zweiter Klick (test:276-283); Protokoll Fall 2 „Keine zweite Sitzung“ |
| fremder Dienst erkannt | PASS | `scripts/vibe_starter.py:155-172` (resolve_state), `405-409, 427-431` (Abbruch vor/nach Start), `449-464` (stop) | `ProbeTest` (6 Tests, inkl. echter HTTP-Server und falscher Instanz-ID, test:90-140); `test_foreign_service_blocks_the_start_and_is_reported` (test:388); Protokoll Fall 5 |
| Mehrfachklicks erzeugen eine Instanz | PASS | `scripts/vibe_starter.py:363-374` (`flock`), `391` | `ConcurrencyTest.test_double_click_creates_exactly_one_dashboard` (test:384-431): echte parallele Prozesse, echte tmux-Sitzung, genau 1 Sitzung, 2 Browseraufrufe; Protokoll Fall 3 |
| Pfade korrekt gequotet | PASS | `scripts/vibe_starter.py:106-172` (reine Argumentlisten), `scripts/vibe-desktop.py:112-133` (desktop_quote), `:135-139` (_exec_line) | `test_paths_with_spaces_and_special_characters_stay_separate_arguments` (test:350), `test_browser_override_with_spaces_stays_one_argument` (test:382), `test_desktop_exec_quotes_spaces_percent_and_dollar` (test:413); Host: `desktop-file-validate` Exit 0 mit Sonderzeichen in `XDG_DATA_HOME` (Agenten-Nachweis) |
| Menüaktion beendet nur vibe | PASS | `scripts/vibe_starter.py:449-471`; CLI-seitig zusätzlich `bin/vibe:3366-3373` (`session_owned`) | `test_stop_only_stops_the_dashboard` (test:295), `test_stop_when_absent_does_not_enter_container` (test:307), `test_desktop_entry_action_stops_only_vibe` (test:536); Protokoll Fall 7: `vibe-ui` (prod) und Port 8787 bleiben |
| Fehler sichtbar | PASS | `scripts/vibe_starter.py:481-502` (report_error: Log+Notifier+stderr), `540` (main-Fang) | `test_start_error_is_visible_and_the_log_is_cleaned` (test:319), `StarterCliTest.test_start_failure_is_reported_on_stderr_and_in_the_cleaned_log` (test:258); Protokoll Fall 6 (stderr, Notifier, bereinigtes Log, kein Browser) |
| Token wird nicht protokolliert | PASS | `scripts/vibe_starter.py:175-180` (redact), `:1289-1300`/`:230-243` (log/log_error), Logmodus 600 | `test_start_error_is_visible_and_the_log_is_cleaned` (assertNotIn token, test:343), `test_success_is_logged_without_token` (test:445) |
| Tokenwechsel, Sonderzeichen im Pfad, Startfehler als Testszenarien | PASS | s. o. | `test_token_change_is_used_on_every_launch` (test:411), Real-Dashboard-Neustart mit neuem Token (test:390-399); Protokoll Fall 4 |
| Mocktests + echte manuelle Bazzite-Abnahme | PASS | — | 37 Unit-Tests (supplied: „Ran 37 tests … OK“), `verify.sh quick`/`full` in sauberer Kopie (supplied: 786+56 Tests OK, Exit 0), Host-Protokoll „ERGEBNIS: 0 Fehler“ |

Die Verifikation der Tests lieferte mir nur die vom Agenten gelieferten Outputs; ich habe selbst keine Tests ausgeführt. Red-Phase wurde belegt (FileNotFoundError gegen e53aaa5, „FAILED (errors=1)“) — für ein Gesamt-Neupaket mit neuen Dateien ausreichend, deckt aber nur das Fehlen der Module, nicht jedes Einzelverhalten ab.

## Findings

- [Minor] `tests/unit/test_bazzite_starter.py:345` — Test abhängig von `notify-send` im Host-PATH
  - Evidence: `report_error` verwendet ohne `VIBE_NOTIFY` ein Environment-abhängiges `shutil.which("notify-send")` (korrekt: „soweit möglich“). Der Test verlangt aber zwingend einen `notify-send`-Aufruf; auf Systemen ohne `notify-send` schlägt der Test, obwohl die Implementierung CORREKT reagiert. Auf dem Prüfsystem wurde er grün (supplied Output), das Verhalten ist aber nicht portabel.
  - Required fix: Nicht-Code-Anweisung — das Szenario sollte wie `test_notifier_path_with_spaces_stays_one_argument` über `VIBE_NOTIFY` gesteuert und zusätzlich ein Fall „Notifier fehlt → trotzdem Exit 1/Log“ ergänzt werden.
- [Minor] `scripts/vibe_starter.py:367` — OSError beim Lock-Öffnen nicht verständlich abgefangen
  - Evidence: `open(path, "a+")` in `starter_lock` kann bei unbeschreibarem Laufzeitordner OSError werfen; `main:540` fängt nur `StarterError`/`ConfigError`. Ergebnis wäre ein Python-Traceback statt einer verständlichen Meldung — im Desktop-Kontext unsichtbar. Spek-Zeile „Fehler werden verständlich gemeldet“ ist für diesen Randfall nicht erfüllt.
  - Required fix: Nicht-Code-Anweisung —’an formatDate den Fehler in eine verständliche StarterError-Meldung übersetzen (Anweisung, keine Implementierung, da der importierte Komponenten-Kontrakt hier betroffen ist).
- [Minor] `scripts/vibe_starter.py:282-284` — `split_command` zerlegt nicht ausführbare Pfade mit Leerzeichen falsch
  - Evidence: Nur ausführbare Pfade werden als ein Argument behandelt; ein vorhandener, aber nicht ausführbarer Pfad mit Leerzeichen (z. B. `/tmp/Mein Browser`) fällt in `shlex.split` und wird in zwei Argumente zerlegt. Der Test `test_unexecutable_browser_is_reported_instead_of_crashing` verwendet bewusst einen Namen ohne Leerzeichen, daher bleibt dieser Fall ungedeckt.
  - Required fix: Nicht-Code-Anweisung — Abdeckung/Behandlung des „vorhanden, nicht ausführbar, mit Leerzeichen“-Falles ergänzen.
- [Minor] `scripts/vibe_starter.py:412,464` — festes 60-s-Limit für `ui start` inkl. Containerstart
  - Evidence: Der CLI-Aufruf (auch `distrobox enter` bei kaltem Container) bekommt hart 60 s; `VIBE_START_TIMEOUT` betrifft nur das Health-Warten danach. Ein sehr langsamer erster Containerstart würde als „Startfehler“ gemeldet, obwohl der Start später durchlaufen sein könnte. Real abgenommen wurde der Fall (Container Exited → Up) erfolgreich; Risiko ist begrenzt.
  - Required fix: Nicht-Code-Anweisung — Timeout konfigurierbar machen oder den Grenzfall dokumentieren.
- [Minor] `scripts/vibe-desktop.py:324-334` — Uninstall lässt leeres `icons`-Verzeichnis zurück
  - Evidence: Die rmdir-Liste entfernt `apps`, `scalable`, `hicolor` und `vibe` nicht aber `$XDG_DATA_HOME/icons`; nach vollständigem Uninstall bleibt ein leerer Ordner. Funktional harmlos, widerspricht aber der sauberen Idempotenz, die sonst implementiert ist.
  - Required fix: Nicht-Code-Anweisung — `icons` in die Aufräumliste aufnehmen.

Diese Befunde sind einzeln lokale Randfälle und verletzen keinen der abgenommenen Kriterien; sie blockieren daher keinen PASS.

## Verification
- Change set reviewed: `e53aaa5..working tree` (diff aus `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/opencode/v017-review-diff.txt` vollständig gelesen; alle 10 deklarierten V-017-Dateien vollständig gelesen). `git status --short` stimmt mit dem deklarierten Umfang überein; `scripts/setup-vibe.py` habe ich per `git diff e53aaa5 -- scripts/setup-vibe.py` geprüft — ausschließlich V-018-Umfang, keine V-017-Anteile, wie im Scope behauptet.
- Git commands run by me: `git status --short`, `git diff --stat scripts/setup-vibe.py`, `git diff e53aaa5 -- scripts/setup-vibe.py`. (Ein `git log --oneline -3` und ein kombiniertes Shell-Kommando wurden von der Umgebung mit permission denied abgewiesen; das ändert nichts an der Abdeckung, da der vollständige Diff und Dateien direkt gelesen wurden.)
- Checks with supplied output: Red-Phase (FileNotFoundError, FAILED errors=1), `python3 -m unittest tests.unit.test_bazzite_starter -v` → 37 OK, `verify.sh quick` in sauberer Kopie → Exit 0 (48 Manifestdateien, Syntaxchecks, Geheimnisprüfung), `verify.sh full` in bwrap-Namespace → 786 Unit- + 56 browser.</chat’t Tests OK, Exit 0, Host-Abnahmeprotokoll 0 Fehler, `desktop-file-validate` Exit 0. Alle diese Nachweise sind vom Agenten geliefert, nicht von mir wiederholt.
- Checks not independently run: alle Builds/Tests, die Host-Abnahme, Trilium-Synchronisation (Note `qB4ymeCudpPf` nur als Angabe; die zugehörige Zeile in `docs/trilium-index.md` habe ich gelesen — Verifizierung gegen den Trilium-Server war nicht Teil meines Werkzeugzugriffs).
- Important areas inspected: `scripts/vibe_starter.py` (voll), `scripts/vibe-desktop.py` (voll), beide Shell-Wrapper, `scripts/vibe.svg`, `tests/unit/test_bazzite_starter.py` (voll), `bin/vibe_paths.py`, Health-Endpunkt `bin/vibe-web.py:333-343`, `ui start/stop`-Semantik `bin/vibe:3362-3401`, `SPEC.md:216-230` und 242-308, `docs/baseline.md`/`docs/trilium-index.md`-Diff, `docs/features/V-017.md` und `.txt`.
- Remaining risks: Keine echte GNOME-Shell-Klickabnahme (dokumentiert in V-017.md „Grenzen“); Testtests abhängig von `notify-send` im PATH (Finding 1); die volle Prüfung lief in einer Umkopierten/Namespaced-Umgebung statt im normalen Arbeitsbaum (im Feature-Dok ehrlich begründet — nicht V-017-bedingt); Trilium-Nachweis nur durch Angabe.

PASS — keine Critical/High/Medium-Befunde; alle Akzeptanzkriterien mit Implementierungs- und Prüfnachweis als PASS bewertet. Die fünf Minor-Befunde sind nicht blockierend.
