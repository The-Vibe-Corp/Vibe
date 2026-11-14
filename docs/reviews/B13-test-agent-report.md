# B13 — Test-Agent-Bericht

Projekt: vibe — Arbeitspaket B13 „Anweisung senden gibt Fehler“ (Bug)
Arbeitskopie: `/var/mnt/data/Dokumente/Informatik/VibeCode/_logs/worktrees/vibe-B13-ARiEja`
Ausgangsstand der Rotphase: `85fa466` (Branch `vibe/vibe-B13-1794634424089328898-6899-666`)
Datum: 14.11.2026

## Rolle und Abgrenzung

Die Testfälle wurden unabhängig aus dem Arbeitspaket, dem vereinbarten
Verhaltensmodell und `SPEC.md`/`AGENTS.md` abgeleitet, nicht aus einem
Implementierungsdiff (es existierte keiner). Geändert wurden ausschließlich:
zwei neue Testdateien, die gemeinsame Läufer-Testinfrastruktur
(`tests/unit/runner_support.py`: neuer Server-Zweig der opencode-Attrappe)
und dieser Bericht. Produktionsdateien, Konfiguration und Prüfskripte wurden
nicht geändert; nichts wurde committed. `.vibe/project.env` (git-ignoriert,
wie in jeder anderen Arbeitskopie vorhanden) wurde als lokale
Prüfkopie für `verify.sh quick` angelegt.

## Neue/geänderte Testdateien

| Datei | Inhalt |
| --- | --- |
| `tests/unit/test_b13_private_server_runner.py` | Läuferseite: AK1, AK2, AK4, AK5, AK6, AK7, AK9 (9 Tests) |
| `tests/unit/test_b13_private_server_steering.py` | Dashboard-Seite: AK3, AK4, AK7, AK8 (9 Tests, davon 1 Test mit 2 Subvarianten) |
| `tests/unit/runner_support.py` | Nur die opencode-Attrappe: neuer `serve`-Zweig (`_b13_serve`) — ein minimales HTTP-Serverlein mit Basic-Auth-geprüftem `GET /api/info`, Beobachtungsprotokoll über `FAKE_SERVE_RECORD`, Verzögerung (`FAKE_SERVE_DELAY`) und „lauscht nie“ (`FAKE_SERVE_NEVER`). Bestehende Aufrufpfade (`run`, Preflight, Paketabschluss) sind unverändert. |

## Testbefehle

```bash
# Rotphase (Ausgangsstand 85fa466) und später Grünphase:
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest \
  tests.unit.test_b13_private_server_steering tests.unit.test_b13_private_server_runner -v
# Regressionen:
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest \
  tests.unit.test_b11_output_view_api tests.unit.test_ap14_output_view_api \
  tests.unit.test_output_view_f19_runner tests.unit.test_f20_harness_dashboard_api \
  tests.unit.test_sandbox
# Projektprüfung:
bash scripts/verify.sh quick
```

## Testfallliste

### tests/unit/test_b13_private_server_steering.py

1. **test_steer_delivers_to_the_private_server_of_the_active_run** [AK3]
   Vorbedingung: aktiver Lauf (`runs.json` running), Zustandsdatei mit
   Hauptsession `ses_main`, nichtleere Kennwortdatei, gültige
   `proj.log.server.json` auf einen lokalen Testserver; der gemeinsame
   Port ist ein gebundener, lauschloser Socket (zuverlässig „Connection
   refused“).
   Aktion: `POST /api/steer` (Dashboard im isolierten VIBE-Root).
   Erwartung: HTTP 200, `ok:true`, Meldung nennt die Zustellung; genau ein
   POST `/api/session/ses_main/prompt` am privaten Server mit korrekter
   Basic-Auth `opencode:<Kennwort>` und dem Anweisungstext; Kennwort in
   keiner Antwort und keinem Protokoll (Antworttext, `proj.log`,
   Dashboard-Log).
   Fehlerfall: „Connection refused“, Zustellung am gemeinsamen Server oder
   falsche Anmeldung.
2. **test_steer_targets_a_running_subagent_via_the_private_server** [AK3]
   wie 1, Ziel `session=ses_child` → Zustellung an
   `/api/session/ses_child/prompt`.
3. **test_steer_accepts_a_localhost_server_url** [AK3]
   Serverdatei mit `http://localhost:<Port>` → akzeptiert, Zustellung am
   Port. Fehlerfall: localhost wird abgelehnt.
