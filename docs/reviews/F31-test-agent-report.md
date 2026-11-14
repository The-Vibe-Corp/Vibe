# F31 — Bericht des unabhängigen Test-Agenten

Datum: 2026-11-14
Arbeitsverzeichnis: Worktree `vibe-F31-N1npLh`, Branch `vibe/vibe-F31-1794682474164702373-1018184-17273`
Grundlage der Fälle: Arbeitspaket F31, `SPEC.md`, `AGENTS.md`, Nutzerentscheidung
F16 (q2fbff67a1c60: „Ansehen und bearbeiten“, integrierte Karte in der
Assistent-Ansicht). Die Tests wurden **vor** der Implementierung geschrieben
und ausführt; es existierte keine Implementierung der geplanten Schnittstellen.

## Testdateien

- `tests/unit/test_f31_agents_file.py` — Unit-Tests für `agents_file_view`,
  `agents_file_save`, `agents_file_create` in `bin/vibe`.
- `tests/browser/test_f31_agents_file_ui.py` — Browserabnahme für die Karte in
  der Assistent-Ansicht und die Web-API `GET/POST /api/agents_file`.

Beide Dateien entstanden ausschließlich durch den Test-Agenten; es wurden keine
bestehenden Tests, keine Produktionsdateien und keine Prüfskripte verändert.
Isolierte Fixtures: eigene temporäre Arbeitsbereiche, kopierte Vorlagen nach
`<root>/_toolchain/templates`, eigene `HOME`-/`VIBE_*`-Umgebung, keine
produktiven Konfigurationen, keine Modellaufrufe.

## Testbefehle

- `python3 -m unittest tests.unit.test_f31_agents_file -v`
- `python3 -m unittest tests.browser.test_f31_agents_file_ui -v`
  (Playwright-Browserpfad: `~/.cache/ms-playwright`, im Test gesetzt)

## Fälle (Unit, `tests/unit/test_f31_agents_file.py`)

Vorbedingung für alle Fälle: isolierter temporärer Arbeitsbereich, Projekt
`proj` (Typ generic), `webproj` (Typ web), `fancyproj` (unbekannter Typ
`fancyx`), `bin/vibe` isoliert geladen, eigene Vorlagenkopie.

| Nr. | Testname | Aktion | Erwartetes Ergebnis | AK |
| --- | --- | --- | --- | --- |
| 1 | `test_view_splits_managed_block_from_free_parts` | AGENTS.md = `Kopfteil-F31\n` + Block + `\nFußteil-F31\n`; `agents_file_view("proj")` | `exists=True`; `before`/`managed`/`after` exakt getrennt, `managed` byte-identisch mit `GENERAL_RULES`, Digest gesetzt | AK1 |
| 2 | `test_view_without_markers_reports_whole_text_as_after` | AGENTS.md ohne Marker; `view` | `managed=None`, `after`=gesamter Text, `exists=True`, Digest gesetzt | AK1 |
| 3 | `test_view_missing_file_reports_empty_view` | keine AGENTS.md; `view` | `exists=False`, alle Strings leer, `digest=""` | AK1 |
| 4 | `test_save_merges_free_parts_with_byte_identical_block` | `view`, dann `save("proj","Neu oben\n","Neu unten\n",digest)` (mit Spion auf `vibe_storage.write_text`) | Datei = `Neu oben\n` + Block byte-identisch + `Neu unten\n`; Schreiben ging mit `expected=<digest>` über die Speicherschicht (V-005); zweiter Lauf mit frischem Digest erfolgreich | AK3, AK7 |
| 5 | `test_save_rejects_stale_digest_and_leaves_file_untouched` | `view`, fremde Änderung an der Datei, `save` mit überholtem Digest | `ValueError`; Datei byte-identisch unverändert | AK4 |
| 6 | `test_save_rejects_markers_in_free_parts` | 6 Subtests: Mark-Start, Mark-Paar, Mark-End jeweils in `before` und in `after`; `save` mit gültigem Digest | je `ValueError`; Datei byte-identisch unverändert | AK5 |
| 7 | `test_save_without_block_writes_after_verbatim` | Datei ohne Block; `save(before="",after="Ersetzt ohne Block.\n",digest)` | Datei = `after` unverändert; kein Marker, kein Block eingefügt; View danach weiterhin `managed=None` | AK3, AK5 |
| 8 | `test_create_uses_type_template_with_name_replaced` | `agents_file_create("webproj")` ohne AGENTS.md | Inhalt = `templates/web/AGENTS.md` mit `{{NAME}}`→`webproj` | AK6 |
| 9 | `test_create_unknown_type_falls_back_to_generic` | `agents_file_create("fancyproj")` ohne AGENTS.md | Inhalt = `templates/generic/AGENTS.md` mit `{{NAME}}`→`fancyproj` | AK6 |
| 10 | `test_create_never_overwrites_existing_file` | vorhandene AGENTS.md; `create` | Rückgabe `kept`; Datei byte-identisch | AK6 |
| 11 | `test_unknown_or_traversal_names_are_rejected` | `view`/`create`/`save` mit `does-not-exist`, `proj/../webproj`, `../f31-outside` | Abweisung (`ValueError` oder `SystemExit`); nichts außerhalb der Projekte angelegt | AK7 |

