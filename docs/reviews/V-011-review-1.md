# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 4
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Jede nicht triviale Angabe mit Quelle/Datum | PASS | `bin/vibe_models.py:117-123` (quelle/datum-Pflicht), Katalog weist jede Angabe mit `art`, `quelle`, `datum` aus (`data/models.json:52-150` u. alle Modelleinträge) | `tests/unit/test_model_catalog.py::test_missing_source_is_reported`, `::test_missing_date_is_reported`, `::test_invalid_date_is_reported`; ausgelieferter Katalog: `::ShippedCatalogTest.test_catalog_matches_its_own_rules` |
| Unbekannte Werte zulässig | PASS | `bin/vibe_models.py:40-44, 107-109` (unbekannt = zulässiger Wert, keine Quelle nötig), UI zeigt „unbekannt" sichtbar (`bin/vibe-web.py:178, 978`) | `::test_unknown_values_are_allowed_without_source`, `::test_unknown_price_text_is_explicit`, Browser `::test_unknown_model_has_no_assessment` |
| Fakten und Einschätzungen getrennt | PASS | `bin/vibe_models.py:24-26, 115-116` (`art_falsch` bei Vermischung), UI-Trennung `bin/vibe-web.py:965-966` | `::test_facts_and_assessments_must_stay_separated`, Browser `::test_detail_separates_facts_and_assessments_with_sources` |
| Keine ungeprüften Preise oder Modell-IDs übernommen | PASS | `bin/vibe_models.py:347-390` (Altpreise→unbekannt), `data/models.json:1045-1109` (9 nicht übernommene Altbestände mit Grund/Quelle/Datum) | `::test_legacy_paid_price_is_not_adopted`, `::ShippedCatalogTest.test_legacy_paid_ids_are_not_adopted`, `::test_no_legacy_price_strings_are_used_as_facts`; unabhängiger Abgleich von mir: models.dev api.json (2026-10-30) bestätigt für alle 8 übernommenen IDs `cost.input/output/cache_read = 0`, Kontext/Ausgabe/Veröffentlichung/offene Gewichte/Bildfähigkeit exakt wie im Katalog; `opencode/nemotron-3-ultra-free` ist dort `deprecated` (Stützt `nicht_uebernommen`) |
| Ausklappbare Tabelle und Detailzeilen erhalten (SPEC.md:129-140) | PASS | `bin/vibe-web.py:952-996` (`<details>`, `data-model-row`, `data-model-detail`, Preis mit Währung/Einheit/Staffeln) | Browser `::test_table_is_collapsed_and_expands`, `::test_price_shows_currency_unit_and_tariff_tiers`, `::test_removed_model_is_marked`; Screenshot `docs/features/V-011-modellkatalog.png` von mir als Bild geprüft: entspricht dem beschriebenen Verhalten |

Ticket-Tests-Themen vollständig abgedeckt: fehlende Quellen ✓, veraltete Preise ✓ (`test_outdated_price_is_reported`, `MAX_PREIS_ALTER_TAGE` `bin/vibe_models.py:170-172`), unbekannte Modelle ✓ (`modell_unbekannt` `bin/vibe_models.py:303-305`), entfernte Modelle ✓ (`modell_entfernt` + UI-Markierung), Währung/Tarifeinheiten ✓, Browserdarstellung ✓. Installation (`bin/vibe_models.py` mitkopiert) getestet in `tests/unit/test_setup_vibe.py::test_fresh_install_copies_programs_templates_and_catalog`; Kostenrechnung via `is_free` gesichert (`bin/vibe:2079`).

## Findings
- [Minor] `bin/vibe-web.py:959-960` — Detailzeile „Kein Katalogeintrag" ist ohne Klick sichtbar
  - Evidence: Für verbundene Modelle ohne Katalogeintrag (`!m`-Zweig) wird `det.style.display='none'` nicht gesetzt (nur `bin/vibe-web.py:972` im bekannten Zweig). Die Detailzeile erscheint damit direkt unter der Zeile, sobald die Tabelle aufgeklappt ist; der erste Klick versteckt sie erst, statt sie zu öffnen. Im Screenshot sichtbar (opencode/fremd ohne Klick). Funktionalität bleibt erhalten; Browser-Test fällt nicht darauf auf, weil er immer zuerst die Zeile anklickt.
  - Required fix: `det.style.display='none'` auch im `!m`-Zweig setzen (Coder); Browser-Test ergänzen, der die Detailzeile für ein unbekanntes Modell ohne Klick als versteckt prüft.
