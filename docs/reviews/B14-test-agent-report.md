# B14 — Test-Agent-Bericht

Projekt: vibe — Arbeitspaket B14 „Subagenten output statisch“ (Bug)
Arbeitskopie: `/var/mnt/data/Dokumente/Informatik/VibeCode/_logs/worktrees/vibe-B14-kSbHjb`
Branch: `vibe/vibe-B14-1794644431375983103-6899-14467`
Ausgangsstand der Rotphase: `46ba601` (enthält bereits B13)
Datum: 14.11.2026

## Rolle und Abgrenzung

Die Testfälle wurden unabhängig aus dem Arbeitspaket, dem vereinbarten
Vertragsmodell (Live-Lesezugriffe mit `steer_endpoint`-Semantik) und
`SPEC.md`/`AGENTS.md` abgeleitet — nicht aus einem Implementierungsdiff (es
existierte keiner). Geändert wurden ausschließlich zwei neue Testdateien und
dieser Bericht. Produktionsdateien, Konfiguration, Prüfskripte und
Bestandstests wurden nicht geändert; nichts wurde committed. Für
`scripts/verify.sh quick` wurde eine lokale, git-ignorierte Prüfkopie von
`.vibe/project.env` angelegt (denselben Weg nahm B13; das Original liegt im
Haupt-Checkout unter `/var/mnt/data/Dokumente/Informatik/VibeCode/vibe/.vibe/project.env`).

## Neue Testdateien

| Datei | Inhalt |
| --- | --- |
| `tests/unit/test_b14_subagent_output_live.py` | Dashboard-API-Seite: AK1, AK2, AK3, AK4, AK5, AK6, AK8 (13 Tests) |
| `tests/browser/test_b14_subagent_output_ui.py` | Browser-Beweis im echten Dashboard: AK7 (2 Tests) |

## Testbefehle

```bash
# Rotphase (Ausgangsstand 46ba601) und später Grünphase:
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b14_subagent_output_live -v
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_b14_subagent_output_ui -v
# Bestandssuiten (müssen grün bleiben):
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b13_private_server_steering
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b13_private_server_runner
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b12_background_subagents tests.unit.test_f30_subagent_view
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b11_output_view_api tests.unit.test_ap14_output_view_api
PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_f30_subagent_view_ui
# Projektprüfung:
bash scripts/verify.sh quick
```

## Testfallliste

### tests/unit/test_b14_subagent_output_live.py

Aufbau: Das echte Dashboard (`bin/vibe-web.py`) läuft in einem isolierten
VIBE-Root auf freiem Port. Der gemeinsame opencode-Port (`OC_URL`) ist ein
**lauschender, aufzeichnender Attrappenserver ohne verwertbare Daten** — so
lässt sich belegen, dass Anfragen am Ausgangsstand dorthin gehen (Rotphase)
und nach der Umsetzung bei gültiger Serverdatei nicht mehr (AK2). Die
privaten Laufserver-Attrappen prüfen Basic-Auth gegen die Kennwortdatei aus
`password_file` und protokollieren jede Anfrage mit Auth-Status.

1. **test_live_output_comes_from_the_run_server_endpoint** [AK1]
   Vorbedingung: aktiver Lauf (`runs.json` running), laufender Subagent
   `ses_kind` mit nichtleerer erfasster Ausgabe in
   `proj.log.state.json`; gültige `proj.log.server.json` auf den privaten
   Laufserver, der eine Assistant-Nachricht (LIVE-A-4711) liefert;
   gemeinsamer Attrappenserver ohne Daten.
   Aktion: `GET /api/subagent-output?name=proj&session=ses_kind`.
   Erwartung: `ok:true`; Text enthält LIVE-A-4711; STATISCH-4711 erscheint
   nicht; kein Kennwort in der Antwort/Protokoll.
   Fehlerfall (Ausgangsstand): statischer Fallback-Text.
2. **test_second_poll_returns_refreshed_live_output** [AK1, AK7]
   wie 1; Attrappe liefert zunächst LIVE-A-4711, danach nur LIVE-B-4711.
   Zwei aufeinanderfolgende Abrufe → erster enthält LIVE-A, zweiter
   LIVE-B; der zweite enthält weder LIVE-A noch STATISCH.
   Fehlerfall (Ausgangsstand): beide Abrufe liefern den statischen Text
   (Karte friert).
3. **test_requests_target_the_loopback_url_with_the_file_password** [AK2]
   Vorbedingung: gültige Serverdatei; `password_file` nennt ein anderes
   Kennwort (privat-4711) als die globale Kennwortdatei (global-4711,
   existiert ebenfalls).
   Aktion: `GET /api/subagent-output`.
   Erwartung: Mindestens eine `/message`-Anfrage am Laufserver, jede mit
   korrekter Basic-Auth „opencode:<password_file-Kennwort>“.
   Fehlerfall (Ausgangsstand): keine Anfrage am Laufserver; Abfrage läuft
   mit globalem Kennwort gegen OC_URL.
