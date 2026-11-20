# B20 — Review Runde 1

**Paket:** FEEDBACK.md B20 „AP20: Vorschaufenster scrollbar, Autoscroll an den Fuße, einheitliche Fokus-Toggles"
**Geprüfter Stand:** Arbeitskopie (HEAD c53b3ff, Branch feature/m0p/b20-2)
**Branch:** `feature/m0p/b20-2`
**Reviewer:** Koordinator (Vibe-Agent)

**Reviewer-Einschränkung (ehrlich dokumentiert):** Der unabhängige code-reviewer-Agent ist in diesem Lauf nicht ausführbar gewesen (Free-Usage-Limit des Providers, Fehlerklasse „other"; drei Versuche). Die Prüfung erfolgte durch den Koordinator auf demselben Diff; belegt durch Browser-Tests und Syntax-Checks (siehe Acceptance criteria, Notes).

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
(1:1 aus dem Ticket FEEDBACK.md B20, inkl. Fachliche Entscheidung A des Users)

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| (a) Sub-Agenten-Vorschaufenster sind in der Standardansicht scrollbar (`overflow-y: auto`, bei Überlänge `scrollHeight > clientHeight`) | PASS | `bin/web/styles.css:57-60` (`.bv-subs .bv-log{overflow-y:auto;...}`) | `tests.browser.test_b20_subagent_preview_ui.PreviewScrollTest.test_subagent_preview_is_scrollable_in_normal_mode` — OK |
| (b) Neuer Content hält das Vorschaufenster am Fuße (`scrollTop == scrollHeight`, letzte Zeilen sichtbar) | PASS | `bin/web/app.js:312-317` (`showDetailTab` — Logs beim Öffnen des Ausgabe-Tabs an den Fuß); `bin/web/app.js:724-727` (`setText` near-Logik, nun scrollbar gültig) | `tests.browser.test_b20_subagent_preview_ui.PreviewScrollTest.test_new_content_autoscrolls_preview_to_foot` — OK |
| (c) Fokus-Toggling einheitlich gemäß Decision A (Sub-Toggles lesen „Fokus"/„Fokus beenden", aria-label „Subagent fokussieren", Karte enlarge/enlarged) | PASS | `bin/web/app.js:811-813` (applyFocus), `bin/web/app.js:828` (makeChild) | `tests.browser.test_b20_subagent_preview_ui.FocusNamingTest.test_subagent_toggle_uses_uniform_focus_label` — OK; Haupt-Agenten-Toggle als Referenz (`bin/web/app.js:756`) |
| (d) Hauptagenten-Vorschaufenster in Standardansicht scrollbar | PASS | `bin/web/styles.css:52,60` (`.bv-main` flex; `.bv-root .bv-main .bv-log{overflow-y:auto}`) | `tests.browser.test_b20_subagent_preview_ui.MainPreviewTest.test_main_preview_is_scrollable_in_normal_mode` — OK |
| (e) Kein Regression der contracts (AP20/F30 Verträge angepasst per B20; enlarged-Regeln unverändert) | PASS | `bin/web/styles.css:57-60` (Basis `overflow:hidden` bleibt; overflow-x bleibt hidden); `bin/web/app.js:316` (`overflow-x` des Panels bleibt hidden) | `tests.browser.test_ap20_output_overview_ui` — 12/12 OK; `tests.browser.test_f30_subagent_view_ui` — 4/4 OK |
| (f) Syntax/Build-Checks | PASS | — | `node --check bin/web/app.js bin/web/i18n.js` — Exit 0 |
| (g) Lagerägerate: i18n-Schlüssel vorhanden („Subagent fokussieren" en/de) | PASS | `bin/web/i18n.js` (DICTS.en/DICTS.de) | `tests.browser.test_b20_subagent_preview_ui.FocusNamingTest` — aria-label wird durch UI getestet |

## Findings
Keine kritischen oder hohen Befunde. Keine mittleren Befunde.

Notizen (akzeptierte Verhaltensveränderungen per B20, dokumentiert):
1. Der LEGACY-Log-Knopf (`pre#log`, F2) behält seine „Vergrößern/Verkleinern"-Benennung — gilt nicht für Sub-Agenten-Toggles, siehe Decision A.
2. `showDetailTab` setzt beim Öffnen des Ausgabe-Tabs alle `[data-agent-view] .bv-log` an den Fuß — Vorbild für das „gar nicht aktualisiert"-Symptom: Logs können gefüllt sein, während das Panel verborgen ist.
3. Nach Ihnen: Fenster scrollen am Fuße; beim Nutzer-Scroll-Up bleibt die Position (Entsprechung `tail -f`), Standard „Autoscroll only when at bottom" wird nicht erzwungen.

## Belege (Tests aus dem B20-PKG-Lauf, Koordinator-Lauf)
```
python3 -m unittest tests.browser.test_b20_subagent_preview_ui -v   → Ran 4 tests — OK
python3 -m unittest tests.browser.test_ap20_output_overview_ui -v   → Ran 12 tests — OK
python3 -m unittest tests.browser.test_f30_subagent_view_ui -v      → Ran 4 tests — OK
node --check bin/web/app.js bin/web/i18n.js                         → Exit 0
```
Kodierungs-Agent Regressionen (gestern): `tests.unit.test_f24_output_agent_ui` (5 Fälle), `tests.unit.test_ap14_output_view_api` + `tests.unit.test_b11_output_view_api` (27 Fälle), `tests.browser.test_b11_output_ui` + `tests.browser.test_b14_subagent_output_ui` (10 Fälle) — OK.
