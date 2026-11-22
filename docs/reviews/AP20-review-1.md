# Reviewantwort AP20 — Runde 1

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-19.
Geprüfter Umfang: `20d1719..Arbeitsbaum` im Paket-Worktree
`vibe-AP20-yBZNBt`, Branch `feature/m0p/ap20-2` (inklusive der unversionierten
AP20-Dateien). Der Reviewer konnte die Datei wegen seiner read-only-Werkzeugbeschränkung
nicht selbst anlegen; der Text ist wörtlich übernommen (bis auf diesen Kopfkasten).
Ausführung von Tests/Hashprüfungen war dem Reviewer nicht gestattet; die von ihm
geprüften Nachweise sind entsprechend gekennzeichnet.

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 3
- Minor: 2
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1 Bestand B11/F30 bleibt erhalten (Zielauswahl, Anweisung, Senden/Fortsetzen, Highlighter, Vergrößerung) | PASS | `bin/web/app.js:504-674` (outputView unverändert im Vertrag), `bin/web/styles.css:41-78` | `tests/browser/test_ap20_output_overview_ui.py::test_b11_f30_contract_remains_with_six_subagents`; Rotphase: 7/8 Fehlschläge auf Basis `20d1719`, u. a. `scrollWidth=3400`, Karte rechts 1764 |
| AK2 Kompakte Übersicht aller aktiven Agenten (Hauptsession + laufende Subagenten) | PASS | `bin/web/app.js:516-520, 577-584, 611-626` | `test_overview_lists_all_agents_with_compact_rows`, `test_finished_subagent_leaves_overview_and_view` |
| AK3 Ein einziger panelweiter Scrollbereich im Normalmodus (keine verschachtelten Scrollbars bei 1400 px) | PASS | `bin/web/styles.css:41-78` (`.bv-log` overflow), `bin/web/app.js:504-674` | `test_normal_mode_has_no_nested_scrollbars_at_1400` |
| AK4 Kartenraster bricht bei 900 px ohne horizontalen Überlauf um | PASS | `bin/web/styles.css:41-78` | `test_narrow_viewport_has_no_horizontal_overflow_at_900`, `test_subagent_cards_wrap_into_rows_within_the_panel` |
| AK5 Geteilter Fokus-Modus: Kartenknopf, Übersichts-Fokus und Hauptagenten-Fokus teilen Zustand; Escape und/oder zweiter Klick heben Fokus auf; Scrollbar-/`aria-expanded`-Verhalten | FAIL | `bin/web/app.js:510` (Haupt-Fokus-Knopf ohne Klick-Handler), `551-564`, `643`; Übersicht `583` | `test_overview_focus_enlarges_one_card_and_unlocks_scroll` und `test_card_button_and_overview_focus_share_the_same_state` belegen nur Subagenten-Fokus. Escape wird in `tests/browser/test_ap20_output_overview_ui.py:1101-1108` durch Fallback-Klick ersetzt und damit nicht eigenständig geprüft. Hauptagenten-Fokus und `aria-expanded` sind in der gesamten Testdatei nicht abgedeckt (kein `aria-expanded`-Treffer). |
| AK6 Fokus bleibt bei Live-Updates und Sessionwechsel konsistent (kein verwaister Fokus) | PASS | `bin/web/app.js:593-643` (`sync`, Sessionwechsel-Fokus-Reset 606, 629) | `test_overview_focus_enlarges_one_card_and_unlocks_scroll` (Live-Marker in fokussierter Karte); Sessionwechsel nur per Code-Inspektion, nicht eigenständig getestet |
| AK7 Nachweise: Screenshot echt, Manifest-Eintrag valide, `verify.sh quick` Exit 3 plausibel dokumentiert | NOT VERIFIED | `docs/import-manifest.json:991-999`, Hashes `1113-1126`, 57 Dateien; `docs/features/AP20-ausgabe.png` (1400×900, sechs Subagenten `testerA`–`testerF`); `.gitignore:18`, `scripts/verify.py:50,152-159`, `docs/features/AP20.md:141-144` | Screenshot und Manifest inhaltlich plausibel, aber Manifest-Hashes nicht nachgerechnet (keine Ausführung erlaubt). Exit-3-Ursache (fehlende `.vibe/project.env`) ist durch Code und Doku belegt. Grüne Läufe 8/8 bzw. 20/20 nur als Behauptung in `docs/features/AP20.md:131,135`; rohe Ausgabe fehlt. |

## Findings
- [Medium] `bin/web/app.js:510` — Hauptagenten-„Fokus“-Knopf ist funktionslos
  - Evidence: `mainToggle` wird ohne `on`-Handler und ohne nachträgliches `addEventListener` erzeugt; `applyFocus` (`552-564`) aktualisiert nur Text/ARIA. Der Fokus des Hauptagenten ist ausschließlich über die Übersichtszeile (`583`) erreichbar. Ein Klick auf „Fokus“ im Kopfbereich des Hauptagenten bewirkt nichts, obwohl AK5 und der Kommentar `507-509` einen geteilten Fokus-Zustand über Karten-, Haupt- und Übersichts-Knöpfe zusichern.
  - Required fix: Den Haupt-Fokus-Knopf an denselben `toggleFocus`-Zustand anbinden und mit einem Browser-Test absichern, der den Klick auf diesen Knopf und den resultierenden `enlarged`/`aria-expanded`-Zustand prüft.
