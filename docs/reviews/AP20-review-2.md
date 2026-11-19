# Reviewantwort AP20 — Runde 2 (Finalreview)

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-19.
Geprüfter Umfang: finaler Stand im Paket-Worktree `vibe-AP20-yBZNBt`, Branch
`feature/m0p/ap20-2`, Basis `20d1719`, inklusive der Reviewfixes aus Runde 1.
Der Reviewer konnte die Datei wegen seiner read-only-Werkzeugbeschränkung
nicht selbst anlegen; der Text ist wörtlich übernommen (bis auf diesen Kopfkasten).
Tests und Hashprüfungen waren dem Reviewer nicht gestattet; die geprüften
Rohausgaben stammen aus `docs/reviews/AP20-test-agent-report.md` Abschnitt 10.

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 4
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1 Bestand B11/F30 bleibt erhalten (Panel, sieben Ansichten, Zielauswahl, Anweisung, Senden/Fortsetzen, Highlighter, Kartenvergrößerung, kein Modal/Tablist) | PASS | `bin/web/app.js:504-683`, `bin/web/styles.css:37-78` | `tests/browser/test_ap20_output_overview_ui.py::ContractTest::test_b11_f30_contract_remains_with_six_subagents`; gelieferte Rohausgabe 12/12 OK (Testbericht §10), Regression 20/20 OK |
| AK2 Kompakte Übersicht aller aktiven Agenten inklusive Hauptsession, Zähler, Status, Fokus-Knopf; Leerzustand und Beendigung | PASS | `bin/web/app.js:516-520,606-636` | `::OverviewTest::test_overview_lists_all_agents_with_compact_rows`, `::OverviewTest::test_finished_subagent_leaves_overview_and_view`, `::FocusModeTest::test_zero_running_subagents_shows_empty_overview`; gelieferte Rohausgabe 12/12 OK |
| AK3 Höchstens ein panelweiter Scrollbereich im Normalmodus, keine verschachtelten Scrollbars bei 1400 px und 900 px | PASS | `bin/web/styles.css:42,56-57,70,76-78` | `::ScrollbarTest::test_normal_mode_has_no_nested_scrollbars_at_1400`, `::ScrollbarTest::test_narrow_viewport_has_no_horizontal_overflow_at_900`; gelieferte Rohausgabe 12/12 OK |
| AK4 Umbrechendes Kartenraster innerhalb der Panelbreite | PASS | `bin/web/styles.css:70-72` | `::GridTest::test_subagent_cards_wrap_into_rows_within_the_panel`; gelieferte Rohausgabe 12/12 OK |
| AK5 Geteilter Fokus über Übersicht, Karte und Hauptkopf; Escape und zweiter Klick; `aria-expanded`; genau ein Scrollbereich; Live-Aktualisierung | PASS | `bin/web/app.js:510,551-568,555,652`; `bin/web/styles.css:76-78` | `::FocusModeTest::test_overview_focus_enlarges_one_card_and_unlocks_scroll`, `::test_second_focus_click_restores_normal_mode`, `::test_card_button_and_overview_focus_share_the_same_state`, `::test_main_agent_header_focus_button_enlarges_main_view`; gelieferte Rohausgabe 12/12 OK; Mutationsläufe Haupt-Handler (§6.2) und Escape (§6.3) plausibel |
| AK6 Fokus bleibt bei Live-Updates und Hauptsession-Wechsel konsistent, keine verwaisten Zeilen/Doppelungen | PASS | `bin/web/app.js:610,638` | `::FocusModeTest::test_session_switch_with_active_focus_keeps_no_orphan_state`; gelieferte Rohausgabe 12/12 OK. Einschränkung: Die Reset-Zweige für fokussierten Hauptagenten bzw. entfernten Subagenten sind nur per Code-Inspektion belegt, siehe Minor 3 |
| AK7 Nachweise: Screenshot echt, Manifest-Eintrag valide, Doku/Baseline plausibel, keine neue Abhängigkeit | PASS | `docs/import-manifest.json:991-1000,1114-1126`, `docs/features/AP20.md`, `docs/baseline.md:296`, `docs/features/AP20-ausgabe.png` | Screenshot selbst gesichtet (1400×900, sechs Subagenten, Hauptzeile, „Fokus“-Knöpfe); gelieferte Ausgaben: Manifest `OK: 57 Dateien`, Syntax, Secrets, `node --check`, `verify.sh quick --project` Exit 0, `git diff --check` Exit 0. Hashes nicht unabhängig nachgerechnet |

## Findings
- [Minor] `docs/features/AP20.md:61` — Leerzustand der Übersicht falsch dokumentiert
  - Evidence: Die Doku behauptet „Bei keinem aktiven Agenten erscheint „Keine aktiven Agenten.“.“ Der Code setzt den Text auf „Keine laufenden Subagenten.“ (`bin/web/app.js:519`) und blendet ihn nur bei `subs.length>0` aus (`bin/web/app.js:636`); die Hauptzeile bleibt ohne Subagenten stehen, wie `test_zero_running_subagents_shows_empty_overview` ausdrücklich erwartet. Damit stimmen weder Text noch Bedingung mit der Implementierung überein.
  - Required fix: Den Satz auf den tatsächlichen Leerzustand korrigieren: sichtbar nur ohne laufende Subagenten, Text „Keine laufenden Subagenten.“, Hauptzeile bleibt bestehen.
