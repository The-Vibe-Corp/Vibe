# AP8 — Review Runde 2 (code-reviewer)

Datum: 2026-11-11
Reviewer: code-reviewer (unabhängig, Subagent session ses_e381ead09ffe0PcUWEVLvzlA4D, Fortsetzung der Runde-1-Sitzung)
Gegenstand: Arbeitspaket AP8 „Bereit für Github Teil 2“, Ausgangscommit `8afde0e`, Arbeitsbaum `vibe/vibe-AP8-1794350105884804023-2529435-12489`
Antwort des Reviewers unverändert aus der Review-Antwort übernommen.

---

# Review result (Runde 2)

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Info: 2
- Verdict: **PASS**

## Behobungen (Runde-1-Befunde) — Prüfung
| Runde-1-Befund | Behoben | Beleg (file:line) | Regressionstest |
|---|---|---|---|
| Medium: unmaskierte Zugangsdaten in Clone-Fehlermeldung | Ja | `bin/vibe_github.py:373-386` (`mask_embedded_credentials`), `:597` (`clone` gibt nur maskierte Meldung weiter) | `CredentialMaskingTest` ×3 (`tests/unit/test_ap8_github_checkout.py:727-785`): mehrzeiliger Freitext inkl. Klartext-URL und Idempotenz (`:730`), Maskierung an der `clone`-Naht (`:751`), realer Loopback-Ausfallpfad ohne Leak und ohne Zielordner (`:774`) |
| Minor: verwaltete Schlüssel implizit über Vorlageninhalt | Ja | `bin/vibe:2365-2369` (`MANAGED_ENV_KEYS`), `:2442-2443` (Diff gefiltert auf `key in MANAGED_ENV_KEYS`) | `test_unmanaged_keys_keep_the_repository_value_while_managed_keys_move_local:512` — nicht verwalteter `EXTRA_KEY` bleibt beim Projektwert, obwohl die lokale Vorlage ihn kennt; verwaltete Schlüssel gehen auf den lokalen Stand |
| Minor: duplizierte Marker→Typ-Zuordnung | Ja | `bin/vibe:460-479` (`TYPE_MARKERS`, `type_from_markers`), `ptype:469-473` behält TYPE-Vorrang; `_detect_project_type:2371-2372` delegiert | Indirekt durch die bestehenden Übernahme- und CLI-Fälle (33/33 gemeldet) |
| Minor: Teilübernahme hinterlässt Restzustand trotz Docstring | Ja | `bin/vibe:2513-2527` (Übernahme + GitHub-Verknüpfung in einem try; `rmtree` + `_pm.clear()` + ValueError „Übernahme fehlgeschlagen, Zielordner entfernt") | `test_an_adoption_failure_removes_the_target_folder_and_reports_the_reason:652` — `ensure_general_rules` mit OSError-Mock (FUSE/rechte-neutral), assertion auf Meldung, Ursache „gesperrt", kein Ordner, nicht in Projektliste |
| Info: Docstring „ohne GitHub zu kontaktieren" mehrdeutig | Ja | `bin/vibe:2490-2494` („keinen GitHub-REST-API-Aufruf oder Token ... `set-head` fragt den Git-Remote selbst ab"), `docs/features/AP8.md:56-58` | — |

Randfallprüfung der Behobungen:
- Maskierungs-Regex (`bin/vibe_github.py:382-385`): linear, kein Backtracking-Risiko; Klartext-URL ohne `@` bleibt unverändert; bereits maskierte Ausgaben sind idempotent (getestet). `str(text or "")` fängt None ab.
- Cleanup-Platzierung: `rmtree` vor `_pm.clear()` (`bin/vibe:2524-2525`); beim Clone-Fehler bleibt der Projektlisten-Cache konsistent, da das Projekt vor dem Clone nie registriert war (`project_map()`-Prüfung `:2506` vor dem Clone; `test_a_failed_clone_leaves_no_project_folder:667` bestätigt `projects() == []`). Bestehende Zielordner können vom Cleanup nicht getroffen werden (Lexists-Ablehnung `:2503-2505`).
- Keine Abschwächung bestehender Tests erkennbar: die 28 Runde-1-Fälle sind unverändert vorhanden, `33 − 28 = 5` neue Fälle, alle mit fachlich tragfähigen Assertions; der Browser-Test (4 Fälle) ist unverändert. Keine `skip`-Marker, keine nicht scheiterbaren Assertions.