4. **test_steer_without_a_server_file_keeps_the_previous_path** [AK4/Rückfall]
   Keine Serverdatei → `ok:false` mit nichtleerer Meldung, keine Zustellung
   am privaten Server (bisheriger Pfad unverändert).
5. **test_steer_without_password_file_rejects_understandably** [AK4]
   Zwei Varianten (Datei fehlt / Datei leer) → `ok:false`, Meldung nennt
   „Kennwort“, nicht „Connection refused“, keine Zustellung.
6. **test_steer_ignores_a_broken_server_file** [AK8]
   Defektes JSON → nicht angenommen: `ok:false`, Meldung, keine Zustellung.
7. **test_steer_ignores_a_server_file_without_usable_url** [AK8]
   JSON ohne URL/Port → nicht angenommen.
8. **test_steer_ignores_a_non_loopback_server_url** [AK8]
   URL `http://example.invalid:<Port>` → nicht angenommen; zusätzlich lauscht
   ein Auffangserver am selben Port auf 127.0.0.1, um zu belegen, dass
   nichts (auch nicht „in der Nähe“) zugestellt wird.
9. **test_pi_steer_stays_forbidden_even_with_a_server_file** [AK7-API]
   Harness pi + gültige Serverdatei → bekannte Meldung „Zusatzanweisungen
   sind bei Pi nicht möglich …“, keine Zustellung.

### tests/unit/test_b13_private_server_runner.py

1. **test_run_starts_private_server_and_uses_it_exclusively** [AK1+AK2]
   Vorbedingung: kein Server am freien gemeinsamen Port, nichtleere
   Kennwortdatei; opencode-Attrappe zeichnet alle Aufrufe auf.
   Aktion: `bash <install>/bin/vibe-run.sh <projekt>`; ein
   Hintergrund-Thread beobachtet `proj.log.server.json` während des Laufs
   und sichert Inhalt und Beobachtungszeitpunkt, sobald die Datei gültiges
   JSON enthält (Teilschreibungen werden nicht eingefangen).
   Erwartung: Lauf endet 0 mit „FERTIG“; genau ein `opencode serve`-Aufruf;
   Agentenaufruf mit `--server http://127.0.0.1:<Port>` und ohne
   `--standalone`; die Attrappe beantwortete vorher `GET /api/info` mit
   gültiger Basic-Auth; die **während des Laufs beobachtete** Serverdatei
   enthält Loopback-URL, zugehörigen Port und `password_file` (zeigt auf
   die Kennwortdatei mit dem Anmeldekennwort); Kennwort nie in
   opencode-Argumenten, Serverdatei oder Protokollen; Serverausgabe in
   `proj.log.server.log`, nicht im Laufprotokoll; die Serverdatei ist nach
   dem Laufende entfernt (Harmonisierung mit AK5/AK6).
   Fehlerfall: `--standalone` bleibt; Serverdatei fehlt/fehlerhaft;
   Kennwort-Leak; Serverausgabe im Laufprotokoll; Serverdatei bleibt
   liegen.
2. **test_run_aborts_when_the_private_server_never_becomes_healthy** [AK1]
   Attrappe lauscht nie (`FAKE_SERVE_NEVER=1`) → Lauf bricht mit Meldung ab,
   kein `opencode run`. Fehlerfall: Agent startet gegen toten Server.
3. **test_server_output_goes_to_the_dedicated_file** [AK2]
   `proj.log.server.log` enthält die Servermarkierung, `proj.log` nicht.
4. **test_run_end_stops_the_private_server_and_removes_the_server_file** [AK5]
   Nach Laufende existiert `proj.log.server.json` nicht mehr und der Port
   des privaten Servers weist Verbindungen ab.
5. **test_run_without_password_file_stays_standalone** [AK4]
   Keine Kennwortdatei → `--standalone`, kein `serve`, keine Serverdatei.
6. **test_run_with_empty_password_file_stays_standalone** [AK4]
   Nur-Leerzeichen-Datei wie fehlende.
7. **test_sandboxed_run_starts_the_private_server_inside_the_sandbox** [AK6]
   SANDBOX=on (echtes bwrap) → Agentenaufruf mit `--server …` statt
   `--standalone`; genau ein Serve-Aufruf, dessen `TMPDIR` im
   Sandbox-Zustandsordner liegt (Wrap-Nachweis); Serverdatei beim Laufende
   entfernt.
