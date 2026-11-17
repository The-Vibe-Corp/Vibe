# Reviewantwort AP18 — Runde 2

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-17.
Geprüfter Umfang: `aabae4c..e3e485c` (Zweig `feature/m0p/ap18-cli-webui-password`).
Die Antwort ist wörtlich übernommen (bis auf diesen Kopfkasten).

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Acceptance criteria
| Kriterium | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| `--stdin` nur mit Unteraktion `set` gültig; `password --stdin`, `clear --stdin`, `status --stdin` brechen mit Usage ab, ohne ui.json zu lesen/ändern | PASS | `bin/vibe:5115-5119` (Bedingung `use_stdin and sub != "set"` → `sys.exit(UI_PASSWORD_USAGE)`); der Abbruch erfolgt beim Argument-Parsen, bevor `_ui_password` ui.json berührt | `PasswordStdinMisuseTest` (4 Fälle) alle ok in `/tmp/vibe-verify-4v22rim_/verify.log:442-445`; Rotphasenangabe „2 der 4 Fälle fehlgeschlagen gegen aabae4c“ ist mit dem alten Code konsistent (alte Bedingung `sub not in (None, "set")` akzeptierte nur `sub=None` still; `clear`/`status` mit `--stdin` wurden dort bereits abgewiesen) |
| `vibe ui password set --stdin` weiterhin gültig (auch `--stdin set`) | PASS | `bin/vibe:5115` (`sub == "set"` erfüllt in beiden Token-Reihenfolgen) | `PasswordSetStdinTest` (4 Fälle) weiterhin ok in verify.log:435-438 |
| Kennwort nie als Argument / Usage-Text unverändert | PASS | `bin/vibe:5036`, `5107-5114` | `PasswordArgumentRejectionTest` ok, verify.log:427; Usage-Literal `5036` identisch mit Testkonstante `PasswordStdinMisuseTest.USAGE` |
| Bestehende AP18-Fälle unverändert (keine Assertion abgeschwächte/gelöschte Tests) | PASS | Diff `tests/unit/test_ap18_cli_ui_password.py`: 127 insertions, 0 deletions — rein additive Klasse + Doku-Block | Gesamter Diff `aabae4c..e3e485c` gelesen; alle 24 AP18-Fälle ok in verify.log:425-448 |
| getpass-Echo-Fallback-Grenze dokumentiert | PASS | `docs/features/AP18.md:107-112` | Direkt gelesen (Minor 3 aus Runde 1 adressiert) |
| Testdatei-Änderungen nach Runde 1 nur durch Test-Agenten | PASS | `docs/reviews/AP18-test-agent-report.md:83-90` („Nachtrag Runde 1 (Test-Agent)“) | Angabe des Testberichts — Autorenschaft ist nicht technisch prüfbar; keine gegenteiligen Indizien im Diff |
| Keine AP18-Regressionen im vollen Lauf | PASS | — | `/tmp/vibe-verify-4v22rim_/verify.log:4460-4462` (1836 Tests, failures=39, errors=96, skipped=1); von mir geprüft: FAIL/ERROR-Listen beider Logs (`_9pfg8d0` Runde 1 vs. `4v22rim_` Runde 2) je 135 Einträge, testweise deckungsgleich; AP13-Reload-Fall ok (Zeile 426) |
| Manifest aktualisiert und stimmig | PASS | `docs/import-manifest.json:933` (erweiterter `grund`), `948-950` (`bytes: 261362`, `sha256: 41a1c47…` für bin/vibe) | verify.log:4 „OK: 57 Dateien stimmen mit docs/import-manifest.json überein.“ (Artefakt-Nachweis; Hash nicht von mir selbst berechnet, siehe Verification) |
| Trilium-Dokumentation vorhanden | PASS | `docs/trilium-index.md:68` (Notiz `LtyM7rb6m1I0`) | Notiz von mir über Trilium-MCP gelesen (Titel, Elternbereich, Inhalt stimmen; s. Minor 2 zur Aktualität) |

## Findings

