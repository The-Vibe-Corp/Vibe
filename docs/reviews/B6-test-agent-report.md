# B6 Test-Agent-Report (Rotphase-Nachweis)

Datum: 2026-11-22

## Deliverable
- tests/unit/test_b6_ticket_marker_states.py (final: 56 Testfälle)
- docs/reviews/B6-test-agent-report.md (aktualisiert)

## Phasen und echte Messergebnisse

### Phase 1 — erste Rotphase (am Baseline-Commit c3d68dd)
- Suite: 34 Fälle (`tests/unit/test_b6_ticket_marker_states.py`, erste Fassung).
- Ergebnis: 20 FAILED / 14 OK.
- Nachweis: bereits in der ersten Berichtsversion dokumentiert; Rotphase für R1–R5 belegt (Teilstring-Erkennung).

### Phase 2 — Suite-Konsolidierung nach Teilimplementierung (reine Blockende-Regel)
- Messzeitpunkt: NACH Teilimplementierung der reinen Blockende-Regel (nicht Baseline).
- Suite: 52 Fälle.
- Ergebnis: 12 FAILED / 40 OK.
- Kennzeichnung: Messung nach Teilimplementierung, NICHT als Baseline-Rotphase.

### Phase 3 — verbindlicher Rotphasen-Nachweis der finalen Suite am Baseline-Commit c3d68dd
- Methode: Wegwerf-Klon (`git clone --no-hardlinks` + `git checkout c3d68dd`, detached), finale Suite (56 Fälle) eingespielt, anschließend Klon entfernt (`rm -rf`).
- Ergebnis: 27 FAILED / 29 OK.
- FAILED-Testnamen:
  1. test_mark_blocked_cli_can_append_to_freetext_block
  2. test_mark_waiting_cli_can_append_to_freetext_block
  3. test_mark_blocked_appends_real_marker_to_freetext_block
  4. test_mark_blocked_is_idempotent_with_real_marker
  5. test_mark_waiting_merge_appends_real_marker_to_freetext_block
  6. test_mark_waiting_merge_is_idempotent_with_real_marker
  7. test_b5_like_block_is_not_blocked_or_waiting
  8. test_blocked_wins_over_waiting_in_head_field
  9. test_freetext_marker_is_not_a_blocked_state
  10. test_freetext_marker_is_not_a_waiting_state
  11. test_last_marker_wins_over_earlier_opposite_marker
  12. test_latest_position_wins_head_blocked_end_waiting
  13. test_latest_position_wins_head_waiting_end_blocked
  14. test_marker_after_description_not_last_does_not_count
  15. test_marker_in_title_does_not_count
  16. test_no_description_line_mid_marker_does_not_count
  17. test_priority_view_marks_freetext_block_as_open
  18. test_select_package_selects_freetext_block_when_only_candidate
  19. test_status_report_treats_freetext_block_as_open
  20. test_b5_like_feedback_block_is_open_everywhere
  21. test_freetext_marker_does_not_beat_draft
  22. test_freetext_marker_does_not_beat_in_progress
  23. test_open_items_freetext_block_is_open
  24. test_parse_entry_case_insensitive_marker_at_end
  25. test_parse_entry_freetext_uppercase_marker_is_open
  26. test_parse_entry_freetext_waiting_marker_is_open
  27. test_parse_entry_latest_position_head_blocked_end_waiting
- Gegenprobe Bestand am selben Klon: `tests.unit.test_b3_merged_waiting` → 26 OK (Teilstring-Implementierung).

### Phase 4 — Grünlauf in der Arbeitskopie (mit Implementierung)
- `python3 -m unittest tests.unit.test_b6_ticket_marker_states` → 56 OK.
- `python3 -m unittest tests.unit.test_b6_ticket_marker_states tests.unit.test_b3_merged_waiting tests.unit.test_ap5_korbat_waiting_state tests.unit.test_ap3_korbat_issues_backend tests.unit.test_package_gates` → 170 OK.

## Zielregel (Kopffeld/Endposition)
Eine `BLOCKIERT:`/`WARTET AUF MERGE:`-Marke zählt als Zustandsmarke genau dann, wenn sie (nach optionaler Einrückung, Groß-/Kleinschreibung egal) an einer Statusposition steht:
(a) letzte nichtleere Blockzeile, oder
(b) Kopffeld vor der ersten `Beschreibung:`-/`Erwartet:`-Zeile (nur wenn eine solche Zeile existiert).
Späteste Position gewinnt; im Kopffeld gewinnt `BLOCKIERT` über `WARTET AUF MERGE`.
Präzedenz unverändert: erledigt > BLOCKIERT > WARTET AUF MERGE > In-Progress > Draft > offen.

