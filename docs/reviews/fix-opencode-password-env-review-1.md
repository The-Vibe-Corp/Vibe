# Review — Fix: Geerbtes OPENCODE_PASSWORD (Runde 1)

> Unverändert gespeicherte Antwort des unabhängigen Reviewers (Code-Reviewer,
> read-only). Diese Datei wurde vom Coding-Agenten wortgleich abgelegt.

## Zusammenfassung

- Critical: 0
- High: 0
- Medium: 2
- Minor: 2
- Verdict: **CHANGES REQUIRED**

**Wichtige Einschränkung vorab:** Die Shell-Berechtigungen für diesen Review wurden verweigert (jeder `shell`-Aufruf endete mit „Permission denied"). Ich konnte daher **weder Git-Befehle** (`git log`, `git diff 10dca46..HEAD`, `git show`) **noch Tests** (`python3 -m unittest …`) oder `bash scripts/verify.sh quick` **ausführen**. Die Prüfung erfolgte ausschließlich durch vollständiges Lesen der Arbeitskopie `/tmp/opencode/f31-wt` (Branch `fix/f31-tests-docs`, Commitstand HEAD) mit den Lese-Werkzeugen sowie durch einen lesenden Trilium-MCP-Abruf. Die vom Coding-Agenten gelieferten Prüfergebnisse (3/3 OK, Rotphase, Regression, quick Exit 0) habe ich **nicht** unabhängig reproduzieren können — sie bleiben für mich unbelegt. Damit ist die Pflichtprüfung nach `AGENTS.md` („Pflichtprüfung nicht möglich: blockiert") nicht vollständig durchführbar; PASS ist auf dieser Basis nicht zulässig.

Der statische Befund lautet dennoch positiv: Die Fixstellen in `bin/vibe-run.sh` und `bin/vibe` sind korrekt gesetzt, konsistent, minimal (KISS) und geheimhygienisch sauber; die Tests prüfen nachweislich die Umgebung des echten Serverprozesses (nicht einer anderen Instanz). Die beiden Medium-Befunde betreffen einen Restpfad, über den ein Kennwert dennoch in die Serverumgebung gelangen kann, sowie Nachweislücken bei Testherkunft und Rotphase.

## Prüfkonto

**Geprüfte Dateien (vollständig bzw. im relevanten Ausschnitt gelesen):**

| Datei | Umfang |
|---|---|
| `bin/vibe-run.sh` | komplett gelesen; Fix bei Z. 41–46 (Kommentar + `unset OPENCODE_PASSWORD`), Kennwortbehandlung Z. 47–58, Serverstart Z. 158–228, `set -a; . ./.vibe/project.env` Z. 232 |
| `bin/vibe` | Ausschnitte: `child_exports()` Z. 248–261, Lauf-Sitzung Z. 2079–2091, `cmd_server` Z. 4837–4881 (tmux-Innenbefehl mit `unset OPENCODE_PASSWORD` Z. 4869), Dashboard-Sitzung Z. 5123–5129 |
| `bin/vibe_sandbox.py` | Umgebungs-/env-Pfade geprüft (Z. 142, 239, 284, 299, 331, 447, 587–646): leitet `os.environ` unverändert weiter, liest `project.env` nur für SANDBOX-Werte — **keine** Wiedereinspeisung von `OPENCODE_PASSWORD` |
| `tests/unit/test_f31_inherited_opencode_password.py` | komplett gelesen |
| `tests/unit/runner_support.py` | Attrappen-Ausschnitt Z. 130–249 (F31-Erweiterung Z. 189–203) |
| `docs/features/fix-opencode-password-env.md` | komplett gelesen |
| `docs/features/B13.md`, `docs/trilium-index.md`, `docs/import-manifest.json`, `scripts/check-import-manifest.py`, `scripts/verify.sh`, `AGENTS.md`, `SPEC.md`, `.vibe/project.env` | gelesen |

**Tatsächlich ausgeführte Befehle (durch mich):**

