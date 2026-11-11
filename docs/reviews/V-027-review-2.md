# Review result (Runde 2)

## Kurzfazit

Alle vier Befunde aus Runde 1 sind korrekt behandelt. Der Reconnect-Ausschluss für Quota/Auth ist vollständig (auch die manuelle IP-Abfrage ist ausgeklammert), das Wiederholungslimit bleibt wirksam, die beiden neuen Tests prüfen den Ausschluss verhaltensbasiert (Aufrufmarkierung + Ausgabemarker) und sind gegen die Attrappe nicht aushebelbar, `cmd_stop` erhält Zustand/Notiz ohne Regression für normale Stopps, und die Setup-Semantik ist nun konservativ korrekt ohne Fehlblockade bei Exitcode 1. Bestehende Tests wurden nicht abgeschwächt; Doku/SPEC/README stimmen mit dem Verhalten überein. Verbleibt ein Minor-Befund: Die Prüf-/Testzählungen in `docs/features/V-027.md` (und die Testzahl in V-026.md-Kontext) nennen weiterhin „14 Tests" / „1527 tests", tatsächlich sind es nach den zwei neuen Regressionstests 16 bzw. 1529, und die neuen Tests fehlen in der Abdeckungsliste.

## Prüfung der Korrekturen

1. **Reconnect-Ausschluss vollständig:** `bin/vibe-run.sh:776–786` — `fritz auto` und die manuelle IP-Abfrage (`read -r -p "Neue IP manuell anfordern…"`) stehen jetzt beide unter `if [ "$CLASS" != "quota" ] && [ "$CLASS" != "auth" ]`. Ein Umgehungspfad existiert nicht: `grep` über `vibe-run.sh` zeigt, dass `$BIN/vibe` ausschließlich an dieser Stelle (Zeile 783) aufgerufen wird; andere Reconnect-Aufrufe gibt es im Läufer nicht. Das Wiederhollimit bleibt wirksam: die Prüfung `ATTEMPT -ge $TRIES_PER_ITEM` (Zeile 794) liegt nach dem Gate und wird von Quota/Auth durchlaufen; die neuen Tests fordern exakt 2 opencode-Aufrufe bei `MAX_RETRIES=1`. Im Modus `stop` ist der Pfad unverändert (sofortige Blockade, Tests bestehen laut Agentenangabe weiterhin).

