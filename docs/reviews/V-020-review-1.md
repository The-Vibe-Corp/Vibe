I have reviewed all material. One more check: the timing figures in the local docs vs. the supplied output, and whether notes were weakened in existing tests — already confirmed from the diff (only additions). Now writing the result.

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 2
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Zentrale Nutzerabläufe automatisiert im Browser | PASS | `tests/browser/test_central_workflows_ui.py:202-2084` (echtes Dashboard + Chromium/Playwright; Hauptablauf und Umgebungsansicht) | `tests.browser.test_central_workflows_ui` — 2 Tests OK (gelieferte Ausgabe); Rotphase (Release-Assert) dokumentiert in `docs/features/V-020.md:889-921` |
| Dokumentierte manuelle Bazzite-Prüfung | PASS (mit Grenzen) | `docs/abnahme-bazzite.md:143-252`, `docs/checkliste.md:565-581` | Dokumentiert als leider weitergeführte/hostseitige V-017-Abnahme plus schreibgeschützte Nachprüfung 2026-11-03; Einschränkungen ehrlich benannt — kein Nachweis verfälscht |
| Bekannte Grenzen veröffentlicht | PASS | `docs/grenzen.md:1005-1107` | `tests.unit.test_release.test_published_documents_exist_and_are_not_empty` |
| Feature-Dokumentation lokal und in Trilium | FAIL | `docs/features/V-020.md` korrekt; `docs/trilium-index.md:25` verweist auf Notiz `3IwzW6WLnBeU` — Notiz enthält veraltete Testzahlen (912 erkannt, 12 Tests, 10 Rotphasenfehler) statt der finalen (913, 13, 13) | Trilium-Notiz von mir über MCP gelesen (Titel, Inhalt, Datum 2026-11-03 vorhanden) → Inhalt widerspricht den lokalen Nachweisen |
| Reviewnachweise vollständig | NOT VERIFIED (Momentaufnahme) | `docs/reviews/V-020-review-<n>.md` laut Ablauf erst nach dieser Antwort zu erzeugen | Workflownachweis zukünftiger Runde; hier nicht bewertbar |
| Release ohne persönliche Daten reproduzierbar | PASS | `scripts/build-release.py:159-1723` (nur gelistgte Git-Dateien, Ausschluss-Abort, Pfad-/Geheimnis-Scan, deterministisches tar.gz), `bin/vibe_paths.py:79-120` | `tests.unit.test_release` 13 Tests OK (geliefert); Rotphase 3× separately belegt; `verify.sh quick/full` Exit 0 |
| Vollständige Suite + Checkliste mit Versionen und Ergebnissen | PASS | `docs/checkliste.md:466-632` (Umgebungsversionen, Testzahlen 855/58/913, bwrap-Verfahren) | Gelieferte Ausgaben: quick Exit 0 (53 Manifestdateien, keine Geheimnisse), full Exit 0 (855+58, 913 erkannt); Zahlen decken sich mit den lokalen Dokumenten |
| Umfang: Handbuch, Diagnose- und Betriebsanleitung | PASS | `docs/handbuch.md`, `docs/betrieb.md` | Inhaltstests + Inhalt von mir gelesen; konsistent zum Code (Releaseanzeige, Health-Felder, Doctor-Zeile) |

## Findings

- [Medium] `docs/trilium-index.md:25` / Trilium-Notiz `3IwzW6WLnBeU` — Trilium-Dokumentation enthält veraltete Testzahlen
  - Evidence: Ich habe die Notiz über den Trilium-MCP-Zugang gelesen (bestätigt: `V-020 Browserabnahme, Dokumentation und Releasebasis`). PRÜFUNGEN nennen dort „854 Unit- + 58 Browsertests, 912 erkannt", Einzeltest „tests.unit.test_release 12 Tests OK" und Rotphase „10 Fehler". Die finalen, in `docs/features/V-020.md:952-979` und in den gelieferten Prüfausgaben belegten Werte sind dagegen 855/58/913, 13 Tests und 13 Rotphasenfehler. Die Pflichtdoku in Trilium verweist so auf eine Zwischenversion des Pakets, nicht auf den abzuschließenden Stand.
  - Required fix: Trilium-Notiz `3IwzW6WLnBeU` auf die finalen Zahlen (13 test_release, 855 Unit + 58 Browser, 913 erkannt, 13 Rotphasenfehler) aktualisieren und den Abschnitt gegenseitig neu einlesen; KEINE Code-, Test- oder Dokuänderung im Repository erforderlich, kein erneuter Testlauf nötig.

