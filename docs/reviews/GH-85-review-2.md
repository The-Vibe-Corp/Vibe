# Review — GH-85 „Check on new regressions" (Runde 2, fokussiert)

> Hinweis des Koordinators: Bericht unverändert gespeichert; er enthält keine
> wörtlichen privaten Pfade.

**Scope:** Verifikation, dass beide Runde-1-Blocker behoben sind und sich gegenüber dem Runde-1-geprüften Stand nichts anderes geändert hat — Worktree `/var/log/custom/vibe-dev/worktrees/vibe-GH-85-WTW8xg` (Branch `feature/korbat/gh-85`, Start-Commit `b28e819320682c55deccc06adb8eeafe273aa184`, uncommittete Arbeitsbaum-Änderungsmenge).

**Befundzählung:** Kritisch 0 · Hoch 0 · Mittel 0 · Klein 1 (Vorschlag, nicht blockierend)

## Blocker-Auflösung

**Blocker 1 (Hoch) — wörtlicher privater Home-Pfad in `docs/features/GH-85.md` Zeile 9: BEHOBEN.**
- `GH-85.md` Zeile 9 verwendet jetzt die regex-sichere Platzhalterform `/home/<nutzer>/…`. `HOME_PATH_RE` (`scripts/build-release.py:72`, `PLACEHOLDER_USERS` in :73-82 enthält `nutzer`) kann nicht matchen: die Zeichenklasse `[A-Za-z0-9._-]+` schließt `<`/`>` aus.
- Unabhängiger Repo-weiter Scan (Muster `/(home|Users)/[A-Za-z0-9._-]+/` plus manuelle Anwendung der Look-behind-Bedingung `(?<![\w/.-])`, da ripgrep hier ohne Look-around arbeitet): exakt **5** Nicht-Platzhalter-Befunde, alle mit dem bestehenden Nicht-Platzhalter-Benutzernamen, und genau die erwarteten Orte — `docs/reviews/GH-58-review-1.md:5,19,82`, `docs/reviews/GH-58-review-3.md:21`, `docs/features/B7-subagent-permissions.md:109`. Die Treffer `/tmp/pruefung/home/.local/…` (`tests/unit/test_release.py:224`) und `/tmp/opencode/f6-check/home/.local/…` (`docs/features/F6.md:279,283`) werden korrekt durch das Look-behind ausgeschlossen (`home` mit vorangestelltem `/`); alle übrigen Treffer nutzen erlaubte Platzhalter-Benutzer. **Kein 6. Befund; nichts Neues im gesamten Baum, einschließlich beider Review-Dateien und GH-85.md.**

**Blocker 2 (Mittel) — Verifikation deckte die finale Änderungsmenge nicht ab: BEHOBEN.**
- `GH-85.md` §„Verifikation" Punkt 3 dokumentiert einen wiederholten Bestätigungslauf `bash scripts/verify.sh full` über den finalen Baum (ausdrücklich einschließlich Paketdokument und Review-Bericht) → **BASELINE-OK, Exit 0, 2721 Tests, 65/76 Module, 11 fehlgeschlagene Module allesamt baseline-bekannt**, darunter `test_release` und `test_repository_hygiene`. Dies ist vom Koordinator gelieferter Prüfausgang, gestützt durch meine unabhängigen Belege: die Content-Scan-Signaturen sind eine deterministische Funktion der Fünf-Befunde-Liste, die ich unabhängig als im Baseline-Zustand bestätigt habe (exakt die 5 bestehenden Befunde), und die behaupteten wiederhergestellten Signaturen `sha256:dbe32e8a…` (test_release) und `sha256:b453a148…` (test_repository_hygiene) stehen in `tests/verify-baseline.json` (Zeilen 90 und 10). Die vier „neuen" Regressionssignaturen und die beiden „unbekannt"-Module aus dem Ticket stehen **nicht** in der Baseline — konsistent mit dem Behobenen-Narrativ.

## Akzeptanzkriterien