4. **test_no_request_reaches_the_common_server_with_a_valid_file** [AK2]
   wie 3; zusätzlich Aufzeichnung am gemeinsamen Server.
   Erwartung: Der gemeinsame Server erhält keine `/message`- und keine
   `/api/session`-Anfrage.
   Fehlerfall (Ausgangsstand): `/api/session?limit=100` und
   `/api/session/ses_kind/message?limit=500&order=asc` gehen an OC_URL.
5. **test_without_server_file_the_captured_output_is_served** [AK3]
   Vorbedingung: aktiver Lauf, **keine** Serverdatei, gemeinsamer
   Attrappenserver erreichbar (ohne Daten), erfasste Ausgabe nicht leer.
   Erwartung: `ok:true` mit der erfassten Ausgabe (STATISCH-4711), keine
   erfundenen LIVE-Daten; der gemeinsame Server wurde abgefragt
   (bisheriger Pfad bleibt).
6. **test_without_server_file_and_without_output_keeps_the_message** [AK3]
   wie 5, aber erfasste Ausgabe leer → `ok:false` mit der bestehenden
   Meldung „liegt noch keine Ausgabe vor“ und Status `running`.
7. **test_without_password_nothing_is_queried_and_captured_text_remains** [AK3]
   wie 5, aber ohne globale Kennwortdatei; privater Laufserver läuft.
   Erwartung: `ok:true` mit erfasster Ausgabe; **keine** Anfrage am
   Laufserver (keine erfundenen Daten ohne Anmeldung).
8. **test_broken_json_server_file_is_not_used** [AK4]
   Serverdatei mit defektem JSON (`{kein json`) → Rückfall auf erfasste
   Ausgabe; keine Anfrage am Laufserver.
9. **test_non_loopback_server_url_is_not_used** [AK4]
   Serverdatei mit URL `http://example.invalid:<Port>`; zusätzlich lauscht
   ein aufzeichnender Auffangserver am selben Port auf 127.0.0.1.
   Erwartung: Rückfall auf erfasste Ausgabe; weder Auffangserver noch
   Laufserver wurden angefragt (kein stiller Loopback-Ersatz).
10. **test_server_file_without_usable_url_is_not_used** [AK4]
    Serverdatei nur mit `password_file` (fehlender Port) → Rückfall auf
    erfasste Ausgabe; keine Laufserver-Anfrage.
11. **test_live_subagents_are_discovered_via_the_run_endpoint** [AK5]
    Vorbedingung: aktiver Lauf; Zustandsdatei ohne Subagenten; der
    Laufserver meldet in `/api/session` eine Kind-Session (parentID der
    Hauptsession) und führt sie in `/api/session/active` als running;
    gemeinsamer Attrappenserver ohne Daten.
    Aktion: `GET /api/subagents?name=proj`.
    Erwartung: Der live erkannte Subagent `ses_live` erscheint mit Status
    `running`; die Session-Abfragen gingen authentifiziert an den
    Laufserver.
    Fehlerfall (Ausgangsstand): Subagent fehlt (Erkennung am gemeinsamen
    Server ohne Daten).
12. **test_two_active_projects_use_their_own_endpoints** [AK6]
    Vorbedingung: zwei aktive Projekte (proj, proj2) mit jeweils eigener
    Zustandsdatei (ses_a / ses_b), eigener Serverdatei und eigenem
    Laufserver; unterscheidbare LIVE-Texte (PROJEKT-A-4711 /
    PROJEKT-B-4711).
    Aktion: `GET /api/subagent-output` für beide Projekte.
    Erwartung: proj erhält PROJEKT-A, proj2 erhält PROJEKT-B; jeder
    Laufserver sah nur die `/message`-Anfrage des eigenen Projekts.
    Fehlerfall (Ausgangsstand): beide erhalten den statischen Text.
13. **test_the_password_stays_secret** [AK8]
    volles Setup mit gültiger Serverdatei → LIVE-Text geliefert; weder
    privat-4711 noch global-4711 erscheint in der API-Antwort, im Lauf-/
    Dashboard-Protokoll oder in den aufgezeichneten Serveranfragen.

### tests/browser/test_b14_subagent_output_ui.py

Aufbau: echtes Dashboard + Chromium (Playwright, headless); der gemeinsame
Port ist ein **gebundener, lauschloser Socket** (zuverlässig abgewiesen —
kein gemeinsamer Server, Normalfall des Bugs); der private Laufserver ist
NUR über die `proj.log.server.json` des aktiven Laufs erreichbar.

