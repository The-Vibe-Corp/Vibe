# Review F31 — Runde 1 (unabhängiger code-reviewer, 2026-11-14)

Reviewer: code-reviewer (Rolle reviewer laut aktivem Profil „kostenlos" in profiles.json). Read-only; Shell-Zugriff von der Umgebung verweigert (siehe Abschnitt Verification).

## Summary
- Critical: 0
- High: 0
- Medium: 2
- Minor: 2
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1 Ansicht der AGENTS.md in der Assistent-Ansicht | PASS | `bin/vibe:2414-2434` (`agents_file_view`), `bin/web/app.js:313,318-343` (Karte in `drawGuide`/`#guide`) | `tests/unit/test_f31_agents_file.py::test_view_*` (3 Fälle), `tests/browser/test_f31_agents_file_ui.py::test_card_shows_content_managed_block_and_explanation`; Screenshot `docs/features/F31-agents-file.png` geprüft (echter Screenshot der Karte) |
| AK2 Verwalteter Block kenntlich + Erklärung | PASS | `bin/web/app.js:336` (Wortlaut „auf den aktuellen Stand gebracht und ist in der Bearbeitung geschützt"), `:339` (`<pre>` schreibgeschützt) | `test_card_shows_content_managed_block_and_explanation` (EXPLANATION + „Ordnung im Git halten" sichtbar); Wortlaut stimmt mit Ticket überein |
| AK3 Freie Teile bearbeitbar, Block byte-identisch | PASS | `bin/vibe:2466-2480` (`before + GENERAL_RULES + after`), `GENERAL_RULES` `bin/vibe:97-129` | `test_save_merges_free_parts_with_byte_identical_block`, `test_save_without_block_writes_after_verbatim`, `test_editing_free_part_saves_file_and_keeps_block_identical` |
| AK4 Digest-Schutz (überholter Digest → Ablehnung, Datei unverändert) | PASS | `bin/vibe:2480` (`write_text(expected=digest)`), `bin/vibe_storage.py:158-173` (`check_expected`, Datei bleibt unverändert), `ConcurrentChangeError(ValueError)` `vibe_storage.py:64` | `test_save_rejects_stale_digest_and_leaves_file_untouched` (byte-identischer Vergleich der Datei nach Ablehnung) |
| AK5 Marker in freien Teilen abgewiesen (ungerade und paarig) | PASS | `bin/vibe:2451-2455` (Marker in before/after), `:2470-2473` (unpaariger Marker in Datei) | `test_save_rejects_markers_in_free_parts` (6 Subtests: Start-, End- und Paarmarker je in before und after; je `ValueError`, Datei byte-identisch) |
| AK6 Fehlende Datei aus Typ-Vorlage ({{NAME}}, generic-Fallback), nie überschrieben | PASS | `bin/vibe:2482-2507` (`{{NAME}}`-Ersetzung, `expected=MISSING`, `"kept"`) | `test_create_uses_type_template_with_name_replaced`, `test_create_unknown_type_falls_back_to_generic`, `test_create_never_overwrites_existing_file`; `tests/browser/test_f31_agents_file_ui.py::test_missing_file_can_be_created_from_template` |
| AK7 Pfadsicherung (kein Traversal, Symlinks abgelehnt) und atomares Schreiben | NOT VERIFIED (nur Symlink-Teil) | Traversal: `ppath`/`known` (`bin/vibe:478-481,713-717`); Symlink-Ablehnung: `bin/vibe:2423,2457,2492`; atomar: `vibe_storage.write_text` (`vibe_storage.py:343-360`) | Traversal/atomar: `test_unknown_or_traversal_names_are_rejected`, `test_save_merges_free_parts_with_byte_identical_block` (write_text-Spy). **Symlink-Ablehnung ist in keinem Test geprüft** — siehe Finding 2 |
| AK8 GET/POST /api/agents_file mit Auth, known(name), unbekannte Aktion abgewiesen | PASS | `bin/vibe-web.py:1034-1035` (GET + `known`), `:1132-1133` (POST-Auth/`known` für alle Steuer-Endpunkte inkl. agents_file), `:1538-1562` (unbekannte Aktion → 400) | `test_get_view_and_unknown_post_action_rejected` (GET 200 mit korrekter View; POST 4xx, Datei unverändert); generische Auth-Gates sind projektweit einheitlich (`do_GET`/`do_POST` vor allen Endpunkten) |
| AK9 Doku: docs/features/F31.md + Handbuch-Abschnitt | PASS | `docs/features/F31.md` (fachlich korrekt, Herkunft/Block/Grenzen), `docs/handbuch.md:162-185` | Beide Dateien gelesen; Feature-Beschreibung deckt sich mit Implementierung. Abweichung nur im Abschnitt „Prüfungen" (Finding 1) |

## Findings

- [Medium] `docs/features/F31.md:112-119` — Abschnitt „Prüfungen" behauptet fälschlich blockierten Browser-Test
  - Evidence: F31.md sagt, die Browser-Suite sei „blockiert durch einen Fehler im Test-Locator" und die Implementierung sei „manuell geprüft". Der Testbericht (`docs/reviews/F31-test-agent-report.md:141-166`) dokumentiert jedoch die korrigierte Locator und die Grünphase mit 4/4 OK (Exit 0). Die Paketdokumentation stellt damit den Prüfstand falsch dar (blockiert/manuell statt bestanden) und widerspricht dem Testbericht.
  - Required fix: Abschnitt „Prüfungen" in F31.md auf den Endstand bringen (Locator-Korrektur + 4/4 OK wie im Testbericht), ohne Aussagen zu erfinden, die nicht im Bericht belegt sind.

- [Medium] `tests/unit/test_f31_agents_file.py` — AK7-Teil „Symlinks abgelehnt" ohne jeden Test
  - Evidence: Die Implementierung lehnt Symlinks an `bin/vibe:2423` (view → `exists=False`), `:2457` (save → ValueError) und `:2492` (create → ValueError) ab, aber weder die Unit- noch die Browser-Suite enthält einen Symlink-Fall (grep nach `symlink|islink` in beiden Testdateien: 0 Treffer). AK7 verlangt ausdrücklich „Symlinks abgelehnt"; dieser Teil der Abnahme ist damit unbelegt. Zur Abwägung: Das Arbeitsverzeichnis liegt auf FUSE/NTFS (`AGENTS.md`: „Auf FUSE/NTFS … Rechte nicht als wirksam voraussetzen") — falls `os.symlink` dort nicht funktioniert, ist das als dokumentierte Grenze zu führen, nicht als stiller Verzicht.
  - Required fix: Vom Test-Agenten einen Symlink-Fall ableiten und ergänzen (Vorbedingung: Symlink-Anlage im isolierten Bereich möglich; falls nicht, Lücke explizit als Umgebungs-Grenze im Testbericht/F31.md dokumentieren). Erwartet: view meldet `exists=False`, save/create werfen `ValueError`, das Link-Ziel bleibt byte-identisch unverändert.

