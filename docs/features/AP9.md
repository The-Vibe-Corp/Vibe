# AP9 — Bereit für GitHub Teil 3: Token je Projekt, Branch-Kontrolle, automatischer Merge-Request

Stand: 2026-11-11
Ticket: TICKETS.md AP9 („github tokens müssen je projekt gespeichert werden.
github tokens sollten verschlüsselt gespeichert werden. github funktionalität
ungenügend. ich benötige mehr kontrolle, welchen branch möchte ich auschecken,
in welchen branch möchte ich pushen. weiterhin soll automatisch mit jedem ap
ein neuer feature branch angelegt werden und nur in diesem gearbeitet werden.
nach abschluss eines jeden AP soll automatisch (sofern github konfiguriert ist)
ein merge request auf den main branch gestellt werden. die entwicklung basiert
immer gegen den main branch, außer es gibt abhängigkeiten zwischen den
arbeitspaketen. vor jeden neuen ap soll der haupt branch aktualisiert werden
(pull). die ui benötigt feedback, ob die verbindungen funktionieren.“)
Arbeitsbranch: `vibe/vibe-AP9-1794355960880323502-2529435-4459`
Ausgangscommit: `4b51ae4` (AP8)

## Ziel

GitHub-Arbeit wird pro Projekt abgesichert und automatisiert: Zugangsdaten
liegen verschlüsselt je Projekt, Branch-Wechsel und Push-Ziele sind bewusst
steuerbar, der Läufer zieht vor jedem Arbeitspaket den Haupt-Branch und stellt
nach dem Abschluss automatisch Push und Merge-Request. Die Oberfläche meldet,
ob die Verbindungen wirklich funktionieren.

## Token je Projekt, verschlüsselt (bin/vibe_github.py)

- Ablage: `<VIBE_STATE>/github-tokens/<sha256(realpath)[:16]>.json` (0600,
  Ordner 0700). Der Masterschlüssel `<VIBE_STATE>/github-token.key` (32
  Zufallsbytes, 0600) wird einmalig erzeugt und nie gedreht; eine falsche
  Länge gilt als beschädigt — Speichern lehnt ab, Lesen liefert Leerwert.
- Verschlüsselung nur mit der Standardbibliothek: scrypt (n=2¹⁴, r=8, p=1)
  als Schlüsselableitung, HMAC-SHA256-Strom als CTR-artige Verschlüsselung,
  Encrypt-then-MAC (Tag über Nichtsec + Ciphertext). Defekte oder
  manipulierte Dateien liefern beim Lesen den Leerwert statt einer Ausnahme
  und niemals Klartext.
- Präzedenz überall gleich: Umgebung (`GITHUB_TOKEN`/`GH_TOKEN`) >
  Projekt-Token > legacy globaler B7-Speicher (Rückfall).
- Tokeninhalt erscheint nie in argv, Logs oder Antworten: Die Credential-
  Konfiguration (`credential.https://github.com.helper=…`) liegt als
  URL-gültiges `-c`-Argument vor dem festen Git-Präfix; der Tokeninhalt wird
  über die Prozessumgebung (`VIBE_GITHUB_CREDENTIAL`) eingespeist.
  `token_for_rest` reicht den Projekt-Token nur an die offizielle
  api.github.com (oder die konfigurierte API-Basis); Umgebungstoken gelten
  überall.
- B7-Migration (mit dem Test-Agenten entschieden): Die Webaktion
  `token.save`/`token.clear` wirkt je Projekt; die frühere globale Datei
  wird nicht mehr erzeugt, der alte Speicher bleibt als Rückfall lesbar
  (`source: "gespeichert"`). Die B7-Tests wurden auf den neuen Vertrag
  umgestellt, ohne die Legacy-Prüfungen abzuschwächen.

## Branch-Kontrolle

- `checkout_branch(project, branch)`: ungültige Namen (`branch_name`-
  Validator) werden vor jedem Git-Aufruf abgelehnt; uncommittete Änderungen
  an getrackten Dateien verweigern den Wechsel, ungetrackte Dateien blockieren
  bewusst nicht; lokal vorhanden → Checkout, sonst wird er aus
  `origin/<branch>` als neuer lokaler Branch erzeugt; bereits ausgecheckt ist
  Erfolg ohne Aktion.
- `push(project, branch, target)`: Push mit Upstream; mit `target` als
  Refspec `<branch>:<target>` (lokaler Branch landet unter dem Zielnamen auf
  origin, ohne einen gleichnamigen Fern-Branch zu berühren).
