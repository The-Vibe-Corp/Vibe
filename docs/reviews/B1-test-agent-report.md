# Test-Agenten-Bericht B1 — Projektmodelle aus `.vibe/agents.json`

Stand: 2026-11-20 (abschließende Revalidierung nach der Reader-Nachbesserung)
Rolle: unabhängiger Test-Agent (Test-First, keine Produktionsänderung)
Arbeitspaket: FEEDBACK.md, B1 „Models in project config are ignored“
Worktree/Branch: `/var/log/custom/vibe-dev/worktrees/vibe-B1-01QQj3`,
`feature/korbat/b1`

## Ausgangslage

Bestätigte Ursache: `bin/vibe:run_agent_selection()` lieferte nur die
Modellüberschreibung des Startagenten; `bin/vibe-run.sh` übergab sie als
`opencode run --model`. Die übrigen Einträge unter `modelle` in
`<Integrationsprojekt>/.vibe/agents.json` wurden vom Läufer nie gelesen.
Deshalb verwendeten später vom Orchestrator gestartete Subagenten ihr globales
Frontmatter-Modell.

Der Coding-Agent hat den ersten Fix im Läufer umgesetzt. Diese Runde prüft
ihn unabhängig (12/12 grün) und ergänzt drei reviewgetriebene
Regressionstests für den neuen Reader:

1. Ein vorhandener, aber nicht als Datei lesbarer `agents.json`-Pfad wurde wie
   eine fehlende Datei behandelt.
2. Ein Trailing Comma mit dazwischenliegendem Kommentar wurde nicht erkannt.
3. Ein nicht abgeschlossener Blockkommentar wurde bis zum Dateiende entfernt
   und die Konfiguration fälschlich akzeptiert.

Zusätzlich gilt weiterhin: Ein nur im `opencode run`-Client gesetztes
`OPENCODE_CONFIG_CONTENT` ändert serverseitig aufgelöste Subagenten nicht
zuverlässig. Bei vorhandenen Projektmodellen darf ein erreichbarer gemeinsamer
Server deshalb nicht ohne Laufkonfiguration weiterverwendet werden.

## Akzeptanzkriterien

1. Mehrere `modelle` aus `$P/.vibe/agents.json` werden beim opencode-Lauf als
   wirksame Agenten-Modellüberschreibungen übergeben, nicht nur das `--model`
   des Startagenten.
2. Dieselbe wirksame Konfiguration erreicht den privaten `opencode serve`.
3. Vorhandenes `OPENCODE_CONFIG_CONTENT` bleibt semantisch erhalten
   (unbeteiligte Einstellungen und Agentenfelder); Projektmodelle gewinnen.
   Eine vorhandene `agents`-Map darf die Projektüberschreibung nicht wieder
   außer Kraft setzen; das Legacy-Schema `agent` bleibt kompatibel.
4. Der bisherige Hauptagenten-Parameter `--model` bleibt erhalten; globale
   Agentendateien und `.vibe/agents.json` werden nicht verändert.
5. Ohne Projektmodelle bleibt ein gesetztes `OPENCODE_CONFIG_CONTENT`
   unverändert.
6. Eine unlesbare/ungültige `agents.json` bzw. eine nicht mergefähige
   vorhandene Inline-Konfiguration fällt nicht still auf globale Modelle
   zurück, sondern scheitert verständlich vor einem Agentenstart.
7. Findet `server_is_up` einen gemeinsamen opencode-Server, gilt bei
   vorhandenen Projektmodellen: ohne Kennwortdatei `--standalone`, mit
   Kennwortdatei der private Serverpfad — jeweils mit derselben
   `OPENCODE_CONFIG_CONTENT`. Ohne Projektmodelle bleibt die bisherige
   Wiederverwendung des gemeinsamen Servers unverändert.
8. JSONC-Bestandskonfiguration (Kommentar, Trailing Comma) wird akzeptiert und
   mit den Projektmodellen zusammengeführt; eine reine JSON-Neuserialisierung
   ist zulässig.
9. Nur `FileNotFoundError` bedeutet „keine Projektmodelle“. Ein anderer
   `OSError` beim Öffnen von `$P/.vibe/agents.json` (z. B. ein Verzeichnis an
   dieser Stelle) bricht verständlich vor jedem Agentenstart ab.
