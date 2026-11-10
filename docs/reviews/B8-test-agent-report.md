# B8 — Testbericht des Test-Agenten

Datum: 2026-11-10
Repository: `/run/host/var/mnt/data/Dokumente/Informatik/VibeCode/vibe`
Branch: `feature/b8-projekt-oeffnen-ohne-remote`
Ausgangsstand: `bea4275`
Ticket: B8 „Projekt öffnen blockiert bei nicht erreichbarem Git-Remote“
(`FEEDBACK.md`), Kriterien zusätzlich aus `SPEC.md` (Abschnitt „Qualität und
Abnahme“) und `AGENTS.md`.

## 0. Herkunft und Umfang dieses Berichts

Beide B8-Testdateien wurden vom Test-Agenten geschrieben:

* `tests/unit/test_b8_no_remote_block.py` — 13 Tests. In einer früheren
  Test-Agenten-Sitzung vor der Implementierung geschrieben; der
  Rotphasenlauf ist in `docs/features/B8.md:65–71` dokumentiert.
* `tests/unit/test_b8_project_open_without_remote.py` — 4 Tests. Ebenfalls
  vom Test-Agenten in einer früheren Sitzung geschrieben und mit Commit
  `bea4275` versioniert. Für diese Suite existiert **kein separater
  Rotphasenlauf**; das wird in Abschnitt 5 ausdrücklich als Lücke vermerkt
  und nicht durch eine Behauptung ersetzt.

In der vorliegenden Sitzung habe ich (Test-Agent):

1. beide Suiten unabhängig gelesen,
2. die Minor-Anforderung aus `docs/reviews/B8-review-3.md` umgesetzt und
   ausschließlich die ENV-Isolation der 4er-Suite an die etablierte
   `B8Case`-Isolation der 13er-Suite angeglichen (keine Assertion geändert,
   kein Test gelöscht oder abgeschwächt),
3. beide Suiten tatsächlich ausgeführt und die echten Ausgaben unten
   übernommen.

Prüfsummen der geprüften Dateien nach dieser Sitzung:

```
60a11afdfd261f4c14ad52a623ce5f803387597e57591fd3ec3848801f0f8295  tests/unit/test_b8_no_remote_block.py
04e933bcd07d69525c1eaaa8fb21fb8559555a2dbd3fe79c6a9871c16fc24f71  tests/unit/test_b8_project_open_without_remote.py
```

`tests/unit/test_b8_no_remote_block.py` ist in dieser Sitzung nicht geändert
worden. Die 4er-Suite hat gegenüber `bea4275` ausschließlich die zusätzliche
ENV-Isolation (+59 Zeilen); alle vier Testmethoden und ihre Assertions sind
inhaltlich unverändert.

## 1. Ableitung der Testfälle

Die Fälle sind aus dem Tickettext B8, dem Symptom (blockierte Projektansicht
bei unerreichbarem `origin`) und `SPEC.md` abgeleitet, nicht aus dem
Implementierungsdiff.

Akzeptanzkriterien des Arbeitspakets:

* **AC1 / AK1** — Die Projektansicht (`vibe_services.project_detail`,
  `GET /api/project`) fragt das Git-Remote nicht an. Ahead/Behind stammt aus
  der lokalen `origin/<branch>`-Referenz; `status(remote=False)` und
  `branches(remote=False)` lösen kein `ls-remote`/`fetch` aus.
* **AC2 / AK3** — Ohne aktivierte GitHub-Verknüpfung (`GITHUB_ENABLED`
  fehlt) wird auch im Normalmodus (`remote=True`) kein Remote kontaktiert.
* **AC3** — Reine Fern-Leseabfragen sind auf 10 Sekunden begrenzt; bewusste
  Aktionen `fetch`/`pull`/`push` behalten 120 Sekunden.
* **AC4** — Git läuft ohne Terminal-Prompt (`GIT_TERMINAL_PROMPT=0`,
  `GCM_INTERACTIVE=never`), unabhängig vom Token; der Tokeninhalt erscheint
  nie in `argv`.

`SPEC.md` („Qualität und Abnahme“) verlangt zusätzlich temporäre
HOME-/VIBE-Verzeichnisse, keine Tests gegen produktive Konfigurationen und
Testprotokolle mit Befehl, Ergebnis und Grenzen. Beides wird unten belegt
bzw. als Grenze benannt.

## 2. Testdateien

| Datei | Testfälle | Stand |
|---|---|---|
| `tests/unit/test_b8_no_remote_block.py` | 13 | unverändert |
| `tests/unit/test_b8_project_open_without_remote.py` | 4 | nur ENV-Isolation ergänzt |