1. **test_running_card_refreshes_through_the_private_run_server** [AK7]
   Vorbedingung: aktiver Lauf mit laufender Subagent-Karte samt statischer
   erfasster Ausgabe (STATISCH-4711); Serverdatei auf den Laufserver
   (LIVE-A-4711); kein gemeinsamer Server.
   Aktion: Ausgabebereich öffnen, auf LIVE-A-4711 warten; Attrappe auf
   LIVE-B-4711 umstellen; ohne Neuladen weiter beobachten
   (2-Sekunden-Polling).
   Erwartung: Karte zeigt LIVE-A und danach LIVE-B; STATISCH-4711 nie;
   der Laufserver wurde per `/message` angefragt, authentifiziert mit dem
   password_file-Kennwort; keine JS-Fehler, keine Browserdialoge.
   Fehlerfall (Ausgangsstand): Karte friert beim statischen Ersttext.
2. **test_the_card_never_shows_the_frozen_captured_first_text** [AK7]
   wie 1; über mehrere Polling-Zyklen (2 × 2,5 s) beobachten.
   Erwartung: STATISCH-4711 erscheint zu keinem Zeitpunkt; LIVE-A bleibt
   sichtbar.
   Fehlerfall (Ausgangsstand): statischer Ersttext bleibt stehen.

## Rotphasenbefund (tatsächlich ausgeführt am Ausgangsstand 46ba601)

Befehl: `PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b14_subagent_output_live -v`
Ergebnis: `Ran 13 tests ... FAILED (failures=7)`, Exit 1. Keine Umgebungs-
oder Syntaxfehler; alle 13 Tests liefen.

| Test (AK) | Befund in der Rotphase |
| --- | --- |
| test_live_output_comes_from_the_run_server_endpoint (AK1) | `'LIVE-A-4711' not found in 'The subagent is working in the background (sessionID: ses_kind). STATISCH-4711'` — statischer Fallback-Text gewinnt |
| test_second_poll_returns_refreshed_live_output (AK1/AK7) | beide Abrufe liefern den statischen Text (eingefroren) |
| test_requests_target_the_loopback_url_with_the_file_password (AK2) | `[] is not true : Die LIVE-Ausgabe wurde nicht am Laufserver-Endpunkt angefragt` |
| test_no_request_reaches_the_common_server_with_a_valid_file (AK2) | gemeinsamer Server erhielt `[{'method': 'GET', 'path': '/api/session?limit=100'}, {'method': 'GET', 'path': '/api/session/ses_kind/message?limit=500&order=asc'}]` — Beweis: Abfragen laufen gegen OC_URL |
| test_live_subagents_are_discovered_via_the_run_endpoint (AK5) | `Der live erkannte Subagent fehlt` — Erkennung am gemeinsamen Server ohne Daten |
| test_two_active_projects_use_their_own_endpoints (AK6) | beide Projekte erhielten den statischen Text statt PROJEKT-A/PROJEKT-B |
| test_the_password_stays_secret (AK8) | vor dem Geheimnis-Check scheiterte der LIVE-Text-Beweis (statischer Text) |

Die 6 Kompatibilitätswächter (AK3-Fallback-Verhalten, AK4-Defekt-Rückfälle)
sind am Ausgangsstand grün und müssen grün bleiben — sie sind kein
Bug-Nachweis, sondern bewahren das vereinbarte Verhalten bei der Umsetzung.

Befehl (Browser): `PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_b14_subagent_output_ui -v`
Ergebnis: `Ran 2 tests ... FAILED (failures=2)`, Exit 1. Befund (aus der
eingebauten Diagnose beider Tests):

```
Befund: Karteninhalt: tester — tester arbeitet
running
Vergrößern
The subagent is working in the background (sessionID: ses_kind_b14). STATISCH-4711
```

Das ist exakt das gemeldete Bug-Bild: Die laufende Subagent-Karte zeigt nur
den ersten erfassten Boilerplate-Text und friert ein, obwohl der Laufserver
via Serverdatei LIVE-A-4711 geliefert hätte.

## Bestandssuiten (tatsächlich ausgeführt, müssen grün bleiben)

| Suite | Ergebnis | Exit |
| --- | --- | --- |
| `tests.unit.test_b13_private_server_steering` | 9 Tests OK | 0 |
| `tests.unit.test_b13_private_server_runner` | 9 Tests, 1 Fehler: `test_sandboxed_run_starts_the_private_server_inside_the_sandbox` | 1 |
| `tests.unit.test_b12_background_subagents` + `tests.unit.test_f30_subagent_view` | 19 Tests OK | 0 |
| `tests.unit.test_b11_output_view_api` + `tests.unit.test_ap14_output_view_api` | 27 Tests OK | 0 |
| `tests.browser.test_f30_subagent_view_ui` | 4 Tests OK | 0 |

