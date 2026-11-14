# Review-Ergebnis

## Zusammenfassung
- Kritisch: 0
- Hoch: 0
- Mittel: 0
- Klein: 2
- Urteil: PASS (Minors blockieren nicht)

## Akzeptanzkriterien
| Kriterium | Status | Implementierung (Datei:Zeile) | Test / Nachweis |
|---|---|---|---|
| Dashboard beenden stoppt weder Agentenläufe noch opencode | PASS | `bin/vibe:2731-2739` (ui stop beendet nur `vibe-ui`-Sitzung, vorher `session_owned (…, "ui")`); `bin/vibe-web.py:561-566` (`/api/shutdown` baut Prozess sauber ab) | `tests/unit/test_lifecycle.py:566` `test_shutdown_ends_streams_and_keeps_run_and_opencode`, `:582` `test_dashboard_stop_command_keeps_run_and_opencode`, `:610` `test_restart_keeps_run_and_opencode`; grün laut gelieferter Ausgabe (`Ran 17 tests … OK`) |
| opencode stoppen beendet nicht vibe | PASS | `bin/vibe:2718-2724` (stop beendet nur die Sitzung nach `session_owned (…, "server")`) | `tests/unit/test_lifecycle.py:590` `test_opencode_stop_keeps_dashboard_and_run` (Dashboard-Sitzung, Lauf und `/api/health` bleiben), `test_every_combination_of_running_processes` |
| Nur verwaltete Prozesse werden beendet | PASS | `bin/vibe:151-171` (`session_marker`/`session_owned`, `VIBE_MANAGED`), `:1101-1110` (`cmd_stop` verlangt Marker `"run"` bzw. Toleranz bei Registereintrag), `:2701-2705`/`:2749-2753` (Start verweigert fremde Sitzung), `:124-128` (`run_key` reserviert `ui`/`server`) | `test_foreign_sessions_with_the_same_name_are_not_stopped` (`:371`, auch mit Registereintrag), `test_start_refuses_a_foreign_tmux_session` (`:394`), `test_projects_named_ui_or_server_do_not_use_their_sessions` (`:408`) |
| Aktive Streams und Hintergrundthreads sauber behandelt | PASS | `bin/vibe-web.py:205-223` (`shutdown_server` im Eigenen Thread), `:219-228` (`request_stop`-Signalhandler), `:587-603` (Stream prüft `STOP`, letzte Zeile, `close_connection`), `:1185-1199` (`daemon_threads=False`, Signalhandler, `server_close`, Exitpfad) | `test_shutdown_ends_streams_and_keeps_run_and_opencode`, `test_sigterm_ends_streams_cleanly` (`:625`, Exitcode 0 + letzte Stream-Zeile), `test_closed_browser_tab_keeps_dashboard_and_run_alive` (`:599`) |
| Ticket-Tests: alle Kombinationen laufender Prozesse | PASS | — | `test_every_combination_of_running_processes` (`:331`): 24 subTests (8 Zustandsmengen × 3 Ziele) |
| Ticket-Tests: Neustart | PASS | — | `test_restart_keeps_run_and_opencode` (`:610`): neue Instanzkennung, Lauf und opencode bleiben |
| Ticket-Tests: belegter Port | PASS | `bin/vibe:173-179` (`port_in_use`), `:188-211` (`dashboard_health` mit App- und Instanzprüfung), `:2670-2689` (`server_health` verlangt `healthy:true` + Version) | `test_dashboard_start_refuses_a_foreign_service_on_its_port` (`:511`), `test_dashboard_start_refuses_a_foreign_vibe_lookalike` (`:520`), `test_opencode_start_refuses_a_foreign_service_on_its_port` (`:533`), `test_opencode_status_requires_a_healthy_opencode_answer` (`:542`) |
| Ticket-Tests: Browser-Tab schließen | PASS | `bin/vibe-web.py:587-603` (`BrokenPipe`/`ConnectionReset` nur lokal behandelt) | `test_closed_browser_tab_keeps_dashboard_and_run_alive` (`:599`) |
| Ticket-Tests: Beenden während eines aktiven Agentenlaufs | PASS | Registry/Dashboard sind entkoppelt; `cmd_stop` tut beides nicht | Dashboard-Tests laufen setUp-seitig immer mit aktivem Lauf + Registereintrag (`start_run`, `:224-238`); Shutdown-Tests prüfen, dass Aufzeichnung und Lauf-Sitzung erhalten bleiben |

