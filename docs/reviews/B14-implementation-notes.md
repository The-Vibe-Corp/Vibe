# B14 — Umsetzungsnotizen (erneut geöffneter Bug „Subagenten-Ausgabe statisch“)

Stand: 2026-11-15
Arbeitsbranch: `vibe/vibe-B14-1794737504673226349-1922610-22707`
Ausgangscommit: `35233ff`
Arbeitsverzeichnis: isolierter Git-Worktree
`_logs/worktrees/vibe-B14-VYTbeT`
(Implementierung und erste Prüfungen liefen im Vorgänger-Worktree
`vibe-B14-z3J0Km` auf Branch `…1794734160214831259-1883146-22278`; der
byteidentische Stand wurde nach dem Laufneustart in diesen Worktree
übertragen — Patch- und Datei-Hashes deckungsgleich.)

## Wurzelursache

`live_subagent_output()` in `bin/vibe-web.py` fragte
`/api/session/<id>/message?limit=500&order=asc` ab. Echtes opencode
begrenzt `limit` auf 200 und antwortet bei 500 mit HTTP 400
`InvalidRequestError` („Expected a value less than or equal to 200“).
`opencode_request()` liefert dafür `None`, die Live-Ausgabe bleibt leer und
die Karte fällt auf den erfassten statischen Ersttext zurück. Die bisherigen
Fake-Server akzeptierten `limit=500` und machten die Tests blind.

Am laufenden System verifiziert (Befund des Koordinators):

| Anfrage | Ergebnis |
| --- | --- |
| `/api/session/<id>/message?limit=500&order=asc` | HTTP 400 `InvalidRequestError` |
| `/api/session/<id>/message?limit=200&order=asc` | HTTP 200 |
| `/api/session/active` | HTTP 200 |
| `/api/session?limit=100` | HTTP 200 |

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `tests/unit/test_b14_subagent_output_live.py` | Fake-Laufserver validiert `limit` streng (400 bei >200); zwei neue Tests für LIVE-Ausgabe trotz Limit-Grenze und exakten Pfad `limit=200&order=asc` |
| `tests/unit/test_ap14_output_view_api.py` | Vertrag 500→200: Test umbenannt (`..._at_most_200_messages`), Docstrings/Kommentare angepasst |
| `tests/browser/test_b14_subagent_output_ui.py` | Fake-Laufserver validiert `limit` streng wie echtes opencode |
| `bin/vibe-web.py` | `limit=500` → `limit=200`; Docstring mit Begründung und Echt-System-Befund |
| `docs/features/B14.md` | Abschnitt „Erneuter Befund 15.11.“; Nachrichtenlimit in Ursache, Umsetzung und Grenzen auf 200 korrigiert |
| `docs/features/F30.md` | beide `limit=500`-Erwähnungen auf 200 korrigiert, Korrekturvermerk ergänzt |
| `docs/import-manifest.json` | Größe/SHA-256 von `bin/vibe-web.py` aktualisiert, B14-Änderungseintrag vom 15.11. ergänzt; **durch den Koordinator nach Review-Runde 3 erweitert:** Manifestsync der Fremdeinträge `bin/vibe` und `scripts/setup-vibe.py` (nur `bytes`/`sha256` neu berechnet, kein Inhaltswechsel an den Dateien) plus Begründungseintrag — die Veröffentlichungs-Commits 67d53bc/f609a3c/35233ff hatten die beiden Dateien ohne Manifestaktualisierung geändert und `check-import-manifest.py` (erster Bestandteil von VERIFY_PACKAGE) damit vorbestehend rot gehalten; die Abweichung wurde am Ausgangsstand `35233ff` identisch verifiziert |

Ein eigenes Manifest-Sync-Werkzeug gibt es im Repository nicht;
`scripts/check-import-manifest.py` prüft nur. Der `hinweis` in
`docs/import-manifest.json` verlangt, den Eintrag im selben Arbeitspaket zu
aktualisieren und zu begründen — so wurde verfahren. Die Datei wurde nicht
pauschal neu formatiert.

Keine Produktionsänderung außer `limit=500` → `limit=200` und dem
zugehörigen Docstring.

