# AP7-Korbat — Rework verify.sh logic

Stand: 2026-11-23 · Branch `feature/korbat/ap7-korbat` · Tickets T-V13, T-V16–T-V21
(Quelle: `docs/features/AP12.md`, `TICKETS.md` AP7-Korbat inkl. Klarstellungen).

## Ziel

`scripts/verify.sh quick|package|full` ist die **einzige Prüfschnittstelle**
(Single Source of Truth). Agenten und Läufer führen dieselbe Logik aus; die
Engine liest `VERIFY_PACKAGE`/`VERIFY_FULL` nicht mehr als Befehl (die
Rekursionsfalle B1 ist damit konstruktiv unmöglich) und wertet im Vollmodus
eine monotone Baseline aus.

## Architektur (T-V16)

| Datei | Rolle |
| --- | --- |
| `scripts/verify.sh` | dünnes Frontend: python3-Prüfung, dann `exec python3 …/verify_engine.py "$@"` |
| `scripts/verify_engine.py` | Kern: Isolation, Modi-Orchestrierung, Guards, Baseline-Auswertung, Exitcodes |
| `scripts/verify.py` | Compat-Shim: delegiert per `os.execv` an `verify_engine.py`, keine eigene Logik |
| `scripts/run-tests-parallel.py` | paralleler Testläufer; neu mit `--report PATH` (strukturierter JSON-Bericht) |
| `tests/verify-baseline.json` | kanonische, committete Baseline (Schema v1, review-gated) |
| `.vibe/verify-baseline` | lokale, unversionierte Baseline (transportiert wie `project.env`) |

Die Isolationslogik (temporäres HOME/VIBE/TMPDIR, XDG, TMUX_TMPDIR, eigene
Ports, opencode-Dienst, Git-Konfiguration) bleibt unverändert in der Engine.

## Modi

- `quick` führt `VERIFY_QUICK` aus (einziger ausgeführter Konfigurationsbefehl).
- `package` führt `VERIFY_QUICK` aus plus optionalen Testnachweis, wenn
  `VERIFY_PACKAGE_TESTS` (oder `--tests`) gesetzt ist: Testdateien müssen
  existieren, Lauf über den Testläufer, Anzahl ≥ `VERIFY_MIN_TESTS` (Standard 1),
  Fehlerfreiheit erforderlich (keine Baseline; Exit 5 bei Prüffehlern, Exit 6
  bei fehlendem Nachweis). Ohne `VERIFY_PACKAGE_TESTS` kein Nachweiszwang.
- `full` baut den Testlauf selbst (`run-tests-parallel.py --dir <specs> …
  --report <tmp>/report.json`) aus `VERIFY_TESTS`/`--tests` und wertet die
  Baseline dreistufig aus.

Die Engine liest `VERIFY_QUICK` als Befehl und die Optionsvariablen
`VERIFY_TESTS`, `VERIFY_PACKAGE_TESTS`, `VERIFY_JOBS`, `VERIFY_MIN_TESTS`,
`VERIFY_BASELINE`, `VERIFY_ENV`, `VERIFY_TOOLS`. `VERIFY_TEST_PATTERN` entfällt
(Zählung kommt strukturiert aus dem Läuferbericht).

## CLI-Vertrag

```
verify.sh quick|package|full [--project DIR] [--tests DIR ...] [--jobs N]
      [--timeout SEK] [--baseline PATH] [--env LABEL] [--min-tests N]
      [--write-baseline] [--keep]
```

`--tests` mehrfach; überschreibt `VERIFY_TESTS` (full) bzw.
`VERIFY_PACKAGE_TESTS` (package). `--baseline` ersetzt für den Fehlvergleich die
Manifest-Dateien, `--env` überschreibt `VERIFY_ENV`, `--min-tests` überschreibt
`VERIFY_MIN_TESTS`.

## Guards (T-V13)

