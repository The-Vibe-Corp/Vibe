# Review — Fix: Geerbtes OPENCODE_PASSWORD (Runde 2)

> Unverändert gespeicherte Antwort des unabhängigen Reviewers (Code-Reviewer,
> read-only). Diese Datei wurde vom Coding-Agenten wortgleich abgelegt.

## Zusammenfassung

- Critical: 0
- High: 0
- Medium: 1
- Minor: 2
- Verdict: **CHANGES REQUIRED**

Alle vier Runde-1-Befunde (M1 Restpfad `.vibe/project.env`, M2 Nachweislücken, Low1 Manifest-`aenderungen`, Low2 Tippfehler) sind sachlich korrekt und vollständig behoben. Die Fixstellen sind statisch nachgeprüft; die konservierten Rot-/Grünphasen-Artefakte existieren, habe ich selbst gelesen, und sie stimmen wortgleich mit dem Testbericht und mit den Assertions der aktuellen Testdatei überein (Zeilennummern der Tracebacks decken sich mit dem Dateistand — ein Indiz, dass nach der Rotphase nichts abgeschwächt wurde). Die Trilium-Notiz habe ich selbst über MCP gelesen und gegen die Behauptungen geprüft — zutreffend.

Ein verbindlicher Prüfschritt bleibt offen: `bash scripts/verify.sh full` wurde weder in Runde 1 noch in Runde 2 ausgeführt oder berichtet, obwohl AGENTS.md beide Modi ausdrücklich verbindlich vorschreibt und frühere Pakete dieses Projekts den full-Lauf regelmäßig erbracht haben. Ein Verzicht darauf wurde nicht begründet; nach AGENTS.md („Pflichtprüfung nicht möglich: blockiert, kein vorgetäuschter Erfolg") ist darauf kein PASS möglich.

## Prüfkonto

**Gelesene Dateien (vollständig bzw. relevantem Ausschnitt):**

| Datei | Befund |
|---|---|
| `docs/reviews/fix-opencode-password-env-review-1.md` | Runde-1-Antwort, 4 Befunde, unverändert abgelegt |
| `docs/reviews/fix-opencode-password-env-test-agent-report.md` | neu; Herkunft (2 Sitzungen mit IDs), Fallbeschreibungen, Rot-/Grünphasen- und Regressionsergebnisse, Aufräumen |
| `docs/features/fix-opencode-password-env.md` | Umsetzungstabelle (zweiter `unset`), AK-Tabelle inkl. AK1b, Bekannte Grenzen, Nachweise; „honoriert" korrigiert (Z. 39); „Runde 2: ausstehend" (Z. 142) |
| `docs/import-manifest.json` | `aenderungen`-F31-Eintrag Z. 851–859 (beide Dateien, 2026-11-14, Begründung inkl. M1-Restpfad); `files`-Einträge `bin/vibe` 257883 B (Z. 873–876), `bin/vibe-run.sh` 56672 B (Z. 878–881) |
| `bin/vibe-run.sh` | Fixstellen Z. 46 (vor Kennwortbehandlung) und Z. 232–239 (`unset` unmittelbar nach `set -a && . ./.vibe/project.env && set +a`); Startpfade Z. 161–202 (`setsid`-Kette, Sandbox-Wrap), `ensure_private_server` Z. 207–228, Aufruf Z. 509 |
| `bin/vibe` | `cmd_server` Z. 4837–4872; `unset OPENCODE_PASSWORD` im tmux-Innenbefehl Z. 4869 nach `source ~/.bashrc`, vor dem Export aus der Kennwortdatei |
| `tests/unit/test_f31_inherited_opencode_password.py` | komplett (518 Zeilen); AK1b-Fall Z. 252–343 inkl. `define_project_env_password()` |
| `bin/vibe_sandbox.py` | Z. 275–319: liest `project.env` nur für `SANDBOX`/`SANDBOX_TOOLS`; Z. 624/646: `execvpe(..., os.environ)` unverändert — keine Wiedereinspeisung |
| `/tmp/opencode/f31-evidence/red-10dca46.txt`, `green-fix-stand.txt` | selbst gelesen: Rot **4 Tests, FAILED (failures=3)** mit `opencode_password_present: True, len 18` (AK1, AK1b, AK3; AK2 ok), Grün **4/4 OK**, Laufzeiten 12,56 s/12,57 s |
| `scripts/verify.py`, `scripts/verify.sh`, `.vibe/project.env` | `VERIFY_FULL` (Z. 5) = Manifest-/Syntax-/Geheimnisprüfung + `unittest discover tests/unit` + `tests/browser` |
| `docs/trilium-index.md` | Z. 66: Notiz-ID `PgaZqt2vEwBQ` stimmt |

**Selbst ausgeführte, nicht-Shell-Prüfungen:**

- Trilium-Notiz `PgaZqt2vEwBQ` per MCP gelesen: Titel korrekt, Elternordner `IjRpjYJTtqam`, Labels `projekt:vibe`/`bereich:Features`; Inhalt enthält „erneut nach dem Einlesen von .vibe/project.env (Restpfad, Review-Befund M1)", „AK1b", Commits `88509a0`/`8a31f5f`, Regression 30/31, `verify.sh quick` Exit 0, „Runde 2 ausstehend". Kein „honor"/„Folgeararbeit"-Tippfehler mehr enthalten.
- Konservierte Rot-/Grünphasen-Rohausgaben selbst gelesen und mit Testbericht, Testdatei-Assertions und Fehlermeldungen abgeglichen — konsistent (inkl. Traceback-Zeilennummern 170/315/485, die exakt zur aktuellen Testdatei passen).
- Statische Reihenfolgeanalyse des Läufers (siehe AK1b-Zeile unten): nach dem zweiten `unset` (Z. 239) gibt es bis zum privaten Serverstart keine Umgebungsschreibquelle mehr.

**Nicht möglich (Shell-Zugang auch in Runde 2 verweigert — jeder `shell`-Aufruf endete mit „Permission denied: shell"):**

- `git status/log/diff/show` im Worktree — Branch, Commitgrenzen (`10dca46`/`88509a0`/`8a31f5f`/`ee8998f`/`a0757d8`/`5128864`), Commitzugehörigkeit der neuen Dateien und Abwesenheit unrelated changes sind **nicht unabhängig verifiziert** (nur aus dem Arbeitspaket und dem Dateistand übernommen).
- `python3 -m unittest …`, `bash scripts/verify.sh quick|full`, `bash -n bin/vibe-run.sh` — nicht von mir ausgeführt.
- SHA-256/Byte-Nachrechnung der Manifest-Einträge — nicht möglich.

## Akzeptanzkriterien

| Kriterium | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: Geerbtes `OPENCODE_PASSWORD` aus der Startumgebung erreicht den privaten Server nicht | PASS | `bin/vibe-run.sh:46` — vor Kennwortbehandlung (Z. 47–58) und vor jedem Serverstart | `test_inherited_opencode_password_is_absent_from_the_server_env` (`test_f31…py:129`); Rotphase belegt (red-10dca46.txt:26), Grünphase 4/4 OK (green-fix-stand.txt:2) |
| AK1b (Runde-1-M1): `OPENCODE_PASSWORD` aus `.vibe/project.env` erreicht den Server nicht | PASS | `bin/vibe-run.sh:239` — `unset` unmittelbar nach dem `set -a`-Einlesen (Z. 232) | `test_project_env_opencode_password_is_absent_from_the_server_env` (`test_f31…py:271`, Fixture Z. 252–269 schreibt genau eine Zeile in `.vibe/project.env`, Prozessumgebung ohne Belegung); Rotphase belegt (red-10dca46.txt:43) |
| AK2: Ohne Belegung bleibt B13 unverändert | PASS | Fixstellen wirken nur bei geerbter Belegung | `test_without_inherited_password_b13_behaviour_is_unchanged` (`test_f31…py:198`); rot wie grün „ok" (red-10dca46.txt:6, green-fix-stand.txt:6) |
| AK3: Gemeinsamer Server (`vibe server start`) erbt nichts | PASS | `bin/vibe:4869` — `unset` im tmux-Innenbefehl nach `source ~/.bashrc`, vor Export aus der Datei | `test_server_start_does_not_inherit_opencode_password` (`test_f31…py:452`, echter tmux auf isoliertem Socket, Attrappe zeichnet eigene Prozessumgebung); Rotphase belegt (red-10dca46.txt:61) |
| AK4: Geheimhygiene — nur Anwesenheit/Länge, nie Klartext | PASS | Attrappen `runner_support.py` und `test_f31…py:366–376`; Klartext-Checks Z. 109–127, 503–514 | statisch verifiziert; Rohausgaben enthalten nur Booleans/Längen |
| Runde-1-M2: Test-Agent-Herkunft + konservierte Rotphase | PASS | `docs/reviews/fix-opencode-password-env-test-agent-report.md` (Sitzungs-IDs, Herleitung vor Implementierung, Größe-Begründung 18/15/33, Aufräumen) | Rohausgaben in `/tmp/opencode/f31-evidence/*` von mir gelesen, stimmig mit Bericht und Testdatei |
| Runde-1-Low1: Manifest-`aenderungen` | PASS | `docs/import-manifest.json:851–859` | statisch verifiziert; Prüfsummen nicht von mir nachgerechnet (Shell gesperrt) |
| Runde-1-Low2: Tippfehler | PASS | `docs/features/fix-opencode-password-env.md:39` („honoriert") | Trilium-Notiz selbst gelesen — korrigiert |
| Verbindliche Pflichtprüfung `bash scripts/verify.sh full` | **NOT VERIFIED** | — | weder ausgeführt noch berichtet (siehe Medium-Befund 1) |
| `bash scripts/verify.sh quick` Exit 0 | PASS (supplied) | — | vom Coding-Agenten berichtet; Manifest-/Syntax-/Geheimnisprüfung statisch plausibel, Ausführung nicht von mir wiederholt |

## Befunde

- [Medium] `scripts/verify.sh full` / `.vibe/project.env:5` — verbindliche Pflichtprüfung „full" weder ausgeführt noch berichtet
  - Evidence: AGENTS.md („Prüfungen") verlangt nach der Implementierung verbindlich `bash scripts/verify.sh quick` **und** `bash scripts/verify.sh full`. Laut AGENTS.md-Definition of Done sind „relevante automatisierte Prüfungen grün". Weder das Runde-1- noch das Runde-2-Material nennt einen full-Lauf. `.vibe/project.env:5` definiert `VERIFY_FULL` als Manifest-/Syntax-/Geheimnisprüfung plus `unittest discover tests/unit` **plus** `tests/browser` — kein echter Modellkosten-/OAuth-Problemfall (frühere Pakete wie V-014/V-016/V-019 haben den Lauf regelmäßig erbracht, notfalls in bwrap-/Mount-Namespace-Workarounds). Fehlschläge, die ein full-Lauf offenlegen würde (z. B. weitere Testsuiten, die vom zweiten `unset` oder vom `vibe_sandbox.py`-Verhalten betroffen sind), wurden daher nie als Ganzes geprüft; die F31- und drei Regressionssuiten allein sind keine full-Abdeckung.
  - Required fix: Keine Codeänderung. `bash scripts/verify.sh full` auf dem finalen Arbeitsstand (HEAD inkl. aller Nachweiscmms) ausführen — bei Umgebungsproblemen mit dem dokumentierten Projekt-Workaround (bwrap/Namespace) — und das Ergebnis in der Feature-Doku/Trilium-Notiz nachweisen; scheitert er, Fehlschläge als vorbestehend vs. regressiv belegen (Baseline-Vergleich) oder sauber blockiert melden.

- [Minor] `docs/reviews/fix-opencode-password-env-test-agent-report.md:22–24` — „konservierte Rohausgaben" liegen nur in vergänglichen `/tmp`-Pfaden
  - Evidence: Der Bericht verweist als dauerhafte Konservierung auf `/tmp/opencode/f31-evidence/red-10dca46.txt` und `green-fix-stand.txt` — außerhalb des Repositorys und bei Reboot/Containerwechsel weg. Dauerhaft bleiben nur die Zitate im Bericht (die im Kern ausreichend sind: drei Assertion-Meldungen + Ergebniszeile, aber nicht die vollständige unittest-Ausgabe mit allen OK/FAIL-Zeilen im Volltext).
  - Required fix: Vor dem Abschlusscommit die beiden Dateien (oder verlustfreie Auszüge) ins Repository übernehmen, z. B. als Anhang des Testberichts oder unter `docs/reviews/…`, und die Pfadangabe im Bericht korrigieren; andernfalls die Ephemerie im Bericht ausdrücklich kennzeichnen.

- [Minor] `docs/features/fix-opencode-password-env.md:99–102` und `docs/reviews/fix-opencode-password-env-test-agent-report.md:62–70` — Regressions- und Zwischenstand-Nachweise nur als Zusammenfassung, ohne Rohausgabe
  - Evidence: Die Regressionsläufe (B13 9 OK, B14 13 OK, B13-runner 8 OK + 1 vorbestehender AK6-Fehlschlag, Baseline-Vergleich am `10dca46`) und der ergänzende AK1b-Rotnachweis am Zwischenstand `a0757d8` sind nur als Zahlen-/Textzusammenfassung berichtet; es existiert kein konserviertes Rohausgaben-Artefakt wie für die Rot-/Grünphase. Die Vorbestehensbehauptung zum AK6-Fehlschlag („identisch am Fix-vorher-Stand") ist damit nicht gegen Manipulation oder Verwechslung abgesichert. Für den Runde-1-Befund M2 ist dies kein Blocker mehr (Rot-/Grünphase ist belegt), aber für die Abschlussabnahme des Pakets wären die Nachweise konservierenswert.
  - Required fix: Regressions- und Baseline-Rohausgaben (oder kompakte, nachprüfbare Auszüge mit Ergebniszeilen) zusammen mit dem full-Lauf (Medium-Befund) konservieren; keine Codeänderung.

**Explizit geprüfte, nicht beanstandete Punkte:**

- Reihenfolge/Restpfad-Analyse (Auftrag 2): Nach dem zweiten `unset` (Z. 239) gibt es bis zum privaten Serverstart keine Quelle mehr, die die Umgebung verändern könnte — die einzige `set -a`/`source`-Stelle ist Z. 232, unmittelbar davor; danach nur noch Lese-/Validierungsaufrufe (`vibe_sandbox.py --enabled/--check` als Kindprozesse), `set -m`/`set +m` (Jobkontrolle, keine Umweltauswirkung) und der `ensure_private_server`-Aufruf (Z. 509) in einem Subshell, das die bereits bereinigte Umgebung erbt; `setsid --fork` (Z. 173) und der Sandbox-Wrap (Z. 166/495) vererben sie unverändert (`execvpe(..., os.environ)`, `vibe_sandbox.py:624/646`). Im Pfad `vibe server start` liegt das `unset` innerhalb des tmux-Innenbefehls **nach** `source ~/.bashrc` und damit nach allen Profil-/bashrc-Injektionen, vor dem Export aus der Kennwortdatei. Der AK1b-Test deckt genau den M1-Restpfad ab: Prozessumgebung bewusst leer, Projektdatei definiert den Wert in exakt der Form, die `set -a; . file; set +a` exportiert; im Fehlerfall wäre `opencode_password_len: 18` beobachtbar — die Rotphase zeigt genau das.
- Assertion-Integrität: Die Traceback-Zeilennummern der Rotphase (170/315/485) stimmen exakt mit dem aktuellen Dateistand überein; die Assertion-Texte sind wortgleich. Zusätzlich zeigt die Rotphase AK2 grün — die Tests scheitern genau an den Fixstellen, nicht an Fixture-/Umgebungsproblemen.
- Manifest/Doku-Konsistenz: F31-`aenderungen`-Eintrag nennt beide Dateien und begründet die Prüfsummen; die `files`-Werte (257883/56672 B) entsprechen den im Arbeitspaket genannten Größen; Feature-Doku, Testbericht und Trilium-Notiz widersprechen einander an keiner Stelle.
- Geheimhygiene: Testliterale sind erkennbar Attrappen (`veraltet-16zeichen` — Länge 18, im Bericht begründet), Records enthalten nur `*_present`/`*_len`; kein Klartextpfad gefunden.

## Verdict

**CHANGES REQUIRED**

Begründung: Ein verbleibender Medium-Befund — die verbindlich vorgeschriebene Pflichtprüfung `bash scripts/verify.sh full` wurde für dieses Arbeitspaket nie ausgeführt oder berichtet. Alle sachlichen Runde-1-Befunde (M1 Restpfad inkl. AK1b-Test und korrekt platzierter zweiter `unset`, M2 Test-Agent-Herkunft und konservierte Rotphase, Low1 Manifest, Low2 Tippfehler) sind korrekt behoben und durch Artefakte belegt, die ich selbst gelesen und gegen den Dateistand geprüft habe; die Trilium-Notiz habe ich selbst verifiziert. Nach Ausführung/Durchführung des full-Laufs (samt Nachweis und ggf. Konservierung der zwei Minor-Punkte) ist ein PASS ohne erneute inhaltliche Prüfung des Codes realistisch.

Empfohlene Reihenfolge für Runde 3: (1) `verify.sh full` ausführen und nachweisen; (2) Minor-Befunde konservieren (Rohausgaben ins Repo, Regressions-/Baseline-Nachweise); (3) Review-Antwort ablegen, finalen Commit nur mit den eigenen Arbeitspaketdateien.
