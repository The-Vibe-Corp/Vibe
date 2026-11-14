# Review AP13 — Runde 1

Datum: 2026-11-12
Reviewer: code-reviewer (unabhängig, read-only)
Umfang: `e872577..4fc26dc` (22 Dateien, 3591+/93-)
Der Bericht wurde unverändert aus der Review-Antwort übernommen.

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 6
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Port-/Bind-Konfiguration über UI (Karte „Zugriffssicherheit"), Neustart-Hinweis | PASS | `bin/vibe-web.py:863-898` (`/api/security` save), `bin/web/app.js` (Karte `security()`, Warnhinweis), `bin/vibe-web.py:434-444` (`restart_required`) | `tests/unit/test_ap13_web_access.py::SecurityApiTest` (6 Fälle), `tests/browser/test_ap13_security_ui.py::test_port_aendern_zeigt_neustart_hinweis_und_schreibt_ui_json`; Grünphase 26/26 und 7/7 laut Test-Agent-Bericht Abschnitt 7, vom Koordinator reproduziert |
| Port-Konfiguration über CLI, „CLI überschreibt immer konfig", ungültige Werte starten nichts | PASS | `bin/vibe:5037-5057` (`_ui_arguments` + Validierung vor Start), `bin/vibe:5060-5140` (`cmd_ui`, Auflösung mit `extra_config`, Export an Kind) | `tests/unit/test_ap13_network_config.py::UiCliOverrideTest` (6 Fälle, echte CLI + tmux-Attrappe); Grünphase 43/43 |
| Prioritätskette Defaults < ui.json < Umgebung < CLI | PASS | `bin/vibe_paths.py:368-405` (`resolve(..., extra_config=...)`), `bin/vibe_ui_config.py:253-256` (`config_extra`) | `tests/unit/test_ap13_network_config.py::ResolvePriorityTest` (5 Fälle) |
| IP-Allowlist Einzel-IP/CIDR, HTTP-Ebene, Loopback-Aussperrschutz | PASS | `bin/vibe_ui_config.py:161-192` (`client_allowed`), `bin/vibe-web.py:544-553, 657-659, 806-808` | `tests/unit/test_ap13_network_config.py::AllowlistTest` (7), `tests/unit/test_ap13_web_access.py::AllowlistHttpTest`-Familie (5, echte Bindung an 0.0.0.0 und Nicht-Loopback-Adresse des Rechners) |
| Token → Kennwort + Session-Cookie (PBKDF2, HttpOnly/SameSite/Path, Logout, strukturierte 403 ohne Geheimnis-Auskunft) | PASS | `bin/vibe_ui_config.py:195-250`, `bin/vibe-web.py:820-853` (login), `bin/vibe-web.py:845-853` (logout), `bin/vibe-web.py:555-581` | `tests/unit/test_ap13_web_access.py::LoginFlowTest`, `::SecurityApiTest`, `::PasswordTest` (test_ap13_network_config.py); Testbericht Abschnitt 7 |
| UI-Option, die die Zugriffssicherheit darstellt (ohne Kennwort-/Hash-Auskunft) | PASS | `bin/vibe-web.py:446-455` (`security_data`, nur `password_set`), `bin/web/app.js` (Karte, „Alle Clients zulassen" mit Bestätigung, Platzhalter „(leer = unverändert)") | `tests/browser/test_ap13_security_ui.py` (7 Fälle, u. a. `test_alle_clients_zulassen_entfernt_allowlist`, `test_allowlist_platzhalter_sagt_leer_ist_unveraendert`) |
| ui.json: Validierung vor Schreiben, atomar, Rechte best effort, defekte Datei gemeldet | PASS | `bin/vibe_ui_config.py:102-158` (validate/save, Tempdatei+replace, chmod best effort), `bin/vibe_ui_config.py:61-82` (defekte Datei → `ConfigError`), `bin/vibe:5076-5081` (Startabbruch mit Meldung) | `tests/unit/test_ap13_network_config.py::UiConfigFileTest`, `::ValidateTest`; F28-Pylint 2/2 grün |
| Bind nur als IP-Adressliteral (DNS-Rebinding-Schutz), SPEC-Anpassung | PASS mit Befund (Medium 1: IPv6-Literale im Vertrag, aber zur Laufzeit nicht bindbar) | `bin/vibe_paths.py:113-135`, `bin/vibe-web.py:117-155` (Host/Origin mit IP-Literalen), `SPEC.md:262-266` | `tests/unit/test_ap13_network_config.py::ValidateBindExtensionTest`, `tests/unit/test_web_api_security.py` (angepasst, Hostnamen bleiben 403) |
| OIDC ausdrücklich nicht umgesetzt (Ticket: „aufwand gering halten") | PASS (dokumentiert) | `docs/features/AP13.md:116-125`, `176-182` | — (Doku) |
| Konsistenz: Manifest, baseline.md, setup-vibe.py, Trilium-Index | PASS | `docs/import-manifest.json` (AP13-Eintrag, aktualisierte SHA-256), `docs/baseline.md:252-255`, `scripts/setup-vibe.py:56`, `docs/trilium-index.md:63` | `check-import-manifest.py OK (60 Dateien)`, `check-no-secrets.py OK` (vom Koordinator ausgeführt) |
| Test-Provenanz (keine Coding-Agent-Teständerungen, keine abgeschwächten Assertions) | PASS | Testbericht `docs/reviews/AP13-test-agent-report.md` (Rot- und Grünphasen, alle Testkorrekturen dem Test-Agenten zugeordnet) | Stichprobe der 6 geänderten Baseline-Testdateien bestätigt die Berichtsaussagen (PROGRAM_FILES +1, Stub-Signaturen variadisch, F28-MODULE +1; keine gelöschten/abgeschwächten Assertions, Hostname-Ablehnung bleibt geprüft) |

## Findings

- [Medium] `bin/vibe-web.py:1575` — IPv6-Bind-Adressen sind im Vertrag zulässig, aber der Server kann sie nicht binden
  - Evidence: `bin/vibe_paths.py:113-135` lässt IPv4- und IPv6-Adressliterale zu (`::`, `::1` inklusive; Test `test_ap13_network_config.py:521-524` fordert das ausdrücklich), und `docs/features/AP13.md:37-38` wirbt genau mit `0.0.0.0`, `::`, `::1`. Der Server startet aber `ThreadingHTTPServer((BIND, PORT), H)`; `http.server.HTTPServer` setzt `address_family = AF_INET` fest, sodass `socket.bind(("::1", …))`/`("::", …)` mit einer OSError scheitert — der Prozess stirbt mit Traceback, der Nutzer sieht danach z. B. „Dashboard-Sitzung läuft bereits, antwortet aber noch nicht" (`bin/vibe:5112`) oder „Port … ist belegt" (`bin/vibe:5108`) statt einer klaren Fehlermeldung. Kein Test bindet je eine IPv6-Adresse zur Laufzeit (die IPv6-Fälle in `test_ap13_web_access.py` prüfen nur Host-/Origin-Header). Zusätzlich bauen `dashboard_health` (`bin/vibe:349`) und alle URL-Ausgaben (`bin/vibe:5105/5112/5133`, `bin/vibe-web.py:1582`) IPv6-Hosts ohne Klammern (`http://::1:PORT/`), wodurch curl und die Health-Erkennung fürs IPv6-Ziel ebenfalls fehlschlagen. Folge: eine validierte, in der Feature-Doku genanntes Konfiguration führt zu einem nicht startenden Dashboard mit irreführenden Statusmeldungen.
  - Required fix: Entscheidung nachholen und umsetzen — entweder `validate_bind` vorläufig auf IPv4-Literale beschränken und Doku/Tests anpassen, oder IPv6-Bindung real unterstützen (Adressfamilie je Literal wählen, klammernde URL-Erzeugung für Health/Print) und einen Laufzeittest mit echter IPv6-Bindung ergänzen; beim IPv6-Registereintrag an das IPv4-mapped-Client-Adressproblem denken (`::ffff:192.168.x.x` passt heute in keine IPv4-Allowlist — Fail-closed, aber verwirrend).
- [Minor] `bin/vibe-web.py:820-841` — `/api/login` ohne Fehlversuchsbegrenzung, Sessions ohne Ablauf
  - Evidence: Jeder erfolgreiche Login legt eine In-Memory-Session ohne Ablaufdatum an (`SESSIONS[session] = time.time()`, comment „ohne Ablaufdatum"); Fehlversuche sind unbegrenzt. Bei gesetzt Kennwort ist ein LAN-Brute-Force damit unbegrenzt möglich. Teilweise bewusst dokumentiert (`docs/features/AP13.md:178-179` nennt nur die Neustart-Semantik, kein Wort zur Fehlversuchslage).
  - Required fix: Grenze (z. B. einfache Fail-Counter mit Verzögerung oder dokumentierte bewusste Nicht-Umsetzung als „Grenze") in AP13.md ergänzen oder ein Minimal-Limit implementieren (Test-Agent leitet Fall ab).
- [Minor] `docs/features/AP13.md:53-71` — Verzicht auf das Secure-Cookie-Attribut ist nicht begründet
  - Evidence: Die Feature-Doku nennt HttpOnly/SameSite=Strict/Path, aber nicht, warum `Secure` fehlt. Da der Server kein TLS anbietet, würde `Secure` die Session bei LAN-Zugriff über http:// unverwendbar machen — die fehlende Begründung ist korrekt, aber nicht dokumentiert (Review-Frage des Arbeitspakets).
  - Required fix: Ein Satz in AP13.md (und ggf. Modul-Docstring), warum `Secure` bewusst entfällt (kein TLS-Angebot; Secure würde die Session im Netzwerkbetrieb deaktivieren).
- [Minor] `bin/vibe-web.py:66-72` + `SameSite`-Cookie ohne Port-Geltungsbereich — Kollision mehrerer Dashboard-Instanzen auf demselben Host
  - Evidence: Cookies sind nicht an Ports gebunden; dieses Produkt unterstützt mehrere Instanzen (Dev-Profil 8788 vs. produktiv 8787, `bin/vibe_paths.py`). Zwei Dashboards auf demselben Host teilen sich das Cookie `vibe_session`; der Wert des einen ist auf dem anderen ein gefälschter Cookie → 403, bis neu angemeldet wird (Fail-closed, aber verwirrend).
  - Required fix: Verhalten in der Feature-Doku als bekannte Grenze nennen (oder Cookie-Pfad-/Namensschema je Port dokumentieren); keine Codeänderung zwingend.
- [Minor] `tests/browser/test_ap13_security_ui.py:387-391` — wirkungslose Wartebedingung im Passwort-Test
  - Evidence: `wait_until(lambda: "ap13-ui-paswort-42" not in self.page.inner_text("body"))` kann nie fehlschlagen: Eingabewerte von `<input type=password>` erscheinen nicht in `inner_text`, und die Meldungen enthalten das Kennwort nie. Die Prüfung ist ein toter Sync-Punkt; der eigentliche Nachweis (Anmeldung mit Passwort im frischen Kontext, Z. 393-400) ist real und deckt den Fall.
  - Required fix: Test-Agent kann die Bedingung entfernen oder durch eine wirksame ersetzen (z. B. Toast „Kennwort gesetzt" abwarten).
- [Minor] `tests/browser/test_ap13_security_ui.py:260-265` — `open_security_card` wartet auf eine trivial wahre Bedingung (Flake-Risiko)
  - Evidence: `get_by_text("Zugriffssicherheit").count() > 0` ist schon vor dem Karten-Render wahr (Nav-Knopf trägt denselben Text). Danach liest z. B. `test_zugriffssicherheit_karte_zeigt_werte` sofort `security_card().inner_text()`; der Locator kann auf den Nav-Knopf auflösen, bevor `main.replaceChildren(...)` die Karte eingesetzt hat. In allen gelieferten Läufen grün (7/7 mehrfach), aber latent instabil.
  - Required fix: Warten auf ein konkretes Karten-Merkmal (`div#security` wie in den Nachtragsfällen) statt auf den allgegenwärtigen Nav-Text.
- [Minor] `bin/vibe:5105` — Netzwerkstart meldet `http://0.0.0.0:PORT/#t=…` als nutzbare Adresse
  - Evidence: Bei Bindung an `0.0.0.0` ist die gedruckte URL vom fremden Rechner aus nicht adressierbar (der Nutzer braucht die LAN-IP); lokal funktioniert sie, und der Folgehinweis (`bin/vibe:5133-5138`) warnt korrekt vor der Exposition. Kosmetische Unschärfe der Startmeldung.
  - Required fix: Startmeldung bei Netz-Bindung um die tatsächlich adressierbare LAN-Adresse (oder den Hinweis „vom anderen Rechner über die LAN-IP des Servers") ergänzen.

## Verification
- Change set reviewed: `e872577..4fc26dc` (22 Dateien, 3591+/93−), Arbeitsbaum sauber (`git status --short` leer), HEAD = `4fc26dc` auf Branch `vibe/vibe-AP13-1794441440266802654-1161723-5229`.
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff e872577..4fc26dc --stat`, `git diff` je Datei (`bin/vibe`, `bin/vibe-web.py`, `bin/vibe_paths.py`, `bin/web/app.js`, `SPEC.md`, `docs/baseline.md`, `docs/trilium-index.md`, `docs/import-manifest.json`, `scripts/setup-vibe.py`, alle 7 geänderten Testdateien).
- Dateien vollständig gelesen: `TICKETS.md` (AP13-Eintrag, Z. 771–776), `SPEC.md`, `bin/vibe_ui_config.py`, `docs/features/AP13.md`, `docs/reviews/AP13-test-agent-report.md`, `tests/unit/test_ap13_network_config.py`, `tests/unit/test_ap13_web_access.py`, `tests/browser/test_ap13_security_ui.py`; gezielt: `bin/vibe` (port_in_use, dashboard_health, cmd_ui), `bin/vibe-web.py` (Guard/Authorized/Login/Security/main).
- Checks with supplied output (vom Koordinator, von mir nicht wiederholt): AP13-Suiten 43/43, 26/26, 7/7; test_vibe_paths+test_web_api_security 54/54; test_f28_pylint_quality 2/2; `verify.sh quick` Exit 0; `verify.sh full` 1632 Tests mit 2 vorbestehenden Fehlschlägen an `e872577` (keine AP13-Regression); Browserstufe der Verify-Kette lief wegen `&&`-Abbruch nicht, Browserabnahme separat 7/7; `check-import-manifest.py` OK (60 Dateien); `check-no-secrets.py` OK.
- Checks not independently run: alle Builds, Tests, Läufe und Skripte — ich habe ausschließlich lesende Git-/Dateizugriffe vorgenommen. Die Rotphase ist nur durch den Testbericht belegt (Quelle im Repo), nicht durch eigene Ausführung.
- Important areas inspected: Session-/Cookie-Management, Login-/Logout-Pfad, Allowlist-Vorprüfung in GET und POST, Host-/Origin-/Sec-Fetch-Site-Prüfung, PBKDF2- und compare_digest-Verwendung, Prioritätskette in `vibe_paths.resolve`/`cmd_ui`, ui.json-Lade-/Speicherpfad, app.js-Anmelde- und Sicherheitskarte, Manifest-/Baseline-Konsistenz, Test-Provenanz und geänderte Baseline-Tests.
- Remaining risks: IPv6-Bindungsfall (Medium) und die dokumentierten Minor-Grenzen; Fehlversuchsbegrenzung bei Kennwort-Anmeldung offen; die Browserstufe der Verify-Kette bleibt separat belegt statt in der Full-Kette.

**Verdict: CHANGES REQUIRED** (1 Medium; nach Behebung des IPv6-Bindungsbefunds und begleitender Minor-Doku ist PASS möglich).