1. **Selbstpfad-Wächter** (für `VERIFY_QUICK`, auf jeder Tiefe): jedes Token mit
   Basisnamen `verify.sh`/`verify.py`/`verify_engine.py` → Exit 3 mit klarer
   Meldung (Variable, Token, Rekursionsfalle B1). Fail-safe: auch nicht
   auflösbare Tokens mit passendem Basisnamen werden abgelehnt.
2. **Tiefenwächter**: `VIBE_VERIFY_DEPTH` ≥ 2 → Exit 3; Wert 1 ist ein legitimer
   geschachtelter Lauf. Die ausgeführte Prüfung erhält Tiefe + 1.

## Baseline (T-V17–T-V19)

Committet kanonisch: `tests/verify-baseline.json`. Lokal: `.vibe/verify-baseline`
(unversioniert, transportiert read-only wie `project.env`). Schema v1:

```json
{
  "version": 1,
  "min_tests": 2000,
  "envs": {
    "<label>": {
      "failures": [
        {"module": "tests.unit.test_x", "class": "Fehlerklasse",
         "signature": "sha256:<hex>"}
      ]
    }
  }
}
```

- Inhalt nur: Versionsnummer, `min_tests` (Ratchet), kurzes Env-Label,
  Modul-IDs (dotted, repo-relativ), Fehlerklassen-Name, normalisierte Signatur
  (sha256 über Modul + Fehlerklasse + normalisierte Meldung; Normalisierung
  entfernt absolute Pfade, Zeilennummern, Zeitangaben). **Keine** IP-Adressen,
  Hostnamen, Geheimnisse oder absoluten Pfade (öffentliches Repository).

### Dreizustands-Auswertung (full)

1. **Grün**: keine fehlgeschlagenen Module, Zählung ≥ effektives Minimum → Exit 0.
2. **Baseline-OK**: fehlgeschlagene Module ⊆ Baseline-Failures des exakt
   passenden Env-Labels, alle Signaturen identisch, Zählung ≥ Minimum → Exit 0
   mit `BASELINE-OK` und Diff. Abschlusszeile:
   `VERIFY_RESULT: mode=full tests=N failed_modules=M baseline_ok=1 env=<label>`.
3. **Regression**: neue/geänderte Fehler → Exit 7. Zählung < Minimum → Exit 6.
   Trifft beides zu, gewinnt Exit 7.
4. Prüfbefehl ohne auswertbares Ergebnis → Exit 5.
5. Ungültige Baseline-Datei → Exit 3 (nie still ignorieren).

### Umgebungs-Schlüssel (T-V18)

Env-Label ausschließlich explizit (`--env` oder `VERIFY_ENV`), kein Best-Match.
Mismatch (kein passendes Label): Baseline ignoriert, jeder Fehlschlag ist eine
Regression (Exit 7), Meldung verweist auf `--write-baseline`. Ohne Fehlschläge
bleibt ein grüner Lauf grün (Exit 0).

### Präzedenz und Ratchet (D1/D2, T-V19)

- **Fehlvergleich**: die erste Quelle mit einer Sektion für das aktuelle Label
  ist exklusiv maßgeblich, in dieser Reihenfolge: `--baseline PATH` →
  lokale `.vibe/verify-baseline` → committete `tests/verify-baseline.json`.
  Kein Union der Failure-Listen.
- **min_tests-Ratchet**: effektives Minimum = max(`VERIFY_MIN_TESTS`/`--min-tests`,
  `min_tests` der committed Baseline, `min_tests` der lokalen Baseline, ggf.
  `min_tests` aus `--baseline`). Senkungen werden abgelehnt (Exit 3).
- **`--write-baseline`** (nur `full`) schreibt nur den lokalen, unversionierten
  Vorschlag `.vibe/verify-baseline`; andere Env-Sektionen bleiben unangetastet,
  `min_tests` wird nie gesenkt. Das Laufurteil ändert sich dadurch **nicht**
  (D2): Mismatch + Fehler ⇒ Datei wird geschrieben **und** Exit 7.

## Exitcodes (Engine, verbindlich)

