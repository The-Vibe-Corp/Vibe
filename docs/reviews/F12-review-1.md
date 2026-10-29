# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: PASS

## Acceptance criteria
| Kriterium | Status | Implementierung (Datei:Zeile) | Test/Beleg |
|---|---|---|---|
| Tokenstatistik je AP: Eingabe, davon cached, Ausgabe je Modell/Agent | PASS | `bin/vibe:1570` (`_usage_add`: input += input+cache_read, output += output+reasoning), `bin/vibe:1737` (`_project_stats`), `bin/vibe:1726` (`_package_of` inkl. Unteragenten über `parent_id`) | `tests/unit/test_costs.py` `TokenAggregationTest.test_cached_tokens_belong_to_input_and_reasoning_to_output`, `test_subagent_messages_count_towards_the_parent_package`, `test_unassigned_sessions_form_their_own_package`; gelieferte Ausgabe „Ran 34 tests OK“ |
| Kosten je AP in Euro mit dem Preis des Modells/Agents | PASS | `bin/vibe:1528` (`_cost_of`), `bin/vibe:1516` (`_price_for`), `bin/vibe:55`-Basis (EUR, 1 Mio. Tokens) | `test_costs_are_calculated_from_tokens_and_prices` (0,0111/0,0115 €, rechnerisch korrekt), Browser: „3,1000 €“; Screenshot `docs/features/F12-kosten.png` von mir als echtes UI-Bild gesichtet |
| Summe aller AP = Projektstatistik | PASS | `bin/vibe:1744``1869` (total in `_project_stats`), `bin/vibe:1802` (`costs_overview`, Projektsumme als Gesamtprojekt) | `test_project_total_is_the_sum_of_all_packages` (inkl. Kosten, Sessions, 4 Sitzungen), `test_overview_lists_every_project_with_its_totals` |
| Unbekannter Preis → 0 € | PASS | `bin/vibe:1516-1526` („unbekannt“ → 0-Preis), Warnhinweis in `cmd_costs` `bin/vibe:1854` | `test_unknown_model_price_is_zero`, `test_a_price_file_in_another_currency_is_not_treated_as_euro` (USD ≠ EUR), Browsertest `test_detail_shows_packages_models_and_unknown_prices` |
| Nutzereingabe der einzelnen Kosten möglich, überschreibt systemische Preise | PASS | UI: `bin/vibe-web.py:791` (Preisfelder), `bin/vibe-web.py:795` (Speichern), `bin/vibe-web.py:415-425` (POST `/api/costs`); Logik `bin/vibe:1444` (Preisquelle „user“ vor „system“) | `test_user_price_overrides_the_system_price`, Browsertest `test_entered_prices_override_unknown_costs_and_persist` (2/0,5/4 → 3,1000 € sofort), Modultests gegen 400-Rejekt ungültiger Preise |
| Nutzereingabe pro Projekt gespeichert | PASS | `bin/vibe:1444``1490` (`costs_set_prices` → `_toolchain/costs.json`, Schema `projects.<name>.models`), atomar über `vibe_storage.write_text` | `test_user_prices_are_stored_per_project` (anderes Projekt unberührt), `test_removing_a_user_price_falls_back_to_the_system_price`, `test_prices_can_be_saved_and_recalculate_the_cost` (API, Persistenzdatei geprüft), Browser-Test Persistenz nach Neuladen |
| Separate Übersicht je Projekt (CLI/API/UI) | PASS | CLI `bin/vibe:1835-1873` (Zeilenbereich von mir gegen Arbeitsbaum verifiziert), API `bin/vibe-web.py:302-305`, UI Reiter „Kosten“ `bin/vibe-web.py:763,776` | `CommandLineTest` (beide CLI-Aufrufe), `Test两家 CostsApiTest.test_overview_and_detail_are_served`, Browser-Tests für Übersicht und Detail; Baseline-Einträge in `docs/baseline.md` (Zeilen `bin/vibe:1835-1873` bestätigt) |

Kein Kriterium ist FAIL oder NOT VERIFIED. Nicht sauber separat testbar, aber abgedeckt: Randfälle fehlende/kaputte DB, unbekanntes Schema, v1/v2, ohne JSON1, fremde Projekte, Unterverzeichnisse, 403/404/400 (alle mit echten Assertions in `DataSourceTest`, `PackageIdTest`, `CostsApiTest` mit echtem Serverprozess).

## Findings
- [Minor] Trilium-Notiz `IwU7vi5DgDdd` — Testzahlen im Notiz-Prüfungsabschnitt widersprechen dem Nachweis
  - Evidence: Die über Trilium-MCP gelesene Notiz meldet „Rot: Ran 32 tests, FAILED (failures=3, errors=35)“ und „Grün: 32 Modultests OK“; die tatsächlich gelieferten Prüfausgaben und `docs/features/F12.md` belegen 34 Tests, FAILED (failures=4, errors=36) bzw. 34 OK. Ziel/Fach/Technik der Notiz stimmen ansonsten mit der Implementierung überein.
  - Required fix: Nur den Prüfungsabschnitt der Notiz auf die belegten Zahlen (34/4/36 rot, 34 grün) berichtigen; sonst nichts ändern.
- [Minor] `bin/vibe:1319` (`package_catalog`) — Paket-IDs ohne Titelzeile werden erkanntunterschiedlich geparsst als die bestehende Logik
  - Evidence: `package_catalog` verlangt `(\S+)\s+(.*)`, also einen nichtleeren Titel hinter der ID; die bestehende `open_items`-Routine (`bin/vibe:218`) akzeptiert `(\S+)\s*(.*)`. Eine Zeile `"- [ ] F99"` ohne Titel würde als Paket-ID fehlen, ihre Sitzungen fielen unter „Ohne Arbeitspaket“. Die Projektsumme bleibt korrekt, nur die AP-Zuordnung entfällt für solche Einträge.
  - Required fix: Parsing-Regel an `open_items` angleichen oder dokumentieren, dass beitragslose ID-Zeilen kein eigenes AP-Paket bilden – in beiden Fällen mit kleinstem Test ergänzen.
