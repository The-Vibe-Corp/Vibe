# Review B3 — Runde 1

Datum: 2026-11-08
Reviewer: unabhängiger Code-Reviewer (`code-reviewer`, wie im Projekt festgelegt)
Paket committed als: `8447de7` (Baseline `eb05351`)
Review-Gegenstand: `git diff eb05351..8447de7 -- bin/vibe docs/import-manifest.json docs/features/B3.md tests/unit/test_b3_password_auto_setup.py`

## Ergebnis

Verdict: PASS

- Critical: 0
- High: 0
- Medium: 0
- Minor: 2 (nicht blockierend, siehe Befunde)

## Akzeptanzkriterien

| Kriterium | Status | Implementierung (Datei:Zeile) | Test / Nachweis |
| --- | --- | --- | --- |
| AK1: Beim Laufstart wird `<runtime>/opencode.password` automatisch angelegt (nichtleer, Laufzeitort, 0600 soweit das Dateisystem trägt) | PASS | `bin/vibe:1641` (Aufruf in `cmd_run`), `bin/vibe:4017–4041` (`ensure_opencode_password`, `secrets.token_urlsafe`, `os.open(..., 0o600)`) | `tests/unit/test_b3_password_auto_setup.py: AutoSetupOnRunStartTest.test_run_start_creates_missing_password_file_in_runtime` — erste Hand gelesen: echte Dateianlage am realen `LOGS`-Ort, Modiprüfung mit FUSE/NTFS-Toleranz (Z. 325–330). Grün: 3/3 OK; Rotphase AK1 belegt (2 failures, Exit 1). |
| AK2: Bestehende, nichtleere Kennwortdatei bleibt unverändert | PASS | `bin/vibe:4025–4032` (nur neues Kennwort, wenn `existing` leer/fehlt) | `test_existing_password_file_survives_run_start` — Inhalt vor/nach dem Laufstart verglichen (Z. 332–346). Rotphase bereits grün (Verhalten existiert), korrekt und transparent in `docs/features/B3.md:104–107` dokumentiert. |
| AK3: Nach automatisch angelegter Kennwortdatei lehnt `POST /api/steer` nicht mehr mit „Kennwortdatei fehlt" ab; Zustellung nur mit gültiger Basic-Auth | PASS | `bin/vibe-web.py:265–341` unverändert — liest dieselbe Datei aus demselben `PATHS.runtime` | `SteerAfterAutoSetupTest.test_auto_created_password_authenticates_steer_delivery` — erster Hand gelesen: echter `vibe-web.py`-Subprozess (Z. 399–427), echter HTTP-Zustellungsvertrag (`_FakeOpenCodeHandler.do_POST`, Z. 187–219) akzeptiert nur `auth_ok` mit dem Kennwort aus der realen Kennwortdatei; Zustellnachweis mit Text und `user=opencode` (Z. 584–590); Geheimnisprüfung in API-Antwort und übrigen Laufzeitdateien (Z. 592–604). Rotphase beobachtete exakt die B3-Originalmeldung als HTTP 400. |

Unterstützende Nachweise (mitgeliefert, nicht vom Reviewer ausgeführt):
F19-Regression 14 OK, F20 8 OK, Unit-Vollvergleich Ausgangsstand 1087 vs.
B3-Stand 1090 mit identischen FAIL/ERROR-Sätzen, `verify.sh quick` Exit 0,
`verify.sh full` in der isolierten Prüfumgebung (tmpfs-Kopie) 1135 vs. 1138
Tests mit identischen FAIL-Sätzen am Ausgangs- und B3-Stand.

## Befunde

### Minor 1 — `bin/vibe:4034–4038`: Kennwortdatei-Anlage nicht atomar/parallel gesichert

`ensure_opencode_password()` schreibt direkt mit `O_WRONLY|O_CREAT|O_TRUNC`
ohne Lock und ohne atomaren Ersatz. B3 verlagert den Aufruf nach `cmd_run`,
das auch über das threaded Dashboard (`/api/run` → `vibe_services.capture`,
`bin/vibe-web.py:619`) parallel erreichbar ist. Parallele Laufstarts können
im Extremfall um dieselbe Datei konkurrieren; ein Abbruch während des
Schreibens hinterließ einen Teildatensatz.

Bewertung: Wirkung begrenzt — Server und `steer_project` lesen dieselbe
Datei, eine leere Datei wird beim nächsten Laufstart neu angelegt, ein
Kennwort-Mismatch zeigt sich als klarer HTTP-401-Fehlerpfad. Bestandsverhalten
aus F19, Code unverändert. SPEC „Dateien atomar schreiben, konkurrierende
Änderungen erkennen" signalisiert größere Ansprüche; hier aber ohne
funktionierende Folge in realistischen Szenarien.

