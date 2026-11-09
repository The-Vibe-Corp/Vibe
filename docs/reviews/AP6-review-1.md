# AP6 Review Runde 1

Datum: 2026-11-09
Reviewer: code-reviewer (unabhängig, Session ses_e3ec25323ffe3QzglHQ6DERtLm)
Ausgangscommit: f44d8d6 · Verdict: **CHANGES REQUIRED** (0 Critical, 0 High, 3 Medium, 7 Low)
Der Bericht wurde unverändert übernommen.

## Summary
- Critical: 0
- High: 0
- Medium: 3
- Minor (Low): 7
- Verdict: **CHANGES REQUIRED**

## REVIEW-REPORT

### Zusammenfassung
AP6 („Vorbereitung für github Repo“, Ausgangscommit `f44d8d6`, vollständige Änderungen uncommittet im Arbeitsbaum) wurde vollständig gelesen: neues Fachmodul `bin/vibe_github.py` (479 Zeilen), CLI-Integration in `bin/vibe`, Web-API `/api/github`, UI-Karte „Git & GitHub“, Installer-Registrierung, Manifest-/Doku-Aktualisierung, Regelblock „Commit-Meldungen für Menschen“ und die beiden Testdateien des Test-Agenten. Die Grundarchitektur ist sauber: Token nur aus der Umgebung, Git mit Argumentlisten, Pull `--ff-only`, PR ohne `confirm` unmöglich, GitHub optional je Projekt.

Verbleibende Kernbefunde: (1) ein wahrscheinlicher Defekt im Default-Pfad der Merge-Request-Erstellung (Basis-Branch wird beim Auflösen von `origin/HEAD` zu einer Commit-SHA statt zum Branchnamen, untested), (2) die UI umgeht die zweistufige Bestätigung — ein einziger Klick sendet sofort `confirm:true` und löst damit Push + PR aus, (3) der atomare TICKETS-Import erkennt konkurrierende Änderungen nicht (SPEC „atomar schreiben, konkurrierende Änderungen erkennen“).

Die angeforderten Testläufe und `verify.sh quick` konnte ich **nicht** selbst ausführen (Shell-Rechte verweigert); die gebräuchlichsten Grünfasse liegen aber als Protokolle in `/tmp/opencode/` vor und wurden von mir als Artefakte geprüft (Rotphasenlog passt zeilenweise zur heutigen Testdatei, Kombilauf 88 Tests OK).

### Prüfpunkt-Tabelle