## Testfälle (final, 56)
1. test_freetext_marker_is_not_a_blocked_state — Freitext nicht Endzeile / is_blocked / False
2. test_freetext_marker_is_not_a_waiting_state — Freitext nicht Endzeile / is_waiting_merge / False
3. test_real_blocked_marker_at_block_end_counts — Endzeile BLOCKIERT / is_* / blocked True
4. test_real_waiting_marker_at_block_end_counts — Endzeile WARTET / is_* / waiting True
5. test_marker_matching_is_case_insensitive_at_block_end — kleingeschriebene Endmarke / is_* / True
6. test_last_marker_wins_over_earlier_opposite_marker — beide Marken, Endzeile BLOCKIERT / is_* / blocked True, waiting False
7. test_b5_like_block_is_not_blocked_or_waiting — B5-ähnlicher Block / is_* / beide False
8. test_head_marker_before_description_counts — Kopffeld-Marker vor Beschreibung / is_* / zählt
9. test_head_marker_before_expected_counts — Kopffeld-Marker vor Erwartet / is_blocked / True
10. test_head_marker_open_and_unproven_checked_variants — Kopffeld-Marker bei offen/abgehakt-ohne-Nachweis / is_blocked / True
11. test_marker_after_description_not_last_does_not_count — Marke nach Beschreibung, nicht letzte Zeile / is_blocked / False
12. test_latest_position_wins_head_blocked_end_waiting — Kopffeld-BLOCKIERT + Endzeile-WARTET / is_* / WARTET
13. test_latest_position_wins_head_waiting_end_blocked — Kopffeld-WARTET + Endzeile-BLOCKIERT / is_* / BLOCKIERT
14. test_blocked_wins_over_waiting_in_head_field — beide Marken im Kopffeld / is_* / BLOCKIERT
15. test_no_description_line_mid_marker_does_not_count — kein Beschreibungsstart, Marker mitten im Text / is_blocked / False
16. test_tab_indented_marker_with_trailing_whitespace_counts — Tab-Einrückung + Trailing-Whitespace als Endzeile / is_blocked / True
17. test_marker_in_title_does_not_count — Marke im Titel / is_blocked / False
18. test_status_report_treats_freetext_block_as_open — B5-ähnlicher Block / status_report / in open
19. test_status_report_treats_head_marker_block_as_blocked — Kopffeld-BLOCKIERT / status_report / in blocked
20. test_status_report_head_marker_unproven_checked_is_blocked — abgehakter Block ohne Nachweis mit Kopffeld-Marker / status_report / in blocked
21. test_select_package_selects_freetext_block_when_only_candidate — B5-ähnlicher Block / select_package / gewählt
22. test_select_package_skips_head_marker_block — Kopffeld-BLOCKIERT + offenes Paket / select_package / zweites gewählt
23. test_priority_view_marks_freetext_block_as_open — B5 in PACKAGE_ORDER / priority_view / „offen“
24. test_mark_blocked_appends_real_marker_to_freetext_block — Freitext-Block / mark_blocked / changed True, Endmarke
25. test_mark_blocked_is_idempotent_with_real_marker — nach erstem mark_blocked / zweiter Aufruf / changed False
26. test_mark_waiting_merge_appends_real_marker_to_freetext_block — Freitext-Block / mark_waiting_merge / changed True, Endmarke
27. test_mark_waiting_merge_is_idempotent_with_real_marker — nach erstem mark_waiting_merge / zweiter Aufruf / changed False
28. test_mark_blocked_cli_can_append_to_freetext_block — Freitext-Block / CLI mark-blocked / Exit 0
29. test_mark_waiting_cli_can_append_to_freetext_block — Freitext-Block / CLI mark-waiting / Exit 0
30. test_b5_like_feedback_block_is_open_everywhere — B5-ähnlicher FEEDBACK-Block / alle Funktionen / offen + auswählbar
31. test_parse_entry_freetext_uppercase_marker_is_open — Freitext-Marker / _parse_entry / „offen“
32. test_parse_entry_freetext_waiting_marker_is_open — Freitext-Marker / _parse_entry / „offen“
33. test_parse_entry_real_blocked_marker_at_end — Endmarke / _parse_entry / „BLOCKIERT“
34. test_parse_entry_real_waiting_marker_at_end — Endmarke / _parse_entry / „WARTET AUF MERGE“
35. test_parse_entry_case_insensitive_marker_at_end — kleingeschriebene Endmarke / _parse_entry / „BLOCKIERT“
36. test_parse_entry_blocked_wins_over_waiting — beide Marken, Endzeile BLOCKIERT / _parse_entry / „BLOCKIERT“
37. test_parse_entry_head_marker_before_description — Kopffeld-Marker vor Beschreibung / _parse_entry / „BLOCKIERT“
38. test_parse_entry_head_marker_before_expected — Kopffeld-Marker vor Erwartet / _parse_entry / „WARTET AUF MERGE“
39. test_parse_entry_head_marker_unproven_checked — abgehakter Block ohne Nachweis mit Kopffeld-Marker / _parse_entry / „BLOCKIERT“
40. test_parse_entry_latest_position_head_blocked_end_waiting — Kopffeld-BLOCKIERT + Endzeile-WARTET / _parse_entry / „WARTET AUF MERGE“
41. test_parse_entry_latest_position_head_waiting_end_blocked — Kopffeld-WARTET + Endzeile-BLOCKIERT / _parse_entry / „BLOCKIERT“
42. test_parse_entry_blocked_wins_in_head_field — beide Marken im Kopffeld / _parse_entry / „BLOCKIERT“
43. test_open_items_freetext_block_is_open — Freitext-Block / open_items / „offen“
44. test_open_items_real_blocked_marker_at_end — Endmarke / open_items / „BLOCKIERT“
45. test_open_items_real_waiting_marker_at_end — Endmarke / open_items / „WARTET AUF MERGE“
46. test_open_items_head_marker — Kopffeld-Marker / open_items / „BLOCKIERT“
47. test_real_markers_not_selectable — blockiert/wartend/offen / select_package / T3
48. test_status_report_classifies_real_markers — blockiert/wartend/offen / status_report / Listen korrekt
49. test_priority_view_real_markers — blockiert/wartend / priority_view / gesperrt/wartet auf Merge
50. test_draft_block_is_skipped_by_select_package — Entwurf/offen / select_package / T2
51. test_apply_proof_still_removes_real_markers — Marker + Nachweis / sync_proof / Marker entfernt
52. test_done_precedes_marker — abgehakter Block mit Freitext-Marker / _parse_entry / „erledigt“
53. test_real_marker_at_state_position_beats_in_progress — in-progress + Kopffeld-Marker / _parse_entry / „BLOCKIERT“
54. test_real_marker_at_state_position_beats_draft — draft + Endzeile-WARTET / _parse_entry / „WARTET AUF MERGE“
55. test_freetext_marker_does_not_beat_in_progress — in-progress + Freitext-Marker / _parse_entry / „In Progress“
56. test_freetext_marker_does_not_beat_draft — draft + Freitext-Marker / _parse_entry / „Draft“