## Rotphase (vor Produktionsänderung)

Fake-Laufserver beider Suiten validieren `limit` wie echtes opencode:
`/message` mit `limit>200` → HTTP 400 mit
`{"_tag":"InvalidRequestError","message":"Expected a value less than or
equal to 200\n  at [\"limit\"]","kind":"Query"}`; `limit≤200` liefert die
V2-Projektionsnachrichten mit LIVE-Text.

### Unit B14

```
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.unit.test_b14_subagent_output_live -v
Ran 15 tests in 8.249s
FAILED (failures=6)
```

Fehlschläge (alle dieselbe Ursache: angefragtes `limit=500` → HTTP 400 →
statischer Fallback):

- `test_real_opencode_limit_cap_still_serves_live_output` (neu):
  `'LIVE-A-4711' not found in '... STATISCH-4711'`
- `test_message_request_uses_the_accepted_limit` (neu):
  `'/api/session/ses_kind/message?limit=200&order=asc' not found in
  ['/api/session/ses_kind/message?limit=500&order=asc']`
- zusätzlich deckten die bisher blinden Live-Tests denselben Fehler auf:
  `test_live_output_comes_from_the_run_server_endpoint`,
  `test_second_poll_returns_refreshed_live_output`,
  `test_two_active_projects_use_their_own_endpoints`,
  `test_the_password_stays_secret` (jeweils fehlender LIVE-Text,
  statischer Text geliefert)

### Unit AP14

```
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.unit.test_ap14_output_view_api -v
Ran 16 tests in 3.824s
FAILED (failures=1)
```

- `test_live_output_requests_at_most_200_messages`:
  `'limit=200' not found in
  '/api/session/ses_child2/message?limit=500&order=asc'`

### Browser B14

```
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.browser.test_b14_subagent_output_ui -v
Ran 2 tests in 42.023s
FAILED (failures=2)
```

- `test_running_card_refreshes_through_the_private_run_server`:
  Karteninhalt `... STATISCH-4711`, LIVE-A-4711 fehlt.
- `test_the_card_never_shows_the_frozen_captured_first_text`:
  gleicher Befund.

## Grünphase (nach `limit=200`)

```
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.unit.test_b14_subagent_output_live -v
Ran 15 tests in 8.254s
OK

PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.unit.test_ap14_output_view_api -v
Ran 16 tests in 3.987s
OK

PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.browser.test_b14_subagent_output_ui -v
Ran 2 tests in 9.023s
OK
```

## Regressionen

```
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest \
  tests.unit.test_ap14_output_view_api tests.unit.test_f30_subagent_view \
  tests.unit.test_b12_background_subagents \
  tests.unit.test_b13_private_server_steering \
  tests.unit.test_b13_private_server_runner \
  tests.unit.test_b11_output_view_api -v
Ran 64 tests in 348.938s
FAILED (errors=1)
```

- Einziger Fehler:
  `test_b13_private_server_runner.SandboxPrivateServerTest.test_sandboxed_run_starts_the_private_server_inside_the_sandbox`
  — `subprocess.TimeoutExpired` nach 300 s beim Aufruf von
  `vibe-run.sh`. Dieser Fall ist bereits in `docs/features/B14.md`
  („Prüfungen“) als eigenständig umgebungsbedingt fehlschlagend
  dokumentiert (Sandbox-/bwrap-Lauf). Er berührt den geänderten
  Nachrichtenabruf nicht. Baseline-Gegenprobe im unveränderten
  `git archive`-Stand `35233ff`:

  ```
  python3 -m unittest tests.unit.test_b13_private_server_runner.SandboxPrivateServerTest.test_sandboxed_run_starts_the_private_server_inside_the_sandbox -v
  Ran 1 test in 300.068s
  FAILED (errors=1)
  subprocess.TimeoutExpired: ... vibe-run.sh ... timed out after 300 seconds
  ```

  Damit ist der Fehler am Ausgangsstand ohne B14-Änderung reproduziert
  und nicht durch dieses Paket verursacht.

```
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME \
  python3 -m unittest tests.browser.test_f30_subagent_view_ui -v
Ran 4 tests in 14.566s
OK
```