2. **Neue Tests prüfen den Ausschluss wirklich:** `tests/unit/test_v027_limits.py:415–482`. Die Attrappe `install_vibe_probe` ersetzt die installierte `$INSTALL/bin/vibe` durch eine beobachtende Variante, die **jeden** Aufruf mit Argumenten in `vibe.calls` markiert. `assert_no_router_reconnect` verlangt (a) keine Zeile mit `fritz auto` in der Markierungsdatei und (b) das Fehlen aller vier Ausgabemarker (`zentraler reconnect`, `neue ip manuell anfordern`, `keine neue ip angefordert`, `fritzbox-automatik`) in stdout/stderr/Protokoll. Damit ist die Prüfung doppelt abgesichert: Selbst wenn die Attrappe keine Datei schreiben könnte, würde der Exit-3-Pfad den Marker „Fritzbox-Automatik ist aus" ins Protokoll schreiben. Nicht aushebelbar über PATH, weil der Läufer `$BIN/vibe` absolut adressiert; andere `$BIN/vibe`-Aufrufe im Läuferfluss existieren nicht. Beide Tests prüfen zusätzlich die korrekte Wiederholung (2 Aufrufe) und den `HINWEIS`-Eintrag, also die Kombination „retry ja, Reconnect nein". Die angegebene Rotphase (Schutz mit `if true` ersetzt → `FAILED (failures=2)` mit „keine neue ip angefordert") ist in sich stimmig; die temporäre Kopie ist laut `git status` entfernt (keine Zusatzdateien im Arbeitsbaum).

3. **`cmd_stop` mit `only_live`:** `bin/vibe:2135–2140` und `2148–2153` — beide Abschlussbuchungen sind jetzt `only_live=True`. Normaler Stopp eines lebenden Laufs: `running` ∈ `LIVE_STATES`, der Eintrag wird regulär auf `stopped` gesetzt (bestehender Test `test_stop_kills_the_session_on_its_own_socket` asserting `stopped` läuft weiterhin grün). Hat der Signalhandler bereits `ended` + Notiz geschrieben, bleibt der Eintrag unverändert; der einzige kosmetische Rest ist, dass `cmd_stop` „Beendet:" ausgibt, obwohl es nur das Sitzungs-Kill ausführte und den Registereintrag nicht änderte — irreführend wäre nur „nichts beendet", das nicht behauptet wird. Keine Zustands- oder Notizverlustrisiken mehr; kein Downgrade möglich, weil `only_live` beendete Einträge grundsätzlich sperrt. Der umgekehrte Fall (Stopp gewinnt zuerst → `stopped`, danach Signalhandler) bleibt durch `only_live` im Handler ebenfalls geschützt.

4. **`setup-vibe.py`-Semantik:** `scripts/setup-vibe.py:1036–1045` — jetzt `0 → True`, `1 → False`, jeder andere Exitcode sowie fehlender `returncode` und Subprocess-Fehler → `None` (konservative Sperre). Exitcode 1 (Sitzung fehlt, inkl. „no server running" beim eigenen Socket) führt zu `False` → Sperre wird **nicht** falsch ausgelöst; ein unerwarteter Fehler blockiert konservativ. Passt zu Docstring (Zeilen 1019–1025) und Kopfkommentar (Zeile 1012) sowie zur vereinheitlichten Semantik in `bin/vibe:279–287` und `bin/vibe_runs.py:614–638` (Doku in `docs/features/V-026.md:144–145`).

5. **Keine Testschwächung:** Der vollständige `git diff c6b2a6c -- tests/` ist unverändert gegenüber Runde 1 — ausschließlich sterile Socket-Anpassungen von Attrappen und Teardowns, das neue `hang`-Mode in `runner_support.py` (reines Schlaf-Stub für die Signaltests), `vibe_limits.py` in den Programmdateilisten. Keine entfernten oder gelockerten Assertions, keine Skip-Marker, keine catch-all-Handler. Die neuen V-027-Tests sind additive Erweiterungen (16 statt 14 Fälle), Bestandstests blieben inhaltlich identisch.

6. **Doku-Konsistenz:** SPEC.md („Quota- und Anmeldefehler lösen weder eine Router-Neuverbindung noch eine manuelle IP-Abfrage aus.") und `docs/features/V-027.md:36–41, 62–65` beschreiben exakt das implementierte Verhalten; der Widerspruch aus Runde 1 ist behoben. README.md behauptet nur noch „keine Dienstlimits umgangen, keine unbegrenzten Wiederholungen" — korrekt und nicht widersprüchlich. `docs/features/V-026.md` dokumentiert die beiden bekannten Wettlauffenster und die Begründung der dreifachen Sitzungsprüfung einschließlich der einheitlichen Exitcode-Semantik (Zeilen 132–145) — deckt sich mit Runde-1-Low-Befunden, die bewusst per KISS-Entscheidung als dokumentierte Grenzen belassen wurden; das ist eine vertretbare, nachvollziehbare Begründung.

## Findings

- [Minor] `docs/features/V-027.md:74, 86, 91` — veraltete Test- und Prüfungszählungen
  - Evidence: Die Tests-/Prüfungen-Abschnitte nennen weiterhin „14 Tests" bzw. „Ran 14 tests" und „Ran 1527 tests"; nach den zwei neuen Regressionstests (`test_continue_quota/auth_does_not_trigger_a_router_reconnect`) sind es 16 bzw. 1529. Die beiden neuen Fälle fehlen zudem in der Abdeckungsliste (Zeilen 77–81). `docs/features/V-026.md` (Zeilen 105, 118) nennt denselben veralteten Gesamtstand.
  - Required fix: Zahlen auf 16/1529 aktualisieren und die beiden Reconnect-Regressionstests in die Abdeckungsliste aufnehmen. Rein dokumentarisch, nicht blockierend.

- No other findings.

## Akzeptanzkriterien (Restprüfung nach Korrekturen)

| Kriterium | Status | Beleg |
|---|---|---|
| Keine Router-Neuverbindung/manuelle IP-Abfrage durch Quota/Auth (auch in `continue`) | PASS | `bin/vibe-run.sh:776–786`; Tests `test_continue_quota/auth_does_not_trigger_a_router_reconnect` (Agentenangabe: Ran 16, OK) |
| Wiederhollimit wirksam bei `continue` | PASS | `bin/vibe-run.sh:794`; `assert_continue_without_reconnect` verlangt exakt 2 Aufrufe |
| `vibe stop` erhält Signalnotiz/`ended` | PASS | `bin/vibe:2135–2153` mit `only_live`; bestehender Stopp-Test grün (Agentenangabe) |
| Setup-Sperre: konservativ, kein Fehlblock bei Exit 1 | PASS | `scripts/setup-vibe.py:1036–1045`; test_setup_vibe 49 OK (Agentenangabe) |
| Alle übrigen Kriterien aus Runde 1 | PASS (unverändert) | siehe Runde-1-Tabelle; Changeset sonst unverändert |

## Verifikation
- Change set reviewed: `c6b2a6c..working tree`; `git status --short` (identisch zu Runde 1, keine Restartefakte der Rotphase), vollständige Diffs zu `bin/vibe-run.sh`, `bin/vibe`, `scripts/setup-vibe.py`, `SPEC.md`, `README.md`, `tests/`; vollständige Lesezugriffe auf die neuen Testabschnitte (`test_v027_limits.py:92–103, 415–482`), `docs/features/V-027.md`, `docs/features/V-026.md` (Grenzen), Greps zur Reconnect-Pfadvollständigkeit.
- Git commands run by me: ausschließlich lesende (`git status --short`, `git diff c6b2a6c -- <Dateien>`); keine Dateien geändert.
- Checks with supplied output: unittest-Ergebnisse (16/18 OK, Regressionsmodule OK, Manifest OK, quick Exit 0, full 1529/2 vorbestehend) — Agentenangaben, von mir nicht ausgeführt.
- Checks not independently run: alle Test- und Verify-Läufe.
- Remaining risks: Testherkunft erneut nur über Sitzungsangaben belegbar; die beiden vorbestehenden `verify.sh full`-Fehler bleiben Agentenangabe; `verify.sh full` bleibt mit den zwei dokumentierten Altlasten auf Exit 5 — für die Abnahme dieser Pakete unschädlich, da unverändert zum Ausgangscommit.

## Verdict

**Verdict: PASS**

Keine Critical-, High- oder Medium-Befunde; der einzelne Minor-Befund (Dokumentzählungen) blockiert nicht. Die für Runde 1 festgestellte dokumentarische Nachbesserung der Testzahlen sollte vor dem Abschlusscommit nachgezogen werden, da `AGENTS.md` aktuelle Dokumentation verlangt — sie rechtfertigt jedoch keine neue Reviewrunde der Implementierung.
