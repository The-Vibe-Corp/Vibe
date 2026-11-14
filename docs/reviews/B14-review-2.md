# B14 — Review Runde 2

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 4
- Verdict: PASS

## Acceptance criteria

| Kriterium | Status | Implementierung (file:line) | Test / Nachweis |
|---|---|---|---|
| AK1: Live-Ausgabe vom Laufserver-Endpunkt, zweiter Abruf liefert gewachsenen Text | PASS | `bin/vibe-web.py:348` (`live_subagent_output`), `:360` (Endpunktwahl), `:984` (Handler) | `tests/unit/test_b14_subagent_output_live.py:598/633`; beide in Vollauf `/tmp/opencode/b14-full-tmpfs3.log:635-642` „ok" (von mir gelesen) |
| AK2: Loopback-URL + password_file-Kennwort; gemeinsamer Server bei gültiger Datei nicht mehr angefragt | PASS | `bin/vibe-web.py:256` (`live_endpoint` → `steer_endpoint`, `:492-516`), `:283` | `test_b14_subagent_output_live.py:679/717`; Vollauf-Log `:637-640` „ok" |
| AK3: Rückfälle ohne Serverdatei/Kennwort bewahrt | PASS | `bin/vibe-web.py:984` (Fallback auf `entry["output"]`), `:207-218` (ohne Kennwort keine Anfrage) | `test_b14_subagent_output_live.py:750/779/803`; Vollauf-Log `:649-654` „ok" |
| AK4: Defekte/fremde Serverdateien unbenutzt | PASS | `bin/vibe-web.py:492-516` (`steer_server_url`-Zwang aus B13) | `test_b14_subagent_output_live.py:834/863/914`; Vollauf-Log `:629-634` „ok" |
| AK5: Live erkannte Kind-Sessions vom Laufserver | PASS | `bin/vibe-web.py:271-283`, `:417` (`subagents_of(name)`) | `test_b14_subagent_output_live.py:949`; Vollauf-Log `:645-646` „ok" |
| AK6: Zwei Projekte, eigene Endpunkte | PASS | `bin/vibe-web.py:256-269` (pro Anfrage gelesen, kein Cache) | `test_b14_subagent_output_live.py:1001`; Vollauf-Log `:647-648` „ok" |
| AK7: Funktionsbeweis im echten Dashboard (gefordert) — Karte folgt dem 2-Sekunden-Polling, eingefrorener Ersttext erscheint nie | PASS | `bin/vibe-web.py:984` + unverändertes Frontend-Polling | `tests/browser/test_b14_subagent_output_ui.py` (2 Tests); `/tmp/opencode/b14-browser2.log:135-138` beide „ok" (echtes Dashboard + Chromium, von mir gelesen); Rotphase belegt (`b14-red-unit.log`: 13 Tests, 7 FAIL; `b14-red-browser.log`) |
| AK8: Kein Kennwort in Antworten/Protokollen | PASS | `bin/vibe-web.py:519-553` (B13-Pfad, Rückgabe ohne Kennwort) | `test_b14_subagent_output_live.py:1067`; Vollauf-Log `:643-644` „ok" |
| Manifest synchron | PASS | `docs/import-manifest.json` (B14-Eintrag + neue Größe/SHA-256 für `bin/vibe-web.py`) | Vollauf-Log Zeile 5: „OK: 60 Dateien stimmen mit docs/import-manifest.json überein."; `verify.sh quick` Exit 0 (gemeldet; Quick-Log `/tmp/opencode/b14-verify-quick.log` vorhanden) |
| Vollauf ohne B14-Regression | PASS | — | `/tmp/opencode/b14-full-tmpfs3.log`: 1766 Tests, `FAILED (failures=7, errors=1)`; Fail-Menge = 7 vorbestehende Fälle (ap04×3, setup_vibe, b4_pi_agent_dir, sandbox×2) + `test_release` als umgebungsbedingtes ERROR; Gegenprobe B13-Baseline `b13-full-run2.log` (gleiche Methode am 46ba601) gelesen; B14-Regressionsatz leer |

## Befunde