## 3. Testfälle

### 3.1 `tests/unit/test_b8_no_remote_block.py` (13 Tests)

Gemeinsame Vorbedingung der Klasse `B8Case`: temporäre Wurzel mit eigenem
`ws`, `home`, `state`, `runtime` und `install`; `VIBE`, `HOME`, `VIBE_STATE`,
`VIBE_RUNTIME`, `VIBE_INSTALL`, `VIBE_AGENTS_DIR` überschrieben;
`GITHUB_TOKEN`, `GH_TOKEN`, Askpass-/Proxy-Variablen entfernt;
`GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` auf `os.devnull`; echte
Git-Repositories mit fester Testidentität. Fernadressen lauschen
ausschließlich auf `127.0.0.1` (hängender `git://`-Dienst bzw.
401-HTTP-Dienst) oder sind lokale `file://`-Repos.

| # | Testname | Kriterium | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 1 | `StatusLocalRefsTest.test_status_liesst_ahead_behind_nur_aus_lokalen_referenzen` | AC1 | Bare-Repo als `origin`, Projekt gepusht, danach ein lokaler Commit; zusätzlich ferne Arbeit im Bare-Repo, die das Projekt nicht abruft; `GITHUB_ENABLED=1`. | `status(project, remote=False)` vor und nach der fernen Arbeit. | Erster Aufruf `unpushed=False`; danach `branch=main`, `(ahead, behind)=(1, 0)`, `unpushed=True`; auch nach fremdem Push bleibt `(1, 0)` — es wurde nur die lokale Referenz gelesen. |
| 2 | `StatusLocalRefsTest.test_status_remote_false_wartet_nicht_auf_haengendes_remote` | AC1 | `origin` zeigt auf hängenden lokalen `git://`-Dienst; `GITHUB_ENABLED=1`. | `status(project, remote=False)` mit Zeitmessung. | Laufzeit < 5 s; `(ahead, behind)=(0, 0)`; der Fake-Dienst wurde 0-mal kontaktiert. |
| 3 | `StatusLocalRefsTest.test_branches_remote_false_bleibt_fernfrei_und_vollstaendig` | AC1 | Wie Fall 2; `subprocess.run` protokolliert argv/Timeout/env, führt aber echt aus. | `branches(project, remote=False)`. | Laufzeit < 5 s; `main` enthalten und als aktuell markiert; `ahead`/`behind` sind `int`; keine Netzwerk-Git-Verben (`ls-remote`/`fetch`/`pull`/`push`) im Protokoll; 0 Kontakte am Fake-Dienst. |
| 4 | `ProjectDetailLocalModeTest.test_project_detail_fragt_origin_trotz_github_enabled_nicht_an` | AC1 | Echtes CLI-/Services-Modul, `origin` auf lokales Bare-Repo, ein lokaler Commit voraus, `GITHUB_ENABLED=1`; `subprocess.run`-Spy. | `vibe_services.project_detail(cli, paths, "proj")`. | Keine Netzwerk-Git-Verben im Protokoll; `github["branches"]` enthält `main` mit `int`-Abständen; `unpushed=True`; `enabled=True` — der Lokalmodus ist der Aufrufort, nicht die Konfiguration. |
| 5 | `ProjectDetailLocalModeTest.test_project_detail_ohne_git_remote_bewahrt_die_karte` | AC1 | Projekt ohne Git-Remote, `GITHUB_ENABLED` fehlt. | `project_detail(...)`. | Karte bleibt erhalten: `main` in der Branchliste, `enabled=False`, `(ahead, behind)=(0, 0)`. |
| 6 | `ApiProjectBlockingTest.test_api_project_antwortet_ohne_fernkontakt_bei_haengendem_remote` | AC1 (Ende-zu-Ende) | Echte `vibe-web.py`-Instanz auf freiem `127.0.0.1`-Port, hängender `git://`-Fake als `origin`, Projekt mit `GITHUB_ENABLED=1`, Token-Datei im isolierten Runtime-Ordner. | `GET /api/project?name=proj` mit Token. | HTTP 200; Antwort < 40 s (nicht das 120-s-Git-Limit); `github["branches"]` ist eine Liste; `branch=main`; 0 Verbindungen am Fake-Dienst. |
| 7 | `NoRemoteWithoutGithubTest.test_status_ohne_github_enabled_kontaktiert_nicht_den_ferndienst` | AC2 | Projekt ohne `GITHUB_ENABLED`, `origin` auf hängenden Fake; Spy aktiv. | `status(project)` — also `remote=True` (Normalmodus). | Keine Netzwerk-Git-Verben; 0 Kontakte; `enabled=False`; `(ahead, behind)=(0, 0)`. |
| 8 | `NoRemoteWithoutGithubTest.test_branches_ohne_github_enabled_bleibt_fernfrei` | AC2 | Wie Fall 7. | `branches(project)` — `remote=True`. | Keine Netzwerk-Git-Verben; 0 Kontakte; `main` in der Branchliste. |
| 9 | `RemoteReadTimeoutTest.test_reine_fernleseabfrage_grenzt_auf_10_sekunden` | AC3 | `GITHUB_ENABLED=1`, `origin` hängt schweigend; Spy aktiv. | `status(project, remote=True)` mit Zeitmessung. | `ls-remote` wurde versucht; Laufzeit ≥ 9 s und < 40 s (also ~10 s statt 120 s); `(ahead, behind)=(0, 0)` bei Fernausfall. |
| 10 | `RemoteReadTimeoutTest.test_fetch_pull_push_behalten_120_sekunden_zeitlimit` | AC3 | Projekt ohne GitHub, `origin` auf nicht existierendes `file://`-Ziel; Spy aktiv. | `fetch`, `pull`, `push` nacheinander. | Alle drei liefern `False`; jeder Aufruf lief mit `timeout=120`; `TIMEOUT_REMOTE_READ == 10`, `TIMEOUT_GIT == 120`. |
| 11 | `PromptFreeGitTest.test_git_aufrufe_sind_stets_ohne_terminal_prompt` | AC4 | Projekt mit `GITHUB_ENABLED=1`; Spy aktiv. | `status(project, remote=True)`. | Mindestens ein Git-Aufruf; jeder Aufruf trägt `GIT_TERMINAL_PROMPT=0` und `GCM_INTERACTIVE=never`. |
| 12 | `PromptFreeGitTest.test_git_aufrufe_bleiben_promptfrei_auch_mit_token` | AC4 | Wie Fall 11, zusätzlich gespeicherter Token und `GITHUB_TOKEN` in der Umgebung; Aufräumen des Tokens als Cleanup. | `status(project, remote=True)`. | Aufrufe vorhanden und promptfrei; weder gespeicherter noch Umgebungs-Token erscheinen in `argv`. |
| 13 | `PromptFreeGitTest.test_http_remote_mit_auth_forderung_blockiert_nicht` | AC4 | Lokaler HTTP-Dienst, der auf jeden Abruf 401 mit `WWW-Authenticate` antwortet; `GITHUB_ENABLED=1`. | `status(project, remote=True)` mit Zeitmessung. | Mindestens ein Kontaktversuch fand statt; Laufzeit < 40 s; Netzwerkaufrufe promptfrei; `(ahead, behind)=(0, 0)`. |