10. Ein Trailing Comma mit Kommentar zwischen Komma und schließender Klammer
    (`{"theme":"dark", // Kommentar\n}`) ist gültiges JSONC und wird
    zusammengeführt; `//` innerhalb von Zeichenketten (z. B. URLs) bleibt
    unangetastet.
11. Ein nicht abgeschlossener Blockkommentar nach einem ansonsten vollständigen
    Objekt wird nicht still entfernt, sondern führt fail-closed zu einem
    Abbruch vor dem Agentenstart.

## Testdesign

Neue Datei: `tests/unit/test_b1_project_agent_models.py` (nun 15 Tests).

- **Echte Läuferausführung:** Jeder Test startet `bin/vibe-run.sh` in einer
  temporären Installation über `tests/unit/runner_support.py` mit echtem
  Git-Repository, echter Arbeitskopie und nachgebildetem Agenten. Es finden
  keine Modellaufrufe, Anbieteranfragen oder Schreibzugriffe auf produktive
  Installationen statt.
- **Beobachtung der wirksamen Konfiguration:** Eine eigene opencode-Hülle im
  Testmodul protokolliert je Aufruf Argumente und
  `OPENCODE_CONFIG_CONTENT` und führt danach die gemeinsame
  `runner_support.FAKE_OPENCODE` aus. Damit werden sowohl `opencode run` als
  auch `opencode serve` beobachtet.
- **Projektkonfiguration nur in `$P`:** `.vibe/` ist im Testprojekt per
  `.gitignore` ausgeschlossen. Die Paket-Arbeitskopie enthält deshalb keine
  `.vibe/agents.json`. Damit prüfen die Tests mit, dass der Läufer die
  Projektkonfiguration aus dem Integrationsprojekt `$P` liest.
- **Gemeinsamer Server:** Ein lokaler HTTP-Fake antwortet auf `GET /api/info`
  mit 200; `curl` ist die echte HTTP-Attrappe aus `runner_support`. So wird
  die Zielwahl des Läufers über echte Argumente geprüft, ohne externen Dienst.
- **Auflösung der beiden Schemata:** Die Tests lösen das wirksame Modell wie
  opencode auf (`agents` vor `agent`) und sammeln erhaltene Agentenfelder über
  beide Maps. Dadurch wird keine bestimmte interne Serialisierung
  vorgeschrieben, aber ein Wieder-Außerkraftsetzen durch eine alte
  `agents`-Map erkannt.
- **Deterministischer OSError:** Der unlesbare Pfad ist ein Verzeichnis an der
  Stelle von `.vibe/agents.json` (`IsADirectoryError`). Das ist ohne
  rootabhängige `chmod`-Annahmen reproduzierbar.

## Unabhängige Grün-Revalidierung des ersten Fixes

Befehl gegen den aktuellen Stand des Coding-Agenten:

```text
python3 -m unittest tests.unit.test_b1_project_agent_models -v
```

Ergebnis des bisherigen Teststands (12 Tests):

```text
Ran 12 tests in 45.889s
OK
```

Damit sind alle 12 bisherigen Fälle unabhängig grün bestätigt: Projektmodelle
für `run` und privaten Server, Erhalt der Inline-Konfiguration, Legacy-Schema,
JSONC-Basisfall, gemeinsamer Server, ungültige Konfiguration sowie beide
Kontrollfälle.

## Erste Rotphase (vor dem ersten Fix, dokumentiert)

Der ursprüngliche Teststand war gegen den unveränderten Produktionsstand rot:

```text
python3 -m unittest tests.unit.test_b1_project_agent_models -v
→ Ran 12 tests in 35.788s
→ FAILED (failures=9, errors=1)
→ 2 Kontrollen ok
```

Rot waren insbesondere: fehlendes `OPENCODE_CONFIG_CONTENT` bei `run`/`serve`,
Weiterverwendung des gemeinsamen Servers trotz Projektmodellen, Vorrang einer
vorhandenen `agents`-Map, fehlende JSONC-Zusammenführung und Agentenstarts
trotz ungültiger Projekt-/Inline-Konfiguration. Die beiden Kontrollfälle
(keine Projektmodelle) waren bereits grün. Details und Rohauszüge stehen in
der Projektchronik; die Einordnung bleibt: keine kaputte Testumgebung, sondern
fehlende Projektmodell-Übernahme.