Projektregeln: TDD mit Rot-Phase (vom Coding-Agenten belegt, plausibel und verhaltensspezifisch, nicht umgebungsbedingt), echte Assertions und keine Skips in `test_lifecycle.py` (geprüft per Grep), keine Abschwächung: Anpassungen in `test_opencode_adapter.py:480-524` und `test_vibe_paths.py:786-806` sind notwendige Anpassungen an die neue Marker-Prüfung und behalten die ursprünglichen Assertion-Ziele. Die UI erklärt die Unterscheidung (Quit-Button-Text: „beendet diese App (das Dashboard), nicht opencode“ / „Laufende Agentenläufe in tmux laufen weiter.“, `bin/vibe-web.py:686`) und erfüllt damit `SPEC.md:209`. Das Dokument `docs/features/V-016.md` ist vollständig mit Umfang und Grenzen; Trilium (`hv8eqCTudXhH` unter `IjRpjYJTtqam`) von mir mit get_note/list_children_notes verifiziert, ID korrekt in `docs/trilium-index.md`.

## Befunde
- [Klein] `bin/vibe:151-171`, `docs/features/V-016.md` (Abschnitt „Grenzen") — Marker ist nicht instanzgebunden
  - Nachweis: `VIBE_MANAGED` speichert nur die Art (`ui`/`server`/`run`), nirgendwo eine Instanz-/Laufzeitkennung. Zwei vibe-Installationen mit demselben Profil erzeugen denselben Sitzungsnamen ("vibe-server"); `server stop` beendet dann auch die Sitzung der anderen Instanz, obwohl sie dort „verwaltet“ ist. Das Dashboard ist über die Instanzprüfung geschützt, diese Lücke ist in „Grenzen“ nur für manuell gefälschte Marker (`forge Marker`) beschrieben, nicht für eine parallele zweite vibe-Instanz.
  - Erforderliche Korrektur (nur Dokumentation): den instanzübergreifenden Aspekt der Vertrauensgrenze in `docs/features/V-016.md` „Grenzen“ ergänzen (auch die Trilium-Notiz sync halten). Keine Codeänderung erforderlich.
- [Klein] `tests/unit` Nachweisumfang — `verify.sh full` lief vor dem letzten Minimalstand (Standardargument `cmd_server`, Manifest-Prüfsummen)
  - Nachweis: laut gelieferter Ausgabe lief `full` (691 Tests) vor der letzten Änderung; nur `quick` und die 17-Testpakete liefen exakt auf dem finalen Stand. Die ausgelieferte Änderung betrifft kein getestetes Verhalten (Standard-Arg nur bei Aufrufen ohne `action`, Prüfsummen), aber der Abnahmelauf deckt den finalen Baum nicht 1:1 ab.
  - Erforderliche Korrektur (keine Codeänderung): vor dem Abschlusscommit `verify.sh full` einmal auf dem exakten finalen Arbeitsstand wiederholen und das Ergebnis dokumentieren.

## Verifizierung
- Überprüfter Änderungssatz: `ec00695.. Arbeitsbaum` (Branch `feature/v-016-lebenszyklus`), gelesen über `git status --short` und den gelieferten Gesamtdiff (1368 Zeilen vollständig). Eine wiederholte Git-Diff-Probe wurde durch die她 Rechte-Sperre verweigert („Permission denied: shell"); der Abgleich Diff ↔ Arbeitsbaum erfolgte stattdessen durch direkte Leseprüfung aller betr. Stellen (`bin/vibe`, `bin/vibe-web.py`, Tests, Manifest, Docs) — konsistent.
- Git-Befehle von mir: nur `git status --short` (+ Branch/Log-Abfrage). Getestet wurde nichts.
- Vorhandene Prüfergebnisse: Rot-Phase `Ran 5 … FAILED (failures=6, errors=1)` inkl. beobachteter Einzelfehler; Grün-Phase `Ran 17 tests … OK`; `verify.sh quick` Exit 0 auf finalen Stand; `verify.sh full` Exit 0 (vor letztem Minimalstand, im Mount-Namespace). Alle vom Coding-Agenten geliefert, von mir nicht ausgeführt.
- Unabhängig nicht ausgeführt: alle Build-/Testläufe, Rot-Phase-Wiederholung, `verify.sh`.
- Wichtig geprüfte Bereiche: `bin/vibe` (Marker-, Port-, Health- und Stop-Pfade, reservierte `run_key`), `bin/vibe-web.py` (Stop-Ablauf, SSE, Signals, Threads), `tests/unit/test_lifecycle.py`, `test_opencode_adapter.py`, `test_vibe_paths.py`, `docs/import-manifest.json`, `docs/features/V-016.md`, `docs/trilium-index.md`, Trilium-Notiz, Übereinstimmung mit `SPEC.md` (Zeilen 202-210).
- Verbleibende Risiken: Marker-Vertrauensgrenzen innerhalb desselben Benutzers inkl. zweiter Instanz (dokumentiert / Minor); Snapshot-Risiko zwischen Portprüfung und Start (in „Grenzen“ dokumentiert); keine Browser-/End-to-End-Prüfung außer den suppestierten Unit-Tests.

PASS