- Lesen der oben genannten Dateien (Werkzeuge `read`/`grep`/`glob`/`execute`-Katalogsuche).
- Trilium-Notiz `PgaZqt2vEwBQ` lesend abgerufen: Titel „Fix: Geerbtes OPENCODE_PASSWORD blockierte den privaten opencode-Server", Elternordner `IjRpjYJTtqam`, Inhalt deckt Ursache, Umsetzung (beide Fixstellen + Manifest), Tests (3/3 OK, Rotphase an `10dca46`), Grenzen und Review-Status ab; Labels `projekt:vibe`, `bereich:Features`. Inhalt stimmt mit der Repository-Doku überein.
- `shell`: **jeder** Aufruf (u. a. `git -C /tmp/opencode/f31-wt log --oneline 10dca46..HEAD`, `git show 88509a0`) endete mit „Permission denied: shell" — auch die im Auftrag ausdrücklich erlaubten read-only-Git-Befehle.

**Nicht ausführbar / nicht unabhängig verifiziert:**

- `git log/diff/show 10dca46..HEAD` (Committrennung, Vollständigkeit des relevanten Diffs, keine unrelated changes im Diff, Testschwächung gegenüber der Basis) — **nicht verifiziert**.
- `python3 -m unittest tests.unit.test_f31_inherited_opencode_password -v` (3/3 OK laut Coding-Agent) — **nicht verifiziert**.
- Rotphase am Stand `10dca46` — **nicht verifiziert** (kein Ausgabe-Artefakt vorhanden, siehe Befund M2).
- `bash scripts/verify.sh quick` (Exit 0) und insbesondere die Manifest-Prüfsummenkonsistenz (`scripts/check-import-manifest.py` rechnet `bin/vibe`/`bin/vibe-run.sh` gegen die Einträge bei Z. 863–867/869 ff. und Z. 869–871 ff.) — **nicht verifiziert** (keine Hashberechnung möglich).
- AK6-Sandbox-Regression (`test_sandboxed_run_starts_the_private_server_inside_the_sandbox` „vorbestehend") — **nicht verifiziert**.

## Akzeptanzkriterien

| Kriterium | Status | Implementierung (file:line) | Test / Evidence |
|---|---|---|---|
| AK1: Kein `OPENCODE_PASSWORD` in der Umgebung des privaten Serverprozesses | **PASS (statisch) / Teilbeeinträchtigt** — Fixstelle korrekt, aber Restpfad über `.vibe/project.env` (Befund M1) | `bin/vibe-run.sh:46` (vor Kennwortbehandlung Z. 47–58 und vor `start_private_server` Z. 161) | `test_inherited_opencode_password_is_absent_from_the_server_env` (`tests/unit/test_f31_inherited_opencode_password.py:129`); Lauf durch `test_f31…` vom Coding-Agenten geliefert („3/3 OK"), von mir **nicht ausgeführt** |
| AK2: Ohne geerbte Belegung bleibt B13 unverändert | PASS (statisch plausibel) | `bin/vibe-run.sh:46` wirkt nur, wenn geerbt; sonst kein Verhaltenunterschied | `test_without_inherited_password_b13_behaviour_is_unchanged` (Z. 198); Ergebnis vom Coding-Agenten, nicht von mir ausgeführt |
| AK3: Gemeinsamer Server (`vibe server start`) erbt kein `OPENCODE_PASSWORD` | PASS (statisch) | `bin/vibe:4869` — `unset OPENCODE_PASSWORD` im tmux-Innenbefehl **nach** `source ~/.bashrc` und vor `export OPENCODE_SERVER_PASSWORD="$(cat …)"` aus der Datei | `test_server_start_does_not_inherit_opencode_password` (Z. 359, echter tmux auf isoliertem Socket, opencode-Attrappe zeichnet ihre eigene Prozessumgebung auf); Ergebnis vom Coding-Agenten, nicht ausgeführt |
| AK4: Geheimhygiene — nur Anwesenheit/Länge | PASS (statisch) | Attrappe `tests/unit/runner_support.py:189–203` und AK3-Attrappe `test_f31…:257–287` notieren nur `*_present`/`*_len`; `assert_no_password_leak` (Z. 109) + Klartext-Checks (Z. 410–421) | statisch bestätigt; Testausführung nicht unabhängig verifiziert |
| Trilium-Doku | PASS | Notiz `PgaZqt2vEwBQ` lesend verifiziert (Titel, Inhalt, Features-Ordner) | `docs/trilium-index.md:66` stimmt mit Notiz-ID überein |
| Review nur über Arbeitspaket, kein unrelated change | **NOT VERIFIED** | — | Diff gegen `10dca46` konnte mangels Git-Zugang nicht gelesen werden |

## Befunde

- [Medium] `bin/vibe-run.sh:46` vs. `bin/vibe-run.sh:232` — Entfernung von `OPENCODE_PASSWORD` wird durch das spätere Einlesen von `.vibe/project.env` teilweise aufgehoben
  - Evidence: Das `unset OPENCODE_PASSWORD` (Z. 46) liegt **vor** `cd "$P"` und `set -a && . ./.vibe/project.env && set +a` (Z. 232). Definiert eine Projektdatei `OPENCODE_PASSWORD=…` (realistische Situation: Nutzer „sichert" den Alt-Export als Workaround in der Projektdatei), wird sie mit `set -a` erneut exportiert und erreicht über die setsid-Kette (Z. 172–184, ggf. via `vibe_sandbox.py` mit `os.execvpe(..., os.environ)`, `bin/vibe_sandbox.py:624/646`) doch wieder den Serverprozess. Das verletzt den wörtlich vereinbarten Grundsatz „Umgebung des Serverprozesses enthält keine Belegung von `OPENCODE_PASSWORD`"; der AK1-Test deckt nur den Weg über die Elternumgebung ab, nicht diesen Weg.
  - Required fix: Nicht-code-Anweisung an den Coding-/Test-Agenten: Die Entfernung von `OPENCODE_PASSWORD` so platzieren bzw. wiederholen, dass sie **nach** dem letzten Punkt liegt, der die Umgebung verändern kann (Einlesen von `.vibe/project.env`), unmittelbar vor dem privaten Serverstart; zusätzlich einen Testfall (vom Test-Agenten) mit `OPENCODE_PASSWORD` in `.vibe/project.env` ergänzen und die Doku-Abschnitte „Umsetzung"/„Bekannte Grenzen" entsprechend aktualisieren.

- [Medium] Nachweislücken: Rotphase ohne konserviertes Artefakt, Test-Agent-Herkunft für F31 nicht belegt (AGENTS.md „Unabhängiger Test-Agent (verbindlich)")
  - Evidence: `AGENTS.md:131`/`134`: „Ein nicht ausgeführter Test ist kein Nachweis", „Nur Tests, die nachweislich vom Test-Agenten stammen, zählen für die Abnahme." Für B13 existiert ein konservierter Bericht (`docs/reviews/B13-test-agent-report.md`, in `docs/features/B13.md:7` verlinkt). Für F31 fehlt ein vergleichbares Artefakt: Rotphase und 3/3-OK sind ausschließlich als Beschreibungstext in `docs/features/fix-opencode-password-env.md:86–99` festgehalten; der Rot-Worktree wurde (laut Arbeitspaket) entfernt, eine Rohausgabe (Fehlertext mit `opencode_password_present: True`, Länge 18) ist nicht abgelegt. Ich konnte weder die Testausführung noch die Herkunftsnachweise unabhängig prüfen (Shell-Zugang verweigert). Damit ist die Abnahmefähigkeit der Tests für den Abschluss des Pakets nicht belegt.
  - Required fix: Test-Agent-Ausgaben dauerhaft speichern (z. B. `docs/reviews/F31-test-agent-report.md` mit Befehl, Datum, exakter Rotphasen-Fehlermeldung am Stand `10dac46` und Grünlauf am Fix-Stand) und in der Feature-Doku verlinken; die Größendifferenz (Doku nennt 16/32 Zeichen für den Produktionsfall, Test nutzt 18/15) im Testbericht kurz begründen.

- [Low] `docs/import-manifest.json:850` — fehlender `aenderungen`-Eintrag für die F31-Änderung
  - Evidence: Die Prüfsummen von `bin/vibe` und `bin/vibe-run.sh` wurden aktualisiert (Commit `88509a0`), aber die Historie `aenderungen` endet bei B14 (Z. 844–850); ein F31-Eintrag existiert nicht (`grep` nach `F31`/`OPENCODE_PASSWORD` im Manifest: 0 Treffer). Alle vergleichbaren Einträge (B13 Z. 841, B14 Z. 849, AP16 Z. 822) begründen die Prüfsummenaktualisierung ausdrücklich im Manifest selbst — die F31-Prüfsummenänderung ist dort dadurch unbegründet.
  - Required fix: `aenderungen`-Eintrag für die Kennwort-Umgebungs-Fix (Datum 2026-11-14, beide Dateien, Begründung „Größe und SHA-256 … aktualisiert") ergänzen und `bash scripts/verify.sh quick` erneut ausführen.

- [Low] `docs/features/fix-opencode-password-env.md:37` und Trilium-Notiz — Sprach-/Tippfehler
  - Evidence: „opencode v2.3.0 **honor** `OPENCODE_PASSWORD`" (soll „honoriert" heißen); in der Trilium-Notiz „Folge**ar**arbeit". Reine Doku-Kosmetik, fachlich unmissverständlich.
  - Required fix: In der Feature-Doku korrigieren; Trilium-Notiz bei Gelegenheit berichtigen (patch_note), kein Blocker.

**Explizit geprüfte, nicht beanstandete Punkte (auf Wunsch des Auftrags):**

- Fixstellen: `bin/vibe-run.sh:46` liegt vor der Kennwortbehandlung (Z. 47–58) und vor jedem Serverstart; `bin/vibe:4869` entfernt die Variable **nach** `source ~/.bashrc` — das ist die richtige Reihenfolge (Profil-/bashrc-Altbelegungen werden erst gebildet, dann entfernt). Beide Pfade verhalten sich konsistent; `OPENCODE_SERVER_PASSWORD` kommt in beiden ausschließlich aus der Kennwortdatei und überschreibt eine geerbte Belegung.
- Weitere Erbpfade geprüft: `bin/vibe_sandbox.py` gibt `os.environ` unverändert weiter (keine Wiedereinspeisung); Preflight-/Assistenzpfade laufen innerhalb des Läufers mit bereits bereinigter Umgebung; Lauf- und Dashboard-tmux-Sitzungen (`bin/vibe:2084–2091`, `5126–5129`) sind keine Serverstartpfade; die Lauf-Sitzung endet in `vibe-run.sh`, das die Variable entfernt. Einziger gefundener Restpfad ist `.vibe/project.env` (Befund M1).
- Attrappenprüfung: Die `listening`-Records in `runner_support.py:194–203` und in der AK3-Attrappe (`test_f31…:267–284`) werden aus `os.environ` **desjenigen Prozesses** gelesen, den der Läufer bzw. tmux als `opencode serve` startet — also tatsächlich die Serverprozess-Umgebung, nicht eine andere Instanz.
- Geheimhygiene: Kein echtes Kennwort im Code; die Testliterale (`b13-privat-4711`, `veraltet-16zeichen`, `gemeinsam-32-zeichen-kennwort-f31`) sind eindeutig Attrappenwerte; Records enthalten nur Booleans/Längen.
- KISS/Clean Code: Fünf-Zeilen-Fix plus Kommentar an zwei Stellen, keine neuen Abstraktionen, konsistent mit dem B13-Dokumuster; `REPO`-Kontext und Fixture-Wiederverwendung im Test folgen dem bestehenden Stil.

## Verdict

**CHANGES REQUIRED**

Begründung: Zwei Medium-Befunde (Restpfad `.vibe/project.env` an der vereinbarten Zusicherung vorbei; nicht konservierte/nicht unabhängig prüfbare Test- und Rotphasennachweise) sowie die instrumentelle Blockade: Mir wurde der Shell-Zugang (auch für die ausdrücklich erlaubten read-only-Git-Befehle) verweigert, sodass der vollständige Diff `10dca46..HEAD`, die Committrennung (`88509a0`/`8a31f5f`/`ee8998f`), die Testausführung und die Manifest-Prüfsummen nicht von mir geprüft werden konnten. Nach `AGENTS.md` („Pflichtprüfung nicht möglich: blockiert, kein vorgetäuschter Erfolg") darf darauf kein PASS folgen.

Empfohlene Reihenfolge für Runde 2: (1) Shell-/Git-Berechtigungen für den Reviewer sicherstellen oder Diff/Rotphasenrohdaten als Artefakte liefern; (2) M1 beheben (Entfernung von `OPENCODE_PASSWORD` endgültig nach dem `project.env`-Einlesen absichern, Testfall vom Test-Agenten ergänzen); (3) Test-Agent-Bericht für F31 konservieren; (4) Low-Befunde umsetzen. Die Fixstellen selbst sind, soweit statisch geprüft, korrekt — nach Behebung der Nachweis- und Restpfad-Befunde ist ein PASS in der nächsten Runde realistisch.