## Fälle (Browser, `tests/browser/test_f31_agents_file_ui.py`)

Vorbedingung: echtes Dashboard auf eigenem Port, isolierter Arbeitsbereich mit
eigenen Vorlagen, Projekt `proj` mit Git-Repository, frische AGENTS.md je Test.

| Nr. | Testname | Aktion | Erwartetes Ergebnis | AK |
| --- | --- | --- | --- | --- |
| 12 | `test_card_shows_content_managed_block_and_explanation` | Projektdetail → Assistent-Tab; Karte „AGENTS.md — Regeln für Agenten“ | Karte vorhanden; Erklärung „… auf den aktuellen Stand gebracht und ist in der Bearbeitung geschützt“; zwei Textareas mit Kopf-/Fußteil; verwalteter Inhalt („Ordnung im Git halten“) sichtbar; Screenshot `docs/features/F31-agents-file.png` | AK1, AK2 |
| 13 | `test_editing_free_part_saves_file_and_keeps_block_identical` | after-Textarea ändern, „Speichern“ | Datei = `before` + Block byte-identisch + geändertes `after` | AK3 |
| 14 | `test_missing_file_can_be_created_from_template` | fehlende AGENTS.md; „Aus Vorlage anlegen“ | Datei = generic-Vorlage mit `{{NAME}}`→`proj`; Karte zeigt danach den Inhalt | AK6 |
| 15 | `test_get_view_and_unknown_post_action_are_rejected` | `GET /api/agents_file?name=proj`; `POST` mit `action:"f31-fremd"` | GET 200 mit View (before/after korrekt); POST wird mit Clientfehler (4xx) abgewiesen, Datei unverändert | AK8, AK5 |

## Ergänzte Fälle nach Review Runde 1, Finding 2 (AK7: Symlinks abgelehnt)

Der Review wies nach, dass der AK7-Teil „Symlinks abgelehnt“ in keinem Test
geprüft war. Die Implementierung lehnt Symlinks in `bin/vibe` ab
(`agents_file_view` → `exists=False`, `agents_file_save`/`agents_file_create`
→ `ValueError`). Ergänzt wurden drei Unit-Fälle in
`tests/unit/test_f31_agents_file.py` (Sektion AK7). Vorbedingung je Fall:
AGENTS.md des Projekts `proj` ist ein Symlink auf die echte Datei
`agents-real.md` im selben Projekt mit Inhalt `Zielinhalt-F31\n`.

Die Fälle sind mit
`@unittest.skipUnless(SYMLINKS_SUPPORTED, …)` versehen; die Probe
(`symlink_supported()`) prüft zur Modulladezeit per Funktionstest, ob
`os.symlink` in der Prüfumgebung tatsächlich anlegt, verlinkt und wieder
entfernt (FUSE/NTFS-Grenze, kein stiller Verzicht). Auf der aktuellen
Prüfumgebung lief die Probe erfolgreich — kein Fall wurde geskippt.