- [Minor] `docs/features/AP18.md:64-94` — Testabschnitt noch auf Runde-1-Stand (20 Fälle / 1832 Tests)
  - Evidence: Nach e3e485c gibt es 24 AP18-Fälle (`PasswordStdinMisuseTest` fehlt in der Liste ab Zeile 70) und der volle Lauf zählt 1836 Tests; Abschnitt „Tests“/„Prüfungen“ nennt weiterhin „20 Fälle“, „20/20 OK“ und „1832 Tests“. Der verschärfte Parser (`--stdin` nur mit `set`) ist in AP18.md nicht beschrieben, nur im Manifest-`grund` und in den Tests.
  - Required fix: Testliste und Prüfungszahlen in AP18.md auf den Stand nach Runde 1 heben und das Usage-Verhalten bei `--stdin` ohne `set` in der Feature-Doku nennen.

- [Minor] Trilium-Notiz `LtyM7rb6m1I0` — ohne Runde-1-Nachtrag
  - Evidence: Notizinhalt (von mir via MCP gelesen) verweist nur auf Commit `aabae4c` und nennt die `--stdin`-Beschränkung nicht; die in Runde 1 nachgeschobene Parser-Änderung ist dort nicht dokumentiert. Die Notiz ist inhaltlich nicht falsch, aber nicht aktuell.
  - Required fix: Notiz um Commit `e3e485c` und die Regel „`--stdin` nur mit `set`“ ergänzen.

Nicht beanstandet (ausdrücklich geprüft): `--stdin set` in umgekehrter Reihenfolge wird akzeptiert — das ist der bewusst tokenbasierte, reihenfolgeninsensitive Parser (analog `--port`/`--bind` anywhere), erfüllt die geforderte Regel „nur mit `set`“ vollständig und hat kein Sicherheitsrisiko (Kennwort bleibt nie argv). Kein Befund.

## Verification
- Change set reviewed: `aabae4c..e3e485c` — vollständige Diffs aller 7 geänderten Dateien (`bin/vibe`, `docs/features/AP18.md`, `docs/import-manifest.json`, `docs/reviews/AP18-review-1.md`, `docs/reviews/AP18-test-agent-report.md`, `docs/trilium-index.md`, `tests/unit/test_ap18_cli_ui_password.py`); Arbeitsbaum sauber (`git status --short` leer, damit byteidentisch mit `e3e485c`).
- Git commands run by me: `git log --oneline -6`, `git status --short`, `git diff --stat aabae4c..e3e485c`, `git diff aabae4c..e3e485c` (aufgeteilt nach Dateigruppen). (`git branch --show-current` und alle Nicht-Git-Shell-Befehle wurden von der Berechtigung abgelehnt.)
- Checks with supplied output (Artefakte ausgewertet, nicht selbst ausgeführt): `/tmp/vibe-verify-4v22rim_/verify.log` — Zeile 4 Manifest-OK (57 Dateien), Zeilen 5-6 Syntax/Geheimnisse OK, Zeilen 425-448 alle 24 AP18-Fälle ok, Zeilen 4460-4462 (1836 Tests, failures=39, errors=96, skipped=1); FAIL/ERROR-Listen von Runde-1- und Runde-2-Log von mir zeilenweise verglichen — identisch (je 135 Einträge, keine neuen Fehlschläge). Trilium-Notiz `LtyM7rb6m1I0` über MCP gelesen.
- Checks not independently run: alle Build-/Test-/Prüfkommandos (unittest, verify.sh quick/full, check-import-manifest, sha256sum — die Richtigkeit von `bytes`/`sha256` für `bin/vibe` beruht auf dem verify.log-Artefakt plus sauberem Arbeitsbaum, nicht auf eigener Hashberechnung); Autorenschaft der neuen Testfälle nicht technisch verifizierbar.
- Important areas inspected: `bin/vibe:5033-5144` (`_ui_password`, `_ui_arguments`, `UI_PASSWORD_USAGE`), kompletter Test-Diff, AP18.md (Tests-/Grenzen-Abschnitte), Testbericht komplett, Manifest-Diff, Trilium-Notiz, beide Verify-Logs.
- Remaining risks: (1) vorbestehende Defekte außerhalb des Pakets unverändert (identische FAIL/ERROR-Liste); (2) `set`/`clear` im laufenden Betrieb mit bereits gesetztem Kennwort weiterhin nur über den AP13-gesicherten `set_password`-Pfad abgedeckt (dokumentierte Grenze aus Runde 1, unverändert).