| Kriterium | Status | Beleg |
|---|---|---|
| (a) Änderungsmenge = GH-71.md-Zeile-7-Umbenennung + neues GH-85.md + neues GH-85-review-1.md; sonst nichts | PASS (mit dokumentierter Grenze) | Reflog (`.git/worktrees/vibe-GH-85-WTW8xg/logs/HEAD`): kein Commit, HEAD = b28e819, einziger Eintrag „reset: moving to HEAD". `docs/features/GH-71.md` zeilenweise verglichen mit der committeten Integrationsstand-Kopie (`/opt/custom/vibe-dev/workspaces/vibe/docs/features/GH-71.md`): **nur Zeile 7 abweichend** („neun historische absolute Home-Pfade" statt des wörtlichen Pfads; alle 26 übrigen Zeilen identisch). Beide neuen Dateien vollständig gelesen. Vollständiger git-basierter Ausschluss weiterer geänderter getrackter Dateien NICHT VERIFIZIERT (siehe Grenzen). |
| (b) Keine neuen HOME_PATH_RE-Befunde | PASS | Unabhängiger Repo-weiter Scan: exakt die 5 bestehenden Befunde, nichts Neues; die Änderungsmenge liefert null Befunde (Details unter Blocker 1). |
| (c) Inhaltliche Richtigkeit von GH-85.md | PASS | Zeile 9: beide Inhaltsscan-Regressionen auf den wörtlichen Pfad in GH-71.md Zeile 7 zurückgeführt, per Umbenennung behoben, Baseline-Signaturen wiederhergestellt (Hashes unabhängig in der Baseline bestätigt). Zeile 10: die beiden „unbekannt"-Regressionen als transient/nicht reproduzierbar dokumentiert (128 Tests OK einzeln und parallel; keine Produktionscodeänderung; Mechanismus erklärt, einschließlich des übernommenen kleineren Vorschlags, dass eine „unbekannt"-Signatur nur Modul + leere Meldung hasht). §„Kein grundsätzliches Setup-Problem": kein grundsätzliches Setup-Problem, kein neues Ticket erforderlich, Platzhalter-Konvention ausdrücklich benannt (übernommener kleinerer Vorschlag). §„Nachweise aus dem Review": Runde-1-Korrektur dokumentiert. §„Verifikation": finaler BASELINE-OK-Lauf dokumentiert. |

**Integrität des Runde-1-Berichts:** `docs/reviews/GH-85-review-1.md` endet mit der unveränderten Klartextzeile `Verdict: CHANGES REQUIRED`; die Schwärzungsnotiz des Koordinators ist vorhanden, und der Bericht enthält keinen regex-treffenden wörtlichen privaten Pfad.

## Befunde

**Erforderliche Korrekturen:** keine.

**Klein (Vorschlag, optional):** In der gespeicherten `docs/reviews/GH-85-review-1.md` präsentiert die Schwärzung im Befundtext den markierten Pfad in der Platzhalterform, während der tatsächlich markierte Benutzername (Nicht-Platzhalter) nur aus der Klammerbegründung in Befund 1 („… ist nicht in `PLACEHOLDER_USERS`") rekonstruierbar ist. Eine ergänzende Notiz im Koordinationskopf (z. B. dass der geschwärzte Benutzername der lokale Nicht-Platzhalter war) würde den historischen Bericht voll selbsterklärend machen. Nicht blockierend; Urteil und Bewertung sind unberührt.

## Grenzen der Prüfung

- `shell` ist in dieser Review-Sitzung verweigert (`Permission denied: shell`); Code Mode stellt keine Git-/Dateisystemwerkzeuge bereit. Folglich: kein `git status`/`git diff`, keine Testausführung, keine sha256-Nachrechnung. Die Änderungsmenge wurde über Reflog/HEAD-Lesezugriffe, den zeilenweisen Vergleich von `GH-71.md` gegen die committete Integrationsstand-Kopie (dieselbe Methode wie in Runde 1) und vollständige Lesezugriffe der beiden neuen Dateien verifiziert. Vollständiger Ausschluss *jeder anderen* geänderten getrackten Datei bleibt durch Git selbst NICHT VERIFIZIERT; er wird indirekt gestützt durch (i) die Runde-1-Festlegung der Änderungsmenge, (ii) meinen unabhängigen Repo-weiten Inhaltsscan ohne Neubefund und (iii) den vom Koordinator gelieferten finalen Full-Run, der über den finalen Baum grün/baseline ist.
- Das finale `verify.sh full` → BASELINE-OK-Ergebnis ist vom Koordinator gelieferter Prüfausgang, nicht von mir ausgeführt; die Baseline-Signatur-Hashes und der Fünf-Befunde-Scan-Zustand wurden wie oben unabhängig verifiziert.
- Scan-Scope-Äquivalenz geprüft: der Release-Scan (`tests/unit/test_release.py:315-347`) umfasst getrackte + ungetrackte, nicht ignorierte Dateien; `TICKET-GH-85.json`, `.vibe/` und pycache sind über `.git/info/exclude`/`.gitignore` ausgeschlossen, und in `docs/` gibt es keine versteckten, nicht ignorierten Dateien.

Beide Runde-1-Blocker sind mit unabhängiger Bestätigung behoben; keine neuen Defekte und keine unerklärten Änderungen gefunden.

Verdict: PASS
