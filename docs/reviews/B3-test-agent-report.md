# B3 (neu) — Unabhängiger Test-Agent: Bericht

Arbeitspaket: B3 (neue ID; altes B3 „Kennwortdatei“ ist ein anderes Thema).
Basis-Commit: `d53efa4`, Branch `feature/korbat/ap3-korbat`.
Neue Testdatei: `tests/unit/test_b3_merged_waiting.py` (26 Fälle).
Testbefehl:

```
python3 -m unittest tests.unit.test_b3_merged_waiting -v
```

Es wurden **keine** Produktionsdateien, keine bestehenden Tests und keine
Konfiguration geändert. `git status` zeigt nur die neue Testdatei.

## 1. Testfälle

Legende: V = Vorbedingung, A = Aktion, E = Erwartung, F = Fehlerfall.
Alle Zustandsfälle laufen in temporären Projektordnern mit einem echten
lokalen Git-Repository und einem echten Commit (siehe §3).

### AK1 — abgehaktes TICKETS.md-Paket mit zitierten Markern gilt als erledigt

| # | Testname | V / A / E / F |
|---|---|---|
| 1 | `TicketEntryDonePrecedenceTest.test_checked_ticket_with_quoted_waiting_marker_is_done` | V: `- [x]`, gültiger Nachweis, wörtlich zitierte `WARTET AUF MERGE:`-Zeile. A: `_parse_entry(..., need_proof=False)`. E: `erledigt`. F: gemergtes Paket bleibt „WARTET AUF MERGE“. |
| 2 | `TicketEntryDonePrecedenceTest.test_checked_ticket_with_quoted_blocked_marker_is_done` | V: `- [x]`, gültiger Nachweis, zitierte `BLOCKIERT:`-Zeile. A: wie 1. E: `erledigt`. F: erledigtes Paket bleibt „BLOCKIERT“. |
| 3 | `OpenItemsDonePrecedenceTest.test_open_items_omits_done_tickets_with_quoted_markers` | V: zwei `- [x]`-Pakete mit Nachweis, eines zitiert `WARTET AUF MERGE:`, eines `BLOCKIERT:`. A: `open_items("proj")`. E: beide IDs fehlen in der offenen Liste. F: gemergtes Paket steht weiter offen/wartend/blockiert. |
| 4 | `StatusReportDonePrecedenceTest.test_status_report_lists_checked_ticket_with_quoted_waiting_as_done` | V: `- [x]` + Nachweis + zitierte Wartemarke. A: `status_report(project)`. E: ID unter `done`, nicht unter `waiting/blocked/open`. F: Live-Fehler AP5 (falsch in `waiting`). |
| 5 | `StatusReportDonePrecedenceTest.test_status_report_lists_checked_ticket_with_quoted_blocked_as_done` | V: `- [x]` + Nachweis + zitierte Blockiermarke. A: `status_report`. E: `done`, nicht `blocked`. F: belegtes Paket bleibt blockiert. |

### AK2 — abgehaktes FEEDBACK.md mit gültigem Nachweis gilt als erledigt

| # | Testname | V / A / E / F |
|---|---|---|
| 6 | `TicketEntryDonePrecedenceTest.test_checked_feedback_with_quoted_waiting_marker_and_proof_is_done` | V: `- [x]`, gültiger Nachweis, zitierte `WARTET AUF MERGE:`. A: `_parse_entry(..., need_proof=True)`. E: `erledigt`. F: Feedback bleibt wartend. |
| 7 | `TicketEntryDonePrecedenceTest.test_checked_feedback_with_quoted_blocked_marker_and_proof_is_done` | V: `- [x]`, gültiger Nachweis, zitierte `BLOCKIERT:`. A: wie 6. E: `erledigt`. F: Feedback bleibt blockiert. |
| 8 | `OpenItemsDonePrecedenceTest.test_open_items_omits_done_feedback_with_quoted_waiting_marker_and_proof` | V: `- [x]` + Nachweis + zitierte Wartemarke. A: `open_items("proj")`. E: ID fehlt. F: erledigtes Feedback bleibt wartend sichtbar. |
| 9 | `StatusReportDonePrecedenceTest.test_status_report_lists_checked_feedback_with_quoted_waiting_as_done` | V: wie 8. A: `status_report`. E: ID unter `done`, nicht `waiting`. F: erledigtes Feedback bleibt wartend. |

### AK3 — Bestandsschutz: echte Marker bleiben erhalten

