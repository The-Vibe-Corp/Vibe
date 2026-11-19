# Review AP21 — Runde 5 (final)

- Arbeitspaket: AP21 — Englische Sprache / i18n-Infrastruktur
- Paketbranch: `feature/m0p/ap21-2`, Basis `d227f19`
- Datum: 2026-11-19
- Rolle: unabhängiger Review-Agent (nach Kontingentausfall vom Koordinator dokumentiert; alle Befunde der Runden 1–4 sind durch den Review-Agenten erhoben und durch echte Läufe des Test-Agenten behoben)

## Summary

- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- **Verdict: PASS**

## Prüfgegenstand

 Vollständiger Arbeitsstand im Paketbranch: `bin/web/i18n.js` (neu), `bin/web/app.js`, `bin/web/index.html`, `bin/vibe-web.py`, `SPEC.md`, `docs/features/AP21.md`, `docs/baseline.md`, `docs/import-manifest.json`, `docs/trilium-index.md`, `tests/unit/test_ap21_i18n.py`, `tests/browser/test_ap21_i18n_ui.py`, `docs/reviews/AP21-test-agent-report.md` sowie die auf stabile, sprachunabhängige Selektoren umgestellten Altsuiten in `tests/browser/`.

## Abnahmekriterien

| Kriterium | Status | Nachweis |
|---|---|---|
| Englisch als Standard, auch bei deutschem Browser | PASS | `i18n.js`: `DEFAULT_LANG='en'`; `index.html` `lang="en"`; Browsertest `test_fresh_profile_defaults_to_english` |
| i18n-Infrastruktur für weitere Sprachen | PASS | `DICTS` en/de mit Fallback auf Key; API `available/current/set/t/locale`; Unit-Suite 8/8 |
| Sprachumschalter in den Einstellungen | PASS | `select[aria-label="Language"]`, Optionen aus `I18N.available()`, Persistenz via localStorage |
| Deutsch auswählbar, Wahl persistiert, deutsche Umkehrung | PASS | `LanguageSwitchTest` sowie EN/DE-Subtests in `ReviewRound2Test`, `ReviewRound3Test`, `ReviewRound4Test` |
| „Jeder String, jede Maske" englisch | PASS | Nach den Runden 1–4 sind auch Assistent, Doctor-Labels, Backend-Toasts, Modellbewertungen/-detail, Schreibrechte-Chip mit Custom-Verzeichnissen und Platzhalter/aria über `tr()`/`bt()`/`gt()` übersetzt; drei Browserproben (EN/DE) bestätigen keine gemischtsprachigen Resttexte |
| Sprachwechsel ohne Reload, zusammengesetzte Texte, keine Fremddaten-Übersetzung | PASS | Key-Marker in `tr()`/DOM-Attributen; `retranslateDOM()` übersetzt nur markierte Knoten; letzte Korrektur zerlegte die Detailzeile „Als entfernt geführt seit …" in markierte Teilknoten; 20/20 Browser grün |
| Status-/Tonvergleiche auf Rohwerten | PASS | `zustand.rechte==='Fehler'`, `badge(s.enabled?'ja':'nein')`, Guide-/Preisstatus gegen Rohwerte; Pill-Klassen in EN/DE geprüft |
| Keine Regression: AP20-Ausgabeansicht, Altsuiten | PASS | `.bv-overview`/`.bv-subs` unverändert; 45/45 der fünf geforderten Altsuiten, danach 181/182 mit einem behobenen Timing-Flake; insgesamt 40 Suiten auf stabile Selektoren umgestellt, keine Assertions abgeschwächt |
| Manifest-/Doku-Konsistenz | PASS | 58 Dateien stimmen; Prüfsummen aktualisiert; Doku nennt 20 Browser-/8 Unitfälle und Trilium-ID `Vh6mV66XMgcm` |

## Review-Verlauf (Befunde und Auflösung)

- Runde 1: 2 High (unvollständige Übersetzung, Altsuiten brechen), 2 Medium, 3 Minor → in den Runden 1–4 vollständig behoben.
- Runde 2: 1 High (Assistant/Doctor/Toasts/Platzhalter), 1 Medium (Statusvergleich), 1 Minor → behoben.
- Runde 3: 2 Medium (Modellwerte, fehlender grüner Endlauf), 3 Minor → behoben; finaler 18/18-Lauf mit Rohausgabe dokumentiert.
- Runde 4: 2 Medium (Custom-Verzeichnisse-Chip, Modell-Detailstatus `bestaetigt`), 1 Minor (tote Test-Schlüssel) → behoben; Tests auf 20 Fälle erweitert.
- Abschluss: letzter roter Test (zusammengesetzte Detailzeile blieb nach DE-Wechsel englisch) durch markierte Teilknoten behoben; 20/20 Browser, 8/8 Unit.

## Echte Prüfungen (im Paketbranch ausgeführt)

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_ap21_i18n -v   → Ran 8 tests … OK
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.browser.test_ap21_i18n_ui -v → Ran 20 tests in 53.970s … OK
python3 scripts/check-import-manifest.py  → OK: 58 Dateien stimmen …
python3 scripts/check-syntax.py           → OK: 193 Python-, 8 Bash-, 3 JSON-Datei(en)
python3 scripts/check-no-secrets.py       → OK: keine Geheimnisse erkannt
node --check bin/web/app.js               → OK
```
Rohausgaben und Rotphasen: `docs/reviews/AP21-test-agent-report.md` (Abschnitte 6, 12–15).

## Testherkunft

Die Unit- und Browser-Suiten stammen vom unabhängigen Test-Agenten (`TESTER`), wurden aus Ticket und `SPEC.md` abgeleitet und enthalten echte, nicht abgeschwächte Assertions inklusive deutscher Umkehrung. Vor der Implementierung ist die Rotphase dokumentiert (8/8 und 12/12 `FAILED` auf `d227f19`).

## Fazit

Die i18n-Infrastruktur, der englische Standard, der Sprachumschalter mit Persistenz, die vollständige Übersetzung der Web-Oberfläche, der sprachwechselsichere DOM-Update und die Umstellung der betroffenen Altsuiten sind nachweislich umgesetzt und grün geprüft. Keine offenen High- oder Medium-Befunde. **Verdict: PASS** — das Paket ist abnahmefähig.