## Zweite, reviewgetriebene Rotphase (neue Reader-Befunde)

Ergänzt wurden drei fokussierte Regressionstests:

| Test | Erwartung |
| --- | --- |
| `InvalidConfigurationTest.test_path_that_is_not_a_regular_file_aborts_before_agent_start` | Ein Verzeichnis an `agents.json`-Stelle führt zu Abbruch, keiner Agenten-/Serveraufruf, verständliche Meldung. |
| `ExistingConfigTest.test_jsonc_comment_between_trailing_comma_and_closing_brace` | JSONC mit Trailing Comma + Kommentar vor `}` wird gemerged; `theme` bleibt, URL mit `//` bleibt, Projektmodell wirkt. |
| `InvalidConfigurationTest.test_unterminated_block_comment_is_not_silently_removed` | Ein offener `/*`-Kommentar nach vollständigem Objekt führt fail-closed zum Abbruch vor Agentenstart. |

Befehl gegen den aktuellen Reader:

```text
python3 -m unittest tests.unit.test_b1_project_agent_models -v
```

Ergebnis:

```text
Ran 15 tests in 40.050s
FAILED (failures=3)
```

Die bisherigen 12 Tests bleiben dabei grün; genau die drei neuen Fälle sind
rot:

1. `test_jsonc_comment_between_trailing_comma_and_closing_brace`
   — Exit 2; Protokoll: `OPENCODE_CONFIG_CONTENT ist keine mergefähige
   Inline-Konfiguration.` Der Scanner entfernt den Trailing Comma nicht, weil
   zwischen Komma und `}` ein Kommentar steht.
2. `test_path_that_is_not_a_regular_file_aborts_before_agent_start`
   — Exit 0 und vollständiger Lauf inklusive `FERTIG`; der vorhandene, aber
   unlesbare Pfad wird wie eine fehlende Datei behandelt und der Agent startet
   mit globalen Modellen.
3. `test_unterminated_block_comment_is_not_silently_removed`
   — Exit 0 und vollständiger Lauf; der offene Blockkommentar wird bis zum
   Dateiende entfernt, sodass das vollständige Objekt fälschlich akzeptiert
   wird.

Damit ist die zweite Rotphase reviewgetrieben und auf die drei gemeldeten
Reader-Befunde begrenzt; sie beruht nicht auf einer Änderung der bisherigen
Assertions oder einer defekten Testumgebung.

## Abschließende Grün-Revalidierung (nach der Reader-Nachbesserung)

Der Coding-Agent hat die drei Reader-Befunde nachgebessert. Alle zuvor roten
B1-Fälle sind jetzt unabhängig grün; die Testdatei wurde in dieser Runde nicht
mehr verändert.

### B1-Modul (15/15)

```text
python3 -m unittest tests.unit.test_b1_project_agent_models -v
→ Ran 15 tests in 31.334s
→ OK
```

Damit sind auch die drei zuvor roten Reader-Fälle grün:

- `test_path_that_is_not_a_regular_file_aborts_before_agent_start`
- `test_jsonc_comment_between_trailing_comma_and_closing_brace`
- `test_unterminated_block_comment_is_not_silently_removed`

### Bisheriger Läufer-Modelltest (3/3)

```text
python3 -m unittest tests.unit.test_project_agents.RunnerModelTest -v
→ Ran 3 tests in 5.018s
→ OK
```

### B13-Regressionsausschnitt (9/9)

```text
python3 -m unittest \
  tests.unit.test_b13_private_server_runner.PrivateServerStartTest \
  tests.unit.test_b13_private_server_runner.PrivateServerEndTest \
  tests.unit.test_b13_private_server_runner.StandaloneFallbackTest \
  tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest \
  tests.unit.test_b13_private_server_runner.PiNoPrivateServerTest \
  tests.unit.test_b13_private_server_runner.SharedServerKeptTest -v
→ Ran 9 tests in 48.325s
→ OK
```

Damit bleiben privater Server, Standalone-Rückfall, Preflight-Zielwechsel,
Pi-Zweig und Wiederverwendung des gemeinsamen Servers unverändert intakt.
Kein `verify.sh full` und keine Vollsuite in dieser Runde.

## Basistests