- CLI: `vibe github checkout <branch>`, `vibe github push <branch>`,
  `vibe github pr --branch <b>`, `vibe clone --branch <b>`; Webaktion
  `checkout` und `push` mit `branch`/`target`.
- Karte „Git & GitHub“: Jede Branch-Zeile bietet „Wechseln“ und „Push“;
  Toasts melden Erfolg („Branch … ausgecheckt“/„… nach origin übertragen“),
  Fehler landen dauerhaft in der Fehlerbox.

## Verbindungsfeedback

- `connection(project)`: prüft die Fernseite (`ls-remote origin`, kurzes
  Zeitlimit, keine Merge-Aktion) und — mit Token und nur für die offizielle
  API bzw. konfigurierte Basis — den GitHub-REST (`GET /repos/<repo>`).
  Wirft niemals; das Ergebnis (`ok`, `message`, Teilergebnisse) wird in der
  Karte als dauerhafte Zeile angezeigt: Knopf „Verbindung testen“, Zeile mit
  ok/fehler-Kennung (`Verbindung: OK/FEHLER — <Meldung>`). Bei einer
  fremden API-Basis wird ohne Auth geprüft und das ehrlich in der Meldung
  benannt.

## Basis-Branch für Merge-Requests (GITHUB_BASE)

- Neuer Konfigurationsschlüssel `GITHUB_BASE` in `.vibe/project.env`
  (Feld „Basis-Branch für Merge-Requests“ in der Karte, Leerwert =
  Standard-Branch der origin). Die Validierung teilt sich mit
  checkout/push (`branch_name`).
- Auflösung der Request-Basis: explizit > `GITHUB_BASE` > `origin/HEAD`.

## Läufer-Automatik (bin/vibe-run.sh, bin/vibe_packages.py, bin/vibe_github.py)

- Feature-Branch je Arbeitspaket und Arbeit nur darin: bereits durch die
  AP5-Worktree-Isolation gegeben (create_worktree mit eigenem Branch);
  dokumentiert, nicht neu gebaut.
- Vor jedem neuen Arbeitspaket ruft der Läufer
  `python3 bin/vibe_packages.py github-pull --project <P>` auf —
  `pull_integration(project)`: nur bei `GITHUB_ENABLED=1` und vorhandenem
  origin, sonst bewusster Skip (Exit 0). Ausgeführt wird `git fetch --quiet
  origin` + `git merge --ff-only origin/<branch>` — der Refspec ist
  ausdrücklich, damit keine Upstream-Konfiguration Voraussetzung ist. Ein
  Fehlschlag (z. B. Divergenz, Exit 1) erzeugt einen HINWEIS und blockiert
  das Paket nicht.
- Nach grüner Abschlussschranke, vor dem lokalen Merge:
  `github-complete --project <P> --branch <B> --id <ID>` —
  `complete_package(...)`: Push des Paket-Branchs mit Upstream, dann
  automatischer Merge-Request auf die aufgelöste Basis. Ein Fehlschlag
  (z. B. abgelehnter Request, kein Token) ist ein HINWEIS; der lokale
  Merge läuft weiter, damit das Paket nicht an GitHub hängt.
- Beide Subkommandos beenden sich mit 0 bei Erfolg/Skip und 1 bei
  Fehlschlag; Meldungen auf stdout/stderr. Die GitHub-Ebene wird träge
  geladen (`_github_module`), damit Teilinstallationen ohne
  `vibe_github.py` die übrigen Subkommandos (gate, select, copy-notes)
  unberührt lassen.

## Grenzen

- **SPEC-Konflikt, erläutert:** SPEC.md stellt „Automatische
  Veröffentlichung, Push, Merge oder Release ohne Freigabe" außerhalb des
  Umfangs; AP9/TICKETS verlangt ausdrücklich automatischen Push und
  Merge-Request nach jedem Arbeitspaket. Auslegung (in Absprache mit dem
  Ticket): Die ausdrückliche, persistente Konfiguration `GITHUB_ENABLED=1`
  in der project.env gilt als stehende Freigabe für Push und
  Merge-Request; das Zusammenführen (Merge) bleibt manuell. Ohne diese
  Konfiguration passiert nichts automatisch (bewusster Skip).
- Kein echtes Netz in Tests: Git läuft gegen `file://`-Bare-Repositories,
  REST gegen lokale Fakes auf 127.0.0.1; github.com wird nie berührt.
- Der Merge-Request wird nur gestellt, sofern GitHub konfiguriert ist; ohne
  Token meldet die API den Versuch ehrlich als abgelehnt (kein Stilllegen
  der Pflicht).