## Findings
- [Minor] `docs/reviews/AP8-test-agent-report.md:441` — Zählfehler im Bericht
  - Evidence: Fixlauf 3 führt fünf ergänzte Testfälle auf (3 Maskierung + 1 unmanaged-keys + 1 Übernahme-Cleanup; 33 − 28 = 5), die Ausführungszusammenfassung sagt jedoch „Alle vier neuen Tests laufen und sind grün".
  - Required fix: Im Bericht „vier" durch „fünf" ersetzen (oder die Aufzählung entsprechend kennzeichnen). Reine Dokumentkorrektur, blockiert nicht. → Behoben durch den Test-Agenten („fünf" mit Einzelnachweisen, nur diese Stelle).

- [Info] `bin/vibe:2519` — Cleanup-Ausnahme deckt ValueError nicht ab
  - Evidence: Der Übernahme-Cleanup fängt nur `OSError`/`StorageError`; ein theoretisches `ValueError` aus `set_env_values` (`bin/vibe:911-915`, ungültiger Schlüssel/Steuerzeichen) würde ohne Ordner-Cleanup entweichen. Praktisch unerreichbar: Schlüssel stammen aus `read_env` (Regex `[A-Z_]+=`) bzw. sind Konstanten, der GitHub-Slug ist vorvalidiert. Für eine spätere Härtung kann `ValueError` in denselben `except`-Block aufgenommen werden — kein Handlungsdruck für AP8.

- [Info] `bin/vibe_github.py:548,560,572` — gleichartiger Maskierungslücke in bestehenden fetch/pull/push-Pfaden (paketfremd)
  - Evidence: `fetch`, `pull/merge` und `push` geben Git-Rohausgaben mit `_auth_guidance`, aber ohne `mask_embedded_credentials` zurück — derselbe Defekttyp wie der Runde-1-Medium-Befund, jedoch am Ausgangscommit 8afde0e bereits vorhanden und nicht Teil dieses Changesets. AP8 hat die Naht nur offengelegt.
  - Required fix: Keine Änderung im Rahmen von AP8; als Follow-up-Ticket (z. B. B-Ticket oder in AP9) aufnehmen, dort die drei Rückgabestellen ebenfalls maskieren.

## Verification
- Change set reviewed: Ausgangscommit 8afde0e → Arbeitsbaum, Diff über `/tmp/opencode/ap8-review-diff2.patch` (495 Zeilen, 6 Dateien: `bin/vibe`, `bin/vibe-web.py`, `bin/vibe_github.py`, `bin/web/app.js`, `docs/baseline.md`, `docs/import-manifest.json`); alle fünf Behobungsstellen zusätzlich direkt im Arbeitsbaum gegengelesen und identisch befunden.
- Git commands run by me: keine — Shell-Berechtigung ist in dieser Review-Sitzung weiterhin verweigert; unabhängige `git status`/`git diff`-Ausführung nicht möglich, Gegenlesung der Dateien erfolgte direkt.
- Checks with supplied output: 33/33 Unit (Test-Agent, desinfizierte Umgebung), 4/4 Browser, `check-syntax.py` OK, `check-import-manifest.py` OK (neue SHA-256/Größen für `bin/vibe` und `bin/vibe_github.py`, zusätzlicher AP8-Fixrunden-Eintrag mit Begründung im Manifest), `verify.sh quick` OK, `verify.sh full` mit den unveränderten 5 paketfremden Baseline-Vorbefunden (8afde0e, durch den Test-Agenten unabhängig bestätigt).
- Checks not independently run: alle Build-, Test- und Verify-Läufe; SHA-256-Berechnung; Git-Metadaten.
- Important areas inspected: `bin/vibe:455-479, 2349-2566, 5151`, `bin/vibe_github.py:368-386, 573-597`, `tests/unit/test_ap8_github_checkout.py` (vollständig, inkl. der 5 neuen Fälle), `docs/reviews/AP8-test-agent-report.md` (Fixlauf 3), `docs/features/AP8.md`, `docs/import-manifest.json`, `docs/reviews/AP8-review-1.md` (abgelegt), `bin/web/app.js:95-99`, `bin/vibe-web.py:764-775`.
- Remaining risks: Echte Netzklone gegen github.com mit Authentisierung bleiben der echten Abnahme vorbehalten (vom Test-Agenten dokumentiert; der Loopback-Ausfallpfad deckt die Maskierung an der realen Git-Naht ab); SHA-256-Werte nur über gemeldetes `check-import-manifest.py`-Ergebnis abgesichert; das [Info]-Restthema fetch/pull/push-Maskierung betrifft AP6-Code außerhalb dieses Pakets.

**Verdict: PASS** — Alle fünf Runde-1-Befunde sind korrekt und im Arbeitsbaum verifiziert behoben, die fünf neuen Regressionstests decken die Behobungen fachlich ab (FUSE/rechte-neutral über Mock bzw. Loopback statt Rechte-Tricks), keine neuen Defekte erkennbar, keine Critical-/High-/Medium-Befunde. Der verbleibende Minor (Zählfehler im Test-Agentenbericht) und die beiden Info-Vermerke blockieren den Abschluss nicht; die Info zur Maskierung in fetch/pull/push sollte als paketfremdes Follow-up-Ticket erfasst werden.

---

Hinweis zur Übernahme: Diese Datei enthält die Review-Antwort des code-reviewer-Subagents wortgetreu; für die Ablage wurden Überschriften, ein Kopfblok, die Abschnittstrenner und der kursive Bearbeitungsvermerk am Minor-Befund ergänzt. Der Minor wurde nach der Runde durch den Test-Agenten behoben (Dokumentkorrektur „vier" → „fünf").