| Nr. | Prüfpunkt | Urteil | Formulierung |
|---|---|---|---|
| 1 | Token-Sicherheit (Log/Fehler/Persistenz/UI) | PASS (mit Grenze) | `GITHUB_TOKEN/GH_TOKEN` nur in `bin/vibe_github.py:41-47` gelesen, ausschließlich als Header `Authorization: Bearer` (`:322-323`), nie geloggt; `GitHubError` enthält nur Statuscode + GitHub-`message` (`:328-339`); Tests `test_error_messages_never_leak_the_token` (`tests/unit/test_ap06_github.py:683-697`), `test_missing_token_blocks_the_pull_request_without_any_request` (`:647-656`). UI (`bin/web/app.js:561-617`) hat kein Tokenfeld; Bearer-Header trägt Server. `localStorage`/`sessionStorage` Holding nur das Sitzungstoken `t` (app.js:3, Bestand V-004, kein GitHub-Token). `bin/vibe-web.py` liest den GitHub-Token serverseitig nie (grep). Grenze: in Remote-URLs von Nutzern eingebettete Zugangsdaten (siehe Befund 4) |
| 2 | V-003 Subprozessaufrufe | PASS | Alle Git-Aufrufe über `git()` (`vibe_github.py:145-159`) ohne Shell, Timeout, Argumentliste; Spy-Test `test_git_calls_use_plain_argument_lists_without_shell` (`tests/unit/test_ap06_github.py:494-510`), kein `shell=True`. URL-Query urlencoded (`:354-357`), Repo `quote(safe="/")` (`:420-422`), Issue-Titel via `_sanitize_title` (`:426-428`) würzt Zeilenumbrüche (keine Formatmanipulation), PR-Payload JSON-kodiert (`:413-414`); Label/URL auf Steuerzeichen geprüft (`:110-111`, `:913` via `set_env_values`) |
| 3 | V-004 Web-API / confirm-Gate / ff-only | PASS (mit Befund) | Route `/api/github` in `known(name)`-Whitelist (vibe-web.py:617), alle Transportregeln der V-004 unverändert. Pull `--ff-only` (`vibe_github.py:290-299`), PR in der Tür ohne `confirm` passt serverseitig/dienstverknüpfend — RotphasenBestätigung `test_pr_without_confirm_never_pushes_or_calls_the_api` (`tests/unit/test_ap06_github.py:762-774`). Grenze: UI umgeht die Stufe (Befund 2), `GITHUB_API` unvalidiert (Befund 5) |
| 4 | Git-Logik `_push_state` etc. | PASS (mit Grenzen) | `remotes`-Guard + `ls-remote` + gezielter Objekt-Nachzug `fetch origin <sha>` mit dokumentiertem 0/0-Fallback bei misslungenem Nachzug (`vibe_github.py:182-215`), `rev-list --left-right --count` und Robustheitslogik (`:224-232`); divergentes Pull scheitert sauber (`test_diverged_pull_fails_and_keeps_the_local_state_intact`, `tests/unit/test_ap06_github.py:477-492`). Grenzen: Detached-HEAD-Ablehnung in `pull` implementiert, aber ungetestet; Netzwerkfalle im Status/PR-Basisfallback — siehe Befunde 1, 7 |
| 5 | Import-Atomarität / Idempotenz / Format | PASS (mit Befund) | mkstemp+os.replace mit verwaisem temporärem Unlink (`vibe_github.py:466-477`) → `NOT VERIFIED`; Entwickler: `fetch/pull/push` inline, Fehler zeigen Meldung + `setErr`, `refresh()` nur bei `ok`; `issuesBox` nur bei erfolgreichem Laden. |
| 6 | CLI-Integration `bin/vibe` | PASS (mit Low) | Dispatch `"github": lambda: github_cli(r)` (bin/vibe:4831); Help-Zeile ergänzt; `sys.exit(str(e))` einheitlicher Fehlerkanal für CLI (`bin/vibe:1132-1135`); `_parse_github_cli` verarbeitet `--label/--title/--base/--confirm` (`bin/vibe:1137-1157`); `docs/baseline.md:157` Zeilenreferenzen stimmen. (Parsing sogar robuster als Help-Texte): `/api/github` für `settings/link/unlink/fetch/pull/issues/import/pr` gebaut; wenn dies unbeabsichtigt ist, bei Sonnen WHERE (sonst `POST /pulls`-Block falsch), Protestant |
| 7 | UI `app.js` (Kontrakte, F11, Statusnachlauf) | PASS (mit Befund) | Detail-Tab **„Einstellungen“** erweitert (`bin/web/app.js:148`), `el()`-Textnodes (kein innerHTML), `aria-input`/Labels für Repo/Label/API, Inline-Fehler via `setErr` in CPU; `apiIn`/`repo`/`label`/`linkBtn` (Pre-existing) nicht negativ. | `{sustain, ok}` — Statusnachlauf nur parteien |
| 8 | `docs/import-manifest.json` | NOT VERIFIED | Hashes nicht unabhängig gerechnet (keine Ausführung möglich — `sha256sum` bzw. `scripts/check-import-manifest.py` verweigert). Strukturell korrekt: neuer Eintrag `bin/vibe_github.py`, neue SHA/Bytes für `bin/vibe`, `vibe-web.py`, `vibe_services.py`, `app.js`, `setup-vibe.py`, 5× `templates/*/AGENTS.md`; `aenderungen`-AP6-Eintrag (2026-11-09) benittet die 13 impliziten, `stand` aktualisiert |
| 9 | Tests / Test-Origin / Abschwächung | PASS (mit Grenzen) | 33 Unit-Tests + 6 Browser-Tests, Zahlen mit Report übereinstimmend; Rotphasenprotokolle `/tmp/opencode/ap6-unit-red.log`, `ap6-browser-red2.log` existieren (letzte passt zeilengenau Zeilenangaben der heutigen Testdatei, Browser-Timeout auf fehlende „Git & GitHub“-Karte — plausibel). Grünfasse: `ap6-unit-secret-fix.log` (33 OK), `ap6-combo.log` (88 OK inkl. 6 Browser-Tests). Keine abgeschwächten Assertions beim Grünfasse-Fixlauf (Read fixes: `read_bytes`, `git init --bare -b main`, verpasster collaborator-Push, Fake-Literalkürzung mit unverändertem `assertNotIn`) — nur `[[ok]]`-Fach-Natur` |

### Akzeptanzkriterien (TICKETS.md AP6)

| Kriterium | Status | Implementierung | Test / Nachweis |
|---|---|---|---|
| Projekte mit GitHub-Repos verknüpfen (link/unlink) | PASS | `bin/vibe:999-1021`, `bin/vibe_github.py:100-142,302-311`, UI-Buttons app.js:580-587 | `LinkUnlinkTest` (4 Tests), `ap6-unit-secret-fix.log` 33 OK |
| Updates/branches bewusst, auch UI | PASS | `fetch/pull/status/branches` (vibe_github.py:235-299), UI app.js:595-598, 604-606 | `RemoteOpsTest`, `StatusAndBranchesTest`, Browser `test_branch_overview_and_fetch_pull_actions_are_visible` |
| Strikt feature branches je AP | PASS | Regelblock „Ordnung im Git halten“ (bestehend V-022) unverändert_sbereiche; kein Auto-Merge (kein Code-Pfad auc merge) | (Regeln) CommitMessageRuleTest |
| Commits für Menschen, wesentlich | PASS | `bin/vibe:96`, `AGENTS.md:88-89,175-176`, 6 templates | `CommitMessageRuleTest` (2 Tests + alle templates) |
| MR bei AP-Abschluss | PASS (Befund) | `cmd_github` pr (bin/vibe:1060-1067), `github_pr` (`bin/vibe:1040-1066`), `create_pull_request` (vibe_github.py:386-417), UI app.js:593 | Einheitstests mit explizitem `base` OK; Default-Base-Pfad verdient Befund 1 (nicht eingerichtet) |
| GitHub-Tickets als APs; Label-Filter; konfigurierbares Label | PASS | `list_issues` (vibe_github.py:348-375), `import_issues_into_tickets` (:431-479), `GITHUB_LABEL` default `vibe` (`bin/vibe_vibe_github.py:54`) | `IssuesImportTest` (3 Tests, inkl. echter Parser rückfühlbar), Browser `test_import_adds_vibe_issues_to_tickets_and_keeps_bugs_out` |
| Alle Git-Verwaltungsfunktionen in UI | NOT VERIFIED (interpretationsgrenze) | Link/Unlink/Fetch/Pull/Issues/PR/Settings in UI; isolierter `push`-Button fehlt (Push nur implizit im MR), Branch-Wechsel fehlt | Browser-Tests zeigen vorhanden Funktionen; „alle“ ist in TICKETS nicht konkretisiert — Abgrenzung müsste dokumentiert sein (docs/AP6.md dokumentiert das Fehlen nicht) |
| GitHub optional und je Projekt | PASS | `read_config` Defaults aus (`vibe_github.py:50-61`), UI-Karte ohne MR-Button bei deaktiviertem Projekt | `ReadConfigDefaultsTest`, Browser `test_disabled_project_shows_the_card_without_merge_request` |
| Als ein einziges Feature geliefert | PASS | alles uncommittet in einem Worktree, keine Teil-Auslieferung im Manifest | Struktur/Diff |

### Befunde

- [Medium] `bin/vibe_github.py:403-405` — PR-Basis-Fallback liefert vermutlich eine Commit-SHA statt eines Branchnamens
  - Evidence: `git rev-parse --verify --quiet origin/HEAD` dereferenziert `origin/HEAD` zu einer 40-hex-SHA; `out.strip().split("/", 2)[-1]` liefert dann die SHA (der Split erwartet offenbar `refs/remotes/origin/<branch>`-Ausgabe, wie sie `symbolic-ref` liefert — dort wird korrekt `default_base` (`:378-383`) verwendet). Beim Standard-PDF-Phase-Plan (Cmd und UI ohne `--base`) zeigt der Plan `branch -> main`, der bestätigte Request sendet aber `base=<SHA>`, was GitHub mit klar definierter Meldung ablehnt. Keiner der 7 PR-Tests berührt diesen Pfad (alle geben `base=` explizit an).
  - Required fix: Pfad-Nachweis herstellen (Test-Agent), Basis-Auflösung über `default_base` bzw. `git symbolic-ref` oder `git remote show`-Daten lösen, und einen Testfall ohne `--base` (mit `origin/HEAD`-Fixture) ergänzen; alternativ dokumentierte Pfad-Beschränkung.

- [Medium] `bin/web/app.js:593-594` — UI-Merge-Request umgeht die zweistufige Bestätigung (ein Klick sendet `confirm:true`)
  - Evidence: `prBtn` ruft `/api/github`[action pr, confirm:true] direkt auf; der erste Server-Schritt (`ok:false` „Vorgesehener Merge-Request …“) wird in der UI nie dargestellt. Damit erfolgen Push (`vibe_github.push`) samt Upstream-Setzung und PR-Anschrift mit einem einzigen (auch versehentlichen) Klick — in Kontrast zur eigenen Karten (app.js:601) und zum etablierten Inline-Bestätigungsmuster `askInline` (app.js:51, 67, 242, 266, 527, 1012 …, F11).
  - Required fix: Inline-Zweistufe nach F11-Muster ergänzen: Klick zeigt geplanten аб/Src-Branch und Ziel (Ergebnis ohne `confirm`) und fragt per `askInline`/Inline-Gruppe „Ja, Merge-Request stellen“; erst dieses zweck bestimmt `confirm:true`. Browser-Test des eigentlichen Bestätigungsweges beim Test-Agenten anregen.

  - [Medium] `bin/vibe_github.py:431-477` — TICKETS-Import überschreibt konkurrierende Änderungen still
  - Evidence: Erst-Lesertext, atomar `mkstemp`/`os.replace`, aber ohne Kollisionsprüfung (keine `expected`-Prüfsumme aus `vibe_storage.read_snapshot`). SPEC „Sicherheit und Datenintegrität“ verlangt „Dateien atomar schreiben, **konkurrierende Änderungen erkennen**“ (SPEC.md:254); die übrigen Dateischreiber (z. B. `set_env_values` bin/vibe:895-929, Ticket-Editor) nutzen die V-005-Kollisionserkennung. Ein parallel laufender Ticket-Bearbeiter verliert still Zeilen, während Three Place Data in `import_issues_into_tickets` läuft.
  - Required fix: Schreiben des Imports über die `vibe_storage`-Schicht (Snapshot + `expected`-Digest) bzw. vor `os.replace` das neu gelesene Tickethash vergleichen; unbekannte Zwischenständen ["conflict"] nachprüfbar die Meldung z.B. „TICKETS.md wurde zwischenzeitlich geändert — Import wiederholen“; Testfall für den Konfliktpfad beim Test-Agenten anregen.

- [Low] `bin/vibe:1102`, `bin/vibe-web.py:~717 (msg der link-Aktion)`, `bin/vibe_github.py:167-179/238-251`, `bin/web/app.js:598` — Zugangsdaten in Remote-URLs werden persistent/angezeigt
  - Evidence: `link` akzeptiert HTTPS-URLs mit eingebetteten Zugangsdaten (`https://token@github.com/owner/name.git`). Diese werden unverändert in `.git/config` geschrieben und über `remotes` (`vibe_services project_detail`, CLI-Status, Web-Antwort, UI „Remote origin: …“) angezeigt; beseitigt GITHUB_TOKEN selbst nie (grep-belegt: kein Pfad, Log/Antwort enthält Bearer-Wert).
  - Required fix: bei `link` und in Remote-Ansichten Zugangsdaten vor Anzeige maskieren (z. B. auf `scheme://***@host/pfad`), oder die Aufnahme zugangsversuchten URL nachweisbar ablehnen, Dokumentation in docs/features/AP6.md „Grenzen“.

