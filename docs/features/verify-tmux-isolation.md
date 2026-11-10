# Prüfisolierung: der tmux-Server des Aufrufers bleibt unberührt

**Art:** Fehlerbehebung (Testisolation)
**Branch:** `feature/verify-tmux-isolation`
**Ausgangsstand:** `979b93d`
**Datum:** 2026-11-10

## Befund

Wird `bash scripts/verify.sh full` aus einer vibe-Sitzung gestartet, endeten
Dashboard und vibe-App vorzeitig. Im Dashboard-Protokoll stand als letzte
Zeile `Dashboard wird beendet.`, danach war die Sitzung weg.

Die Meldung ist kein Auslöser, sondern die Folge: `bin/vibe-web.py` behandelt
SIGHUP wie SIGTERM, setzt `STOP` und beendet den offenen SSE-Stream mit dieser
Zeile. Das Signal kam von einem beendeten tmux-Server.

## Ursache

`vibe` legt Dashboard (`vibe-ui`), opencode (`vibe-server`) und den
Agentenlauf (`vibe-proj`) als Sitzungen eines tmux-Servers an. `verify.sh full`
läuft in der Sitzung `vibe-proj` und erbt deshalb `TMUX` und `TMUX_PANE`.

Zwei Unit-Tests räumten ihren eigenen tmux-Server so auf:

```python
subprocess.run(["tmux", "kill-server"],
    env={**os.environ, "TMUX_TMPDIR": str(cls.tmux_dir)}, ...)
```

`TMUX_TMPDIR` allein genügt nicht: **tmux bevorzugt ein gesetztes `TMUX` und
verbindet sich mit dem dort genannten Socket.** `TMUX_TMPDIR` wird dann
ignoriert. `kill-server` traf damit den Server des Aufrufers und beendete alle
drei Sitzungen – Dashboard, opencode und den laufenden Agentenlauf.

Betroffen waren:

* `tests/unit/test_f20_harness_dashboard_api.py` (`tearDownClass`)
* `tests/unit/test_output_view_f19_api.py` (`tearDownClass`)

Bisher unentdeckt blieb das, weil die dokumentierten Vollnachweise in einem
Mount-Namespace mit `tmpfs` auf `/tmp` liefen: der tmux-Socket
`/tmp/tmux-<uid>/default` war dort nicht sichtbar, der `kill-server` lief ins
Leere.

## Nachweis der Ursache

Zwei Wegwerf-Server A und B, danach `tmux ls` mit gesetztem `TMUX` auf A und
`TMUX_TMPDIR` auf B:

```
$ TMUX=<A>/default,1,0 TMUX_TMPDIR=<B> tmux ls
probe-a
$ TMUX=<A>/default,1,0 TMUX_TMPDIR=<B> tmux kill-server
$ TMUX_TMPDIR=<A> tmux ls   → no server running
$ TMUX_TMPDIR=<B> tmux ls   → probe-b
```

Die alte Aufräumzeile gegen einen isolierten Opfer-Server ausgeführt, beendet
diesen ebenfalls (`no server running`). Die Ursache ist damit reproduziert,
ohne den echten Server anzufassen.

## Änderungen

| Datei | Änderung |
| --- | --- |
| `scripts/verify.py` | `TMUX` und `TMUX_PANE` werden aus der Prüfumgebung entfernt; `TMUX_TMPDIR` zeigt auf `<Prüfverzeichnis>/tmux` (Modus 700). Docstring ergänzt. |
| `tests/support/tmux_cleanup.py` | Neuer Helfer `cleanup_env(environ, tmux_dir)`: entfernt `TMUX`/`TMUX_PANE`, setzt `TMUX_TMPDIR`, verändert die Eingabe nicht. |
| `tests/unit/test_f20_harness_dashboard_api.py` | Aufräumen über `cleanup_env(os.environ, cls.tmux_dir)`. |
| `tests/unit/test_output_view_f19_api.py` | Aufräumen über `cleanup_env(os.environ, cls.tmux_dir)`. |
| `tests/unit/test_tmux_cleanup.py` | Neue Regressionstests mit echten, eigenen tmux-Servern. |
| `tests/unit/test_verify_script.py` | Neuer Test `VerifyTmuxIsolationTest`: ein geerbtes `TMUX` erreicht die Prüfung nicht. |

Zwei Ebenen: Die Tests räumen nur noch ihren eigenen Server auf, und die
Prüfung reicht gar kein `TMUX` mehr weiter. Damit kann auch ein künftiger Test
den Server des Aufrufers nicht mehr über `TMUX` erreichen.