- `pull_integration` verweigert bei divergiertem Haupt-Branch bewusst
  (ff-only, kein Merge-Commit); der Läufer arbeitet dann mit dem lokalen
  Stand weiter und meldet den Hinweis.
- Legacy-globale Token werden nur an die offizielle GitHub-API bzw. den
  Git-Host github.com gereicht (B7-Vertrag bleibt).
- Die scrypt-Ableitung des Projekt-Tokens läuft bei jedem Git-Aufruf neu
  (Dateilesen + n=2¹⁴). Ein Zwischenspeichern des abgeleiteten Materials
  wurde bewusst unterlassen: Projektregeln erlauben Caching nur mit
  benannter Invalidierung, und Geheimnis-Material wird nicht ungeprüft
  zwischengespeichert. Der Aufwand ist pro Aufruf gering und wird als
  akzeptierter Kompromiss dokumentiert.

## Prüfungen (tatsächlich ausgeführt)

- Unit: `tests/unit/test_ap9_github.py` — 44/44 OK (Test-Agent), enthält
  Token-Verschlüsselung, Präzedenz, Checkout/Push-Regeln, Verbindungsprüfung,
  Credential-Routing und CLI-Verträge.
- Unit: `tests/unit/test_ap9_runner_github.py` — 17/17 OK (Skip, Erfolg,
  Divergenz-Fehler, Exitcodes der Subkommandos).
- Unit (Migration): `tests/unit/test_b7_github_auth.py` — 31/31 OK;
  `tests/unit/test_ap8_github_checkout.py` — 33/33 OK.
- Browser: `tests/browser/test_ap9_github_ui.py` — 5/5 OK (echtes Dashboard,
  Chromium headless): Verbindungstest mit ok/fehler-Kennung, Token-Zeile
  „für dieses Projekt gespeichert (verschlüsselt)“ ohne Token-Leck,
  Wechseln/Push je Branch-Zeile (wirklich verifiziert: HEAD-Wechsel und
  Fern-Ref), Basis-Branch-Feld persistiert `GITHUB_BASE`.
- Browser (Migration): `tests/browser/test_b7_github_auth_ui.py` — 7/7 OK.
- `bash scripts/verify.sh quick` — OK (Manifest 57 Dateien, Syntax, keine
  Geheimnisse).
- `bash scripts/verify.sh full` — 1460 Tests; die verbleibenden Fehlschläge
  (`test_dry_run_explains_pi_and_its_install_command`,
  `test_other_findings_block_even_with_keep_changes`,
  `test_repository_content_has_no_personal_home_paths_or_secrets`)
  treten am Ausgangscommit `4b51ae4` in identischer Form auf (Baseline,
  paketfremd); ein Abgleich der Fehlschlagslisten zeigt keine neuen
  Fehlschläge gegenüber dem Ausgangsstand.

## Testherkunft

- Alle AP9-Tests stammen vom unabhängigen Test-Agenten (Konfiguration
  `TESTER=test-agent`): Rotphase vor der Implementierung, danach Korrektur-
  läufe an seinen eigenen Testdefekten (untracked-vs-tracked Dirty-Check,
  CompletedProcess-Auswertung, ls-remote-Einschränkung, seed-Remote,
  zu früh gelesener Sollwert, Browser-Race beim Verbindungstest,
  zugeklapptes Branch-Details) und an Implementierungsbefunden
  (expliziter Pull-Refspec). Die Coding-Seite hat keine Testdatei
  erstellt, geändert oder abgeschwächt; die B7-Migration hat der
  Test-Agent entschieden und durchgeführt.

## Nachweise

- Manifest: `docs/import-manifest.json` (Stand 2026-11-11) — SHA-256/Größe
  von `bin/vibe`, `bin/vibe-run.sh`, `bin/vibe-web.py`, `bin/vibe_github.py`,
  `bin/vibe_packages.py`, `bin/web/app.js` aktualisiert;
  `python3 scripts/check-import-manifest.py` OK.
- Bestandsaufnahme: `docs/baseline.md` — Zeilen `vibe github` und
  `POST /api/github` um die AP9-Aktionen ergänzt; `tests/unit/
  test_baseline_inventory.py` 8/8 OK.
- Review: `docs/reviews/AP9-review-*.md` (unabhängiger Reviewer).
- Trilium: Notiz „AP9 — GitHub-Token je Projekt, Branch-Kontrolle,
  Merge-Request-Automatik“ (über Trilium-MCP angelegt).