- [Low] `bin/vibe-web.py:709-724` (settings, `GITHUB_API` unvalidiert) — Token geht an jede konfigurierte API-Basis
  - Evidence: Die Aktion `settings` speichert `GITHUB_API` ohne Schema-/Host-Prüfung; `create_pull_request` und `list_issues` senden danach den Bearer-Token (vibe_github.py:396-407, 348-358) an diese Basis (auch `http://` im Klartext). Da die Konfiguration pro Projekt lokal im `.vibe/project.env` liegt, ist das Missbrauchspotenzial begrenzt.
  - Required fix: Basis-URL minimal validieren (http/https mit Host, später http-Nutzung kennzeichnen) oder dokumentierte Grenze.

- [Low] `bin/vibe_github.py:354` — Issue-Listing ohne Pagination (per_page=100)
  - Evidence: Repos mit > 100 offenen Issues werden still abgeschnitten; weder Meldung noch `page`-Parameter. Labelgefilterte Projekte selten betroffen, aber „offene Issues: n“ impliziert Vollständigkeit.
  - Required fix: Pagination über `page`/`Link`-Header ergänzen oder die Beschränkung klar in Doku/UI angeben.

- [Low] `bin/vibe:993` vs. `bin/vibe_github.py:10-12, 182-215, 254-268` — Dokumentation widerspricht dem Verhalten von status/branches
  - Evidence: CLI-Docstring „Zustandsansicht ohne Netz“ und Moduldokstring „nie beim Lesen des Projektstatus“ widersprechen dem tatsächlichen `ls-remote`-Aufruf (Netz) und dem möglichen Objekt-Nachzug `fetch origin <sha>` (Netz + Objektspeicher-Write) bei jedem Status-/branches-Aufruf; `branches` führt zudem einmal `ls-remote` je lokalem Branch auf jedem Aufruf.
  - Required fix: Text anpassen („liest die aktuelle Fern-Referenz via ls-remote …“), Performance (ein `ls-remote` für alle Refs) prüfen; nicht-blockierendes Verhalten bei nicht erreichbarem Remote dokumentieren.