| Nr. | Testname | Aktion | Erwartetes Ergebnis | AK |
| --- | --- | --- | --- | --- |
| 16 | `test_view_rejects_symlink_and_reports_missing_file` | AGENTS.md als Symlink; `agents_file_view("proj")` | `exists=False`, `before=""`, `managed=None`, `after=""`, `digest=""`; Link-Ziel unverändert | AK7 |
| 17 | `test_save_rejects_symlink_and_leaves_target_untouched` | AGENTS.md als Symlink; `agents_file_save("proj", "Neu oben\n", "Neu unten\n", "0"*64)` | `ValueError`; Link-Ziel byte-identisch; AGENTS.md bleibt Symlink | AK7 |
| 18 | `test_create_rejects_symlink_and_leaves_target_untouched` | AGENTS.md als Symlink; `agents_file_create("proj")` | `ValueError`; Link-Ziel byte-identisch; der Symlink wurde weder überschrieben noch durch eine echte Datei ersetzt | AK7 |

## Rotphase (tatsächliche Ausgaben)

Alle Fälle wurden vor der Implementierung tatsächlich ausgeführt. Beleg im
Einzelnen:

### Unit: `python3 -m unittest tests.unit.test_f31_agents_file -v`

- Exit-Code: `1`
- Ergebnis: `Ran 11 tests — FAILED (errors=18)` (18 = 11 Tests + 7 Subtests)
- Fehlerbild: sämtliche Fehler sind `AttributeError` an den geplanten
  Schnittstellen, z. B.:
  - `AttributeError: module 'vibe_f31_agents_file_under_test' has no attribute 'agents_file_view'` (view/create/save-Fälle)
  - `AttributeError: ... has no attribute 'agents_file_create'`
  - `AttributeError: ... has no attribute 'agents_file_save'`
- Das Fixture (isoliertes Laden von `bin/vibe`, Projektfixtures, Vorlagenkopie)
  lief bei allen 11 Tests fehlerfrei durch; die Rotphase entsteht also
  ausschließlich an den geplanten, noch nicht vorhandenen Funktionen und nicht
  an Umgebungsproblemen.

### Browser: `python3 -m unittest tests.browser.test_f31_agents_file_ui -v`

- Exit-Code: `1`
- Ergebnis: `Ran 4 tests in 91.588s — FAILED (errors=4)`
- Fehlerbild:
  - 3 × `TimeoutError` beim Warten auf die AGENTS.md-Karte in `#guide`
    (`filter(has_text="Regeln für Agenten")` + Speichern-/Anlegen-Button):
    die Karte existiert in der Assistent-Ansicht noch nicht (AK1/AK2/AK3/AK6).
  - 1 × `HTTPError: HTTP Error 404: Not Found` bei
    `GET /api/agents_file?name=proj`: die geplante Web-API existiert noch
    nicht (AK8).
- Der Serverstart, das Erreichen des Projekts und die Playwright-Steuerung
  funktionieren; die Rotphase entsteht an den geplanten Schnittstellen.

## Hinweise für den Coding-Agenten (Vertragsanker der Tests)

- Die Karte ist über den sichtbaren Titeltext „Regeln für Agenten“ und einen
  `Speichern`- bzw. `Aus Vorlage anlegen`-Button innerhalb von `#guide`
  auffindbar; DOM-Klassen sind bewusst nicht vorgegeben. Die Karte braucht
  genau zwei `role="textbox"`-Eingaben (zuerst `before`, dann `after`).
- Erklärungstext für den geschützten Block muss die Teilzeichenkette
  „auf den aktuellen Stand gebracht und ist in der Bearbeitung geschützt“
  enthalten, und der verwaltete Inhalt muss sichtbar sein (geprüft über
  „Ordnung im Git halten“).
- Unbekannte Projektnamen/Traversal dürfen als `ValueError` oder `SystemExit`
  abgewiesen werden; Digest- und Marker-Abweisungen müssen `ValueError` sein
  und die Datei byte-identisch lassen.
- `save` muss den Digest-Schutz über `vibe_storage.write_text(expected=…)`
  durchreichen (V-005, atomar).

## Umgebungs-Baseline (nicht durch F31 verursacht)

- `python3 -m unittest tests.unit.test_project_guide` weist bereits vor F31
  einen bestehenden Fehler auf (`ProjectGuideApiTest.setUpClass`:
  „vibe-web ist nicht erreichbar“). Betroffen ist die API-Gruppe dieses
  Alt-Tests, nicht die F31-Dateien.

## Locator-Korrektur in der Browser-Testdatei (2026-11-14, Grünphase)