| # | Testname | V / A / E / F |
|---|---|---|
| 10 | `TicketEntryDonePrecedenceTest.test_unchecked_ticket_with_genuine_waiting_marker_stays_waiting` | V: `- [ ]` + echter `WARTET AUF MERGE:`. A: `_parse_entry`. E: `WARTET AUF MERGE`. F: Erledigt-Vorrang verdeckt echte Wartezustände. |
| 11 | `TicketEntryDonePrecedenceTest.test_unchecked_ticket_with_genuine_blocked_marker_stays_blocked` | V: `- [ ]` + echter `BLOCKIERT:`. A: `_parse_entry`. E: `BLOCKIERT`. F: blockierte Einträge gelten als erledigt. |
| 12 | `TicketEntryDonePrecedenceTest.test_unchecked_ticket_with_both_markers_stays_blocked` | V: `- [ ]` + beide echten Marker. A: `_parse_entry`. E: `BLOCKIERT` gewinnt. F: WARTET verdrängt BLOCKIERT. |
| 13 | `TicketEntryDonePrecedenceTest.test_checked_feedback_with_genuine_waiting_marker_but_no_proof_keeps_marker` | V: `- [x]`, echter Wartemarker, **kein** gültiger Nachweis. A: `_parse_entry(..., need_proof=True)`. E: `WARTET AUF MERGE` (nicht `erledigt`, nicht `ohne Nachweis`). F: Häkchen ohne Nachweis gilt als erledigt oder verliert den Markenzustand. |
| 14 | `TicketEntryDonePrecedenceTest.test_checked_feedback_with_genuine_blocked_marker_but_no_proof_keeps_marker` | V: `- [x]`, echter Blockiermarker, kein Nachweis. A: wie 13. E: `BLOCKIERT`. F: blockierte Einträge automatisch erledigt. |
| 15 | `OpenItemsDonePrecedenceTest.test_open_items_keeps_unchecked_genuine_waiting_and_blocked` | V: offenes wartendes + offenes blockiertes Paket. A: `open_items`. E: `("T1", …, WARTET AUF MERGE)` und `("T2", …, BLOCKIERT)`. F: Vorrang verdeckt echte Marken. |
| 16 | `StatusReportDonePrecedenceTest.test_status_report_keeps_unchecked_waiting_and_blocked` | V: wie 15. A: `status_report`. E: T1 in `waiting`, T2 in `blocked`, beide nicht `done`. F: echte Marken verschwinden. |
| 17 | `StatusReportDonePrecedenceTest.test_status_report_keeps_checked_feedback_without_proof_in_marker_state` | V: `- [x]` + echter Wartemarker ohne Nachweis. A: `status_report`. E: bleibt in `waiting`, nicht `done/open`. F: Häkchen ohne Nachweis gilt als erledigt. |

### AK7 — Regressionsschutz: `priority_view`/`standard` unverändert

| # | Testname | V / A / E / F |
|---|---|---|
| 18 | `StatusReportDonePrecedenceTest.test_priority_view_treats_checked_proven_package_with_quoted_waiting_as_done` | V: `PACKAGE_ORDER="T1,T2"`, T1 `- [x]` + Nachweis + zitierte Wartemarke, T2 offen. A: `priority_view`. E: `order` T1 `erledigt`; `standard` enthält T1 nicht, T2 `offen`. F: Ansichten weichen von `status_report` ab. **Im Rotlauf bereits grün (Schutzwache).** |
| 19 | `StatusReportDonePrecedenceTest.test_priority_view_keeps_genuine_waiting_unchanged` | V: T1 offen + echter Wartemarker, T2 offen. A: `priority_view`. E: `order` und `standard` T1 `wartet auf Merge`. F: echte Wartezustände werden verändert. **Im Rotlauf grün (Schutzwache).** |

### AK5 — klassische Oberfläche `bin/web/app.js`

| # | Testname | V / A / E / F |
|---|---|---|
| 20 | `ClassicGuiPackageCloseTest.test_classic_ticket_card_offers_package_close_button` | V: Funktion `ticketCard`. A: Region prüfen. E: enthält „Paket abschließen“. F: Button fehlt in der klassischen UI. |
| 21 | `ClassicGuiPackageCloseTest.test_classic_package_close_posts_to_the_package_endpoint` | V: Button in `ticketCard`. A: `api('/api/package', {…})` prüfen. E: sendet `name`, `id: i.id`, `action: 'close'`. F: falscher Endpunkt / fehlende ID. |
| 22 | `ClassicGuiPackageCloseTest.test_classic_package_close_is_limited_to_blocked_and_waiting_tickets` | V: `ticketCard`. A: Zustandsbedingung prüfen. E: echte `i.state`-Bindung an `BLOCKIERT` und `WARTET AUF MERGE` (Vergleich oder `[…].includes(i.state)`). Damit kein Button für `offen`, `ohne Nachweis`, `erledigt`. F: Button bei jedem Paket oder fehlt bei wartenden. |
| 23 | `ClassicGuiPackageCloseTest.test_classic_package_close_reports_backend_message_and_refreshes` | V: Button in `ticketCard`. A: Umgebung des Buttons prüfen. E: `/api/package`, `toast`, `message`, `detail(name)` im Umfeld. F: Fehler unsichtbar oder Ansicht veraltet. |
| 24 | `ClassicGuiPackageCloseTest.test_classic_feedback_card_offers_no_package_close` | V: `feedbackCard`. A: Region prüfen. E: kein „Paket abschließen“, kein `/api/package`. F: Feedback ließe sich als Paket abschließen. **Im Rotlauf grün (Schutzwache).** |

### AK6 — i18n `bin/web/i18n.js`

