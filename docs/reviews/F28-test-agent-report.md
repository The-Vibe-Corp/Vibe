# F28 — Test-Agenten-Bericht (Akzeptanztests Code-Verbesserungen nach pylint-Bericht)

Datum: 2026-11-10, Worktree `vibe-F28-KS72IZ`, Ausgangscommit `1c54d39`
(„Konfiguration: pylint als erlaubtes Sandbox-Werkzeug ergänzt“).
Quellen: TICKETS.md „F28 Code Verbesserungen“, FEEDBACK.md Z. 510,
`docs/reviews/F28-nutzer-pylint-report_2026_11_10.txt` /
`docs/reviews/F28-pylint-baseline_2026_11_10.txt` (pylint 4.0.5, Rating 8.65/10),
`SPEC.md`, `AGENTS.md`, `.vibe/project.env`.

## 1. Testdateien und Testnamen

- `tests/unit/test_f28_pylint_quality.py` (neu, Test-Agent)
  - `test_ak1_pylint_ausfuehrung_gesichert` — AK1-Schutzgitter
  - `test_ak1_keine_befunde_ausser_ausnahmen` — AK1-Haupttest

Der pylint-Lauf im Test ist identisch mit dem Baseline-Bericht: dieselben
16 Module in `bin/` (Liste im Test fest verdrahtet), Arbeitsverzeichnis `bin/`,
`-j 1`, `/usr/bin/pylint` (4.0.5, Python 3.14.8), Parsung per
`--output-format=json`. Fehlt pylint, springt der Test mit `skipTest` und
verweist auf `/usr/bin/pylint`.

## 2. Autonome Ableitung: Abruf- und Ausnahmemenge

Aus dem Baseline-Bericht abgeleitete Kategoriemenge (32 Kategorien). Die
offen im Testdateikopf dokumentierte Ausnahmeliste lautet:

- Struktur-/Design-Befunde der Klassen aus dem Arbeitspaket:
  `too-many-branches` (R0912), `too-many-locals` (R0914),
  `too-many-arguments` (R0913), `too-many-positional-arguments` (R0917),
  `too-many-statements` (R0915), `too-many-return-statements` (R0911),
  `too-many-nested-blocks` (R0101), `too-many-boolean-expressions` (R0916),
  `too-many-lines` (C0302).
- Zusätzlich ausdrücklich als unter dieselbe „lines"-Klasse fallend
  dokumentiert: `line-too-long` (C0301, 153 Befunde in der Baseline).
  Begründung: AK2 verlangt Verhaltenserhaltung; Zeilenumbrüche in den
  HTML-/URL-Template-Strings von `vibe-web.py` ändern andernfalls die
  Bytefolge der ausgelieferten Oberfläche. (Falls der Paketverantwortliche
  dies enger sieht: die Konstante `AUSNAHMEN_SYMBOLE` im Test ist
  kommentiert und kann um `line-too-long` verkürzt werden.)
- `invalid-name` (C0103) NUR für den Modulnamen der beiden
  Bindestrich-Einstiegsdateien `fritz-reconnect.py` und `vibe-web.py`
  (Filter: Meldung beginnt mit „Module name“). Alle anderen invalid-name-
  Befunde (SRV, do_GET, do_POST in vibe-web.py) sind NICHT ausgenommen.
- Alles Weitere — u. a. die 428 Baseline-Befunde aus
  `missing-function-docstring` (77), `multiple-statements` (186),
  `no-member` (30), `broad-exception-caught` (25), `raise-missing-from` (21),
  `consider-using-f-string` (12), `wrong-import-position` (11),
  `duplicate-code` (3), `import-error` (E0401 „Unable to import 'vibe'“),
  `unspecified-encoding` (2), `consider-using-with` (3) sowie die
  übrigen Restkategorien — muss der Coding-Agent beheben; der Test zählt diese
  weiterhin als Verletzung.

## 3. Ausgeführte Befehle (Red-Phase, Ausgangsstand)

```
python3 -m unittest tests.unit.test_f28_pylint_quality -v
→ Ran 2 tests in 13.054s  FAILED (failures=1)  Exit-Code=1
  - test_ak1_pylint_ausfuehrung_gesichert ... ok
  - test_ak1_keine_befunde_ausser_ausnahmen ... FAIL:
    „AK1 verletzt: 428 pylint-Befunde außerhalb der Ausnahmeliste“
```

Bestätigung Rotphase: Der Haupttest schlägt am Ausgangsstand fehl, weil die
von der Verbesserung betroffenen Kategorien (o. a. Kategoriezählung im
Fehlerausdruck) noch Befunde liefern; der Schutzgitter-Test ist grün und
verhindert verbrannte Läufe (rc=0, Parsefehler, übersprungene
Einstiegsdateien). Die Testdatei enthält keine Attrappen und prüft die
echte pylint-Ausgabe.

Wiederholung nach letzter rein sprachlicher Bereinigung der Testdatei selbst
(Sprach-Korrekturen im Kommentar; Logik unverändert):
`python3 -m unittest tests.unit.test_f28_pylint_quality -v`
→ `Ran 2 tests in 13.193s / FAILED (failures=1)`, Exit-Code 1
(Protokoll: /tmp/opencode/f28-test-agent/rotphase-2.log).

