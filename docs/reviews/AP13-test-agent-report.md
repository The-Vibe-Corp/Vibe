# AP13 — Bericht des unabhängigen Test-Agenten

Datum: 2026-11-12
Branch: `vibe/vibe-AP13-1794441440266802654-1161723-5229`
Ausgangsstand: Commit `e872577` (AP10-Abschluss); **keine AP13-Implementierung
vorhanden** (`bin/vibe_ui_config.py` existiert nicht).

## 1. Provenanz (Übernahme und Prüfung der Tests)

Die drei AP13-Testdateien waren in einem früheren, abgebrochenen Lauf
erstellt worden, ohne Abnahmebericht. Der Test-Agent hat sie in dieser Runde
vollständig gelesen, gegen Arbeitspaket AP13 (TICKETS.md, Z. 771–779),
SPEC.md (Abschnitt „Sicherheit und Datenintegrität", Port-/Pfad-Priorität,
„Qualität und Abnahme") und die bestehenden Testmuster
(`tests/unit/test_web_api_security.py`, `tests/unit/test_vibe_paths.py`,
`tests/browser/*`) übernommen und übernimmt sie hiermit als seine Tests.

Prüfergebnis der Herleitung:

- Jeder Fall adressiert ein AP13-Kriterium (Port-Konfiguration über ui.json
  mit CLI-Vorrang, IP-Allowlist, Token→Password/Session, Security-UI) bzw.
  eine durch AP13 geänderte Verhaltensbedingung (Bind auf IP-Literale,
  Host/Origin mit IP-Literalen). Kein Fall ist aus einem
  Implementierungsdiff abgeleitet — es gibt keinen.
- Die HTTP-/Dashboard-Fixtures folgen exakt dem etablierten Muster des
  V-004-Sicherheitstests (echter Prozess, isolierte VIBE_*/HOME-Pfade,
  freie Ports, Token aus `web.token`), nicht einem Implementierungsvertrag
  über die bestehende API hinaus: `login`/`logout`/`security`/
  `vibe_session` sind die im Testmodul-Docstring dokumentierten
  AP13-Neuverträge („erwartete Zielstruktur, die Implementierung folgt").
- Standardbibliothek only; tmux ausschließlich als Attrappe
  (`FAKE_TMUX` auf isoliertem PATH); keine produktiven Konfigurationen, keine
  externen Dienste, keine automatischen Router-Aktionen.

## 2. Getestete Verträge (Zusammenfassung; Details in den Modul-Docstrings)

Alle implementierungsrelevanten Verträge sind in den Testdateien selbst
dokumentiert (Modul-Docstrings + Testfall-Kommentare). Kurzreferenz:

### tests/unit/test_ap13_network_config.py (43 Fälle)

| Vertrag | Testfälle |
|---|---|
| `ui.json`-Dateivertrag (fehlt/leer/defekt; save validiert, Roundtrip, Pfadrückgabe; keine Teil-Schreibungen bei Fehlern) | `UiConfigFileTest` (6 Fälle) |
| `validate`: bereinigt, akzeptiert `{}`, lehnt ungültige Ports/Binds/Typen und nicht-IP-Allowlist-Einträge ab; `ConfigError` ist ValueError | `ValidateTest` (5) |
| `client_allowed`-Allowlist: leer/fehlend erlaubt alles, Loopback immer (Aussperrschutz), Einzel-IP, CIDR, IPv6, gemischt; unparserver Client-IP → ablehnen statt Absturz | `AllowlistTest` (7) |
| Passwort: Mindestlänge 8, gesalzener Hash ohne Klartext, unterschiedliche Salze, verify korrekt/falsch/ohne Hash, clear entfernt Hash, Typprüfung | `PasswordTest` (7) |
| `config_extra`: nur gesetzte Felder `ui_port`/`ui_bind`, sonst `{}` | `ConfigExtraTest` (2) |
| Priorität Defaults < ui.json (`extra_config`) < Umgebung (VIBE_UI_PORT/VIBE_UI_BIND) < CLI-Übergabe; ungültiges `extra_config` abgelehnt; Default-Bind bleibt 127.0.0.1, Default-Port 8787 | `ResolvePriorityTest` (5) |
| `validate_bind`-Erweiterung: IP-Literale (`0.0.0.0`, `::`, `::1`, …) erlaubt, Hostnamen außer `localhost` abgelehnt, `localhost`→`127.0.0.1`, ungültige Werte abgelehnt | `ValidateBindExtensionTest` (5) |
| CLI-Override via tmux-Attrappe: `vibe ui start [--port N] [--bind A]` und `vibe ui` ohne Subkommando übergeben die effektiv aufgelösten Werte; ungültige Werte starten nichts; `ui stop` unverändert | `UiCliOverrideTest` (6) |

### tests/unit/test_ap13_web_access.py (26 Fälle)

Echtes Dashboard als Prozess, isolierte Pfade, freie Ports:

| Vertrag | Testfälle |
|---|---|
| `/`, `/static/*`, `/api/health` ohne Auth lesbar; andere API-Routen 403 `unauthorized` | `LoginFlowTest.test_health_and_page_and_static_stay_readable_without_auth`, `test_reads_without_credentials_are_rejected` |
| `POST /api/login` mit Instanz-Token setzt HttpOnly-Session-Cookie `vibe_session` (SameSite=Strict, Path=/) ohne Klartext-Token | `test_login_with_instance_token_sets_a_session_cookie` |
| Cookie autorisiert GET/POST; Same-Origin-Pflicht bleibt; Logout beendet Session; gefälschter Cookie abgelehnt; falsche Zugangsdaten strukturiert ohne Kennwortdetails; `X-Token` bleibt gültig; `?t=` nur für `/api/stream`; Passwort-Login nach Setzen über Security-API | `LoginFlowTest` (7 weitere) |
| `GET/POST /api/security`: Auth-Pflicht, Ansicht von Port/Bind/Allowlist/Passwortstatus/`restart_required`, Speichern schreibt ui.json, ungültige Eingaben → 400 ohne Dateiänderung, Passwort-Aktionen wirken, Kennwort nie in Logs/Responses | `SecurityApiTest` (6) |
| Host/Origin: IP-Literale (IPv4/IPv6) erlaubt, DNS-Hostnamen 403 `forbidden_host`, Origin mit passendem Port erlaubt, falscher Port/ohne Port 403 `forbidden_origin` | `HostOriginLiteralTest` (4) |
| Allowlist auf HTTP-Ebene an `0.0.0.0` mit der Nicht-Loopback-Adresse des Rechners: offener Server erlaubt LAN-IP, Allowlist lässt zu/verweigert mit 403 `forbidden_ip`, Loopback bleibt immer erlaubt, Quelladressen-Vorbedingung verifiziert; ohne Nicht-Loopback-Adresse im System → skip mit Begründung | `AllowlistHttpTest`-Familie (5) |

### tests/browser/test_ap13_security_ui.py (7 Fälle)

Playwright/Chromium aus dem Nur-Lese-Nutzer-Cache (`~/.cache/ms-playwright`):

| Akzeptanzkriterium | Testfall |
|---|---|
| Anmeldekarte statt Projektliste ohne Session | `test_anmeldekarte_ohne_session` |
| `#t=`-Hash einmalig gegen Session-Cookie eingetauscht; `location.hash` und `sessionStorage.t` leer; Reload bleibt angemeldet | `test_hash_wird_gegen_session_eingetauscht_und_geleert` |
| Karte „Zugriffssicherheit" zeigt Port, Bind `127.0.0.1`, Passwortstatus | `test_zugriffssicherheit_karte_zeigt_werte` |
| Port ändern → Neustart-Hinweis, ui.json enthält `ui_port` | `test_port_aendern_zeigt_neustart_hinweis_und_schreibt_ui_json` |
| Passwort setzen (≥ 8 Zeichen), Anmeldung mit Passwort in frischem Kontext, ohne Cookies wieder Anmeldekarte | `test_passwort_setzen_und_anmeldung_mit_passwort` |
| Karte „Alle Clients zulassen“: Inline-Bestätigung (askInline) warnt, dass danach alle Clients im Netz zugreifen dürfen; danach Fakt-Zeile „alle Clients erlaubt“, ui.json ohne Allowlist-Einträge, GET /api/security in der gleichen Session ohne Allowlist | `test_alle_clients_zulassen_entfernt_allowlist` |
| Allowlist-Eingabe (aria-label „IP-Allowlist“): Platzhalter enthält „(leer = unverändert)“ und nicht mehr „(leer = alle Clients)“ | `test_allowlist_platzhalter_sagt_leer_ist_unveraendert` |

### Angepasste Baseline-Tests (bereits im Vorlauf durch den Test-Agenten geändert, uncommitted)

- `tests/unit/test_vibe_paths.py`: `test_bind_accepts_ip_literals_and_still_rejects_hostnames` — AP13-Nutzerentscheidung: IPv4-/IPv6-Adressliterale (inkl. `0.0.0.0`) zulässig, Hostnamen bleiben abgelehnt.
- `tests/unit/test_web_api_security.py`: IP-Literal-Host (inkl. `[::1]`) erlaubt; `LoopbackBindTest` verlangt jetzt, dass Bind `0.0.0.0` das Dashboard startet (Health ohne Token lesbar) statt es zu verweigern. Der Testprozess wird sauber beendet.

## 3. In dieser Runde behobener Testdefekt

- `tests/unit/test_ap13_network_config.py`, `UiCliOverrideTest`: das Attribut
  `self.tmux_log` (Pfad) überschattete die gleichnamige Hilfsmethode; vier
  Tests scheiterten mit `TypeError: 'PosixPath' object is not callable`
  statt an fehlender AP13-Funktionalität. Behoben durch Umbenennung des
  Attributs in `self.tmux_log_path` (nur Testdatei; kein Vertrag geändert).

## 4. Tatsächlich ausgeführte Rote Phase

Alle Befehle im Repository-Root, Python 3.14.8.

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_ap13_network_config -v` | Exit 1 — **Ran 43 tests, FAILED (failures=32, errors=10), 5 ok** |
| `python3 -m unittest tests.unit.test_ap13_web_access -v` | Exit 1 — **Ran 26 tests, FAILED (failures=12, errors=4), 10 ok** |
| `python3 -m unittest tests.unit.test_vibe_paths tests.unit.test_web_api_security -v` | Exit 1 — **Ran 54 tests, FAILED (failures=5), 51 ok** |
| `python3 -m unittest tests.browser.test_ap13_security_ui -v` | Exit 1 — **Ran 5 tests, FAILED (failures=1, errors=4)** |

### Rot-Status nach Ursache (alle Fehlschläge betreffen fehlende AP13-Funktionalität)

- **Fehlendes Modul `bin/vibe_ui_config.py`**: alle `UiConfigFileTest`-,
  `ValidateTest`-, `AllowlistTest`-, `PasswordTest`- und
  `ConfigExtraTest`-Fälle scheitern mit der klaren Meldung
  „AP13-Modul bin/vibe_ui_config.py existiert nicht".
- **`vibe_paths.resolve(..., extra_config=...)` fehlt**: 4
  `ResolvePriorityTest`-Fälle mit
  `TypeError: resolve() got an unexpected keyword argument 'extra_config'`.
- **`validate_bind` lehnt IP-Literale ab**: 4 Subtest-`ERROR`s in
  `ValidateBindExtensionTest.test_address_literals_are_now_allowed`
  („vibe bindet nur an IPv4-Loopback; '0.0.0.0' ist nicht erlaubt").
- **CLI ohne `--port/--bind`**: `UiCliOverrideTest` scheitert (keine
  `VIBE_UI_PORT`/`VIBE_UI_BIND`-Exporte im tmux-Attrappen-Log bzw.
  ungültige Werte werden nicht abgelehnt).
- **Dashboard ohne Session-Login**: `/api/login` existiert nicht
  (`unauthorized`), daher alle Cookie-/Logout-/Forged-Cookie-Fälle rot.
- **Host-/Origin-Prüfung ohne IP-Literale**: `forbidden_host` auf
  `192.0.2.10`/`[::1]` statt 200.
- **Security-API fehlt**: `/api/security` rot (Ansicht/Speichern/Passwort).
- **Allowlist auf HTTP-Ebene nicht vorhanden**: 4 `ERROR`s
  `ConnectionRefusedError: [Errno 111]` — das Dashboard honoriert
  `ui_bind: 0.0.0.0` aus ui.json nicht (bindet nur Loopback), daher ist die
  Nicht-Loopback-Adresse nicht erreichbar. Das ist die fehlende
  AP13-Funktionalität, kein Testdefekt.
- **Browser-Fälle rot aus fehlender AP13-UI**: kein „Anmelden"-Knopf
  (TimeoutError), keine Karte „Zugriffssicherheit", Token-Hash bleibt
  stehen (`sessionStorage.t` nicht geleert → FAIL bei
  `test_hash_wird_gegen_session_eingetauscht_und_geleert`).
- **Angepasste Baseline-Fälle rot wie erwartet**: IP-Literale bei
  `validate_bind`/Host-Header (5 Fälle), u. a. „Pfadkonfiguration: vibe
  bindet nur an IPv4-Loopback; '0.0.0.0' ist nicht erlaubt"; 51 weitere
  Baseline-Fälle bleiben grün.

In der Rotphase grün gebliebene Fälle testen unverändertes Bestandsverhalten
(z. B. Health/Side lesbar, strukturierte Fehler, `X-Token` gültig,
`ui stop` ohne Sitzung harmlos) — das ist korrekt.

## 5. Umgebung und Blockierungen

- **Keine Blockierung**: Playwright und Chromium waren im Nutzer-Cache
  vorhanden (`~/.cache/ms-playwright`, `chromium-1243`,
  `chromium_headless_shell-1243`); der Browser-Test wurde tatsächlich
  ausgeführt (5 Tests, 121 s). Die Browserabnahme läuft nach
  Implementierung ohne zusätzliche Installation.
- Keine echten externen Dienste, keine bezahlten Modellaufrufe, keine
  produktiven Konfigurationen berührt; alle Server-Tests liefen auf freien
  Ports mit temporären HOME-/VIBE_*-Pfaden; tmux nur als Attrappe.
- Zwei aus der Suite-Ausführung verwaiste Test-Dashboard-Prozesse
  (isolierte Sandbox-Pfade, Ports 36079/37877) wurden nach Abschluss
  beendet; im Repository hinterließen sie keine Spuren.
- **Vorbestehende Baseline-Fehler außerhalb AP13** (kein Teil dieses
  Arbeitspakets, nicht vom Test-Agenten verursacht): die volle
  Unit-Suite (`unittest discover -s tests/unit`, 1584 Tests) meldet neben
  den AP13-Rotanteilen auch Fehler in anderem Umfang, z. B.
  `test_storage` (13 `ERROR`s), `test_costs`, `test_models`,
  `test_questions`, `test_pause_after`, `test_sandbox`, `test_agents_ui`
  usw. Verifikation der Vorbestehens: mit `git stash` (alle AP13-Dateien
  entfernt) blieb `python3 -m unittest tests.unit.test_storage` mit
  denselben 13 `ERROR`s rot (Stash wurde danach vollständig
  wiederhergestellt). Diese Module liegen außerhalb des AP13-Umfangs und
  werden nicht vom Test-Agenten dieser Runde geändert.

## 6. Erklärung

Alle implementierungsrelevanten Verträge des Arbeitspakets AP13 sind in den
drei Testdateien (Modul-Docstrings und Testfall-Kommentare) und in den
zwei angepassten Baseline-Testdateien dokumentiert. Die Tests wurden vor
der Implementierung geschrieben und tatsächlich ausgeführt; die Rote Phase
ist oben belegt. Nach der Implementierung wird der Test-Agent dieselben
Befehle erneut ausführen und den Grün-Status dokumentieren; keine
Assertion wird dafür abgeschwächt.

Geänderte/neue Dateien dieser Runde (ausschließlich Tests):

- `tests/unit/test_ap13_network_config.py` (neu; 1 Testdefekt behoben)
- `tests/unit/test_ap13_web_access.py` (neu, unverändert übernommen)
- `tests/browser/test_ap13_security_ui.py` (neu, unverändert übernommen)
- `tests/unit/test_vibe_paths.py` (Vorlauf-Änderung des Test-Agenten, bestätigt)
- `tests/unit/test_web_api_security.py` (Vorlauf-Änderung des Test-Agenten, bestätigt)
- `docs/reviews/AP13-test-agent-report.md` (dieser Bericht)

Kein Produktionscode geändert, keine Commits erstellt.

---

# Grün-Phase/Korrekturen (zweite Runde, 2026-11-12)

Nach der AP13-Implementierung blieben 6 Fälle rot. Jede Coder-Analyse wurde
vom Test-Agenten am tatsächlichen Fehlerbild verifiziert — **alle sechs
Analysen sind korrekt**; jeder Defekt lag im Test, keiner am
Produktionscode. Zusätzlich fand der Test-Agent bei der Prozessaufräumung
einen siebten, bislang unentdeckten Fixture-Defekt (siehe Korrektur 7).

## Verifizierte Analysen und Testkorrekturen

1. **`ResolvePriorityTest.test_invalid_extra_config_is_rejected`
   (tests/unit/test_ap13_network_config.py) — Analyse korrekt.**
   Fehlerbild: `vibe_paths_ap13.ConfigError` entweicht als ERROR. Ursache
   wie analysiert: `load_paths()` erzeugt je Aufruf ein neues
   Modulobjekt mit eigenem `ConfigError`-Klassenobjekt; `assertRaises`
   fing die Klasse der einen Instanz, geworfen wurde die der anderen.
   Korrektur: Prüfung über `ValueError` (`ConfigError` ist eine
   ValueError-Unterklasse — verifiziert in `bin/vibe_paths.py:66`),
   konsistent mit dem bestehenden Fall `test_config_error_is_a_value_error`.
2. **`SecurityApiTest.test_security_view_reports_current_values`
   (tests/unit/test_ap13_web_access.py) — Analyse korrekt.** Fehlerbild:
   `password_set` war `True` statt `False`. Ursache: alphabetische
   Reihenfolge — `test_password_is_never_in_logs_or_responses` setzt ein
   Kennwort und räumte nicht auf. Korrektur: dieser Test entfernt das
   Kennwort am Ende über die Security-API (`clear`), womit keine
   Erwartung mehr von der Ausführungsreihenfolge abhängt.
3. **`AllowlistOpenServerTest.test_open_server_allows_the_local_network_ip`
   — Analyse korrekt.** Fehlerbild: 403 `unauthorized` — das Token des
   Extra-Servers ging an den Klassen-Server (das Extra-`ui.json` enthält
   kein Kennwort; der Klassen-Server kennt das fremde Token nicht).
   Korrektur: `request()` hat einen `port`-Parameter; der Request läuft
   jetzt gegen `open_port`.
4. **`AllowlistRestrictiveServerTest.test_allowlist_admitting_the_local_ip_allows_it`
   — Analyse korrekt.** Fehlerbild: 403 mit Allowlist `["203.0.113.7"]` am
   falschen Server. Korrektur wie bei 3: beide Requests (LAN-IP und
   Loopback-Aussperrschutz) laufen gegen `admitting_port`; der Contract
   (Admit + Loopback-Schutz am selben Server) bleibt unverändert.
5. **`test_port_aendern_zeigt_neustart_hinweis_und_schreibt_ui_json`
   (tests/browser/test_ap13_security_ui.py) — Analyse korrekt.**
   Fehlerbild: `ui.json` enthielt bereits `password_hash`. Ursache:
   `test_passwort_setzen_und_anmeldung_mit_passwort` läuft (alphabetisch)
   vorher und räumt `ui.json` nicht auf. Korrektur: `setUp` entfernt eine
   vorhandene `ui.json` vor jedem Test — die Vorbedingung „kein ui.json"
   ist damit explizit und reihenfolgenunabhängig, statt dass ein Test die
   Hinterlassenschaften eines anderen erbt.
6. **`test_passwort_setzen_und_anmeldung_mit_passwort` — Analyse korrekt.**
   Fehlerbild: `AttributeError: 'ElementHandle' object has no attribute
   'locator'`. Korrektur: die Helfer `login_card`/`login`/
   `project_list_visible` wurden seitenparametrisiert und ohne
   `evaluate_handle`/`ElementHandle` neu geschrieben (`page.locator
   ("div.card").filter(has=button)` — struktureller Locator für den
   vereinbarten Vertrag „Behälter mit Eingabe plus Knopf ‚Anmelden'").
   Der frische Kontext im Passwort-Test benutzt denselben Helfer. Die
   Prüfschärfe blieb gleich (Anmeldekarte muss Eingabe enthalten).
7. **Zusätzlich gefundener Fixture-Defekt (vom Coder nicht gemeldet):**
   `AllowlistHttpTest.tearDownClass` überschrieb
   `DashboardFixture.tearDownClass`, ohne den Klassen-Server zu beenden —
   jede Suite-Ausführung hinterließ zwei verwaiste Dashboard-Prozesse
   (im Worktree fanden sich 16 aus mehreren Läufen). Korrektur:
   `tearDownClass` stoppt Extra-Server und Klassen-Server und schließt
   das Log; nach dem Lauf verifiziert: keine verwaisten
   `vibe-web`-Prozesse mehr. Ein erster Korrekturversuch über
   `DashboardFixture.tearDownClass()` als Klassenaufruf scheiterte
   (Bindung an die Basisklasse) und wurde in der Suite mit 2
   tearDown-ERRORs sichtbar; die endgültige Variante stoppt direkt.

## Tatsächliche Grün-Ergebnisse (alle Befehle im Repository-Root)

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_ap13_network_config -v` | **Exit 0 — Ran 43 tests, OK** |
| `python3 -m unittest tests.unit.test_ap13_web_access -v` | **Exit 0 — Ran 26 tests, OK** |
| `python3 -m unittest tests.unit.test_vibe_paths tests.unit.test_web_api_security -v` | **Exit 0 — OK (54 Tests)** |
| `python3 -m unittest tests.browser.test_ap13_security_ui -v` | **Exit 0 — Ran 5 tests, OK** |

Alle 128 AP13-Fälle (+ 54 Baseline-Fälle) sind grün; die anfangs
grünen Fälle blieben grün. Es wurden keine Assertions abgeschwächt und
kein Test gelöscht; die Korrekturen betreffen Testisolierung
(Reihenfolgenunabhängigkeit, korrekte Serveradressierung, Prozessaufräumen)
und eine nicht lauffähige Locator-API — nicht die geprüften Verträge.

## Keine Implementierungsfehler festgestellt

Keine der sechs Analysen war falsch; es gab keinen Fall, in dem der
Produktionscode die Ursache war. Offene Grenze: die HTTP-Allowlist-Fälle
laufen nur, wenn das Testsystem eine Nicht-Loopback-Adresse hat (dieses
System hat eine; der Skip-Fallback bleibt im Test dokumentiert).

---

# Fixture-Anpassungen an die erweiterte AP13-Produktion (dritte Runde, 2026-11-12)

Die Produktion wurde erweitert: `bin/vibe_ui_config.py` ist im Setup-Katalog
(`scripts/setup-vibe.py` `PROGRAM_FILES`) enthalten; `dashboard_health`
bekommt jetzt Bind/Port (`dashboard_health(paths.ui_bind, paths.ui_port)`)
und `child_exports(paths)` wird mit Argument gerufen. Die Test-Fixtures sind
darauf angepasst — Verhalten und Prüfschärfe unverändert.

## Korrekturen (ausschließlich Testdateien)

1. **`tests/unit/test_setup_vibe.py`**: testseitige `PROGRAM_FILES`-Kopie um
   `vibe_ui_config.py` ergänzt (an der Position des Produktionskatalogs).
   Verifikation: `set(Kopie) == set(scripts/setup-vibe.py PROGRAM_FILES)` —
   die bestehenden Prüfungen (`make_kit`, `InstallFilesTest`,
   Launcher-Importprüfung) laufen alle über die Liste bzw. Mengen und
   bleiben inhaltlich unverändert.
2. **`tests/unit/test_install_lifecycle.py`**: dieselbe Ergänzung in der
   testseitigen Kopie. Die Mengengleichheits-Assertion
   (`Testabbild und Setup müssen dieselben Programmmodule kennen`) und die
   `len(PROGRAM_FILES) + len(WEB_FILES) + 3`-Erwartung bleiben konsistent,
   weil exakt ein Eintrag ergänzt wurde (Produktion ebenfalls +1).
3. **`tests/unit/test_f28_pylint_quality.py`**: `MODULE` um
   `vibe_ui_config.py` ergänzt, damit das neue Modul gelintet wird; die
   Ausnahmeliste wurde **nicht** angetastet (siehe Befund unten).
4. **Stub-Signaturen** (verhaltensgleich, nur variadisch):
   - `tests/unit/test_lifecycle.py` und
     `tests/unit/test_v026_run_isolation.py`:
     `dashboard_health=lambda: None` →
     `dashboard_health=lambda *args, **kwargs: None` mit einzeiligem
     Kommentar („AP13: Produktion ruft dashboard_health(bind, port)“).
   - `port_in_use=lambda host, port: ...` passt unverändert (Produktion
     ruft weiterhin `port_in_use(bind, port)`).
   - `child_exports` hat in der Produktion einen `paths=None`-Default;
     die Tests stuben es nicht, keine Änderung nötig.
   - `server_health` blieb argumentlos — unverändert.

## Implementierungsbefund (gemeldet, nicht durch Teständerung kaschiert)

`python3 -m unittest tests.unit.test_f28_pylint_quality -v` schlägt mit
**genau 1 pylint-Befund außerhalb der Ausnahmeliste** fehl:

```
duplicate-code (R0801):
  ==vibe_paths:[178:185]
  ==vibe_ui_config:[69:76]
  try:
      with open(target, encoding="utf-8") as handle:
          raw = handle.read()
  except FileNotFoundError:
      return {}
```

Das heißt: `vibe_ui_config.py` dupliziert den schreibgeschützten
Datei-Lese-Helper aus `vibe_paths.py`. Das ist ein **echter
Implementierungsbefund** (Code-Duplikation, in zwei Folgeläufen stabil
reproduziert), den der Koordinator im Produktionscode beheben lassen
sollte (z. B. Helper aus `vibe_paths` importieren). Die Ausnahmeliste des
F28-Tests wurde dafür bewusst nicht erweitert. Hinweise zur Einordnung:

- Das neue Modul liefert **keine weiteren** pylint-Befunde.
- Mit der unveränderten 16-Modul-Basisliste ist der aktuelle Baum sauber
  (verifizierter Kontrolllauf: 0 Verletzungen); der Befund entsteht erst
  durch die Aufnahme des neuen Moduls in die Baseline — der F28-AK1-Vertrag
  („keine Befunde außerhalb der Ausnahmeliste“) gilt damit für die
  erweiterte Modulliste.
- Bis zur Behebung bleibt diese Suite rot; die übrigen sechs Suiten sind grün.

## Tatsächliche Ergebnisse (alle Befehle im Repository-Root, Python 3.14.8)

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_setup_vibe -v` | **Exit 0 — Ran 49 tests, OK** |
| `python3 -m unittest tests.unit.test_install_lifecycle -v` | **Exit 0 — Ran 43 tests, OK** |
| `python3 -m unittest tests.unit.test_f28_pylint_quality -v` | **Exit 1 — Ran 2 tests, FAILED (failures=1)**: 1 Befund `duplicate-code` `vibe_paths` ↔ `vibe_ui_config` (Implementierungsbefund, siehe oben); Schutzwächter (`test_ak1_pylint_ausfuehrung_gesichert`) grün |
| `python3 -m unittest tests.unit.test_lifecycle -v` | **Exit 0 — Ran 17 tests, OK** |
| `python3 -m unittest tests.unit.test_v026_run_isolation -v` | **Exit 0 — Ran 18 tests, OK** |
| `python3 -m unittest tests.unit.test_ap13_network_config tests.unit.test_ap13_web_access tests.unit.test_vibe_paths tests.unit.test_web_api_security -v` | **Exit 0 — Ran 123 tests, OK** (0 skipped: die HTTP-Allowlist-Fälle liefen gegen die Nicht-Loopback-Adresse) |

Zusätzlich verifiziert: nach den Läufen blieben keine verwaisten
`vibe-web`-Prozesse zurück. Vorbestehende Umgebungsfehler außerhalb AP13
(z. B. `test_release`-Geheimnisprüfung, `test_sandbox`-Realtest,
`test_dry_run_explains_pi...`) sind bekannt und wurden nicht berührt.

## Geänderte Dateien dieser Runde (nur Tests; keine Commits)

- `tests/unit/test_setup_vibe.py` (PROGRAM_FILES-Kopie +1 Eintrag)
- `tests/unit/test_install_lifecycle.py` (PROGRAM_FILES-Kopie +1 Eintrag)
- `tests/unit/test_f28_pylint_quality.py` (MODULE +1 Eintrag; Ausnahmeliste unverändert)
- `tests/unit/test_lifecycle.py` (Stub variadisch + Kommentar)
- `tests/unit/test_v026_run_isolation.py` (Stub variadisch + Kommentar)
- `docs/reviews/AP13-test-agent-report.md` (dieser Abschnitt)

---

# 7. Grünphase nach Implementierung (diese Runde, 2026-11-12)

Die vier Befehle der Rotphase (Abschnitt 4) wurden nach der AP13-
Implementierung im Arbeitsbaum-Wurzelverzeichnis unverändert erneut
ausgeführt (Python 3.14.8). Keine Assertion wurde abgeschwächt, kein
Test geändert oder gelöscht.

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_ap13_network_config -v` | **Exit 0 — Ran 43 tests in 6.766s, OK** (0 Failures, 0 Errors) |
| `python3 -m unittest tests.unit.test_ap13_web_access -v` | **Exit 0 — Ran 26 tests in 5.078s, OK** (0 Failures, 0 Errors) |
| `python3 -m unittest tests.browser.test_ap13_security_ui -v` | **Exit 0 — Ran 7 tests in 2.252s, OK** (0 Failures, 0 Errors; enthält die zwei Nachtragsfälle `test_alle_clients_zulassen_entfernt_allowlist` und `test_allowlist_platzhalter_sagt_leer_ist_unveraendert`) |
| `python3 -m unittest tests.unit.test_vibe_paths tests.unit.test_web_api_security -v` | **Exit 0 — Ran 54 tests in 6.881s, OK** (0 Failures, 0 Errors) |

Zusammenfassung: **130 Tests, alle grün** (43 + 26 + 7 + 54), kein Skip,
keine verwaisten `vibe-web`-Prozesse nach den Läufen; die produktive
Installation (`_toolchain`, Port 8787) wurde nicht berührt. Abschnitt 4
(Rote Phase) bleibt unverändert als historischer Beleg stehen. Offen aus
der dritten Runde: der `duplicate-code`-Pylint-Befund in
`vibe_ui_config.py` ↔ `vibe_paths.py` (Implementierungsbefund, F28-Suite
rot) — nicht Teil dieser vier Befehle, vom Koordinator im
Produktionscode zu beheben.