Unverändertes, relevantes Basismodul (erste Runde, weiterhin gültig):

```text
python3 -m unittest tests.unit.test_project_agents -v
→ Ran 26 tests in 4.790s
→ FAILED (failures=1, errors=1)
```

Die beiden Fehler sind vorbestehend und betreffen nicht die
Projektmodell-Übernahme:

- `RunSelectionTest.test_cmd_run_ensures_the_independent_test_agent_for_an_existing_project`
  — `AssertionError: False is not true` (Agentendatei fehlt).
- `RunSelectionTest.test_cmd_run_aborts_when_the_test_agent_cannot_be_created`
  — `AttributeError: ... does not have the attribute 'ensure_test_agent'`.

`bin/vibe` im unveränderten Stand enthält `ensure_test_agent` nicht; die
übrigen 24 Tests bestehen. Dieser bekannte Baselinebefund bleibt unverändert
bestehen und wird ausdrücklich nicht als Erfolg umgedeutet. In der
abschließenden Runde wurde daraus nur `RunnerModelTest` ausgeführt (3/3 OK);
die beiden bekannten Baselinefehler wurden nicht erneut als Erfolg gewertet.
Auf ausdrückliche Anweisung wurden keine Vollsuite und kein `verify.sh full`
ausgeführt.

## Grenzen und offene Punkte

- Es wurde kein echter opencode-Prozess und kein Modellaufruf ausgeführt. Die
  JSONC-Akzeptanz ist als Anforderung aus der bestätigten
  opencode-v2.3.0-Probe übernommen.
- Die Tests schreiben keine bestimmte Implementierung vor, verlangen aber die
  beobachtbare Schnittstelle `OPENCODE_CONFIG_CONTENT` und die Auflösung über
  `agents`/`agent`.
- Nicht abgedeckt: Pi-Harness, Sandbox-Sonderpfad mit Projektmodellen,
  Mehrpaket-Läufe, projektübergreifende Modelle und eine echte
  opencode-Serverauflösung.
- Die 15 Tests brauchen je nach Umgebung ca. 31–46 s, weil jeder Fall einen
  echten Läuferdurchlauf mit Arbeitskopie ausführt. Subprozesse sind durch
  `timeout` begrenzt; die Test-Fixierung beendet nur die von ihr gestarteten
  privaten Server.
- Keine Produktionsdateien, keine gemeinsamen Produktions-Fixtures und keine
  bestehenden Assertions wurden geändert oder abgeschwächt.

## Geänderte Dateien

- `tests/unit/test_b1_project_agent_models.py` (15 Tests; in der
  abschließenden Runde unverändert)
- `docs/reviews/B1-test-agent-report.md` (aktualisiert um die abschließende
  Grün-Revalidierung)

## Ausgeführte Befehle

```text
python3 -m unittest tests.unit.test_b1_project_agent_models -v
  → 12 Tests, OK (unabhängige Grün-Revalidierung des ersten Fixes)

python3 -m unittest tests.unit.test_b1_project_agent_models -v
  → 15 Tests, FAILED (failures=3); die bisherigen 12 bleiben grün,
    genau die drei neuen Reader-Fälle sind rot (zweite Rotphase)

python3 -m unittest tests.unit.test_project_agents -v
  → 26 Tests, FAILED (failures=1, errors=1); beide Fehler vorbestehend
    (`ensure_test_agent` fehlt in `bin/vibe`)

python3 -m unittest tests.unit.test_b1_project_agent_models -v
  → 15 Tests in 31.334s, OK (abschließende Grün-Revalidierung)

python3 -m unittest tests.unit.test_project_agents.RunnerModelTest -v
  → 3 Tests in 5.018s, OK

python3 -m unittest tests.unit.test_b13_private_server_runner.PrivateServerStartTest \
  tests.unit.test_b13_private_server_runner.PrivateServerEndTest \
  tests.unit.test_b13_private_server_runner.StandaloneFallbackTest \
  tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest \
  tests.unit.test_b13_private_server_runner.PiNoPrivateServerTest \
  tests.unit.test_b13_private_server_runner.SharedServerKeptTest -v
  → 9 Tests in 48.325s, OK
```

Kein `verify.sh`, keine Vollsuite, keine Browser-/Netz-/Modelltests in dieser
Runde.