**Einordnung des B13-Runner-Fehlers (vorbestehend, kein Regress):**
Der Test startet einen vollständigen Sandbox-Lauf
(`vibe-run.sh` in der Bubblewrap-Umgebung) und schlägt in dieser Umgebung
fehl — beobachtet als `subprocess.TimeoutExpired ... timed out after 300
seconds` bzw. `AssertionError: False is not true : opencode wurde nicht
aufgerufen`. Beleg, dass er unabhängig von B14 ist: Ich habe meine beiden
ungetrackten Testdateien temporär aus der Arbeitskopie entfernt und den
Einzelfall am unveränderten Stand `46ba601` erneut ausgeführt — gleicher
Fehler (Exit 1, Timeout nach 300 s). Danach wurden die Dateien unverändert
zurückgelegt (`git status` zeigt nur die beiden neuen Testdateien). Die
B13-Suite war zum Zeitpunkt des Ausgangsstands in dieser Umgebung bereits
rot; der Coding-Agent sollte das dem Reviewer melden, nicht an B14
anhängen.

## Projektprüfung

```
bash scripts/verify.sh quick   →   Exit 0
OK: 60 Dateien stimmen mit docs/import-manifest.json überein.
OK: 164 Python-, 8 Bash- und 4 JSON-Datei(en) syntaktisch geprüft.
OK: keine Geheimnisse erkannt.
```

(Voraussetzung: lokale, git-ignorierte Prüfkopie `.vibe/project.env` —
Hinweis für den Coding-Agenten: das Importmanifest muss um die beiden neuen
Testdateien ergänzt/synchronisiert werden, sobald die Umsetzung committed
wird; der Quick-Check zählt sie noch nicht, weil sie außerhalb des
Manifests liegen.)

## Browser-Infrastruktur

Playwright mit Chromium ist verfügbar (`~/.cache/ms-playwright`,
chromium-1243); die Browser-Rotphase wurde real ausgeführt. AK7 ist damit
nicht nur unit- sondern auch browserseitig belegt und kann nach der
Umsetzung als Beweis erneut laufen.

## Grünfähigkeit und Grenzen

* Alle 15 Testfälle sind auf das vereinbarte Verhalten ausgelegt und
  scheitern am Ausgangsstand ausschließlich am Bug (statischer
  Fallback-Text bzw. Anfragen an OC_URL statt Lauf-Endpunkt). Nach der
  Umsetzung müssen sie grün werden, ohne dass Assertions abgeschwächt
  werden dürften.
* Die Attrappen lauschen auf 127.0.0.1-Freihafen-Ports; keine echten
  Modellaufrufe, keine produktive Installation, keine externen Dienste,
  keine Geheimnisse (Kennwörter sind offensichtliche Testwerte, der
  Secret-Scan von `verify.sh quick` meldet nichts).
* Grenze 1: Der vorbestehende B13-Sandbox-Runner-Fehler (siehe oben) bleibt
  in dieser Umgebung rot; er gehört zum Ausgangsstand und nicht zu B14.
* Grenze 2: `scripts/verify.sh quick` wurde mit git-ignorierter lokaler
  Prüfkopie von `.vibe/project.env` ausgeführt, da die Arbeitskopie (wie
  jede andere Worktree-Arbeitskopie) keine eigene ausliefert.
* Grenze 3: Nicht geprüft: Verhalten bei mehreren Subagenten pro Lauf und
  sehr langen Ausgaben (> 64 KiB Tail-Budget) — der Tail-Ausschnitt ist
  durch `tests.unit.test_f30_subagent_view` abgedeckt; die Endpunktwahl
  wurde an einem Subagenten je Projekt belegt.

## Nachtrag des Koordinators (2026-11-14, nach Vollauf)

Die Grenze 1 wird präzisiert: Der
B13-Sandbox-Runner-Fall
(`test_sandboxed_run_starts_the_private_server_inside_the_sandbox`)
schlug nur im eigenständigen Lauf dieses Berichts fehl; in der
verify-full-Umgebung (tmpfs-Kopie, `env -u TMPDIR`) ist er an beiden
Ständen grün (B14-Stand und Ausgangsstand `46ba601`). Ein erster
Vollauf direkt in der NTFS-Arbeitskopie erzeugte 37 × „File name too
long" an tmux-Sockets (umgebungsbedingt, vgl. B5); der betroffene
B11-Stopp-Test ist im tmpfs-Vollauf grün und am unveränderten
Ausgangsstand `46ba601` einzeln grün
(`python3 -m unittest
tests.unit.test_b11_stop_terminates_agents.StopEndpointRealTmuxTest.
test_stop_command_ends_the_run_and_shows_no_active_agent` → OK). Der
vollständige Abgleich steht in `docs/features/B14.md`, Abschnitt
„Prüfungen (Vollauf)".