8. **test_pi_run_starts_no_private_server** [AK7]
   harness.json=pi, Kennwortdatei vorhanden → Pi wird aufgerufen, kein
   `serve`, keine Serverdatei.
9. **test_reachable_shared_server_keeps_the_shared_target** [AK9]
   Erreichbarer „gemeinsamer“ Testserver am Port aus VIBE_OPENCODE_PORT →
   Agentenaufruf mit `--server http://127.0.0.1:<gemeinsamer Port>`, kein
   `serve`, keine Serverdatei.

## Rotphasen-Ergebnis (Ausgangsstand 85fa466)

Befehl: `PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest
tests.unit.test_b13_private_server_steering tests.unit.test_b13_private_server_runner -v`
Exit-Code 1.

* Steering-Suite: 9 Tests, 3 Fehler — genau die AK3-Fälle
  (`test_steer_delivers_to_the_private_server_of_the_active_run`,
  `..._targets_a_running_subagent_...`, `..._accepts_a_localhost_server_url`)
  mit dem belegten Fehlerbild
  `Der opencode-Server ist nicht erreichbar: [Errno 111] Connection refused`.
  Die übrigen 6 (AK4/AK7-API/AK8) sind grüne Regressionsschutze: Am
  Ausgangsstand wird eine Serverdatei ignoriert, und die bisherigen
  Ablehnungen bleiben unverändert — sie müssten nach der Umsetzung grün
  bleiben.
* Runner-Suite: 9 Tests, 5 Fehler — AK1
  (`Genau ein privater Server je Lauf erwartet: []` — es wurde kein `serve`
  aufgerufen; der Lauf blieb bei `--standalone`), AK1-Gesundheitswarten
  (Lauf startete den Agenten ohne gesunden Server, Exit 0), AK2
  (`server.log fehlt`), AK5 (`Es wurde nie ein Server gestartet`) und AK6
  (`In der Sandbox startete kein privater Server`). Die übrigen 4 (AK4 ×2,
  AK7, AK9) sind grüne Regressionsschutze des unveränderten Verhaltens.

Während der Rotphase korrigierte Testmängel (keine Erwartungsabschwächungen):
die Dashboard-Ablehnungen kommen mit HTTP 400 + `ok:false` — die
Status-Assertion der Rückfall-/Ablehnungstests akzeptiert jetzt 200/400
(der Semantik entsprechend, die `test_b11_output_view_api` und
`test_ap14_output_view_api` zeigen); im Pi-Test wurden `vibe_harness.py`/
`vibe_opencode.py` in `install/bin` (statt `install/`) abgelegt und die
B6-Pi-Attrappe (vollständige Paketabschluss) verwendet.

## Während der Implementierungsphase korrigierte Testmängel

### AK1-Korrektur: Beobachtungszeitpunkt der Serverdatei (14.11.2026)

**Was:** In
`tests/unit/test_b13_private_server_runner.py`
(`PrivateServerStartTest.test_run_starts_private_server_and_uses_it_exclusively`)
wird die Serverdatei `proj.log.server.json` jetzt **während des Laufs**
beobachtet und eingefangen: Ein Hintergrund-Thread mit 10-ms-Polling
sichert Inhalt und den monotone-clock-Zeitpunkt, sobald die Datei
vollständiges gültiges JSON enthält (Teilschreibungen werden nicht
eingefangen). Alle Inhaltsassertionen prüfen den eingefangenen Inhalt;
zusätzlich wird geprüft, dass der Beobachtungszeitpunkt innerhalb des
Laufzeitfensters liegt und dass die Datei nach dem Laufende nicht mehr
existiert. Es wurden **keine Assertions abgeschwächt und keine entfernt** —
alle AK1-Inhaltsprüfungen (Loopback-URL, Port stimmt mit dem
listening-Ereignis überein, `password_file` zeigt auf die Kennwortdatei mit
dem Anmeldekennwort, Kennwort-Leak-Prüfung gegen die beobachtete
Serverdatei, opencode-Argumente, Laufprotokoll, Läufer-Ausgabe,
Serverausgabe nur in `proj.log.server.log`) sind vollständig erhalten
geblieben.

**Warum (Beweis des Widerspruchs):** AK1 las die Serverdatei erst **nach**
`subprocess.run(...)`. Zu diesem Zeitpunkt ist die Datei gemäß AK5 und AK6
zwingend entfernt:

* `PrivateServerEndTest.test_run_end_stops_the_private_server_and_removes_the_server_file`
  verlangt: `proj.log.server.json` existiert nach dem Laufende **nicht
  mehr**.
* Der Sandbox-Test (AK6) verlangt dasselbe
  (`assertFalse(self.server_file().exists())` nach dem Lauf) und war auch
  in der Rotphase bereits als erwartetes Grün nach Umsetzung formuliert.
* Die Implementierung entfernt die Datei im EXIT-Trap
  (`bin/vibe-run.sh`: `trap 'stop_agent_group' EXIT` → `stop_private_server`
  → Entfernen der Serverdatei).

Beide Erwartungen („Datei existiert nach dem Lauf mit vollständigem
Inhalt“ in AK1 und „Datei existiert nach dem Lauf nicht“ in AK5/AK6) sind
gleichzeitig unerfüllbar; der Beobachtungszeitpunkt in AK1 war falsch.
Der Fehler bildete sich in der Grünphase exakt als
`AssertionError: False is not true : Serverdatei fehlt` (Zeile 405) —
der einzige Fehlschlag von 18 Tests, während AK5 und AK6 grün waren.

**Kein Implementierungsfehler:** Die Produktionsänderung ist korrekt; der
Widerspruch lag ausschließlich im Test. Korrigiert wurde nur
`tests/unit/test_b13_private_server_runner.py`.

## Grünphasen-Ergebnis (14.11.2026)

Nach der Implementierung (Arbeitsbaum: geändert `bin/vibe-run.sh`,
`bin/vibe-web.py`, `tests/unit/runner_support.py`; uncommitted) wurden die
folgenden Prüfungen tatsächlich ausgeführt:

| Befehl | Ergebnis | Exit-Code |
| --- | --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b13_private_server_steering tests.unit.test_b13_private_server_runner -v` | 18 Tests OK | 0 |
| `… tests.unit.test_b11_output_view_api tests.unit.test_ap14_output_view_api tests.unit.test_output_view_f19_runner tests.unit.test_f20_harness_dashboard_api tests.unit.test_sandbox` (mit `TMPDIR=/tmp`) | 76 Tests OK | 0 |
| `… tests.unit.test_b3_password_auto_setup tests.unit.test_b6_pi_runner_events tests.unit.test_b12_background_subagents` | 18 Tests OK | 0 |
| `… tests.unit.test_ap14_runner_continue tests.unit.test_v026_run_isolation tests.unit.test_v027_limits tests.unit.test_f25_session_continue` | 57 Tests OK | 0 |
| `… tests.unit.test_b5_sandbox tests.unit.test_b4_pi_agent_dir tests.unit.test_b8_no_remote_block tests.unit.test_run_control` | 63 Tests OK | 0 |
| `… tests.unit.test_b11_stop_terminates_agents` | 14 Tests OK | 0 |

Unmittelbar vor der AK1-Korrektur wurde der Widerspruch als Rotphasenstand
dokumentiert: 18 Tests, genau 1 Fehler (`Serverdatei fehlt`, Zeile 405),
Exit-Code 1.

### Vorbestehender, umgebungsbedingter Fehlschlag in `test_sandbox` (nicht B13)

Der erste Regressionslauf (5 Suiten, 76 Tests, Exit 1) enthielt genau einen
Fehler:
`test_sandbox.SandboxCommandTest.test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths`
(`HOME_DENIED` fehlt, stattdessen `HOME_OPEN`). Beleg, dass dies **keine
B13-Regression** ist:

* Der Test läuft ausschließlich über `bin/vibe_sandbox.py` — keine der drei
  geänderten Dateien (`bin/vibe-run.sh`, `bin/vibe-web.py`,
  `tests/unit/runner_support.py`) ist an diesem Pfad beteiligt;
  `bin/vibe_sandbox.py` ist im Arbeitsbaum unverändert.
* Ursache: Das Fixture (`SandboxFixture.setUp`) setzt HOME auf einen
  Tempordner; `tempfile` erzeugt ihn unter dem Sitzungs-`TMPDIR`
  (`/tmp/opencode/vibe-sandbox/vibe-B13-ARiEja-…/tmp`). Die Sandbox bindet
  `/tmp/opencode` als Standard-Schreibverzeichnis **komplett schreibbar**
  ein, daher gelingt der „HOME-Escape“-Touch.
* Gegenprobe: derselbe Test mit `TMPDIR=/tmp` → **OK** (Exit 0); ein
  direkter bwrap-Probe mit identischen Kernargumenten außerhalb
  `/tmp/opencode` liefert `DENIED`.
* Es wurde nichts abgeschwächt und keine Datei verändert; die Regression
  wurde mit `TMPDIR=/tmp` als Nachweislauf wiederholt (76 Tests OK, Exit 0).
  Hinweis für Coding-/Review-Agent: Dieser Bestandstest hängt von der
  `TMPDIR`-Lage ab — vorbestehende Umgebungsabhängigkeit, kein B13-Thema.

## Gesamtprüfung in tmpfs-Kopie und behobene Testinfrastruktur-Befunde

Die Gesamtprüfung (`verify.sh full`) lief in einer tmpfs-Kopie des
Arbeitsbaums (`/tmp/opencode/b13-full`) gegen die Baseline
`85fa466` (`/tmp/opencode/b13-baseline`):

* Baseline `85fa466`: 1735 Tests, 13 Failures + 2 Errors (= 15 fehlgeschlagene Tests) — alle
  vorbestehend und umgebungsbedingt, identische Fail-Menge.
* B13-Stand: 1753 Tests, 16 Failures + 2 Errors. **Drei Fälle neu** (B13-
  Regressionsatz), alle drei Testinfrastruktur-Probleme (keine
  Produktionsfehler); sie wurden vom Test-Agenten behoben.

### Befund 1 — F10-Suite (`tests/unit/test_run_autostop.py`): 2 neue Fehlschläge

`test_session_ends_when_the_runner_has_finished` und
`test_session_ends_even_when_the_run_pauses` brachen ab mit
„ABBRUCH: Der private opencode-Server wurde unter
http://127.0.0.1:<Port> nicht gesund; ohne erreichbaren Server startet
kein Agent." (belegt im Full-Log `/tmp/opencode/b13-full-run.log`,
Abschnitt `test_run_autostop`).

Ursachenkette (vollständig belegt): `start_run()` ruft `bin/vibe`
(`cmd_run`) auf; B3s `ensure_opencode_password()` (`bin/vibe:4811`,
`cmd_run`-Aufruf bei 2051) legt die Kennwortdatei an; `bin/vibe-run.sh`
wertet die nichtleere Kennwortdatei (`HAS_SERVER_PASSWORD=1`) und ohne
gemeinsamen Server als `PRIVATE_SERVER=1`; die Gesundheitsprüfung benutzt
curl — die Attrappe `FAKE_CURL` in `tests/unit/runner_support.py` war
`#!/usr/bin/env bash; exit 7` und ließ jede Prüfung scheitern → ABBRUCH.
Die B13-Fixtures umgingen das, weil sie curl durch `REAL_CURL` ersetzten.

**Fix:** `REAL_CURL` (echte HTTP-Attrappe: führt GET wirklich aus,
Basic-Auth über `-u`, Erfolg nur bei 2xx, Exit 7 ohne Verbindung) liegt
jetzt in `tests/unit/runner_support.py` vor, gemeinsam mit dem Helfer
`install_real_curl(fakebin)`. Das F10-Fixture setzt sie nach
`install_fake_tools` ein (`support.install_real_curl(self.fakebin)`) und
setzt `VIBE_OPENCODE_PORT` im Test auf einen deterministisch toten Port
(gebundener Socket ohne `listen()`, wie im B13-Fixture) — die Prüfung
hängt nicht mehr vom Nutzerzustand ab (ein produktiv laufender
gemeinsamer Server kann die Tests nie beeinflussen).
`test_b13_private_server_runner.py` nutzt dieselbe gemeinsame Konstante
(lokales Duplikat entfernt, Verhalten identisch).

**Erneut (echter Lauf):** `tests.unit.test_run_autostop` — 2 Tests OK,
Exit 0 (vorher 2 Failures, Exit 1).

### Befund 2 — AK6 (`SandboxPrivateServerTest.test_sandboxed_run_starts_the_private_server_inside_the_sandbox`)