### 3.2 `tests/unit/test_b8_project_open_without_remote.py` (4 Tests)

Gemeinsame Vorbedingung (nach der Isolation dieser Sitzung): echtes
temporäres Git-Repo mit `origin` auf die nicht erreichbare TEST-NET-1-Adresse
`https://192.0.2.1/b8/nie-erreichbar.git`, lokale
`refs/remotes/origin/main`- und `refs/remotes/origin/feature`-Referenzen;
temporäres `HOME`, `VIBE_STATE`, `VIBE_RUNTIME`, `VIBE_INSTALL`,
`VIBE_AGENTS_DIR`; `XDG_CONFIG_HOME`/`XDG_STATE_HOME`/`XDG_CACHE_HOME`/
`XDG_DATA_HOME` im temporären Home; Zugangsdaten- und Proxy-Variablen
entfernt. Der Wrapper `no_network_git` lässt ausschließlich `ls-remote` und
`fetch` sofort fehlschlagen und protokolliert sie; alle übrigen Git-Aufrufe
gehen unverändert an das echte Git.

| # | Testname | Kriterium | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 1 | `ProjectWithoutReachableOrigin.test_project_detail_does_not_touch_unreachable_origin` | AK1 | Repo mit unerreichbarem `origin`, lokaler `origin/main`-Referenz, einem lokalen Commit voraus, `GITHUB_ENABLED=1`; `StubVibe` liefert nur nicht getestete CLI-Ansichten. | `project_detail(vibe, paths, "proj")` unter Netzwerk-Sperre, mit Zeitmessung. | Kein `ls-remote`/`fetch`; Laufzeit < 5 s; kein `error` in der GitHub-Ansicht; `branch=main`, `(ahead, behind)=(1, 0)`; Remotes genau `["origin"]`; Branches `{main, feature, local-only}`. |
| 2 | `ProjectWithoutReachableOrigin.test_status_offline_uses_local_origin_refs` | AK2 | Wie oben. | `status(path, remote=False)` unter Netzwerk-Sperre. | Kein `ls-remote`/`fetch`; `enabled=True`; `branch=main`; `(ahead, behind)=(1, 0)`; `unpushed=True`; Remotes genau `["origin"]`. |
| 3 | `ProjectWithoutReachableOrigin.test_branches_offline_uses_local_origin_refs` | AK2 | `main` 1 voraus; `feature` auf der Basis, `origin/feature` einen Commit voraus (0/1); `local-only` ohne `origin`-Referenz. | `branches(path, remote=False)` unter Netzwerk-Sperre. | Kein `ls-remote`/`fetch`; genau `{main, feature, local-only}`; `main` ist aktuell mit `(1, 0)`; `feature` nicht aktuell mit `(0, 1)`; `local-only` `(0, 0)` — deckt den in der 13er-Suite fehlenden Behind-1-Fall ab. |
| 4 | `ProjectWithoutReachableOrigin.test_status_without_github_enabled_does_not_query_remote` | AK3 | `.vibe/project.env` ohne `GITHUB_ENABLED`. | `status(path)` ohne `remote`-Argument (Normalmodus). | Kein `ls-remote`/`fetch`; `enabled=False`; `branch=main`. |