- [Minor] `bin/vibe-web.py:415-425` — Kollision beim Speichern von Preisen wird wie eine normale Ablehnung behandelt
  - Evidence: `costs_set_prices` übergibt ein vom Client mitgeliefertes `expected` an `vibe_storage.write_text`; bei Änderung durch Dritte wirft das `ConcurrentChangeError` (Unterklasse von `ValueError`, `bin/vibe_storage.py:56`), das hier als generisches `400/rejected` landet. `/api/agent` und `/api/mcp` mappen denselben Fehler auf `409/conflict` (`bin/vibe-web.py:473-474, 485-486`). Praktische Auswirkung ist klein, da die Oberfläche kein `expected` sendet und die Speicherfunktion selbst die Prüfsumme aus dem Snapshot ableitet.
  - Required fix: Im Handler `/api/costs` zusätzlich `except vibe_storage.ConcurrentChangeError` auf `409/conflict` abbilden – gleiche Semantik wie die etablierten Endpunkte.

## Verification
- Change set reviewed: `faed514..Arbeitsbaum`. Ich konnte keine Git-Befehle selbst ausführen (Shell-Permission verweigert: `git log`/`git status` abgelehnt); den vollständigen relevanten Diff und alle neuen Dateien habe ich stattdessen vollständig aus `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/opencode/f12-review-input.md` gelesen und die Kernstellen (alle Funktionszeilen der Kostenlogik in `bin/vibe`, Handler in `bin/vibe-web.py`, `vibe_storage`-Semantik, `docs/baseline.md`, `docs/trilium-index.md`) direkt im Arbeitsbaum gegen den diff gegengelesen — alles deckungsgleich.
- Git commands run by me: keine (Permission denied); Abgrenzung der Paketdateien basiert auf der gelieferten Eingabe plus direkter Gegenlektüre der genannten Dateien.
- Checks with supplied output: Rot-Modultests (34, failures=4, errors=36) und Rot-Browsertest (4 Fehler) gegen `faed514`; grüne 34 Modul- und 4 F12-Browsertests; `verify.sh quick` Exit 0; `verify.sh full` Exit 5 mit vorbestehend reproduzierter Fehlerliste (6 Sandbox-Tests ohne User-Namespaces, 8 Läufer-Tests mit schreibgeschütztem `/tmp`, Autostop-Browsertest) — alles nur gelieferte, nicht von mir ausgeführte Ausgaben. Die Einordnung ist nachvollziehbar: Die Fehlerlista enthält keinen F12-Bezug, dasselbe Testbaum-Setup scheitert identisch auf `faed514`, und die Grenze `/tmp`/Namespaces entspricht dieser Sandbox-Umgebung.
- Checks not independently run: alle Build-, Test- und Prüfkommandos; auch sha256/Manifestprüfung nicht selbst berechnet (durch `verify.sh quick`-Ausgabe „28 Dateien stimmen …“ belegt).
- Eigene Lese-Prüfungen: alle Formeln und Expected-Values der Tests handschriftlich nachgerechnet (u. a. 0,0111/0,0115 €, 3,1 € aus 400k·2 + 600k·0,5 + 500k·4 je 1 Mio. — korrekt); Screenshot als echtes, zur beschriebenen Browserabnahme passendes Bild gesichtet (Reiter „Kosten“, Preishinweise, „Preise gespeichert“-Toast); Trilium-Notiz `IwU7vi5DgDdd` gelesen; Authentisierung (`403` via globalem Guard), Projektvalidierung (`known`) vorm Schreibpfad, `mode=ro`+URI-Quoting für den DB-Zugriff und die Gültigkeitsprüfung der Preise (negativ/NaN/Inf/Typen/Modellname ≤200/keine Newlines) im Quelltext geprüft.
- Important areas inspected: `bin/vibe` (F12-Abschnitt), `bin/vibe-web.py` (API + Kosten-UI), `tests/unit/test_costs.py`, `tests/browser/test_costs_ui.py`, `docs/features/F12.md`, `docs/baseline.md`, `docs/import-manifest.json`, `docs/trilium-index.md`, `bin/vibe_storage.py`, `docs/features/F12-kosten.png`, Trilium `IwU7vi5DgDdd`.

## Remaining risks
- Die Tokensemantik („input inklusive cache.read“, cached als Teilmenge der Eingabe) ist eine Auslegung, die exakt dem Wortlaut des Tickets entspricht („davon cached input token“) und im Test mit konstruierter Datenbank verifiziert ist; gegen die echte opencode-Datenbank produktiver Läufe wurde sie nicht geprüft. Weicht das tatsächliche Sitzungsbuch碑ungsmodell von opencode ab, müsste die Formel nachgeführt werden — heute stammt der Testbestand aber aus derselben Quelle.
- `verify.sh full` ist in dieser Sandbox nicht ganz grün; die 14 Fehler wurden nur von Prüfbottle beim Agenten (mit Reproduktion gegen `faed514`) geliefert, nicht von mir verifiziert. Eine vollständige grüne Suite verbleibt bis zur Umgebungsklärung ausstehend.
- Trilium-Zahlen (oben, Minor) und drei kleine Inkonsistenzen sind als Folgekorrekturen offen; sie betreffen keine Akzeptanzkriterien und blockieren PASS nicht.

**Verdict: PASS**