Nur in der Gesamtprüfung neu rot; isoliert war der Test grün — ein Zufall,
der den Test nie wirklich geprüft hat: Das Fixture aktivierte die Sandbox
nirgends (`project.env` aus `support.write_project` enthielt kein
`SANDBOX=on`; `env()` entfernt `SANDBOX*`-Keys). Der Läufer bewertete
SANDBOX über `bin/vibe_sandbox.py --enabled` → off → der private Server
lief **unverpackt**, und die TMPDIR-Assertion
(`startswith('/tmp/opencode/vibe-sandbox/')` oder `/vsb/`) bestand nur,
weil der äußere TMPDIR der opencode-Sitzung zufällig unter
`/tmp/opencode/vibe-sandbox/` lag. Gegenprobe vor der Korrektur: derselbe
Test mit bewusst fremdem TMPDIR (`/tmp/opencode/b13-fremd-tmpdir`) → rot
mit `Der Server lief außerhalb der Sandbox
(TMPDIR='/tmp/opencode/b13-fremd-tmpdir')` — der Nachweis, dass der
unverpackte ServerTMPDIR aus der Umgebung übernahm.

**Fix (echter AK6-Nachweis):**

* Das Fixture schreibt `SANDBOX=on` und `SANDBOX_TOOLS="git"` in
  `.vibe/project.env` und commitet den Stand (die Arbeitskopie erbt
  beides; `bin/vibe_sandbox.py status()` liest die Projektumgebung).
* `bin/vibe_sandbox.py` wird in die Testinstallation nach `install/bin`
  kopiert (`install_runner` enthält es nicht; der Läufer bricht sonst mit
  „vibe_sandbox.py fehlt" ab, `bin/vibe-run.sh:699`).
* `VIBE_SANDBOX_ROOT` zeigt auf eine kontrollierte, kurze Fixture-Wurzel
  unter `/tmp/opencode` (dort auch in der Sandbox beschreibbar).
* Die TMPDIR-Assertion ist jetzt **exakt**: Die Arbeitskopie wird aus der
  Versuch-Zeile des Laufprotokolls gelesen, ihr Zustandsordner mit dem
 selben Sandbox-Modul und derselben `VIBE_SANDBOX_ROOT` berechnet
  (`state_dir(WT)`, fallback `/tmp/opencode/vsb` bei >84 Zeichen ist in
  der Berechnung enthalten), und es wird genau `state_dir(WT)/tmp`
  gefordert — unabhängig vom äußeren TMPDIR. Zusätzlich verlangt der Test
  jetzt „Sandbox: on" im Laufprotokoll (die Sandbox muss wirklich
  eingeschaltet gewesen sein).
* Scharf geblieben: Agentenaufruf mit `--server` statt `--standalone`,
  genau ein Serve-Aufruf, Serverdatei beim Laufende entfernt.
* `kill_leftover_serve` behandelt TMPDIRs unter der Fixture-Sandboxwurzel
  ebenfalls als umhüllt (PID-Umgebung vom Host nicht adressierbar; die
  Sandbox räumt selbst ab).

**Erneut (echte Läufe):** B13-Suiten 18 Tests OK — einmal mit normalem
TMPDIR (Exit 0) und einmal mit bewusst fremdem TMPDIR
(`/tmp/opencode/b13-fremd-tmpdir`, Exit 0); die Unabhängigkeit vom
äußeren TMPDIR ist damit belegt.

**Kein Produktionsbefund:** Der nun echte Sandbox-Lauf zeigt korrektes
Verhalten — das Laufprotokoll meldet „Sandbox: on" und „Sandbox bereit:
git", der private Server läuft innerhalb des Wraps (Serve-TMPDIR exakt
`state_dir(WT)/tmp`), die Gesundheitsprüfung (außerhalb der Sandbox gegen
127.0.0.1) erreicht ihn, `auth_ok: true`, der Agent läuft mit `--server`,
und Serverdatei/Server werden beim Laufende entfernt. Es gab keinen
Beleg für einen unverpackten Server oder einen Abbruch; die Produktion
wurde nicht verändert und keine Assertion abgeschwächt.

### Endergebnis: Zweite Gesamtprüfung nach den Fixes (14.11.2026)

Nach den Fixes wurde die Gesamtprüfung erneut vollständig ausgeführt:

```text
Befehl:  env -u TMPDIR -u VIBE_RUNTIME bash scripts/verify.sh full
Umgebung: aktualisierte tmpfs-Kopie des Arbeitsbaums (/tmp/opencode/b13-full)
Log:      /tmp/opencode/b13-full-run2.log
Ergebnis: 1753 Tests, 13 Failures + 2 Errors (= 15 fehlgeschlagene Tests), Exit 5 (Prüf-Exit)
```