- [Minor] `TICKETS.md:1066` / `docs/features/AP20.md:114` — Ticketstatus noch offen, Doku behauptet Abschluss
  - Evidence: `TICKETS.md:1066` führt weiterhin `- [ ] AP20`; `docs/features/AP20.md:114` listet „TICKETS.md | AP20 auf `[x]` mit Commit/Test“. Der Arbeitsbaum enthält zudem noch keinen Paket-Commit (`git status` zeigt nur Änderungen/Untracked-Dateien).
  - Required fix: AP20 im Abschluss auf `[x]` mit Commit und Test setzen oder die Doku auf den offenen Stand korrigieren; den Paketcommit vor Abschluss ausführen.
- [Minor] `tests/browser/test_ap20_output_overview_ui.py:1494-1564` — Sessionwechsel-Test prüft den verwaisten Haupt-Fokus nicht
  - Evidence: Der Test fokussiert Subagent A (`:1511`) und wechselt anschließend die Hauptsession. Die Reset-Bedingung `focusedSession!==session&&!children.has(focusedSession)` (`bin/web/app.js:610`) wird dabei nicht ausgelöst, weil A weiterhin in `children` liegt. Die Assertion `assertFalse(self.is_main_enlarged())` (`:1539-1541`) ist im Szenario nicht aussagekräftig, weil die Hauptansicht nie fokussiert war; ein Entfernen von `bin/web/app.js:610` bliebe für die Suite grün. Auch der Reset beim Entfernen eines fokussierten Subagenten (`bin/web/app.js:638`) wird nicht ausgelöst: `test_finished_subagent_leaves_overview_and_view` (`:968-1002`) setzt keinen Fokus.
  - Required fix: Je einen Test ergänzen: Haupt-Fokus setzen → Hauptsession wechseln → `enlarged`/`bv-focusing`/Scrollbereich prüfen; Subagent fokussieren → `completed` → Fokus/`bv-focusing`/Scrollbereich prüfen.
- [Minor] `tests/browser/test_ap20_output_overview_ui.py:1301-1307` — Ersatzpfad beim Karten-Knopf „Verkleinern“
  - Evidence: Wird der Knopf mit sichtbarem Text „Verkleinern“ nicht gefunden, klickt der Test ersatzweise `card_button` und führt danach dieselben Zustandsassertions aus. Ein Fehler, bei dem der Karten-Knopf seinen sichtbaren Text nicht auf „Verkleinern“ umstellt, wird dadurch nicht rot, obwohl der Test genau diesen Pfad behauptet. Die geteilte Fokus-Zustandslogik selbst wird weiterhin geprüft; es handelt sich nicht um einen Handler-Ersatz wie in Runde 1.
  - Required fix: Den Knopf über sichtbaren Text und `aria-label` eindeutig lokalisieren, den Ersatzpfad entfernen und Beschriftung sowie `aria-expanded` explizit assertieren.

## Verification
- Change set reviewed: `20d1719..Arbeitskopie` im Worktree `vibe-AP20-yBZNBt` (Branch `feature/m0p/ap20-2`), inklusive der untracked Dateien `tests/browser/test_ap20_output_overview_ui.py`, `docs/features/AP20.md`, `docs/features/AP20-ausgabe.png`, `docs/reviews/AP20-test-agent-report.md` und `docs/reviews/AP20-review-1.md`.
- Git commands run by me: `git status --short`, `git diff --stat 20d1719`, `git diff 20d1719 -- bin/web/app.js`, `git diff 20d1719 -- bin/web/styles.css`, `git diff 20d1719 -- docs/import-manifest.json docs/baseline.md`. Weitere Git-Unterbefehle (`git branch --show-current`, `git log`, `git hash-object`, `git ls-files | grep`) wurden durch die Berechtigungsprüfung abgelehnt.
- Checks with supplied output: 12/12 AP20 (Rohausgabe in `docs/reviews/AP20-test-agent-report.md` §10), 20/20 Regressionen, Manifest `OK: 57 Dateien`, Syntaxprüfung, Secret-Prüfung, `node --check`, `verify.sh quick --project` Exit 0, `git diff --check` Exit 0; Rotphase 7/8 Fehlschläge auf Basis `20d1719` (§5) und Mutationsnachweise Haupt-Handler (§6.2) und Escape (§6.3) liegen als Ausgabe vor. Diese Ausgaben wurden vom Test-Agenten/Koordinator geliefert, nicht von mir ausgeführt.
- Checks not independently run: Alle Build-, Test-, Hash- und Verifikationsläufe (`unittest`/Playwright, `sha256sum`, `scripts/check-*`, `verify.sh`, `node --check`). Die Manifest-Hashes habe ich nicht nachgerechnet.
- Important areas inspected: `bin/web/app.js` (`outputView` 504-683), `bin/web/styles.css:37-78`, `tests/browser/test_ap20_output_overview_ui.py` (12 Fälle, Escape-Pfad 1214-1237, Haupt-Fokus 1377-1492, Sessionwechsel 1494-1564, Leerzustand 1566-1626), `docs/features/AP20.md`, `docs/reviews/AP20-test-agent-report.md`, `docs/reviews/AP20-review-1.md`, `docs/import-manifest.json:991-1000,1114-1126`, `docs/baseline.md:296`, `docs/features/AP20-ausgabe.png` (Bild gesichtet), bestehende Suiten `test_b11_output_ui.py`, `test_f30_subagent_view_ui.py`, `test_b14_subagent_output_ui.py`, `test_ap16_syntax_highlighting_ui.py`.
- Remaining risks: Manifest-Hashes und Größen sind nur über die gelieferte Prüfausgabe bestätigt; der `title`-Tooltip (`bin/web/app.js:624`) ist nur per Code-Inspektion belegt und wird von keinem automatisierten Test geprüft; die Fokus-Reset-Zweige für Hauptsession-Wechsel und Entfernen eines fokussierten Subagenten sind nicht eigenständig getestet (Minor 3); AP20 ist in `TICKETS.md` noch offen und der Arbeitsbaum noch nicht committet.