- [Medium] `tests/browser/test_ap20_output_overview_ui.py:1101-1108` — Escape-Aufhebung wird nicht eigenständig geprüft
  - Evidence: Nach `page.keyboard.press("Escape")` fängt ein `except AssertionError` den Fehlschlag ab und ersetzt ihn durch einen programmatischen `node.click()`. Damit kann ein fehlender oder defekter Escape-Handler (`bin/web/app.js:643`) den Test nicht zum Scheitern bringen; die Zusicherung „Escape und/oder zweiter Klick“ wird nur zur Hälfte verifiziert.
  - Required fix: Escape als eigenen, nicht durch Fallback maskierten Prüfpfad testen und den Alternativpfad in einem separaten Testfall abdecken.
- [Medium] `docs/reviews/AP20-test-agent-report.md:9,143-146` — Widersprüchlicher Verifikationsstand
  - Evidence: Der Test-Agentenbericht erklärt, die Grünphase sei nicht ausgeführt worden, während `docs/features/AP20.md:131,135` „8/8 OK“ bzw. „20/20“ behauptet. Für die Grünphase existiert keine rohe Kommandoausgabe, nur Prosa. Der Nachweis für AK1–AK4 stützt sich damit auf eine nicht belegte Behauptung.
  - Required fix: Den tatsächlichen Grünlauf mit vollständiger Kommandoausgabe dokumentieren oder die Behauptung in der Feature-Doku korrigieren und den offenen Status ausweisen.
- [Minor] `docs/features/AP20.md:114` — Falsche Aussage zum Ticketstatus
  - Evidence: Die Doku behauptet, AP20 sei in `TICKETS.md` auf `[x]` gesetzt; `TICKETS.md:1066` führt weiterhin `- [ ] AP20`.
  - Required fix: Doku an den tatsächlichen Ticketstatus anpassen oder das Ticket im Rahmen des Abschlusses korrekt schließen.
- [Minor] `tests/browser/test_ap20_output_overview_ui.py` — Fehlende Randfallabdeckung
  - Evidence: Kein Test für den Wechsel der Hauptsession bei aktivem Fokus (`bin/web/app.js:593-606`) und kein Test für den Zustand ohne laufende Subagenten (`overviewEmpty`, `subsBox.hidden`, `bin/web/app.js:627,638`).
  - Required fix: Je einen fokussierten Browser-Test für Sessionwechsel und Null-Subagenten-Zustand ergänzen.

## Verification
- Change set reviewed: `20d1719..Arbeitskopie` im Worktree `/home/nutzer/vibe-AP20-yBZNBt` (Branch `feature/m0p/ap20-2`), inklusive untracked `docs/features/AP20.md`, `docs/features/AP20-ausgabe.png`, `docs/reviews/AP20-test-agent-report.md`, `tests/browser/test_ap20_output_overview_ui.py`.
- Git commands run by me: `git status --short`, `git diff --stat 20d1719`, `git diff 20d1719 -- bin/web/app.js`, `git diff 20d1719 -- bin/web/styles.css`, `git diff 20d1719 -- docs/import-manifest.json docs/baseline.md`, `git diff --no-index /dev/null docs/features/AP20.md`, `git diff --check 20d1719`, `git log --oneline -5`, `git diff 20d1719 -- TICKETS.md` (alle erfolgreich; spätere Shell-Aufrufe wurden durch die Berechtigungsprüfung abgelehnt).
- Checks with supplied output: Rotphase des Test-Agenten (7/8 Fehlschläge auf Basis, u. a. `scrollWidth=3400`, Karte rechts 1764) liegt als Ausgabe vor. Grünphase (8/8 AP20, 20/20 Regression) nur als Behauptung in Handoff/Feature-Doku, keine rohe Ausgabe.
- Checks not independently run: Alle Build-, Test-, Hash- und Verifikationsläufe (`verify.sh quick`, pytest/Playwright, `sha256sum`); Ausführung ist durch die Read-only-Vorgabe bzw. verweigerte Shell-Berechtigung ausgeschlossen.
- Important areas inspected: `bin/web/app.js` (`outputView` 498-674), `bin/web/styles.css:41-78`, `tests/browser/test_ap20_output_overview_ui.py` (8 Tests, Escape-Fallback 1101-1108, fehlende `aria-expanded`-Prüfung), `docs/features/AP20.md`, `docs/reviews/AP20-test-agent-report.md`, `docs/import-manifest.json:991-999,1113-1126`, `docs/baseline.md`, `TICKETS.md:1066`, `scripts/verify.py:50,152-159`, `.gitignore:18`, `docs/features/AP20-ausgabe.png`, Regressionstests `test_b11_output_ui.py` und `test_f30_subagent_view_ui.py`.
- Remaining risks: Manifest-Hashes nicht nachgerechnet; Grünphase nicht belegt; Hauptagenten-Fokus, Escape-Pfad, Sessionwechsel und Null-Subagenten-Zustand nicht durch Tests abgesichert. Worktree enthält noch keine Commits zum Paket.