## Konfliktlösung (AP3-Präzedenzvertrag)
Die ursprünglichen Fälle 33/34 („Status schlägt Marke“) wurden durch `test_real_marker_at_state_position_beats_in_progress`/`..._draft` ersetzt (echte Marke an Statusposition gewinnt) plus Freitext-Gegenfälle `test_freetext_marker_does_not_beat_in_progress`/`..._draft`. Begründung: Runner-Schranken dürfen nicht durch In-Progress/Draft maskiert werden (Sicherheitsprinzip, AP3-Konsistenz).

## Modul-/Klassendocstrings
- Moduldocstring: „Statusmarken zählen nur an Statuspositionen (letzte nichtleere Blockzeile oder Kopffeld vor der ersten Beschreibung:/Erwartet:-Zeile); Freitext zählt nicht.“
- `MarkerLastLineSemanticsTest`: Statuspositionen (letzte nichtleere Zeile oder Kopffeld vor Beschreibung/Erwartet); Freitext an anderen Positionen zählt nicht.

## Nicht abgedeckt
- Keine GUI/i18n-Prüfungen.
- Keine Git-Proof-Tests mit echten Commits; `_parse_entry` mit `need_proof=False`/`True` deckt Präzedenz ab.

## Blocker
- Keine. Tests laufen deterministisch ohne Netz/Modellaufrufe.