Der Fail-Mengenvergleich gegen die Baseline `85fa466`
(`/tmp/opencode/b13-baseline`, Log `/tmp/opencode/b13-baseline-run.log`)
ist in **beide Richtungen leer** (`comm -23` und `comm -13` ohne
Unterschiede):

* **B13-Regressionsatz: leer.** Die drei zuvor neuen Fälle (F10 ×2,
  AK6) sind durch die Testinfrastruktur-Fixes behoben; kein B13-Bezug
  bleibt in der Fail-Menge.
* Die 18 Tests Differenz (1735 → 1753) sind ausschließlich die neuen
  B13-Tests (AK1–AK9), sämtlich grün.
* Die verbleibenden 13 Failures + 2 Errors (= 15 fehlgeschlagene Tests) sind die **vorbestehenden,
  umgebungsbedingten Baseline-Befunde** und sind in Baseline und
  B13-Stand identisch (gleiche Fail-Menge) — kein B13-Einfluss.

Schlussfolgerung: Die B13-Implementierung verursacht keine Regression in
der Gesamtprüfung; die Prüfgrenze Exit 5 stammt ausschließlich aus den
vorbestehenden Baseline-Befunden.

### Befund 3 — Regressionsläufe nach den Fixes (alle tatsächlich ausgeführt)

| Befehl | Ergebnis | Exit-Code |
| --- | --- | --- |
| `tests.unit.test_run_autostop` | 2 Tests OK | 0 |
| B13-Suiten (normaler TMPDIR) | 18 Tests OK | 0 |
| B13-Suiten (TMPDIR=`/tmp/opencode/b13-fremd-tmpdir`) | 18 Tests OK | 0 |
| Output-View/Dashboard/Sandbox-Suiten (mit `TMPDIR=/tmp`) | 76 Tests OK | 0 |
| B3/B6/B12-Läufer-Suiten | 18 Tests OK | 0 |
| AP14/V026/V027/F25-Suiten | 57 Tests OK | 0 |
| B5/B4/B8/Run-Control-Suiten | 63 Tests OK | 0 |
| `test_b11_stop_terminates_agents` | 14 Tests OK | 0 |
| `bash scripts/verify.sh quick` | Manifest 60 Dateien OK, Syntax OK, keine Geheimnisse | 0 |

Alle Nachweise aus den vorangegangenen Kapiteln (Rotphase, AK1-Korrektur,
`verify.sh quick` Exit 0) bleiben bestehen.

## Nachweis: `verify.sh quick` nach Importmanifest-Sync (14.11.2026)

Der Coding-Agent hat das Importmanifest sync't (`docs/import-manifest.json`
prüfsummenbelegt die legitimen Implementierungsänderungen in
`bin/vibe-run.sh` und `bin/vibe-web.py`; `tests/unit/runner_support.py`
liegt außerhalb der Manifest-Scopes). Anschließend wurde die Prüfung vom
Test-Agenten tatsächlich ausgeführt:

```text
Befehl: bash scripts/verify.sh quick
Ergebnis:
OK: 60 Dateien stimmen mit docs/import-manifest.json überein.
OK: 162 Python-, 8 Bash- und 4 JSON-Datei(en) syntaktisch geprüft.
OK: keine Geheimnisse erkannt.
OK: Prüfung 'quick' erfolgreich. (Exit 0)
Exit-Code: 0
```

Damit ist die Projektprüfung `quick` auch nach der Implementierung und dem
Importmanifest-Sync grün; der Sync selbst wurde vom Coding-Agenten
erbracht, der Nachweislauf vom Test-Agenten.

## Bestandssuiten am Ausgangsstand (alle grün)

* `tests.unit.test_b11_output_view_api`, `tests.unit.test_ap14_output_view_api`,
  `tests.unit.test_output_view_f19_runner`: 32 Tests OK.
* `tests.unit.test_f20_harness_dashboard_api`, `tests.unit.test_sandbox`:
  44 Tests OK.
* `bash scripts/verify.sh quick`: Exit 0 (Importmanifest 60 Dateien,
  Syntaxcheck 162 Python-/8 Bash-/4 JSON-Dateien, keine Geheimnisse).
