# F27 Review Runde 2

## Ergebnis

**PASS**

Keine Critical/High/Medium-Befunde. Der Low-Befund aus Runde 1 ist in der Dokumentation angemessen und korrekt kartiert; die neue Formulierung deckt sich mit der Implementierung. Die beiden Minor-Hinweise bleiben unverändert offen (nicht blockierend, Zuständigkeit Test-Agent).

## Befunde

- Keine blockierenden Befunde. Zwei unveränderte Minor-Hinweise (siehe „Bezug zu Runde 1").
- [Minor] `docs/features/F27.md:136-139` — Lücken nur dokumentiert statt durch Tests geschlossen
  - Beleg: Die Grenzen benennen die ungetesteten CLI-Fehlerpfade (`bin/vibe:1951-1965`, Doppel-/Unbekannte-Option ohne Testfall) und die nicht geprüfte Dateinennung in der reinen CLI-Ausgabe (Implementierung `bin/vibe:1828-1829`, keine Assertion in `CliKeepChangesTest`, `tests/unit/test_f27_keep_changes.py:673-707`).
  - Auswirkung: Keine — Dokumentation einer nachvollziehbaren, von Runde 1 bereits so eingestuften Lücke. KISS-rein: kein Code- oder Testrückgriff durch den Coding-Agenten, korrekt.
  - Geforderte Korrektur: Keine blockierende; empfohlen als Nachkartierung: Test-Agent ergänzt CLI-Fehlpfadfälle, dann Grenztext aktualisieren.
- [Minor] `tests/browser/test_f27_keep_changes_ui.py:311-322` — schwache Assertion für sauberes Projekt (unverändert aus Runde 1)
  - Beleg: if-branch akzeptiert weiterhin „Button vorhanden, aber unsichtbar/deaktiviert" als „Pass"; die Grenzen von `docs/features/F27.md` erwähnen diese Lücke nicht.
  - Auswirkung: Gering; Kriterium 5 bleibt abgedeckt, nur schwächer als die Implementierung zeigt.
  - Geforderte Korrektur: Obliegt dem Test-Agenten (Schärfung), nicht dem Coding-Agenten.

## Bezug zu Runde 1

- **Low-Befund** (`bin/vibe-run.sh:507-511`, pauschale Neutralisierung des Zwischen-Checks unter Keep-Changes): **Adressiert.**
  - Runde 1 verlangte als Korrektur eine dokumentierte Einschränkung statt einer Änderung am Ticketverhalten. Genau das wurde umgesetzt:
    - `docs/features/F27.md:47-50` formuliert jetzt korrekt: „Bei Keep-Changes wird der Dirty-Check zwischen zwei Arbeitspaketen für den gesamten Lauf nicht zum Blocker, sondern als Hinweis protokolliert. Das toleriert bewusst auch zwischenzeitlich neu entstehende Änderungen; die Änderungen werden nicht Teil der Paketbranches."
    - `docs/features/F27.md:132-135` („Grenzen") ergänzt die Toleranz für neu entstehende Änderungen und benennt die mögliche spätere Verschärfung als Nicht-Ticket.
  - Die frühere, zu wohlwollende Lesart („bleibt grundsätzlich bestehen", auf den Erstbefund beschränkt) ist bereinigt.
  - **Keine falsche Zusicherung:** Der Formulierung liegt das tatsächliche Verhalten zugrunde — `DIRTY_NOW="$(git -C "$P" status --porcelain)"` wird in **jedem** Schleifendurchlauf bei `VIBE_KEEP_CHANGES=1` auf leer gesetzt und als HINWEIS nach stdout/Log geschrieben (`bin/vibe-run.sh:507-511`); der Kommentar dort (504-506) entspricht dem Dokumenttext. Auch die Gegenprüfungen stimmen: Die abschließende Gesamtprüfung bleibt ohne Keep-Changes-Ausnahme streng (`bin/vibe-run.sh:671-680`, `INTEGRATION_DIRTY` ohne Exemption), was die Dokumentbegriffe „Gesamtprüfung bleibt streng" (Z. 51-52, 130-131) und der Grenzformulierung „nicht Teil dieses Tickets" stützen.
- **Minor 1 (CLI-Edgecases ungetestet):** Status gleich geblieben (nicht geschlossen), aber zumindest durch `F27.md:136-137` sichtbar dokumentiert. Angemessen; die tatsächliche Beseitigung (zusätzliche Testfälle) obliegt dem Test-Agenten, nicht dem Coding-Agenten.
- **Minor 2 (schwache Browser-Assertion):** Unverändert offen, in der Doku nicht erwähnt; bleibt nicht-blockierender Hinweis.

## Geprüfte Nachweise

- Von mir ausgeführt (nur lesend): `git status --short`, `git log --oneline -8` (HEAD = `7c5a76f`, alle F27-Dateien uncommitted im Arbeitsbaum), `git diff --stat 7c5a76f`, `git diff 7c5a76f -- AGENTS.md bin/vibe-run.sh docs/import-manifest.json`, `git diff 7c5a76f -- docs/features/F27.md` (leer, Datei untracked). Volltext von `docs/features/F27.md` (141 Zeilen), `docs/reviews/F27-review-1.md`, Auszüge aus `bin/vibe-run.sh` (494-523, 668-685), `bin/vibe` (1785-1829, 1915-1974), `tests/unit/test_f27_keep_changes.py` (395-434, 650-724, grep auf Dateinennung/CLI-Tests), `tests/browser/test_f27_keep_changes_ui.py` (308-325), grep auf `bin/vibe` für die CLI-Fehlermeldungen.
- Bestätigung „keine Produktions-/Teständerung seit Runde 1": Die Zeilenangaben der Runde-1-Befunde treffen unverändert zu (`vibe-run.sh:507-511`, `tests/browser/test_f27_keep_changes_ui.py:311-322`), die Befundstrings und der Umsetzungstext sind identisch (`bin/vibe:1931, 1945-1970`, `1824-1829`, `vibe-run.sh`-F27-Kommentare). Ich kann keine Dateizeitstempel prüfen (scp-/ls-Berechtigungen denegiert), aber Inhaltsabgleich und die Angabe des Auftraggebers decken sich.
- Nicht von mir ausführbar: Keine Builds/Tests (read-only, keine Freigabe); Testergebnisse beruhen weiter auf übergebenen Ausgaben des Runde-1-Pakets.

## Restrisiken/Grenzen

- Die Abwesenheit produktiver Änderungen seit Runde 1 ist über Inhaltsabgleich belegt, nicht durch Zeitstempel oder Hashvergleich — Restunsicherheit gering, aber formal nicht zwingend.
- Die im Arbeitsbaum fremde AGENTS.md-Änderung (gestrichener Commit-Meldungspunkt) besteht weiter unverändert; sie muss beim F27-Commit weiterhin ausgeschlossen bleiben (Runde 1 nannte das als Bewusstzustand, nicht als F27-Verstoß).
- Die Fehlschläge der Vollprüfung (`test_ap04_setup_harness`, `test_release`) sind nach wie vor `7c5a76f`-Reproduktionen aus Agentenberichten, nicht von mir nachgestellt.
