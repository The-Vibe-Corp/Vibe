# B6 — Statusmarken (Statuspositionen)

Status: Implementiert (2026-11-22); Reviewstand: siehe docs/reviews/B6-review-*.md (jüngster Bericht ist maßgeblich)
Ticket: FEEDBACK.md `- [ ] B6` (Art: Bug)
Branch: `feature/korbat/b6` (Arbeitskopie `worktrees/vibe-B6-iGrKk1`)
Ausgangscommit: `c3d68dd` (AP6-Korbat-Merge, `dev`)

## Ziel

Der Läufer und die Oberfläche sollen offene Pakete mit eingefügten
Laufberichtszeilen (wie B5) nicht mehr fälschlich als blockiert oder
wartend einstufen. Eine `BLOCKIERT:`-/`WARTET AUF MERGE:`-Marke gilt nur
dann als Zustandsmarke, wenn sie an einer Statusposition steht.

## Beobachtetes Fehlverhalten

Der offene Block B5 erschien in der Oberfläche als „offen", während der
Läufer „Offen: keine" meldete und B5 nie auswählte. Ursache war eine
unterschiedliche, zu breite Erkennung:

- `bin/vibe_packages.py` (`is_blocked`, `is_waiting_merge`) prüfte
  `BLOCKIERT:`/`WARTET AUF MERGE:` als case-insensitive Teilzeichenkette
  über den ganzen Block.
- Der B5-Block enthält eingefügte Berichtszeilen wie
  `Blockiert: AP6-Korbat (...)` und `Wartet auf Merge: keine`, die deshalb
  als Sperre/Warten fehlinterpretiert wurden.
- `bin/vibe` (`_parse_entry`, `open_items`) arbeitete case-sensitiv mit
  derselben Teilzeichenkettenprüfung, klassifizierte denselben Block aber
  als „offen" — Läufer und Oberfläche liefen auseinander.

## Ursache

Die Marken wurden nicht an ihrer Position (Statusposition) erkannt, sondern
überall im Blocktext. Dadurch zählten Freitextzeilen im Abschlussbericht
als Zustandsmarke. Die Regeln in FEEDBACK.md („Darunter `BLOCKIERT: <Grund>`
schreiben") und die Implementierung von `mark_blocked`/`mark_waiting_merge`
sehen die Marke dagegen als letzte nichtleere Blockzeile bzw. im Kopffeld
vor der Beschreibung vor.

## Änderung

- Neue gemeinsame Erkennung `block_marker_state(block)` in
  `bin/vibe_packages.py`: eine Marke zählt genau dann, wenn sie
  (a) die letzte nichtleere Blockzeile ist oder
  (b) im Kopffeld vor der ersten `Beschreibung:`-/`Erwartet:`-Zeile steht.
  Die späteste Position gewinnt; im Kopffeld schlägt `BLOCKIERT` stets
  `WARTET AUF MERGE`. Blöcke ohne Beschreibungszeile nutzen nur (a).
- `is_blocked`/`is_waiting_merge` nutzen diese Erkennung.
- `mark_blocked`/`mark_waiting_merge` prüfen Idempotenz jetzt über die
  strenge Statuspositions-Erkennung; Freitext-Blöcke können weiterhin eine
  echte Marke angehängt bekommen.
- `bin/vibe` (`_parse_entry`, `open_items`) nutzt dieselbe Erkennung aus
  `vibe_packages`, sodass Läufer und Oberfläche identisch klassifizieren.
- `_apply_proof` (breite Entfernung von Markerzeilen beim Abhaken) und
  `is_draft` bleiben unverändert.

## Auswirkung auf Bestandsdaten

- Echte Marken an Statuspositionen bleiben wirksam (inkl. B3-AK3-Platzierung
  vor `Beschreibung:`).
- Marken, die von weiterem Blocktext gefolgt werden (z. B. eingefügte
  Berichtszeilen), gelten nicht mehr als Zustandsmarke; der dokumentierte
  Stand bleibt maßgeblich, es werden keine Daten umgeschrieben.
- Blöcke mit echter Statuspositions-Marke werden weiterhin nicht ausgewählt.

## Verhaltensregeln (R1–R6, kompakt)

- R1: Marke zählt nur an Statusposition: (a) letzte nichtleere Zeile oder
  (b) Kopffeld vor `Beschreibung:`/`Erwartet:` (nur wenn vorhanden).
- R2: Freitextzeilen (auch zeilenanfangend, beliebige Groß-/Kleinschreibung)
  zählen nicht, solange sie nicht an einer Statusposition stehen; solche
  Blöcke sind „offen".
- R3: `bin/vibe_packages.py` und `bin/vibe` klassifizieren identisch;
  Präzedenz erledigt > BLOCKIERT > WARTET AUF MERGE > In-Progress > Draft >
  offen (bzw. „ohne Nachweis").
- R4: `mark_blocked`/`mark_waiting_merge` sind idempotent nur bei echter
  Statuspositions-Marke; Anhängen an Freitext-Blöcke möglich.
- R5: Der B5-ähnliche offene Block ist offen und auswählbar.
- R6: Echte Statuspositions-Marken wirksam; Done/Draft/In-Progress-Präzedenz;
  `_apply_proof` entfernt Markerzeilen weiterhin breit.


## Grenzen

- Ein eingefügter Bericht, der mit einer ``Blockiert:``-/``Wartet auf Merge:``-
  Zeile endet, gilt weiterhin als blockiert/wartend: die Position entscheidet.
  Nutzer können die Zeile redigieren, wenn sie als Freitext gemeint war.
- Eine echte Marke verliert ihre Wirkung, sobald danach weiterer Blocktext
  steht (z. B. Beschreibung oder Berichtszeilen). Dann die Marker-Zeile ans
  Ende verschieben bzw. erneut als letzte nichtleere Zeile schreiben.
- FEEDBACK.md-Regel: die Marke wird „darunter" als letzte nichtleere
  Blockzeile geschrieben; das entspricht `mark_blocked`/`mark_waiting_merge`.


## Verifikation

Ausgeführte Befehle (Arbeitskopie
`/var/log/custom/vibe-dev/worktrees/vibe-B6-iGrKk1`, Ausgangscommit
`c3d68dd`):

- `python3 -m unittest tests.unit.test_work_packages`
  → Ran 56 tests, OK.
- `python3 -m unittest tests.unit.test_work_packages
  tests.unit.test_ap5_korbat_waiting_state tests.unit.test_ap3_korbat_issues_backend
  tests.unit.test_package_gates`
  → Ran 114 tests, OK.
- `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_verify_script`
  → Ran 34 tests, FAILED (failures=1): bekannter umgebungsbedingter
  `RepositoryVerifyTest.test_repository_quick_check_passes` (kein
  transportiertes `.vibe/project.env` in dieser Arbeitskopie).
- `python3 scripts/check-import-manifest.py` → OK (70 Dateien).
- `bash scripts/verify.sh quick` → Exit 0.

Zusätzlich dokumentiert (Koordinator, unverändert):
- Volllauf `python3 scripts/run-tests-parallel.py --dir tests/unit --jobs 4`
  → 2492 Tests, 6 fehlgeschlagene Module, identische Baseline-Modulliste am
  Ausgangscommit `c3d68dd` (keine B6-Regression).
- Rotphase der finalen Suite am Baseline-Klon: 27 FAILED / 29 OK
  (`docs/reviews/B6-test-agent-report.md`, Phase 3).