* Weitere Läufer-nahe Suiten (nutzen dieselbe geänderte Attrappe), alle OK:
  `test_b3_password_auto_setup test_b6_pi_runner_events
  test_b12_background_subagents` (18 Tests), `test_ap14_runner_continue
  test_v026_run_isolation test_v027_limits test_f25_session_continue`
  (57 Tests), `test_b5_sandbox test_b4_pi_agent_dir test_b8_no_remote_block
  test_run_control` (63 Tests), `test_b11_stop_terminates_agents` (14 Tests).
* Isolierte Gesamtprüfung `bash scripts/verify.sh full` (Exit 5 wegen der
  unten erläuterten, vorbestehenden Baseline-Mängel): 1753 Tests,
  10 Fehler — davon die 8 erwarteten Rotphasen-Fehler der neuen B13-Suiten
  und 2 **vorbestehende Baseline-Mängel** ohne Bezug zu B13:
  * `test_ap04_setup_harness.SetupHarnessTest.
    test_dry_run_explains_pi_and_its_install_command`: erwartet
    `@earendil-works/pi-coding-agent` in der Setup-Ausgabe, geliefert wird
    ein Pi.dev-Hinweistext (Inhaltsabweichung in `bin/vibe`).
  * `test_release.ReleaseBuildTest.
    test_repository_content_has_no_personal_home_paths_or_secrets`:
    verfolgte Inhalte (z. B. `docs/features/B4.md:15`) enthalten absolute
    Home-Pfade.
  Beide scheitern identisch am Ausgangsstand 85fa466 (durch temporäres
  Zurückstellen der eigenen Änderungen per `git stash -u` und erneute
  Ausführung belegt; die eigenen Dateien tragen keine Befunde — geprüft
  mit `HOME_PATH_RE`/`secret_patterns` von `scripts/build-release.py`).
  Die nicht-isolierte Vollsuite (`unittest discover`) wurde zusätzlich
  versucht, war aber wegen eines gleichzeitig laufenden produktiven
  Agentenlaufs nicht verwertbar (Port-/Cache-Kollisionen, abgebrochen); die
  isolierte `verify.sh full`-Prüfung ist die maßgebliche Regression.

## Hinweise für Coding- und Review-Agenten

* **Bestandsverträglichkeit:** Die bestehenden Sandbox-Läufer-Tests
  (`test_sandbox.SandboxRunnerTest`) legen **keine** Kennwortdatei an;
  nach dem vereinbarten Verhalten (fehlende Kennwortdatei →
  `--standalone`) bleiben sie grün. Läufer-Tests, die künftig eine
  Kennwortdatei anlegen (B3-Suite etc.), wurden am Ausgangsstand geprüft —
  sie laufen über denselben Pfad. Beobachtet wurde kein Bruch.
* **curl im Gesundheitscheck:** Der Läufer prüft die Servergesundheit
  über curl; die curl-Attrappe der B13-Runner-Tests führt die Anfrage
  wirklich aus (Basic-Auth über `-u`). Das Kennwort gelangt dabei wie bisher
  als curl-Argument an den Prüfaufruf; die Geheimhaltungsassertionen
  (AK2) beziehen sich auf opencode-Argumente (`serve`/`run`),
  `proj.log.server.json`, Laufprotokoll und Läufer-Ausgabe.
* **Sandbox-Beobachtung:** Die Server-Attrappe legt ihre Beobachtungsdatei
  in `/tmp/opencode/…` ab, weil nur dort auch innerhalb der Sandbox
  geschrieben werden kann; das Runner-Setup der Sandbox-Suite gibt
  `permissions.json` die Laufzeit als Schreibverzeichnis, damit die
  Agenten-Attrappe das Paket abschließen kann.
* **Offene Grenzen:** `::1`-Loopback-URLs werden nicht einzeln als
  akzeptiert geprüft (die Attrappe lauscht auf 127.0.0.1); die
  localhost-Variante deckt die Loopback-Akzeptanz ab. Das Verhalten
  „Server überlebt zwischen Paketen und wird nur beim Laufende beendet“
  wird über „genau ein serve-Aufruf je Lauf“ geprüft; der TERM-Mechanismus
  des Beendens selbst wird nicht vorgeschrieben (nur Port geschlossen und
  Datei entfernt). Kein Test deckt das Verhalten ab, wenn der private
  Server während des Laufs abstirbt (mündliche Zustellung schlägt dann
  sichtbar fehl) — dies ist keine Akzeptanzkriterien-Vorgabe.