- [Minor] `bin/vibe_models.py:135-138` — `cache_schreiben` ungeprüft, wenn `cache_lesen` vorhanden
  - Evidence: `tarif.get("cache_lesen", tarif.get("cache_schreiben"))` liest `cache_schreiben` nur, wenn `cache_lesen` fehlt. Ein Tarif `{"cache_lesen": 0, "cache_schreiben": "n/a"}` mit ungültigem `cache_schreiben` wird als gültig durchgelassen, obwohl SPEC.md:139 getrennte Cachepreise fordert.
  - Required fix: beide Schlüssel einzeln validieren (Coder); ggf. Testfall für `cache_schreiben` neben `cache_lesen`.
- [Minor] `bin/vibe_models.py:293-305` und `309-327` — doppelte Fachregel `modell_entfernt`/`modell_unbekannt`
  - Evidence: Dieselbe Abgleichslogik existiert zweimal (roh im Katalog in `validate`, auf der Sicht in `compare`). Aktuell fehlerfrei und durch Tests gedeckt, aber ein späterer Pflegeschritt an nur einer Stelle divergiert. In `bin/vibe:1726` wird `compare` bewusst ergänzend genutzt, weil `load()` ohne `aktuell` lädt.
  - Required fix: auf Dauer eine interne Hilfsfunktion fasern, die `validate` und `compare` gemeinsam nutzen; keine Blocking-Anforderung.
- [Minor] `docs/features/V-011.md:93-94` — Formulierung „acht `opencode/*-free`-IDs" unpräzise
  - Evidence: Nur 7 der 8 geführten IDs enden auf `-free`; `opencode/big-pickle` (`data/models.json:152`) trägt das Suffix nicht. `models.json` macht die Aussage selbst nicht, nur die Feature-Doku.
  - Required fix: Formulierung nachziehen („acht bestätigte opencode-IDs" o. ä.); rein dokumentarisch.

## Verification
- Change set reviewed: `2d78d04..working tree` — jedoch nicht per Git: Shell-/Git-Zugriff wurde in dieser Sitzung von den Berechtigungen verweigert (`permission.rejected: shell` für `git status` und `git diff`). Verwendete Grundlage: der gelieferte Diff `/tmp/opencode/.../v011-diff-1.patch` (11 Dateien, deckungsgleich mit der Paketliste) plus vollständige Direktlektüren der Arbeitsbaumdateien, die das Post-Image des Diffs bestätigen (`bin/vibe_models.py` 469 Zeilen, `bin/vibe` Änderungen bei :39, :1598, :1713-1737, :2079, :2536-2537, :2625, `bin/vibe-web.py` :183, :911-996, `data/models.json` vollständig 1110 Zeilen, beide Testdateien, `scripts/setup-vibe.py:30`, `docs/import-manifest.json`).
- Git commands run by me: none (verweigert).
- Checks with supplied output (vom Coding-Agenten, nicht von mir ausgeführt): `unittest tests.unit.test_model_catalog` 32 OK, Browser 6 OK, `verify.sh quick` Exit 0, `verify.sh full` im Mount-Namespace Exit 0 (585 Unit + 47 Browser), rot vor der `tarif`-Korrektur. Die rot-gesehen-Ausgabe des neuen Tests ist als Beleg angegeben und in sich stimmig (Fehlertext passt zu `_check_tarif`).
- Checks not independently run: alle Build-/Test-/verify-Läufe.
- Independent von mir: öffentlicher Abruf `https://models.dev/api.json` (lesend, 2026-10-30) — alle 8 übernommenen Modelle: Kosten tatsächlich 0 USD, `modalities.input` (bild ja/nein), Kontext, Ausgabe, `release_date`, `last_updated`, `open_weights` stimmen mit dem Katalog exakt überein; `nemotron-3-ultra-free` dort `status: deprecated`. Screenshot als Bild inhaltlich geprüft (kein Platzhalter; zeigt echte Oberfläche mit Befundblock, Detailzeilen, Staffelpreisen, Altbeständen).
- Important areas inspected: `bin/vibe_models.py` (vollständig), `bin/vibe` Katalog-/Kosten-/Doctor-Pfade, `bin/vibe-web.py` modelsCard und `/api/agents`, `data/models.json`, beide Testdateien, `scripts/setup-vibe.py`, `docs/import-manifest.json`, `docs/features/V-011.md`, Trilium-Verweis `docs/trilium-index.md`.
- Remaining risks: Die von mir nicht ausführbaren Läufe (Unit-/Browser-/verify.sh) sind agentenberichtet; die Sitzungsumgebungs-Problematik bei `verify.sh full` (15 vorbestehende Fehler laut Agent) ist plausibel, aber von mir nicht unabhängig auf dem Ausgangscommit reproduziert. Kein Hinweis auf Geheimdaten, Scope-Überschreitung oder textbook-Testumgehung (keine Skips, keine Assert-Weisungen, keine entkernten Tests).

Urteil: **PASS** — kein Critical-/High-/Medium-Befund; die vier Minor-Befunde sind lokal, dokumentiert und blockieren nicht.