### `bash scripts/verify.sh quick`

Der Worktree enthält keine eingecheckte `.vibe/project.env` (per
`.gitignore` ausgeschlossen). Für die Prüfung wurde die lokale,
ignorierte `.vibe/project.env` aus der Installation übernommen.

```
FEHLT: bin/vibe: Größe weicht ab (Manifest 263019, Datei 257322)
FEHLT: bin/vibe: Prüfsumme weicht ab (Manifest 7f9982fbc228, Datei 6f68a8f27778)
FEHLT: scripts/setup-vibe.py: Größe weicht ab (Manifest 64185, Datei 70550)
FEHLT: scripts/setup-vibe.py: Prüfsumme weicht ab (Manifest 8665fb5b6070, Datei def52b1e2c59)
FEHLT: 4 Abweichung(en) zwischen Bestand und docs/import-manifest.json
```

Der eigene Eintrag `bin/vibe-web.py` stimmt nach der Aktualisierung; die
verbleibenden Abweichungen bestehen bereits am Ausgangscommit `35233ff`.
Gegenprobe im unveränderten `git archive`-Stand `35233ff`
(`/tmp/opencode/b14-base-check`):

```
python3 scripts/check-import-manifest.py
FEHLT: bin/vibe: Größe weicht ab (Manifest 263019, Datei 257322)
FEHLT: bin/vibe: Prüfsumme weicht ab (Manifest 7f9982fbc228, Datei 6f68a8f27778)
FEHLT: scripts/setup-vibe.py: Größe weicht ab (Manifest 64185, Datei 70550)
FEHLT: scripts/setup-vibe.py: Prüfsumme weicht ab (Manifest 8665fb5b6070, Datei def52b1e2c59)
FEHLT: 4 Abweichung(en) zwischen Bestand und docs/import-manifest.json
exit=1
```

(identisch zum Worktree; `git show HEAD:bin/vibe` = 257322 Bytes
gegenüber Manifest 263019, `git show HEAD:scripts/setup-vibe.py` = 70550
Bytes gegenüber Manifest 64185). **Nachtrag (Koordinator, nach Review-Runde
3):** Diese beiden Fremdeinträge wurden daraufhin im selben Arbeitspaket
synchronisiert (nur `bytes`/`sha256` nach der Methodik des F31-Manifestsyncs
neu berechnet, Begründungseintrag im Manifest; kein Inhaltswechsel an
`bin/vibe` oder `scripts/setup-vibe.py`). Einzeln ausgeführt:

```
python3 scripts/check-syntax.py
OK: 168 Python-, 8 Bash- und 3 JSON-Datei(en) syntaktisch geprüft.

python3 scripts/check-no-secrets.py
OK: keine Geheimnisse erkannt.
```

## Abschließende Prüfung am Endstand (Koordinator, 2026-11-15)

Nach dem Manifestsync der Fremdeinträge, ausgeführt im Arbeitsverzeichnis
`vibe-B14-VYTbeT` am uncommitteten Endstand (die ungetrackte
`.vibe/project.env` wurde wie vom Läufer üblich aus dem Projekt übernommen):

```
python3 scripts/check-import-manifest.py
OK: 57 Dateien stimmen mit docs/import-manifest.json überein.
exit=0

bash scripts/verify.sh quick
=== vibe-Prüfung: quick ===
OK: 57 Dateien stimmen mit docs/import-manifest.json überein.
OK: 168 Python-, 8 Bash- und 3 JSON-Datei(en) syntaktisch geprüft.
OK: keine Geheimnisse erkannt.
OK: Prüfung 'quick' erfolgreich. (Exit 0)
verify-exit=0
```

## Offene Punkte

- Keine blockierenden. Der B13-Sandbox-Fall
  (`test_sandboxed_run_starts_the_private_server_inside_the_sandbox`,
  Timeout nach 300 s) ist am Ausgangsstand `35233ff` identisch
  reproduziert und damit vorbestehend, nicht B14-verursacht (Gegenprobe
  `git archive 35233ff`, siehe Regressionsteil).
- Keine Commits durch den Umsetzer; der Koordinator committet.