Maßnahme: Nicht für B3 blockierend. Für ein Folgepaket vormerken: Anlage über
Temp-Datei + `os.replace` (atomar) und/oder einen bestehenden
vibe-Storage-Lock. Keine Änderung innerhalb von B3 ohne erneuten Review.

### Minor 2 — Arbeitskopie-Status: Doku-Ergänzung und Prüfreste

`git status --short` zeigt (a) `M docs/features/B3.md` — der im Commit
`8447de7` enthaltene Platzhalter `<nach Abschluss ergänzt>` ist in der
Arbeitskopie durch die tatsächliche Commit-Angabe ersetzt; (b) vier nicht
git-ignorierte Prüfverzeichnisse `vibe-verify-5lpu4a50/`,
`vibe-verify-770jjeao/`, `vibe-verify-gb5iujpd/`, `vibe-verify-w3pn5owa/`
(Inhalt: `verify.log`, `gitconfig`, `opencode-config/service.json`);
(c) `docs/reviews/B3-review-1.md` existiert noch nicht, FEEDBACK.md verweist
bereits darauf.

Maßnahme: Kein Befund am Code. Nach finalem PASS gemäß AGENTS-Arbeitsablauf
(Schritte 10–13) die Doku-Ergänzung zusammen mit der Review-Ablage committen
und die `vibe-verify-*`-Reste aus dem Projektordner entfernen (nicht
committen).

## Prüfungsumfang

- Change-Set: `eb05351..8447de7` (voller Diff: `bin/vibe` +7 Zeilen,
  `docs/import-manifest.json` Prüfsumme/Größe für `bin/vibe`,
  `docs/features/B3.md` neu, `tests/unit/test_b3_password_auto_setup.py`
  neu, 608 Zeilen). Zusätzlich Arbeitskopie-Delta inspiziert
  (`git diff -- docs/features/B3.md`), untracked Verzeichnisse.
- Keine Änderungen an `bin/vibe-web.py`, F19-/F20-Tests oder Prüfskripten;
  keine Testabschwächung, keine gelöschten/verschobenen Tests.
- Erste Hand verifiziert: Implementierungsabschnitt `bin/vibe:1586–1678`
  (Aufrufposition nach Agentenwahl, vor `run_agent_selection` und vor
  `registry.start`/tmux — kein Registereintrag ohne Kennwortdateianlage),
  `ensure_opencode_password` (`bin/vibe:4017–4041`), Kennwort-/Fehlbehandlung
  im Dashboard (`bin/vibe-web.py:265–351`, SystemExit sauber in
  `vibe_services.capture` abgefangen, kein Kennwort in Meldung/Antwort),
  `vibe-run.sh:40–56` (Läufer liest dieselbe Datei), die vollständige
  Testsuite des Test-Agenten (echte Dateianlage, echter HTTP-Subprozess,
  keine Attrappen für das geprüfte Verhalten, isolierte `VIBE`/`HOME`
  Umgebungen, kein tmux-Start, keine produktiven Konfigurationen),
  `FEEDBACK.md`-Nachweislinie (Commit `8447de7`, Testreferenzen korrekt),
  `docs/features/B3.md`, `.vibe/project.env` (`TESTER=test-agent`),
  `.opencode/agents/test-agent.md`, `.gitignore` (FEEDBACK.md/TICKETS.md
  git-excluded wie behauptet), Trilium-Notiz `VeT8g41vNy9Y` (Titel, Inhalt,
  Labels `#status=abgeschlossen`, `#commit=8447de7`, `#ticket=B3` — über
  den Trilium-MCP-Zugang direkt gelesen).
- Wichtige inspectierte Bereiche: `bin/vibe` (`cmd_run`,
  `ensure_opencode_password`, `cmd_server`), `bin/vibe-web.py` (`/api/run`,
  `/api/steer`), `bin/vibe-run.sh` (F19-Auth-Lese-Seite), B3-Testsuite,
  Manifest + Prüflogik`scripts/check-import-manifest.py`,
  SPEC-Sicherheitsregeln (Sensitivdaten, FUSE/NTFS-Rechte-Toleranz
  eingehalten), aus dem Auftrag genannte Grenzfälle (bestehender
  unauthentifizierter Server, Pi/Sandbox) — in `docs/features/B3.md:71–85`
  als verbleibende F19-Grenzen dokumentiert; B3 verändert sie nicht.

## Restliche Risiken

- Konkurrenz-/Atomaritätsrand (Finding 1, Minor, vf. Folgepaket).
- Die manuellen Prüf- und Testergebnisse beruhen auf mitgelieferten
  Ausgaben und wurden mangels Berechtigung nicht unabhängig wiederholt.
- Die für OPs relevante Grenze „Produktivserver läuft außerhalb der
  vibe-Verwaltung ohne Kennwort" bleibt wie dokumentiert über den
  bestehenden `vibe server stop && start`-Empfehlungspfad abgedeckt.