Befund vor der Korrektur: In `agents_card()` war der `has=`-Filter an einen
an `#guide` verankerten Locator gebunden:

```python
buttons = guide.get_by_role("button", name=re.compile(r"^Speichern$|^Aus Vorlage anlegen$"))
guide.locator("div").filter(has_text="Regeln für Agenten").filter(has=buttons)
```

`has=` bettet den Selektor Seite-relativ zum Kandidaten-Div ein. Der
Karten-Div liegt **innerhalb** von `#guide` und kann keinen weiteren
`#guide`-Nachfahren enthalten, daher lieferte der Filter immer 0 Treffer
(Beweis am echten DOM durch den Coding-Agenten:
`filter(has=page.get_by_role("button", name="Speichern")).count() == 3`,
`filter(has=guide.get_by_role(...)).count() == 0`).

Korrektur: Der `has=`-Filter nutzt jetzt einen **page-relativen**
Button-Locator (`self.page.get_by_role(...)`), die Suche bleibt weiterhin auf
`#guide` beschränkt, da der Kandidaten-Div-Suchraum `guide.locator("div")`
bleibt. Geändert wurden **nur die Locatoren**: Testfälle, fachliche
Erwartungen, AK-Zuordnung und Vertragsanker sind unverändert, keine
abgeschwächten Assertions. Geänderte Datei: `tests/browser/test_f31_agents_file_ui.py`.

## Grünphase (2026-11-14, nach Implementierung)

Beide Suiten wurden unverändert (abgesehen von der oben dokumentierten
Locator-Korrektur im Test selbst) erneut ausgeführt.

### Unit: `python3 -m unittest tests.unit.test_f31_agents_file -v`

- Erstlauf nach Implementierung (2026-11-14): Exit-Code `0`,
  `Ran 11 tests in 0.076s — OK`, alle 11 Fälle grün (inkl. Marker-Subtests in
  Fall 6).
- Nach Ergänzung der Symlink-Fälle (Review Runde 1, Finding 2, 2026-11-14):
  Exit-Code `0`, `Ran 14 tests in 0.125s — OK`, alle 14 Fälle grün, **kein
  Skip** (die Symlink-Probe war in der Prüfumgebung erfolgreich; alle drei
  neuen Fälle wurden tatsächlich ausgeführt).

### Browser: `python3 -m unittest tests.browser.test_f31_agents_file_ui -v`

- Exit-Code: `0`
- Ergebnis: `Ran 4 tests in 2.167s — OK`
- Alle 4 Fälle grün:
  - `test_card_shows_content_managed_block_and_explanation` (AK1, AK2) —
    Karte, zwei Textareas, Erklärungstext, verwalteter Block sichtbar,
    Screenshot `docs/features/F31-agents-file.png` erstellt.
  - `test_editing_free_part_saves_file_and_keeps_block_identical` (AK3) —
    Datei = before + Block byte-identisch + geändertes after.
  - `test_missing_file_can_be_created_from_template` (AK6) — generic-Vorlage
    mit `{{NAME}}`→`proj`, Karte zeigt den neuen Inhalt.
  - `test_get_view_and_unknown_post_action_are_rejected` (AK8, AK5) — GET 200
    mit korrekter View; POST mit unbekannter Aktion → 400 Bad Request,
    Datei unverändert.
- Nebenbefund (kein Fehler, keine Assertion abgeschwächt): Bei Fall 15 meldet
  Python ein `ResourceWarning: Implicitly cleaning up <HTTPError 400>` — das
  erwartete `HTTPError`-Objekt wird im except-Pfad nicht explizit geschlossen.
  Rein kosmetisch, verhält sich fachlich exakt wie erwartet.

## Status

- Rotphase: 15 Fälle (11 Unit inkl. Subtests als 18 Ergebnisse, 4 Browser) —
  allesamt fehlgeschlagen an den geplanten Schnittstellen. Belegt. (Vor der
  Ergänzung der Symlink-Fälle.)
- Grünphase: **abgeschlossen.** Unit 14/14 OK (Exit 0, kein Skip; Stand nach
  Review Runde 1, Finding 2), Browser 4/4 OK (Exit 0). Keine abgeschwächten
  Assertions, keine gelöschten Tests.
- Vom Test-Agenten gemeldete Implementierungsdefekte: keine.