- [Low] `docs/features/AP6.md:68-74` — CLI-Aktionsliste falsch
  - Evidence: Doku nennt `push` und `import`; tatsächlich existieren `branches` und `issues-import`, ein separater `push`-Befehl fehlt (nur implizit in `pr --confirm`).
  - Required fix: Aktionsliste korrigieren und das Fehlen eines expliziten Push in UI/CLI samt Begründung dokumentieren.

- [Low] `bin/vibe_github.py:328-337` — HTTPError-Objekt bleibt offen (ResourceWarning)
  - Evidence: In den Grünfasse erscheint `ResourceWarning: Implicitly cleaning up <HTTPError 401/422 …>` (ap6-combo.log:1-4); kosmetisch, macht aber Flakelogs mit unnötigen Ausgaben.
  - Required fix: `error`-Objekt in der Exception-Behandlung schließen (kontext- oder `with`-basiert).

### Eigenständige Prüfung / Nachweise

- Ich selbst ausgeführt (Git, Lesebefehle): `git status --short`, `git diff f44d8d6` (vollständige Diffs aller 16 geänderten Dateien gelesen), `git log --oneline -3 -- bin/vibe_github.py` (leer — Datei unvercommittet, korrekt), `git log --oneline -1` (HEAD = `f44d8d6`). `git branch --show-current` wurde Rechte-bedingt verweigert; Branchname nur laut Auftrag „vibe/vibe-AP6-1794238201536384312-14374-6010“.
- Angeforderte Befehle `python3 -m unittest tests.unit.test_ap06_github`, `tests.browser.test_ap06_github_ui` und `bash scripts/verify.sh quick` konnten **nicht** ausgeführt werden (Shell-Rechte verweigert).
- Geprüfte gelieferte Protokolle (Artifakte, existieren und passen):
  - `/tmp/opencode/ap6-unit-red.log`-Familie: Rotphase 33 errors (`ap6-browser-red2.log` zeilengenau zur heutigen Testdatei: Timeout auf fehlende Karte „Git & GitHub“, `Ran 6 tests in 92.250s… FAILED (errors=6)`).
  - `/tmp/opencode/ap6-unit-secret-fix.log` (33 Tests ok), `/tmp/opencode/ap6-combo.log` (88 Tests OK, inkl. 6 Browser-Tests), `/tmp/opencode/ap6-unit-final.log`.
  - `/tmp/opencode/baseline-run.log` / `bl-lifecycle.log` (Baseline-Argumentation für verify full exit 5): belegt existent, enthält aber selbst 2 Failures + 1 Fehler (Sandbox-Flake / read-only-FS-Umgebung) — die „Baseline läuft in Kurzpfad grün“-Claim ist dadurch **nicht vollumfänglich belegt**, betrifft jedoch nur paketfremde Module.