## Tests

`tests/unit/test_tmux_cleanup.py` (2 Tests, echte tmux-Server in temporären
Verzeichnissen):

1. `test_cleanup_env_drops_the_inherited_client_socket` – Ergebnis enthält kein
   `TMUX`/`TMUX_PANE`, `TMUX_TMPDIR` ist das eigene Verzeichnis, die Eingabe
   bleibt unverändert.
2. `test_cleanup_env_never_targets_the_callers_server` – `kill-server` mit der
   Aufräumumgebung beendet den eigenen Server, der Aufrufer-Server lebt weiter.

`tests/unit/test_verify_script.py::VerifyTmuxIsolationTest` (1 Test):

3. `test_caller_tmux_is_not_handed_to_the_check` – ein gesetztes `TMUX` aus der
   Aufruferumgebung ist im Prüfbefehl nicht sichtbar; `TMUX_TMPDIR` liegt unter
   dem Prüfverzeichnis.

Rote Phase vor der Implementierung: Test 1/2 scheiterten mit
`ModuleNotFoundError: No module named 'tests.support'`, Test 3 mit
`AssertionError: '/tmp/tmux-1000/default,1,0' is not None`.

Zusätzlicher Ende-zu-Ende-Nachweis: ein Opfer-Server lief, danach wurden
`tests.unit.test_f20_harness_dashboard_api` (8 Tests) und
`tests.unit.test_output_view_f19_api` (14 Tests) mit gesetztem `TMUX` auf
diesen Server ausgeführt. Beide grün, der Opfer-Server lebte danach weiter.

## Prüfungen (tatsächlich ausgeführt)

```
python3 -m unittest tests.unit.test_tmux_cleanup tests.unit.test_verify_script.VerifyTmuxIsolationTest -v
  Ran 3 tests … OK

python3 -m unittest discover -s tests/unit -p "test_tmux_cleanup.py" -v        → Ran 2 … OK
python3 -m unittest discover -s tests/unit -p "test_verify_script.py" -v       → OK (17 Tests)

bash scripts/verify.sh quick   → Exit 0
  OK: 57 Dateien stimmen mit docs/import-manifest.json überein.
  OK: 127 Python-, 8 Bash- und 6 JSON-Datei(en) syntaktisch geprüft.
  OK: keine Geheimnisse erkannt.

bash scripts/verify.sh full    → Exit 5 (vorbestehende Fehlschläge, siehe unten)
  Ran 1366 tests in 255.570s
```

### Vorbestehende Fehlschläge (nicht durch dieses Arbeitspaket verursacht)

Am Ausgangsstand `979b93d` in einem eigenen Worktree reproduziert:

* `test_ap04_setup_harness.SetupHarnessTest.test_dry_run_explains_pi_and_its_install_command`
  – die Dry-Run-Ausgabe nennt `@earendil-works/pi-coding-agent` nicht.
* `test_release.ReleaseBuildTest.test_repository_content_has_no_personal_home_paths_or_secrets`
  – `docs/features/B4.md` enthält einen absoluten Home-Pfad in einem
  zitierten Fehlertext.

Die Browsersuite (`python3 -m unittest discover -s tests/browser`, 113 Tests)
hat einen weiteren vorbestehenden Fehlschlag
(`test_central_workflows_ui…test_central_flow_lists_opens_creates_and_verifies`,
am Ausgangsstand ebenfalls rot) und einen Lastfehler in `test_fritz_ui`
(am Ausgangsstand und einzeln zweimal grün). `verify.sh full` bricht wegen der
Unit-Fehlschläge vor der Browsersuite ab; sie wurde deshalb separat ausgeführt.

Beim direkten Browserlauf schreiben die Tests Screenshots nach
`docs/features/`; die dabei überschriebenen Bilddateien wurden verworfen
(`git checkout -- docs/features`), sie sind nicht Teil dieses Arbeitspakets.

## Grenzen

* Der Nachweis nutzt echte tmux-Server, aber nur in temporären Verzeichnissen;
  der Server des Aufrufers wird nicht angefasst.
* Ein geerbtes `TMUX` kann weiterhin über andere Wege als tmux selbst
  weitergegeben werden (z. B. ein Test, der `/tmp/tmux-<uid>/default` direkt
  adressiert). Die Prüfebene entschärft den praktisch relevanten Weg.
* Die zwei vorbestehenden Fehlschläge und der flakige Browsertest bleiben
  offen; sie gehören nicht zu diesem Arbeitspaket.