| Code | Bedeutung |
| --- | --- |
| 0 | Erfolg (grün ODER Baseline-OK) |
| 1 | interner Fehler |
| 2 | Aufruf/Modusfehler |
| 3 | Konfiguration (Selbstreferenz/Rekursion, ungültige Baseline, gesenkte min_tests, fehlende Konfiguration) |
| 4 | Werkzeug fehlt |
| 5 | Prüfbefehl fehlgeschlagen (ohne auswertbares Ergebnis) |
| 6 | Testnachweis fehlt |
| 7 | neue Regression gegenüber Baseline |

Der Läufer behandelt 6/7 wie jede andere Nicht-Null (Reparaturrunde über den
bestehenden B9-Mechanismus). Er führt `VERIFY_PACKAGE`/`VERIFY_FULL` verbatim aus
und hat **keine** Sonderbehandlung für 6/7.

## Verdrahtung Runner (T-V20, Nutzerschritte)

Die autoritative `.vibe/project.env` des Integrationsverzeichnisses (`$P`)
wird vom **Nutzer** (nicht vom Agenten) umgestellt:

```
VERIFY_PACKAGE="bash scripts/verify.sh package"
VERIFY_FULL="bash scripts/verify.sh full"
VERIFY_ENV="<kurzes Label>"
```

Damit laufen Agentenaufruf und Endgate durch dieselbe Logik; ein Klick auf
„Prüfung package“ im Dashboard erreicht über den Wrapper die Engine. `full`
liest `VERIFY_FULL` nicht als Befehl (Hinweisausgabe statt Fehler).

## Hash-/Diff-Wächter (T-V21, Lean)

`bin/vibe-run.sh` erfasst nach dem Transport (Paketstart) den sha256 von
`.vibe/project.env` und (falls vorhanden) `.vibe/verify-baseline`; vor jeder
Paketprüfung (auch nach einer Reparaturrunde) wird erneut gehasht. Eine
Abweichung — Veränderung ebenso wie das Löschen einer beim Start vorhandenen
Datei — → `record_block` mit klarer Meldung (welche Datei betroffen ist) und
Paket-Abbruch ohne Reparaturrunde. Best effort wie der Transport selbst:
fehlende Startdatei hat keinen Wächter. `final_verify`/`run_package_tests`/
`verify_run` bleiben funktional unverändert.

Mit GH-46 entfällt der Wächter-Anteil für `.vibe/verify-baseline`: Der
Transport dieser Datei entfällt, Arbeitskopien nutzen die committete Baseline
aus dem Branch; der Wächter gilt weiterhin für `.vibe/project.env`.

## Befüllungs-Workflow

1. `bash scripts/verify.sh full --env <label> --write-baseline` erzeugt den
   lokalen, unversionierten Vorschlag `.vibe/verify-baseline`.
2. Der Vorschlag wird geprüft (Review) und die relevanten Einträge in die
   kanonische `tests/verify-baseline.json` über einen geprüften Merge-Request
   übernommen. Die committete Baseline wird vom Engine nie automatisch
   erweitert.
3. Nach Übernahme der Einträge per Merge-Request wird der lokale Vorschlag
   `.vibe/verify-baseline` gelöscht (ephemeraler Vorschlag, kein Dauerzustand;
   B5/GH-46).

## Grenzen

- Die committete Baseline ist nur ein Schema-Rumpf (`envs={}`, `min_tests=2000`);
  die Befüllung ist ein Review-/Nutzer-Workflow, kein Bestandteil dieses Pakets.
- Der Env-Label-Vergleich ist exakt; ein ähnliches Label gilt nicht als Treffer.
- Die Browserabnahme/Playwright wurde in dieser Umgebung echt und grün
  ausgeführt (headless Chromium, `tests/browser/test_f31_verify_package_ui.py`,
  `Ran 1 test … OK`); die Grenze ist die Beschränkung auf Chromium/headless —
  keine manuelle Tastatur- und keine Cross-Browser-Prüfung.