Referenzmessung mit denselben Parametern (Protokoll-exakt):
`cd bin && /usr/bin/pylint --output-format=json -j 1 <16 Module>`
→ Exit 30 (Bitmaske error/warning/refactor/convention),
680 Befunde, davon 250 in der Ausnahmemenge (line-too-long 153,
too-many-* 97) und **430** außerhalb (Test-Rotmenge, Konsistenzcheck mit
Baseline: identische Kategorien; 2 der 4 invalid-name-Restbefunde sind die
Modulnamen der Einstiegsdateien und werden begrenzt ausgenommen, der
Haupttest meldet daher 428).

## 4. AK2-Baseline der bestehenden Suiten (vor Implementierung)

```
python3 -m unittest discover -s tests/unit
→ Ran 1315 tests in 221.824s  FAILED (failures=19, errors=61)  Exit-Code=1
python3 -m unittest discover -s tests/browser
→ Ran 91 tests in 141.058s  FAILED (failures=1, errors=9)  Exit-Code=1
```

Diese Rotstände sind vorbestehend (nicht durch F28-Tests verursacht; der
einzige F28-Beitrag ist der bewusst rote
`test_ak1_keine_befunde_ausser_ausnahmen` unter den 19 Failures). Muster der
vorbestehenden Fehler (Stichproben im Protokoll):
- Unit: `test_costs`/`test_storage`/`test_mcp_config` (z. B.
  `vibe_storage.write_text`-Aufrufe enden in OSError), `test_process_safety`
  (Agent nur projektbezogen ausgewählt), `test_sandbox` (echte Sandbox),
  `test_release` (persönliche Pfade), `test_f27_keep_changes` u. a. —
  vermutlich FUSE-/Berechtigungsbedingungen dieses Worktree-Containers.
- Browser: 9 setUpClass-ERRORs „vibe-web wurde vorzeitig beendet“
  (prepare_runtime → write_private → OSError bei chmod auf FUSE).

→ Nach der Implementierung muss die Suite-Ergebnismenge identisch oder
besser sein; eine Neuaufkündigung dieser Muster ist eine Regression durch
F28 und wird vom Test-Agenten gemeldet.

## 5. Protokolle

- `/tmp/opencode/f28-test-agent/pylint-now-parseable.txt` (Textformat, 747 Zeilen, Rating 8.65/10)
- `/tmp/opencode/f28-test-agent/pylint-now.json` (JSON, 680 Befunde)
- `/tmp/opencode/f28-test-agent/rotphase.log` (Red-Phase-Lauf)
- `/tmp/opencode/f28-test-agent/baseline-unit.log`, `baseline-browser.log`

## 6. Hinweise an Coding- und Review-Agenten

- Testbefehl: `python3 -m unittest tests.unit.test_f28_pylint_quality -v`
- Der Coding-Agent darf die Testdatei nicht ändern/abschwächen; melden, nicht
  anpassen.
- Betroffene Kategorien, die definitiv dem Coding-Agenten obliegen
  (nicht ausgenommene), siehe Kategoriezählung in Abschnitt 3; insbes.
  `import-error` (E0401) und `no-member` müssen überlegt und korrigiert
  werden — echte Korrekturen statt globaler Abschaltung sind erwünscht.
  Setzt der Coding-Agent per-Datei-Disable-Kommentare statt echter
  Korrekturen ein, bleiben die Testergebnisse formal grün; dies ist als
  Grenze im Bericht benannt und ist kein Nachweis echter Beseitigung.
- Reviewer: Die Tests stammen nachweislich vom Test-Agenten (neu erstellte Datei
  in diesem Arbeitspaket; git-Diff des Coding-Agenten darf den Test nicht
  berühren).

## 7. Verbleibende Lücken und Grenzen

1. AK2 wird nicht als verschachtelter Unittest, sondern durch getrennte Baseline- und Wiederholungsläufe der bestehenden
   Suiten belegt
   (Baseline-Werte oben). Die Browser-Suite hat 9 vorbestehende setUpClass-Fehler
   (FUSE/chmod im Container) — die Vergleichbarkeit bleibt trotzdem erhalten; Maßnahmen, die neue
   Fehler in den Suiten erzeugen oder die Fehleranzahl erhöhen, gelten
   als Regression.
2. Anti-Gaming-Grenze: Bräuchte der Coding-Agent pylint-Befunde über ein `pylintrc` oder
   Disable-Kommentare zum Verschwinden, bliebe der Haupttest dennoch grün,
   solange das Schutzgitter besteht (Mindestbedingung: mehr als 0 Befunde
   und die beiden Modulnamen-Befunde der Einstiegsdateien). Ein vollständiges
   Abschalten lässt das Schutzgitter anschlagen (roter Lauf ohne Befunde).
3. Kein produktives HOME/Geheimnis im Test; pylint schreibt sein
   `PYLINTHOME` unter `/tmp/opencode/f28-test-agent/.pylint-home`.
4. Zeitaufwand je Testlauf inkl. pylint: ~13 s; die Unit-Regression nimmt
   ~4 min, die Browser-Regression ~2.5 min in Anspruch.