Fehlerfälle: Jede unerwartete Netzwerk-Git-Abfrage wird protokolliert und
lässt den jeweiligen Test fehlschlagen. Vor der Implementierung äußerte sich
eine fehlende `remote`-Schnittstelle als `TypeError`; das ist die
Testkonstruktion, nicht ein in dieser Sitzung beobachteter Rotlauf (siehe
Abschnitt 5).

## 4. Tatsächlich ausgeführte Befehle und Ergebnisse

Alle Befehle wurden in dieser Sitzung im Repository ausgeführt.

### 4.1 4er-Suite (Nachtrag, nach der Isolationsänderung)

```
python3 -m unittest tests.unit.test_b8_project_open_without_remote -v
```

Ausgabe (gekürzt auf die Ergebniszeilen):

```
Ran 4 tests in 0.098s

OK
```

Exit-Code: 0. Alle vier Tests `ok`:
`test_branches_offline_uses_local_origin_refs`,
`test_project_detail_does_not_touch_unreachable_origin`,
`test_status_offline_uses_local_origin_refs`,
`test_status_without_github_enabled_does_not_query_remote`.

### 4.2 13er-Suite

```
python3 -m unittest tests.unit.test_b8_no_remote_block -v
```

Ausgabe (gekürzt auf die Ergebniszeilen):

```
Ran 13 tests in 12.506s

OK
```

Exit-Code: 0. Alle 13 Tests `ok`.

## 5. Rotphase

* **13er-Suite:** Die Rotphase vor der Implementierung ist in der früheren
  Test-Agenten-Sitzung beobachtet und in `docs/features/B8.md:65–71`
  dokumentiert: Lauf gegen den Vor-B8-Stand (`28cf66d^`, ausgetauschte
  `bin/vibe_github.py`/`bin/vibe_services.py`) —
  `Ran 13 tests in 426,9 s — FAILED (failures=3, errors=9)`, Exit 1.
  Ich übernehme diese Angabe als dokumentierten früheren Nachweis; in dieser
  Sitzung habe ich sie wegen der bereits vorhandenen Implementierung **nicht
  erneut reproduziert**.
* **4er-Suite:** Für `tests/unit/test_b8_project_open_without_remote.py`
  existiert **kein separater Rotphasenlauf**. Die Datei wurde in einer
  früheren Sitzung geschrieben und mit `bea4275` versioniert; ein Lauf gegen
  einen Vor-B8-Stand ist nicht dokumentiert und wird hier nicht erfunden.
  Bekannt ist nur die Konstruktion: Ohne die `remote`-Schnittstelle würde
  `status(..., remote=False)` mit `TypeError` scheitern. Dieser Rotlauf ist
  **nicht beobachtet**. Die 4er-Suite ergänzt die 13er-Suite um den lokalen
  Behind-1-Fall und die exakten Branch-Abstände; ihre Regressionswirkung ist
  durch den statischen Codepfad (`use_remote = remote and
  config["enabled"]`) und den Grünlauf belegt, nicht durch einen eigenen
  Rotlauf.