- [Minor] `bin/web/app.js:330,342` — Speichern-Button aktiv, solange die Datei fehlt
  - Evidence: Bei `exists:false` bleibt der Speichern-Button sichtbar und aktiv. Ein Klick löst `agents_file_save` mit `digest=""` aus und scheitert an `bin/vibe:2449-2450` mit „Prüfsumme fehlt. Bitte die Ansicht neu laden." — die Meldung verleitet zum Neuladen, obwohl „Aus Vorlage anlegen" der richtige nächste Schritt ist.
  - Required fix: Den Speichern-Button im Zustand `!v.exists` ausblenden (analog zum Create-Button) oder in diesem Zustand eine gezieltere Meldung zeigen.

- [Minor] `bin/vibe:2451-2455` vs. `:2470-2473` — unpaariger Marker in der Datei führt über den UI-Pfad zur generischen Marker-Meldung
  - Evidence: Bei unpaarigem Marker liefert `_agents_file_split` (`:2404-2412`) den gesamten Text als `after`; der gespeicherte `after` enthält damit den Marker und die Prüfung an `:2451` feuert zuerst mit „Marker dürfen nicht in den freien Teilen stehen". Die dedizierte Meldung (`:2470-2473`, „unpaarigen Marker von Hand bereinigen") ist über den UI-Ablauf praktisch unerreichbar. Verhalten korrekt (Ablehnung, Datei unverändert), nur die Fehlermeldung hilft dem Nutzer bei der Behebung weniger.
  - Required fix: Reihenfolge oder Bedingung der Prüfungen so anpassen, dass im Fall „Datei enthält unpaarigen Marker" die dedizierte Meldung erscheint. Verhaltenfrei, rein diagnostische Klarheit.

## Verification
- Change set reviewed: Der Ausgangsstand `88509a0` und die Änderungsliste wurden vom Koordinator vorgegeben; alle genannten Dateien wurden vollständig im Arbeitsbaum gelesen (`bin/vibe` F31-Abschnitt, `bin/vibe-web.py` GET/POST, `bin/web/app.js` Karte, `docs/handbuch.md`, `docs/features/F31.md`, `docs/import-manifest.json`, beide neuen Testdateien, Testbericht, Screenshot, Manifest).
- Git commands run by reviewer: keine — sämtliche Shell-Befehle (auch read-only Git) wurden von der Umgebung mit „Permission denied: shell" abgelehnt. Die Vollständigkeit des Änderungssatzes (keine weiteren geänderten Dateien, keine Änderungen an Prüfwerkzeug/`scripts/verify.sh`) ist damit nicht unabhängig bestätigt; beide Testdateien sind laut Testbericht neu.
- Checks with supplied output: Unit `test_f31_agents_file` 11 OK, Browser `test_f31_agents_file_ui` 4 OK (Rotphase dokumentiert), Regressionen (test_project_management 32 OK, test_project_guide 36 OK, test_project_guide_ui 4 OK), `node --check`, Manifest/Syntax/Secrets, `verify.sh quick` Exit 0 — agentenseitig geliefert, vom Reviewer nicht unabhängig ausgeführt.
- Checks not independently run: alle Builds, Tests, Syntax-/Manifest-/Secret-Checks, Hash-Berechnung des Import-Manifests.
- Important areas inspected: `agents_file_view/_agents_file_split/agents_file_save/agents_file_create` (`bin/vibe:2397-2507`), `GENERAL_RULES` (`bin/vibe:97-129`), `vibe_storage` Digest-/Atomik-Schicht (`vibe_storage.py:64,94-173,307-360`), `/api/agents_file` GET/POST inkl. Auth-Gates (`vibe-web.py:899-919,1078-1133,1538-1562`), UI-Karte (`app.js:305-343`), Doku, Tests, Manifest.
- Remaining risks: (1) Umfangsabdeckung des Diffs gegen `88509a0` nicht unabhängig verifizierbar; (2) Regressionssuiten und `verify.sh full` nur als agentenseitige Ergebnisse vorliegend; (3) Symlink-Verhalten implementiert, aber ungeprüft (Finding 2); (4) TOCTOU-Fenster bei islink→open existiert projektweit im selben Muster wie `ensure_general_rules` (kein neuer, F31-spezifischer Defekt — schreibseitig schützt `os.replace` vor Traversal).

## Verdict: CHANGES REQUIRED
