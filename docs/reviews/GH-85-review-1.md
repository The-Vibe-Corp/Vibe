# Review — GH-85 „Check on new regressions" (Runde 1)

> Hinweis des Koordinators (Speicherung gemäß Repository-Regeln „keine privaten
> Pfade in Dokumenten"): Im Bericht zitierte absolute private Home-Pfade im
> Format `/home/<nutzer>/…` wurden beim Speichern geschwärzt; Inhalt und
> Urteil sind unverändert.

**Geprüfte Änderungsmenge:** Worktree `/var/log/custom/vibe-dev/worktrees/vibe-GH-85-WTW8xg`, Branch `feature/korbat/gh-85`, Start-Commit `b28e819320682c55deccc06adb8eeafe273aa184`. HEAD/ORIG_HEAD/reflog bestätigen: **noch kein Commit vorhanden** — die Änderungsmenge besteht aus uncommittetem Arbeitsbaum-Inhalt: der überarbeiteten `docs/features/GH-71.md` (1 Zeile) und dem neuen `docs/features/GH-85.md`, plus Laufzeitstand (`TICKET-GH-85.json`, ungetrackte pycache/lock-Verzeichnisse, `.vibe/project.env` — alles gitignored und außerhalb des Scopes).

**Zusammenfassung:** Die Ursachenanalyse und die Korrektur an `GH-71.md` sind stimmig und verifiziert. Das Paket-Dokument **`docs/features/GH-85.md` selbst führt jedoch genau den behobenen Defekt wieder ein**: Zeile 9 zitiert den wörtlichen privaten Home-Pfad `/home/<nutzer>/…`, den der Release-Inhaltsscan als 6. Befund flaggt. Mit diesem Inhalt im Baum kann `test_release` seine Baseline-Signatur nicht reproduzieren; der gelieferte `full → BASELINE-OK`-Nachweis kann damit für die finale Änderungsmenge nicht gültig sein, und der Abschluss-Commit würde Exit 7 mit neuer Regression auslösen — genau das Szenario, nach dem das Ticket fragt.

**Befundzählung:** Kritisch 0 · Hoch 1 · Mittel 1 · Klein (Vorschläge) 2

## Akzeptanzkriterien

| Kriterium | Status | Ort / Beleg |
|---|---|---|
| (a) Diff = nur GH-71.md-Zeile-7-Umbenennung + neues GH-85.md | **Teilweise verifiziert** | GH-71.md im Worktree unterscheidet sich von der committeten Kopie im Integrationsstand (`/opt/custom/vibe-dev/workspaces/vibe`, Branch `dev`) **nur** in Zeile 7: „neun historische absolute `/home/<nutzer>/…`-Pfade" → „neun historische absolute Home-Pfade". Reflog: kein Commit. Vollständiges „nichts anderes geändert" **NICHT VERIFIZIERT** (siehe Grenzen). |
| (b) Signatur-Begründung | **Mechanismus verifiziert, exakte Hashes NICHT VERIFIZIERT** | `verify_engine.py:506-521`: Signatur = sha256(Modul + Klasse + erste Meldungszeile nach `normalize_message`); Normalisierung entfernt Pfade/Zeilennummern/Daten/Zeiten, aber **nicht** den `[...N chars]`-Kürzungsmarker — der Hash hängt also von der Befundanzahl ab. `run-tests-parallel.py:62-65,156-161`: erste Traceback-Zeile gemäß `EXCEPTION_RE` liefert Klasse+Meldung. Baseline `tests/verify-baseline.json:10,90` enthält `b453a148…` (test_repository_hygiene) und `dbe32e8a…` (eine von 4 test_release-Varianten); keines der vier „neuen" Signaturen steht in der Baseline. Exakte sha256-Werte nicht nachgerechnet (keine Shell). |
| (c) GH-71.md war der einzige neue Scan-Befund | **Für die Umbenennung korrekt — für den aktuellen Baum widerlegt** | Repo-weites Greppen nach `HOME_PATH_RE`-treffenden Stellen: exakt 5 bestehende Nicht-Platzhalter-Befunde (GH-58-review-1.md:5/19/82, GH-58-review-3.md:21 — `/home/<nutzer>/VibeCode/vibe`; B7-subagent-permissions.md:109 — `/home/<nutzer>/…`; alle `nutzer`/`name`-Treffer sind Platzhalter gemäß `build-release.py:72-82`), plus der neue `GH-85.md:9`. |
| (d) test_harness / test_setup_vibe nicht reproduzierbar, transient | **Plausibel** | `run-tests-parallel.py:31,118-128,141-161`: 900-s-Modulzeitlimit; bei Zeitüberschreitung (oder jeglichem Ausgang ohne `Error/Exception/Failure`-Ausnahmezeile) liefert `error_details` `(None, None)` → Bericht meldet Klasse „unbekannt". Einzeln-Läufe sind vom Koordinator geliefert; konsistent mit der Full-Run-Beobachtung. Keine Codeänderung gerechtfertigt. |
| (e) GH-85.md zutreffend, keine privaten Pfade/Geheimnisse | **NICHT ERFÜLLT** | Zentrale Aussagen („beide Module stellen die Baseline-Signaturen wieder her", „genau einmal") werden von GH-85.md-Zeile 9 selbst widerlegt (siehe Befund 1). Keine Geheimnisse enthalten. |
| (f) Antwort auf „grundsätzliches Setup-Problem / neues Ticket?" | **Im Prinzip korrekt** | Der Scan ist inhaltsbasiert (`test_release.py:315-347` scannt getrackte + ungetrackte; `test_repository_hygiene.py:78-81,260-286` scannt getrackte, liest Arbeitsbaum-Inhalt); baseline-bekannte Fehlschläge bestehen fort und sind akzeptiert; ein neuer Fehlschlag tritt nur bei **neuem** verstoßendem Inhalt auf. GH-85.md §„Kein grundsätzliches Setup-Problem" stellt das korrekt dar — die Änderungsmenge committet dann aber neuen verstoßenden Inhalt, womit die Schlussfolgerung sich selbst widerlegt. |

## Befunde — erforderliche Korrekturen

**[Hoch] 1. `docs/features/GH-85.md:9` enthält den wörtlichen privaten Home-Pfad `/home/<nutzer>/…`.**
- Ort: `docs/features/GH-85.md`, Zeile 9: „…den wörtlichen absoluten Home-Pfad `/home/<nutzer>/…` (selbstbezüglich als Beispiel…)".
- Folge: `HOME_PATH_RE` (`scripts/build-release.py:72`) matcht („vibe" ist nicht in `PLACEHOLDER_USERS`); die Datei ist weder excluded noch gitignored. `test_release` (getrackte + ungetrackte Scan) meldet dann **6 Befunde** statt der baseline-bekannten 5 → die gekürzte `Lists differ: [...N chars]…] != []`-Erstzeile weicht von allen 4 Baseline-test_release-Signaturen ab → `verify.sh full` über diese Änderungsmenge meldet neue Regression (Exit 7), und nach Committen von GH-85.md regrediert `test_repository_hygiene` (nur getrackte) ebenso. Der gelieferte `BASELINE-OK`-Nachweis kann daher nicht der finalen Änderungsmenge entsprechen, und die Aussagen von GH-85.md zu wiederhergestellten Baseline-Signaturen und „genau einmal" sind so nicht haltbar.
- Empfohlene Korrektur: Zeile 9 ohne wörtlichen Pfad umformulieren, gemäß etablierter Platzhalter-Konvention (z. B. „…einen wörtlichen absoluten Home-Pfad im Format `/home/<nutzer>/…`", vgl. `docs/features/AP6-Korbat.md:290` und die AP17-Review-Präzedenz). Danach nachverifizieren und den Verifikationsabschnitt von GH-85.md an den finalen Baum anpassen.

**[Mittel] 2. Gelieferte Verifikation deckt die finale Änderungsmenge nicht ab.**
- Der beobachtete `full → BASELINE-OK, exit 0`-Lauf kann GH-85.md in der vorliegenden Form nicht enthalten haben (Befund 1 hätte eine test_release-Regression erzwungen), und die behaupteten wiederhergestellten Signaturen `dbe32e8a…`/`b453a148…` wurden von mir nicht unabhängig reproduziert. Erforderlich: nach der Zeile-9-Korrektur die Prüfungen über den finalen Baum erneut ausführen — mindestens `bash scripts/verify.sh full` (oder die beiden Scan-Module plus `quick`) — und diesen Ausgang als Paketnachweis dokumentieren. Ein akzeptierter Lauf über den tatsächlichen Endstand ist für die Übergabe erforderlich.

## Befunde — optionale Vorschläge

- **[Klein, Vorschlag]** GH-85.md könnte die Platzhalter-Regel explizit nennen (z. B. Verweis auf die `/home/<nutzer>/…`-Konvention), damit künftige Nachweisdokumente den Fehler nicht wiederholen; das Dokument verweist derzeit nur auf `docs/verification-baselines.md` und eine allgemeine Prozessregel.
- **[Klein, Vorschlag]** Für die transienten „unbekannt"-Einstufungen: vermerken, dass eine Signatur mit unbekannter Klasse/leerer Meldung nur Modul + leeren Payload hasht, sodass ein erneutes Auftreten einer „unbekannt"-Fehlschlags in `test_harness`/`test_setup_vibe` die identische Signatur reproduziert und sich diese bei Persistenz gezielt in die Baseline aufnehmen ließe.

## Grenzen der Prüfung

- `shell` wurde in dieser Review-Sitzung verweigert (`Permission denied: shell`); Code Mode stellt keine Git-/Dateisystemwerkzeuge bereit. Folglich: kein `git status`/`git diff`, keine Testausführung, keine sha256-Nachrechnung. (a) wurde durch Inhaltsvergleich der Worktree-Kopie von GH-71.md gegen die committete Integrationsstand-Kopie und über das Reflog verifiziert (kein Commit, HEAD = ORIG_HEAD = b28e819); vollständige Ausschlussprüfung weiterer Arbeitsbaum-Änderungen NICHT VERIFIZIERT. Alle Signaturwerte sind mechanismusbasierte Behauptungen, nicht nachgerechnete Ergebnisse.
- Prüfausgänge des Koordinators (`full` → BASELINE-OK exit 0, 2721 Tests, 65/76 Module; `quick` exit 0) sind als gelieferte Belege behandelt; sie werden für die finale Änderungsmenge gemäß Befund 1/2 widerlegt.

Verdict: CHANGES REQUIRED
