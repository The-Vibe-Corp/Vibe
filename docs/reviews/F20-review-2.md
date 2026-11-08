# F20 Review — Runde 2 (unabhängiger code-reviewer, Korrekturen)

Datum: 2026-11-08
Stand: d9690e7 → Arbeitskopie nach Fixes aus Runde 1
(Branch vibe/vibe-F20-1794094233248968013-2071287-14400)
Geprüft von: Agent `code-reviewer` (read-only, unabhängige Sitzung)
Gegenstand: Nur die Korrekturen aus Runde 1 (Verdict: PASS, 3 Minor)

## Korrekturen der Runde 1
1. `bin/web/app.js`, `header()`: Tooltip des „Dashboard beenden“-Knopfs ist jetzt
   bedingt nach Harness-Wahl: bei Pi „Beendet diese App (das Dashboard), nicht
   laufende Agentenläufe in tmux“, sonst unverändert „…, nicht opencode“.
2. `docs/import-manifest.json`: Changelog-Eintrag F20 mit 2/3-Leerzeichen-Einrückung
   wie die übrigen Einträge; `bin/web/app.js`-Eintrag mit neuer Prüfsumme/Größe
   (93523 Bytes).
3. `docs/features/F20.md`: verify-Ziffern korrigiert auf die belegten Läufe
   (Arbeitsstand: failures=36, errors=2; Baseline-Klon: failures=36, errors=3),
   Baseline-Abweichungen als Klon-Artefakte erläutert; persönlicher Home-Pfad durch
   den Platzhalter „<lokales Playwright-Cache-Verzeichnis>“ ersetzt.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Prüfpunkte

**1. Bedingter Tooltip des „Dashboard beenden“-Knopfs (`bin/web/app.js:67`)**
- PASS — Das `title`-Attribut lautet bei `isPi` „Beendet diese App (das Dashboard),
  nicht laufende Agentenläufe in tmux“, sonst „…, nicht opencode“. Beide Zweige
  erzeugen einen nichtleeren String; `el()` setzt `title` über `setAttribute`, das
  Attribut geht in beiden Fällen nicht verloren. Laut gestaltete Attribute/Kinder
  bleiben unverändert; Musterchecks auf Restfehler des zwischenzeitlich fehlerhaften
  Zwischenstands (z. B. `,,`, doppelte Blöcke) ergaben keine Treffer; die
  `replaceChildren`-/`el()`-Hierarchie des Blocks (Zeilen 65-73) ist korrekt.

**2. Changelog-Eintrag F20 in `docs/import-manifest.json`**
- PASS — Alle `"arbeitspaket"`-Einträge nutzen identischen Einzug; der F20-Block
  (Zeilen 807-815) ist exakt nach demselben Muster eingerückt. Der
  `bin/web/app.js`-Eintrag nennt die neue SHA-256 (491c9457…) und 93523 Bytes und
  ist konsistent.
- Keine Befunde.

**3. `docs/features/F20.md`**
- PASS — full mit `failures=36, errors=2`; Baseline-Klon mit `failures=36,
  errors=3`; Abweichungen des Baseline-Klons sind als Klon-Artefakte erläutert.
  Ein RegEx nach `/home/` liefert in der Datei keine Treffer.
- Keine Befunde.

## Findings
- [Minor] `tests/browser/test_f20_harness_ui.py` — Kein Test für den bedingten
  Tooltip (`title`-Attribut). Die Browser-Tests prüfen die Texte aller Karten und
  den Server-Kasten, aber keiner das `title`-Attribut des Beenden-Knopfs; auch der
  bisherige opencode-Titel war nicht getestet. Das ist eine
  Testabdeckungs-Vervollständigung für das kleine Delta, kein Abbruchkriterium.

## Verification
- Change set reviewed: d9690e7 → Arbeitskopie (Fokus: `bin/web/app.js`,
  `docs/import-manifest.json`, `docs/features/F20.md`).
- Git-Befehle: mangels Shell-Zugangs im Reviewkontext nicht durch mich ausführbar;
  stattdessen Vergleich der Dateistellen gegen die geforderten Zustände.
- Mit Agent-Nachweis (vom Coding-Agent ausgeführt, nicht unabhängig durch mich
  wiederholbar): `node --check` OK; `check-syntax.py` OK (102 Python, 8 Bash,
  4 JSON); unittest tests/unit test_f20_harness_dashboard_api → 8 OK; Playwright
  tests/browser pattern test_f20_harness_ui.py → 12 OK; check-import-manifest.py →
  OK: 56 Dateien.
- Remaining risks: errors-Ziffern des full-Laufs aus der Feature-Doku übernommen,
  nicht selbst reproduziert; SHA-256/Größe von `bin/web/app.js` mangels Werkzeug
  nicht unabhängig berechnet.

Verdict: PASS