- [Minor] `scripts/build-release.py:1401+159-1664` (Konstanten bzw. mode-Mapping in `build_release`/`tracked_entries`) — Symlink-Modus INTERESSANTENFALL unsauber behandelt
  - Evidence: `tracked_entries` akzeptet Git-Datenträgermode `120000` (Symlink) als blob; `build_release` schreibt den Eintrag dann als reguläre 0o644-Datei mit dem Zielnamen als Inhalt. Im aktuellen Repo gibt es keine Symlinks, Tests greifen den Fall nicht; ein auftretender Fall wäre still verfälscht statt abgebrochen.
  - Required fix: Bewusster Aufräumbrief: Symlink-Handling (oder Zordnung zum expliziten Abbau wie bei Untermodule) in `docs/features/V-020.md` bzw. `docs/grenzen.md` benennen mit Fall oder die Fallzeile als nicht unterstützt agar.

- [Minor] `docs/checkliste.md:526-527` — zitierte Laufzeiten weischen von der nachgelieferten Sessionausgabe ab (106.156 s/45.614 s vs. 106.575 s/45.592 s)
  - Evidence: Beides sind plausible Verlauf anderer Läufe, aber die dokumentannten Sekunden sind nicht die nachgelieferten. Kein sachlicher Grund zum Verstoß; es wird aber Call out, dass Dokument- und Sessionnachweis nicht ein Entwurf sind.
  - Required fix: In der Checkliste einmalig formulieren, dass die Zeitangaben aus einem der einzelnen vollständigen Läufe stammen (nicht aus der Head-Sessionlauf), oder die Sekundenn nachtragbar präzisieren — je besser: einfach „Zeiten variieren je nach Lauf" ergänzen.

## Prüfung der weiteren Schwerpunkte

- `scripts/build-release.py` logisch korrekt in den geprüften Fällen: deterministisches tarfix (mtime 0, uid/gid 0, leere uname/gname, gzip mtime 0), Manifest `RELEASE.json` in sich bei diskrepanter Größe/SHA geprüft (`test_verify_rejects_an_altered_file`), Ausschluss-Abort statt stabiler Verlust (`test_tracked_personal_path_is_refused...`), `verify` lehnt Unsicherer Pfad, fehlende Pflichtdateien, doppelte Einträge und veränderte Prüfsummen ab.
- `bin/vibe_paths.release_info` (Diff L79-120) eindeutige Priorität version.json → VERSION → unbekannt; Commit wird nie geraten (`test_source_version_is_used_and_no_commit_is_invented`, `test_broken_metadata_falls_back_without_guessing`).
- Keine Ausschü/Weichungen in bestehenden Tests: `tests/unit/test_web_api_security.py` erhielt nur ergänzende Umgebungsvariablen und die drei Releasefeld-Assertions; `verify.sh` wurde nicht angerührt.
- Keine Skips, keine leeren Tests, echte Assertions; Fehlanlerinin etwa `assertTrue(true)`-Styles überall nicht gefunden.
- Terminologie konsistent: „Quelle/Installation/unbekannt" in CLI (`bin/vibe:3525-3534`), API (`bin/vibe-web.py:222-271`) und UI (`bin/web/app.js:129-134`); `/api/health` bleibt abwärtskompatibel.
- Umfang: keine fremden Änderungen; F4/F5/F14–F17 enthalten wie deklariert nur Pfad-/Namen-Anonymisierung (Diff durchggetContext).
- `VERA: /home/…`-Pfade in Git- und Unterlagen: grep zeigt keine user-identifizierenden absoluten Home-Pfade mehr; `tests/unit/test_storage.py:348` verwendet „nutzer" (Platzhalter) und passt so auch zur Release-Whitelist (`PLACEHOLDER_USERS`).

## Verification
- Change set reviewed: `d2d0fa9..working tree` (23 Dateien, vollständiger Diff über `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/opencode/v020-review.patch` + jedem neuen untracked Datei samt Quellcode erfolgreich gelesen; Arbeitsstand ist derselbe).
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git branch --show-current`.
- Checks with supplied output: verify.sh quick (Exit 0), verify.sh full in bwrap (Exit 0, 855/58/913), test_release -v (13 OK), test_central_workflows_ui -v (2 OK), HealthTest -v (2 OK). Zusätzlich von mir unabhängig: Trilium-Notiz `3IwzW6WLnBeU` via MCP gelesen; Grep nach `/home/<user>/`-Pfaden; VERSION = 0.18.0; Existenz von `scripts/check-no-secrets.py` (PATTERNS), `docs/compatibility.md`, `docs/features/V-017-bazzite.txt` verifiziert.
- Checks not independently run: alle Build/Laufzeit-Tests (durfte ich nicht selbst ausführen; nur gelieferte Ausgaben bewertet).
- Remaining risks: Trilium-Abschluss nach Zahlenkorrektur noch ausstehend; manuelle Bazzite-Abnahme datiert vom V-017-Zyklus (dokumentiert); Firefox/WebKit nicht geprüft (dokumentierte Grenze).