## 6. Isolation

### 6.1 13er-Suite

`B8Case` (Zeilen 267–341) überschreibt `VIBE`, `VIBE_NO_CONTAINER`, `HOME`,
`VIBE_STATE`, `VIBE_RUNTIME`, `VIBE_INSTALL`, `VIBE_AGENTS_DIR`,
`GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM`/`GIT_CONFIG_NOSYSTEM` und `NO_PROXY`
mit temporären Werten, entfernt `GITHUB_TOKEN`, `GH_TOKEN`, Askpass- und
Proxy-Variablen sowie `VIBE_CONFIG_FILE`/`VIBE_PROFILE` und stellt die
Umgebung per `addCleanup` wieder her. Der Ende-zu-Ende-Test startet
`vibe-web.py` mit derselben isolierten Umgebung und eigenem Port.

### 6.2 4er-Suite (Änderung dieser Sitzung)

Die Modulaufrufe von `vibe_github`/`vibe_services` liefen zuvor mit der
geerbten Prozessumgebung; `vibe_github.git()` kopiert `os.environ`
vollständig, und `token_state_dir()`/`read_stored_token()` lösen über
`VIBE_STATE` bzw. `~` den Zustandsordner auf. Damit konnten produktives
`HOME`, produktives `VIBE_STATE`, produktives `VIBE_RUNTIME` und
`XDG_*`-Pfade in die Aufrufe gelangen (Befund [Minor] in
`docs/reviews/B8-review-3.md`).

Angeglichen an `B8Case`:

* `ISOLATED_ENV_KEYS` umfasst jetzt zusätzlich zu den B8-Schlüsseln auch
  `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`.
* `setUp` legt temporäre Verzeichnisse für `HOME`, `VIBE_STATE`,
  `VIBE_RUNTIME`, `VIBE_INSTALL` und `VIBE_AGENTS_DIR` an, entfernt
  `GITHUB_TOKEN`, `GH_TOKEN`, Askpass-/Proxy-Variablen,
  `VIBE_CONFIG_FILE` und `VIBE_PROFILE`, setzt die isolierten Pfade inklusive
  `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM`/`GIT_CONFIG_NOSYSTEM` und
  registriert `restore_env` als Cleanup.
* Keine Testmethode, keine Vorbedingung der geprüften Aussage und keine
  Assertion wurde geändert; die Sperre für `ls-remote`/`fetch` und das echte
  Git bleiben unverändert.

Damit liest die Suite keinen produktiven Token und keine produktive
Projektkonfiguration mehr. Die geprüften Aussagen (kein Fernkontakt, lokale
Referenzen, `GITHUB_ENABLED`-Verhalten) sind davon unberührt.

## 7. Verbleibende Lücken

1. **Kein eigener Rotlauf der 4er-Suite** (siehe Abschnitt 5). Der Nachweis
   der Regressionswirkung stützt sich auf die dokumentierte Rotphase der
   13er-Suite und den statischen Codepfad.
2. **Kein echtes Netz, kein echter GitHub-Endpunkt:** Beide Suiten nutzen
   lokale `127.0.0.1`-Fakes bzw. TEST-NET-1. Ein realer GitHub-Ausfall
   (DNS, TLS, Proxy) ist damit nicht abgebildet.
3. **`GCM_INTERACTIVE=never`** ist über die protokollierte Prozessumgebung
   belegt, nicht durch einen installierten Credential-Manager.
4. **Der hängende Fake ist `git://`-spezifisch;** ein nicht-GitHub-HTTPS-Host
   bleibt ungetestet (bereits in `docs/features/B8.md:91–96` benannt).
5. **Der Ende-zu-Ende-Test** prüft `GET /api/project`, nicht die visuelle
   Darstellung im Browser; eine Browsertest-Abnahme ist nicht Teil dieses
   Nachtrags.

## 8. Änderungen durch diesen Bericht

Geändert wurde ausschließlich:

* `tests/unit/test_b8_project_open_without_remote.py` — ENV-Isolation
  ergänzt (59 Zeilen), keine Assertion abgeschwächt, kein Test gelöscht.
* diese Berichtsdatei `docs/reviews/B8-test-agent-report.md` — neu angelegt.

`tests/unit/test_b8_no_remote_block.py`, Produktionscode, Konfiguration,
`docs/features/B8.md` und `FEEDBACK.md` wurden nicht geändert. Es gab keinen
Commit, keinen Push, keinen Merge und keinen Branchwechsel.
