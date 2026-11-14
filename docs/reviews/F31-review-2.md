# Review F31 — Runde 2 (unabhängiger code-reviewer, 2026-11-14)

Reviewer: code-reviewer (Rolle reviewer laut aktivem Profil „kostenlos" in profiles.json). Runde 1: docs/reviews/F31-review-1.md (CHANGES REQUIRED, 2 Medium/2 Minor — alle behoben).

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1 Ansicht der AGENTS.md in der Assistent-Ansicht | PASS | `bin/vibe:2414-2434` (`agents_file_view`), `bin/web/app.js:313,318-343` (Karte in `drawGuide`) | Unit-Fälle 1-3 (`test_view_*`), Browser-Fall 12; Screenshot `docs/features/F31-agents-file.png` in Runde 1 geprüft |
| AK2 Verwalteter Block kenntlich + Erklärung | PASS | `bin/web/app.js:336` (Wortlaut „auf den aktuellen Stand gebracht und ist in der Bearbeitung geschützt"), `:339` (`<pre>`) | Browser-Fall 12 (EXPLANATION + „Ordnung im Git halten" sichtbar) |
| AK3 Freie Teile bearbeitbar, Block byte-identisch | PASS | `bin/vibe:2489-2491` (`before + GENERAL_RULES + after`), `GENERAL_RULES` `bin/vibe:97-129` | Unit-Fälle 4, 7; Browser-Fall 13 |
| AK4 Digest-Schutz (überholter Digest → Ablehnung, Datei unverändert) | PASS | `bin/vibe:2491` (`write_text(expected=digest)`), `bin/vibe_storage.py:64,158-173` | Unit-Fall 5 (byte-identischer Vergleich nach Ablehnung) |
| AK5 Marker in freien Teilen abgewiesen (ungerade und paarig) | PASS | `bin/vibe:2480-2490` (neue Prüfreihenfolge: unpaarige-Marker-Prüfung vor der Freiteil-Prüfung; beide Ablehnungen erhalten) | Unit-Fall 6 (6 Subtests) + Fall 7; gegen die neue Reihenfolge gegengeprüft |
| AK6 Fehlende Datei aus Typ-Vorlage ({{NAME}}, generic-Fallback), nie überschrieben | PASS | `bin/vibe:2503-2528` (`{{NAME}}`, `expected=MISSING`, `"kept"`) | Unit-Fälle 8-10; Browser-Fall 14 |
| AK7 Pfadsicherung (kein Traversal, Symlinks abgelehnt) und atomares Schreiben | PASS | Traversal: `ppath`/`known` (`bin/vibe:478-481`); Symlinks: `bin/vibe:2423,2457,2513`; atomar: `vibe_storage.py:343-360` | Unit-Fall 11 (Traversal) + neu Fälle 16-18 (`test_view_rejects_symlink_and_reports_missing_file`, `test_save_rejects_symlink_and_leaves_target_untouched`, `test_create_rejects_symlink_and_leaves_target_untouched`, `tests/unit/test_f31_agents_file.py:330-366`); agentenseitig `Ran 14 tests — OK, kein Skip` (Testbericht Z. 174-176) |
| AK8 GET/POST /api/agents_file mit Auth, known(name), unbekannte Aktion abgewiesen | PASS | `bin/vibe-web.py:1034-1035,1132-1133,1538-1562` | Browser-Fall 15 (GET 200, POST 4xx, Datei unverändert); Auth-Gates unverändert projektweit |
| AK9 Doku: docs/features/F31.md + Handbuch-Abschnitt | PASS | `docs/features/F31.md:112-129` (korrigiert), `docs/handbuch.md:162-185` | Beide gelesen; F31.md-Prüfungen decken sich jetzt mit dem Testbericht (Rotphase, Locator-Korrektur, Grünphase, Verweis als verbindliche Quelle), keine erfundenen Zahlen |

## Findings

- No findings.

## Verification
- Change set reviewed: `88509a0..working tree` — vom Reviewer selbst mit `git status --short`, `git diff 88509a0 -- bin/vibe`, `git diff 88509a0 -- bin/vibe-web.py`, `git diff 88509a0 -- bin/web/app.js docs/handbuch.md`, `git diff 88509a0 -- docs/import-manifest.json` und `git diff --stat 88509a0`. Umfang exakt: `bin/vibe` (+112), `bin/vibe-web.py` (+29), `bin/web/app.js` (+30), `docs/handbuch.md` (+25), `docs/import-manifest.json` (+22/-7) sowie die neuen untracked Dateien (F31.md, Screenshot, Testbericht, Review Runde 1, beide Testdateien). Keine Änderungen an `scripts/verify.sh` oder Prüfwerkzeug.
- Git commands run by reviewer: `git status --short`, `git diff --stat 88509a0`, `git diff 88509a0` (je geänderte Datei), `git log --oneline -3`. Weitere Shell-Kommandos (z. B. `sha256sum`) wurden von der Umgebung abgelehnt.
- Checks with supplied output (agentenseitig, vom Reviewer nicht ausgeführt): Unit `tests.unit.test_f31_agents_file` → `Ran 14 tests in 0.125s — OK` inkl. 3 Symlink-Fälle, kein Skip; Browser 4/4 OK; `tests.unit.test_project_management` 32 OK; `node --check`, `check-syntax.py`, `check-no-secrets.py`, `check-import-manifest.py` (60 Dateien) OK; `bash scripts/verify.sh quick` Exit 0. Plausibilitätsprüfung der Manifest-Hashes: der `git diff` des Manifests zeigt aktualisierte Einträge für alle drei geänderten bin-Dateien (`bin/vibe` 263019/7f9982…, `bin/vibe-web.py` 92839/274cdc…, `bin/web/app.js` 125827/378986…), konsistent mit dem agentenseitigen Check — die Hashwerte selbst konnte der Reviewer wegen der Shell-Sperre nicht unabhängig neu berechnen.
- Checks not independently run: alle Tests und Hash-Berechnungen.
- Befund-Fixes einzeln geprüft:
  1. **F31.md „Prüfungen"**: beschreibt jetzt belegbar Rotphase, Locator-Korrektur (nur Locator, Erwartungen unverändert), Grünphase und verweist als verbindliche Quelle auf den Testbericht; keine hartcodierten Zahlen, keine unbelegten Aussagen. Behoben.
  2. **AK7-Symlinks**: Drei neue Unit-Fälle mit Vorbedingungs-Assertion (`test_f31_agents_file.py:176`), byte-identischer Zielprüfung und Erhalt des Symlinks. Das `skipUnless`-Muster ist eine dokumentierte, funktionsgeprüfte Umgebungs-Grenze (FUSE/NTFS, `symlink_supported()` mit Probe), kein stiller Verzicht — im Bericht ist belegt, dass in der Abnahmeumgebung alle 14 Fälle tatsächlich liefen (kein Skip). Nicht als Test-Integrity-Verstoß bewertet. Behoben.
  3. **UI-Speichern-Button**: `app.js:342` rendert `Speichern` nur bei `v.exists`, sonst nur `Aus Vorlage anlegen`; der `el`-Helfer überspringt `null`-Kinder (`app.js:13`, etabliertes Muster). Browser-Vertragsanker bleiben in beiden Zuständen erfüllt (Fall 13/14 bedienen beide Zustände). Behoben.
  4. **Prüfreihenfolge `agents_file_save`**: Unpaariger Marker in der Datei feuert jetzt vor der Freiteil-Prüfung (`bin/vibe:2480-2490`) und liefert die dedizierte Meldung. Gegen alle 14 Unit-Erwartungen gegengeprüft: Fall 6 (paariger Block + Marker in before/after → generische Meldung), Fall 5 (Stale-Digest, `ConcurrentChangeError` weiterhin `ValueError`-Subklasse → Web-Endpunkt unverändert kompatibel), Fall 7 unverändert grün; Ablehnung + unveränderte Datei in allen Pfaden erhalten. Neue Randfälle: Marker-freie Datei + Marker im Submit → korrekt über die Freiteil-Prüfung abgewiesen; END-vor-START → dedizierte Unpaarig-Meldung. Keine Erwartung verletzt. Behoben.
- Important areas inspected: F31-Abschnitt `bin/vibe:2397-2528`, `/api/agents_file` (`vibe-web.py`), Karte (`app.js:308-343`), beide Testdateien vollständig, Testbericht (Fälle 16-18, Grünphase-Nachtrag), F31.md, handbuch-Abschnitt, Manifest-Diff, `el()`-Helfer.
- Remaining risks: (1) Test- und Hash-Ergebnisse liegen nur agentenseitig vor (Werkzeugrechte des Reviewers erlaubten nur Git) — die Belege sind konsistent und vollständig dokumentiert, wurden aber nicht wiederholt; (2) Browser-Regression der geänderten Button-Bedingung beruht auf den 4 bestehenden Fällen (beide Zustände abgedeckt), ein dedizierter „kein Speichern bei fehlender Datei"-Fall existiert nicht — kosmetisch, da die Änderung rein darstellerisch ist.

## Verdict: PASS