- [Minor] `docs/features/B14.md:160` — Zusammenfassung der Vollauf-Zeile leicht ungenau
  - Evidence: Das Log sagt wörtlich `FAILED (failures=7, errors=1)`; die Doku schreibt „FAILED (failures=8, als Zeilen 8 FAIL/ERROR)". Die Klammererklärung macht die gemeinte Aussage (8 Fail/ERROR-Zeilen) klar, die wörtliche Wiedergabe ist aber nicht zeilengenau.
  - Required fix: In `docs/features/B14.md` die Logzeile wörtlich zitieren oder die Paraphrase als solche kennzeichnen (z. B. „7 Failures + 1 Error = 8 Zeilen"). Reine Textkorrektur, keine Codeänderung.
- [Minor] `docs/features/B14.md:163-171` — Gegenrichtung des Baseline-Abgleichs nicht erwähnt
  - Evidence: Die B13-Baseline (`b13-full-run2.log`, `FAILED (failures=13, errors=2)`) enthält 7 weitere Fail-Zeilen, die im tmpfs3-Lauf nicht wiederkehrten (2× `test_feedback_entries` ERROR, 2× `test_f27_keep_changes`, 2× `test_project_agents.RunSelectionTest`, `test_release…source_without_git`). Das ist zugunsten des B14-Stands und Environment-bedingt, aber ein „zeilenweiser Abgleich" beider Richtungen sollte das ausweisen.
  - Required fix: In `docs/features/B14.md` eine Zeile ergänzen, die die nicht wiederkehrenden Baseline-Fälle nennt und als umgebungsbedingt einordnet. Kein Blockiergrund: keiner der Fälle betrifft B14-Code oder B14-Tests.
- [Minor] `docs/features/B14.md:153-157` — Zusammensetzung der tmpfs-Kopie unvollständig beschrieben
  - Evidence: Beschrieben ist „git archive + Arbeitskopie der zwei geänderten manifestierten Dateien". Der Lauf enthält aber auch die 13 neuen B14-Unit-Tests (Log `:629-654`, +13 gegenüber der Baseline) und die 2 B14-Browsertests (+2 im Browserlauf); die ungetrackten Testdateien müssen also ebenfalls übernommen worden sein. Der Unterschied 1766−1753 bzw. 153−151 belegt das.
  - Required fix: Die Beschreibung der Prüfkomposition um die übernommenen neuen Testdateien ergänzen, damit die Prüfmethode reproduzierbar beschrieben ist.
- [Minor] Trilium-Notiz `8wh54Pvgr8ip` — fehlerhaftes HTML-Tag im Ursachenabsatz
  - Evidence: Per MCP `get_note` gelesen; im Satz „…läuft ein Lauf … an seinem privaten Loopback-Server</b>" schließt ein `</b>` ein `<strong>`-Öffnungstag. Kosmetischer Renderfehler in der Wissensbasis, Inhalt korrekt.
  - Required fix: Beim nächsten Trilium-Update (z. B. bei der ohnehin vorgesehenen Commit-Hash-Ergänzung) das schließende Tag zu `</strong>` korrigieren.

## Verification
- Change set reviewed: `46ba601..working tree` (Branch `vibe/vibe-B14-1794644431375983103-6899-14467`); `git status --short` zeigt ausschließlich die 7 B14-Dateien (2 geänderte manifestierte Dateien, 5 neue Doku-/Testdateien) — das Runde-1-Befund-Verzeichnis `vibe-verify-svw3b2e2/` ist entfernt.
- Git commands run by me: `git status --short`, `git log --oneline -3`, `git diff 46ba601 --stat`, `git diff 46ba601 -- bin/vibe-web.py docs/import-manifest.json`.
- Checks with supplied output (Artefakte von mir selbst gelesen, nicht nur gemeldet):
  - `/tmp/opencode/b14-full-tmpfs3.log`: 1766 Tests, 8 FAIL/ERROR-Zeilen; alle 13 B14-Unit-Tests und alle `test_b11_stop_terminates_agents`-Fälle inkl. RealTmux-Stopptest „ok"; `test_b13_…test_sandboxed_run_starts_the_private_server_inside_the_sandbox` an beiden Ständen „ok" (auch `b13-full-run2.log:594-595`).
  - `/tmp/opencode/b14-browser2.log` (153 Tests, 8 FAIL + 1 ERROR) gegen `/tmp/opencode/b14-browser-base.log` (151 Tests, 8 FAIL + 1 ERROR): die 9 Fail-Zeilen sind identisch (Kosten-/AP7-/AP8-/F27-/Fritz-UI); B14-Browsertests grün — der geforderte Funktionsbeweis.
  - Rotphasen-Logs `b14-red-unit.log` (13 Tests, 7 FAIL) und `b14-red-browser.log` vorhanden; Testbericht-Nachtrag und `docs/features/B14.md` decken sich mit den Logs.
  - Runde-1-Reproduktion des Release-Tests in der echten Arbeitskopie (Shell-Artefakt `sh_1d96ea836…out`: „First list contains 10 additional elements", Ersttreffer `docs/features/B4.md:15`) konsistent zur Doku.
  - Trilium per MCP (`get_note`): Notiz `8wh54Pvgr8ip`, Titel „B14 Subagenten output statisch — Live-Ausgabe über den privaten Laufserver", Elternnotiz `IjRpjYJTtqam` (projektgleich mit B13), Inhalt vollständig und ehrlich (Commit-Hash als nach Abschlusscommit nachzutragend gekennzeichnet, „B14-review-2.md — folgt").
- Checks not independently run: alle Builds/Tests selbst nicht ausgeführt (Review-Rolle); `verify.sh quick`/`full` nur über die genannten Artefakte belegt.
- Implementierungsdiff geprüft: Änderung beschränkt sich auf Endpunktwahl (`opencode_request`-Parameter, `live_endpoint`, Durchreichung des Projektnamens); Wiederverwendung der B13-Loopback-Validierung, kein Cache, kein Kennwortabfluss, keine Kopplung an tmux-/Lebenszyklus-Code, keine Abschwächung bestehender Fallbacks.
- Remaining risks: Der Einzelnachweis „b11-Stopp-Test am unveränderten Ausgangsstand OK" stützt sich auf ein Shell-Artefakt („Ran 1 test … OK", exakter Testdokstring), das den Ausführungspfad/Stand nicht selbst protokolliert; die Einordnung als Umgebungsproblem ist aber unabhängig davon durch den grünen tmpfs-Vollauf am B14-Stand getragen. Der Abschlusscommit (inkl. FEEDBACK.md-Häkchen, Commit-Hash in Trilium/FEEDBACK) steht gemäß Arbeitsablauf noch aus und ist nach diesem PASS zu leisten; danach sind die vier Minor-Korrekturen im Rahmen der ohnehin fälligen Doku-Updates einzuarbeiten.

Verdict: PASS