| # | Testname | V / A / E / F |
|---|---|---|
| 25 | `I18nPackageCloseTest.test_english_dictionary_translates_package_close` | V: `DICTS.en`. A: Eintrag für „Paket abschließen“ suchen. E: nichtleerer englischer Wert, nennt „package“, ist nicht der Schlüssel. F: englische UI zeigt Deutsch. |
| 26 | `I18nPackageCloseTest.test_german_dictionary_keeps_package_close_identity` | V: `DICTS.de` (ab `de: {`). A: Eintrag prüfen. E: Identitätspaar `"Paket abschließen": "Paket abschließen"`. F: deutscher Default fällt auf Englisch zurück. |

## 2. Rotphase (unveränderter Bestand)

Befehl und Ergebnis:

```
$ python3 -m unittest tests.unit.test_b3_merged_waiting -v
...
Ran 26 tests in 0.333s

FAILED (failures=15)
exit code 1
```

15 Fälle sind wie vorgesehen rot; die 11 übrigen sind Schutzwachen und im
Bestand korrekt grün (AK3-Bestandsschutz, AK7, Feedback-Karte ohne Button).

Auszüge der beobachteten Fehler (echtes Verhalten, keine Attrappen):

```
test_checked_ticket_with_quoted_waiting_marker_is_done
AssertionError: 'erledigt' != 'WARTET AUF MERGE'
 {'id': 'T1', ..., 'state': 'WARTET AUF MERGE', 'checked': True}

test_checked_feedback_with_quoted_blocked_marker_and_proof_is_done
AssertionError: 'erledigt' != 'BLOCKIERT'
 {'id': 'F2', ..., 'state': 'BLOCKIERT', 'checked': True}

test_status_report_lists_checked_ticket_with_quoted_waiting_as_done
AssertionError: 'T1' not found in []
 {'open': [], 'waiting': ['T1'], 'blocked': [], 'done': []}

test_open_items_omits_done_tickets_with_quoted_markers
AssertionError: 'T1' unexpectedly found in ['T1', 'T2']
 [('T1', 'Gemergt', 'WARTET AUF MERGE'), ('T2', 'Gemergt', 'BLOCKIERT')]

test_classic_ticket_card_offers_package_close_button
AssertionError: 'Paket abschließen' not found in <ticketCard>

test_english_dictionary_translates_package_close
AssertionError: Kein englischer Eintrag
```

Zusätzlich live reproduziert (Bestand, nur gelesen):

```
python3 -c '... vibe_packages.status_report(".")'
{'open': ['AP3-Korbat'], 'waiting': ['AP5-Korbat'], 'blocked': [],
 'done': ['AP1', 'AP2-Korbat', 'AP4-Korbat', 'B1', 'B2']}
```

Damit ist der vom Projektordner gemeldete Fehler (AP5-Korbat fälschlich
„wartet auf Merge“) unabhängig bestätigt.

## 3. Fixture-Grenzen und Hinweise

- **Echter Nachweis:** `proof_ok`/`_proof_ok` prüfen `Commit:` per
  `git cat-file`. Die Tests legen deshalb im temporären Elternordner ein
  echtes Git-Repository mit einem Commit an; die Blöcke zitieren dessen
  Kurzhash. Attrappen ersetzen den Nachweis nicht.
- **Isolation:** `bin/vibe` wird mit eigenem `VIBE`, `HOME` und
  `VIBE_NO_CONTAINER=1` geladen. Keine produktive Konfiguration, keine
  Netz- oder Modellaufrufe, keine GitHub-Aufrufe.
- **Nur Zustand, keine Datei-Umschreibung:** Die Fälle prüfen die
  Klassifikation (`_parse_entry`, `open_items`, `status_report`,
  `priority_view`); sie verlangen keine Änderung an TICKETS.md/FEEDBACK.md.
- **GUI nur strukturell:** Browser/Playwright steht nicht zur Verfügung.
  AK5/AK6 sind Quelltext-/Strukturassertionen wie in
  `test_ap5_korbat_waiting_state.py`. Nicht geprüft werden echtes Klicken,
  Layout/Position und das tatsächliche DOM-Verhalten. Die Bedingung in Fall
  22 erwartet eine positive `i.state`-Bindung an `BLOCKIERT`/`WARTET AUF
  MERGE` innerhalb von `ticketCard`; eine Auslagerung des Buttons in eine
  Top-Level-Hilfsfunktion außerhalb von `ticketCard` würde die Strukturtests
  nicht erfüllen.
- **AK4:** `tests/unit/test_ap5_korbat_waiting_state.py` wurde nicht
  verändert; der Bestand läuft weiterhin grün (`Ran 23 tests … OK`).
- **Teil 3 des Arbeitspakets** (Prozessfrage zum weitergezogenen
  `dev`-Branch) ist laut Auftrag nicht Testgegenstand.

## 4. Status

- Testdatei: `tests/unit/test_b3_merged_waiting.py`, 26 Fälle.
- Rotphase: 15/26 rot, 11/26 Schutzwachen grün, Exit 1.
- Grünphase nach Implementierung: offen; nach der Umsetzung ist derselbe
  Befehl erneut auszuführen. Assertions werden dabei nicht abgeschwächt.