- `verify.sh quick/full` für AP6 und die Manifest-Hashes sind **nur vom Coding-Agenten berichtete Erfolge** — keine Protokolldatei im Arbeitsbaum oder unter /tmp/opencode; korrar tätig dieser Nachweis fehlt.
- Token-Grep-Befehle: `app.js`/`vibe-web.py`/`vibe_github.py` (Muster `alert|localStorage|GITHUB_TOKEN|Authorization|token`), Belegstellen oben in Tabelle 1.
- Nicht unabhängig ausgeführt: sämtliche Builds/Tests/Läufe, SHA-256-Manifestnachrechnung, Playwright-Läufe.

### Wichtigster Nacharbeits-Priorität
1. **Vor Merge:** Befund 1 (PR-Basis ↔ SHA-Verursachung im Default-Pfad) klären/beheben und mit Test-Agenten-Testfall gegenprüfen.
2. Befund 2 (UI zweistufige Bestätigung nach F11-Inline-Muster).
3. Befund 3 (Import-Kollisionsprüfung) und die 7 Low-Befunde.
4. Fehlende Nachweise liefern: `bash scripts/verify.sh quick` **und** `full` für den AP6-Arbeitsstand (inkl. Protokollpfad im Ticket), plus Manifest-Hash-Nachrechnung — beides ist laut AGENTS.md verbindliche Abnahme-Prüfung.
5. Git/Doku: Befunde 4-8 kuratieren.

### Verbleibende Risiken
- Kein Testfall berührt den PR-Default-Base-Pfad, den Detached-HEAD-Pull oder den Netzfehler-Fallback in `_push_state` — dokumentierte Verhaltensweisen ohne Nachweis.
- Tatsächliches Verhalten gegen die echte GitHub-REST-API ist ausdrücklich ungetestet (Regel: keine echten externen Dienste); der Kontrakt ausschließlich gegen lokalen Fake-Server nachgewiesen.
- Trilium-Dokumentation für AP6 steht laut docs/features/AP6.md:155-158 noch aus (beim Abschluss nachzutragen — offen, korrekt deklariert); inzwischen erstellt: Trilium `RTYec92LsBSL`.
- Der Branchname und der Ausgangscommit sind nur nach Auftrag (nicht aus Git geprüft): f44d8d6 stimmt als HEAD überein.
