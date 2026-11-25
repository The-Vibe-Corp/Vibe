# B4 — Installation scheitert an leerem Laufzustand (runs.json)

Status: Abgeschlossen (2026-11-22; Review `docs/reviews/B4-review-3.md`
Verdict: PASS)
Ticket: FEEDBACK.md `- [ ] B4 Install fails with error` (Art: Bug)
Branch: `feature/korbat/b4` (Arbeitskopie `worktrees/vibe-B4-A8gjp9`)
Ausgangscommit: `578a6dd` (AP3-Korbat-Merge, `dev`)

Hinweis zur Kennung: Der alte, bereits geschlossene B4 „Fehler bei
Verwendung des Pi-Harness" ist ein anderes Thema und bleibt unter
`docs/features/B4.md` erhalten; die Kennung wurde im Projektordner neu
vergeben. Dieser Bericht gehört zum NEUEN B4 („Install fails with error");
Review dieser Kennung: `docs/reviews/B4-review-3.md` (Runde 3 der Kennung —
Runden 1–2 in `B4-review-1/-2.md` gehörten zum alten B4).

## Fehlerbild (laut Eintrag)

Nach dem AP3-Korbat-Update schlägt `vibe install` fehl (interaktiv, Auswahl
„a" = aktualisieren):

```
Bestehende Installation gefunden: 21/22 Programme, Laufzeitdaten: models.json, profiles.json
Bestehende Installation [w]iederverwenden, [a]ktualisieren oder [q] abbrechen? [w]: a
Werkzeuge:
  OK    git / tmux / flock / curl / opencode
FEHLER: Die Installation wird gerade verwendet; nichts geändert.
  - Laufzustand /var/log/custom/vibe-dev/runs.json ist nicht lesbar
Beende die Läufe/Sitzungen oder nutze --force für eine bewusste Aktualisierung.
```

Die beanstandete Datei existiert und ist LEER (0 Bytes,
`-rw------- 1 vibe-dev vibe-dev 0 … runs.json`); `more` gibt nichts aus.
Neben ihr liegt `runs.json.1` (14921 Bytes) — im Logverzeichnis wurden zum
selben Zeitpunkt ALLE Zustandsdateien (`sessions.json`, `web.token`,
`web.instance`, …) nach `*.1` rotiert und leere Nachfolger hinterlegt.
`update.sh` läuft als root und ruft den Installer unter dem Nutzer
`vibe-dev` auf; ein Rechteproblem liegt damit nicht vor (Besitzer und
Modus passen zu `vibe-dev`).

## Ursachenanalyse

`running_installation()` in `scripts/setup-vibe.py` (Guard der drei
Modi update/uninstall/rollback in `main()`) liest `<logs>/runs.json` und
behandelte JEDES Scheitern von `json.loads` als Sperrgrund
„Laufzustand … ist nicht lesbar" — auch `json.loads("")` bei einer leeren
Datei (ValueError). Damit sperrte bereits ein nachweislich leeres Register
jede Aktualisierung, obwohl:

- eine FEHLENDE `runs.json` nie gesperrt hat (`else: data = None`), und
- die Laufzeit selbst leere/unlesbare Register als „keine Einträge"
  behandelt (`bin/vibe_runs.py`, `RunRegistry._read` und
  `SessionRegistry._read`: `except (OSError, ValueError): return []` bzw.
  Rückfall auf Defaults).

Ein leerer Laufzustand ist also ein legitimer, semantisch eindeutiger
Zustand „keine Läufe" (hier nach externer Rotation der Zustandsdateien
entstanden), kein unbekannter Zustand. Diagnostische Reproduktion am
Ausgangsstand: fehlende Datei → kein Grund; leere Datei und `"  \n"` →
je `['Laufzustand … ist nicht lesbar']`; `"{kein json"` → derselbe Grund.

Nach der Sperre liest nichts im weiteren Update-Pfad `runs.json`; der Guard
ist die einzige Fehlerstelle des gemeldeten Abbruchs.

## Entscheidung

- Eine vorhandene, aber leere oder nur aus Leerraum bestehende
  `runs.json` wird wie eine fehlende Datei behandelt: kein Sperrgrund.
  Das folgt der in-repo-Konsistenz (Bestandsverträge „fehlt = leer" und
  `RunRegistry._read`) und der Anforderung, Aktualisierungen ohne
  Verlust/Nutzereingriff zu ermöglichen (SPEC.md „Konfiguration und
  Migration").
- Konservativ bleibt die Sperre für Zustände, die der Installer nicht
  auswerten kann: nicht-leerer unlesbarer Inhalt (ValueError) und
  Lesefehler (OSError). Der zugehörige Bestandsvertrag ist durch
  `RunningGuardTest.test_update_refuses_when_the_run_state_is_unreadable`
  und die neuen Schutzwachfälle gesichert.
- Die Live-Erkennung (`LIVE_RUN_STATES`, `session_state`, tmux-Prüfung,
  konservatives Verhalten ohne prüfbare Sitzung) bleibt unverändert.
- Keine `vibe ask`-Rückfrage nötig: Der Fehlerzustand ist eindeutig
  bestimmt (leer = keine Läufe); die Grenzfälle sind durch bestehende
  Verträge fixiert.

## Umsetzung

| Datei | Änderung |
| --- | --- |
| `scripts/setup-vibe.py` | `running_installation()`: Registerleseblock ersetzt — leeres/nur-Leerraum-Register ergibt keinen Sperrgrund (`data = None` wie bei fehlender Datei); OSError beim Lesen und ValueError bei nicht-leerem Inhalt bleiben Sperrgrund „… ist nicht lesbar"; Docstring um die B4-Regel ergänzt |
| `docs/import-manifest.json` | `files`-Eintrag `scripts/setup-vibe.py` (SHA-256/Bytes) aktualisiert; `aenderungen`-Eintrag B4 ergänzt |
| `tests/unit/test_b4_install_empty_runs.py` | neu, vom unabhängigen Test-Agenten (16 Fälle, vor der Implementierung geschrieben, Rotphase belegt) |
| `docs/reviews/B4-test-agent-report.md` | neu, Bericht des Test-Agenten (Fälle, Rotphase, Baseline) |
| `docs/features/B4-install-leerer-laufzustand.md` | diese Doku |
| `docs/reviews/B4-review-3.md` | Review der Kennung (Runde 3; Runden 1–2 gehören zum alten B4) |
| `FEEDBACK.md` | Eintrag B4 wird nach Review-PASS mit Commit-/Testnachweis abgehakt (git-excluded, Bestandteil des Pakets) |

KISS: Die Änderung betrifft ausschließlich den geprüften Registerleseblock
des Guards — ein Ordnerwechsel der Semantik (leer → fehlt), keine neuen
Konfigurationen, Abhängigkeiten, Meldetexte oder Auswertungen.

## Grenzen (ehrlich benannt)

- Getestet wird der Guard-Vertrag inklusive der drei Guard-Nutzer
  (update/uninstall/rollback) über die CLI-Funktion `main()` mit
  bereinigter Umgebung; das echte interaktive Update unter root/`update.sh`
  wurde nicht ausgeführt (keine produktiven Pfade).
- Kein echtes tmux: Die Sitzungsprüfung wird über injizierte
  `which`/`runner`-Callables gesteuert (Muster aus dem Bestandstest).
- Lesefehler werden über ein Verzeichnis anstelle der Datei simuliert
  (`IsADirectoryError` ⊂ OSError); auf `chmod` wird verzichtet, weil
  Rechteänderungen auf FUSE/NTFS nicht verlässlich wirken (Projektregel).
- Entstehung und Vermeidung der externen `*.1`-Rotation der
  Zustandsdateien sind nicht Teil dieses Pakets; der Guard muss mit dem
  resultierenden Zustand (leere Dateien) korrekt umgehen — das ist hier
  behoben. Andere leere Zustandsdateien (`sessions.json`, `web.token`,
  `web.instance`) liest der Installer nicht; die Laufzeit behandelt sie
  bereits fehlertolerant.

## Tests (Autor: unabhängiger Test-Agent; Rotphase vor Implementierung)

Datei: `tests/unit/test_b4_install_empty_runs.py` (16 Fälle; eigenes Laden
von `scripts/setup-vibe.py` als `setup_vibe_b4`, nur `tempfile`-Pfade,
kein echtes `HOME`/`VIBE_*`, kein Netz, kein echtes tmux). Bericht:
`docs/reviews/B4-test-agent-report.md`.

| AK | Testfälle (Klasse) | Prüfung |
| --- | --- | --- |
| AK1 leere Datei sperrt nicht | `test_empty_runs_file_is_not_a_block_reason`, `test_update_runs_through_with_an_empty_runs_file` | Guard direkt + `--yes --update` läuft durch, Datei ersetzt, keine Zeile „wird gerade verwendet" |
| AK2 Leerraum wie leer | `test_whitespace_only_runs_file_is_not_a_block_reason` (2 subTest), `test_update_runs_through_with_a_whitespace_only_runs_file` | `"\n"`, `"  \n\t \n"` |
| AK3 nicht-leer unlesbar sperrt weiter | `test_non_empty_unreadable_runs_file_remains_a_block_reason`, `test_update_still_refuses_a_non_empty_unreadable_runs_file` | `"{kein json"` → Grund enthält „ist nicht lesbar" + Pfad; Exit 1, „ALT" bleibt |
| AK4 OSError sperrt weiter | `test_oserror_when_reading_the_runs_path_remains_a_block_reason`, `test_update_still_refuses_when_the_runs_path_is_unreadable` | Verzeichnis statt Datei (IsADirectoryError) |
| AK5 Uninstall/Rollback | `test_uninstall_runs_through_with_an_empty_runs_file`, `test_rollback_runs_through_with_an_empty_runs_file`, `test_uninstall_still_refuses_a_running_run_with_live_session`, `test_rollback_still_refuses_a_running_run_with_live_session` | leer sperrt nicht; laufender Lauf sperrt weiterhin |
| AK6 Live-Sperre erhalten | `test_live_run_with_existing_session_remains_a_block_reason`, `test_update_still_refuses_a_running_run_with_live_session`, `test_update_still_refuses_a_starting_run_with_live_session` | `running`/`starting` + existierende (Fake-)Sitzung |
| Schutzwache fehlt = leer | `test_missing_runs_file_is_not_a_block_reason` | Bestandsvertrag „fehlende Datei sperrt nicht" |

Rotphase am Ausgangsstand `578a6dd` (dokumentiert im Test-Agenten-Bericht):
`Ran 16 tests … FAILED (failures=7)` — exakt die AK1/AK2/AK5-Fälle
(leere/Leerraum-Register sperren Update/Uninstall/Rollback); die 9
Schutzwachfälle (fehlende Datei, AK3, AK4, AK6) waren bereits grün.

Grünphase nach Implementierung (Koordinator bestätigt):

```
$ python3 -m unittest tests.unit.test_install_lifecycle -v
Ran 16 tests in 0.154s

OK
```

Bestandsregression (dokumentierte B17-Vorlast, Zähler unverändert, vom
Koordinator nachgemessen): `tests.unit.test_setup_vibe` →
`Ran 50, FAILED (failures=6, errors=4)` (AP3-Doku: „6 Failures/4 Errors");
`tests.unit.test_install_lifecycle` → `Ran 43, FAILED (failures=7,
errors=28)` (AP3-Doku: „7/28"; Ursache ist der historische Harness, der in
`InstallLifecycleBase.install()` den Vibe-Root statt der Toolchain
übergibt — nicht B4, nicht Bestandsteil dieses Pakets);
`tests.unit.test_b17_isolation` → `Ran 12, OK` (kausaler Wächter der
B17-Quellensperrung bleibt grün).

## Pflichtprüfungen

- `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh quick` → Exit 0
  (Manifest 68 Dateien OK, Syntax, keine Geheimnisse).
- `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh package` → Exit 0.
- Zielmäßigkeitsnachweise: B4-Unit 16/16 OK (Test-Agent, Coding-Agent und
  Koordinator unabhängig); Baseline-Zähler wie oben unverändert.
- `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh full` (einmal je Paket
  vor Abnahme): **2396 Tests, 107/132 Module bestanden, 25 Module rot,
  Exit 5** — die 25 Rotmodule sind vollständig die vorbestehende,
  dokumentierte Baseline; kein durch B4 rot gewordenes Modul. Beleg:

  - Das neue Modul `tests.unit.test_b4_install_empty_runs` lief im
    Volllauf grün (nicht in der Fehlerliste; 132 = 131 Bestandsmodule +
    1 neues Modul).
  - Klassifizierung gegen den Ausgangsstand: Für jedes Modul, das die
    geänderten Dateien berührt (alle mit Referenz auf
    `scripts/setup-vibe.py`: ap04_setup_harness, ap12_github_readiness,
    b17_isolation, install_lifecycle, release, setup_vibe,
    v026_run_isolation; alle mit Referenz auf `docs/import-manifest.json`:
    baseline_inventory, import_manifest, verify_script), wurde der
    Ausgangsstand `578a6dd` in einem lokalen Klon (identische
    `.vibe/project.env`) ausgeführt und mit dem Ist-Stand verglichen —
    Resultat signaturenidentisch (setup_vibe 6F/4E beidseits,
    install_lifecycle 7F/28E beidseits, v026 1F+2E beidseits, ap12 2F
    beidseits, release 1F beidseits, baseline_inventory 1F beidseits;
    ap04/b17/import_manifest/verify_script beidseits grün).
  - Die übrigen Rotmodule berühren keine geänderte Datei; Stichprobenlauf
    im Ausgangsklon bestätigt identische Signaturen (ap03, ap06, ap08,
    b13, b3, b4_pi_agent_dir, b5, f22, f27, feedback_capture,
    project_agents, project_guide, rebuild_profile, sandbox,
    ticket_feedback_processing, v025 — jeweils gleiche Ran/F/E-Zähler).
    `test_run_autostop` ist beidseits im Einzellauf grün (OK); seine
    Volllauf-Rotheit ist ein Parallel-Lastartefakt der
    4-Jobs-Volllauf-Umgebung, ohne B4-Bezug.
    `test_feedback_entries` (1E) und `test_project_management` (6F+1E)
    entsprechen im Ist-Stand exakt der dokumentierten AP5-Baseline
    („Ran 36, FAILED (failures=6, errors=1) — F22-Baseline"); der Klon
    zeigt dort zusätzliche Fehler nur, weil die ignorierten Dateien
    `AGENTS.md`/`FEEDBACK.md` im Klon fehlen — Arbeitskopie und
    dokumentierte Baseline stimmen überein.

## Review und Dokumentation

- Review Runde 3 der Kennung: `docs/reviews/B4-review-3.md` —
  **`Verdict: PASS`** (0 Critical, 0 High, 0 Medium, 0 Minor). Der
  Reviewer hat geprüft: fachliche Korrektheit aller AK am Quelltext,
  KISS-Umfang (nur Registerleseblock + Docstring), Testqualität und
  Unabhängigkeit (Rotphase belegt, keine abgeschwächten Assertionen,
  Bestandstests unverändert), Bestandsverträge
  (`test_update_refuses_when_the_run_state_is_unreadable`, B17-Schutz),
  Manifest-Konsistenz, Hygiene (keine Geheimnisse; FEEDBACK/TICKETS vor
  PASS unangetastet), Dokumentations-Fakten und die
  Baseline-Klassifizierung des Volllaufs. Grenze: Der Reviewer führte
  eigenständig Quelltext-/Dateiinspektionen durch; Kommandos wurden aus
  der Koordinator-Nachweislage übernommen und im Bericht als solche
  gekennzeichnet.
- Trilium: In dieser Laufumgebung ist kein Trilium-MCP verbunden
  (Ressourcendiscovery leer); die Synchronisation entfällt und wird im
  Abschlussbericht als nicht verfügbar gemeldet. Das Paket ist dadurch
  nicht blockiert (AGENTS.md Schritt 8).

## Abschluss

- Volllauf: einmal je Paket vor Abnahme ausgeführt und vollständig gegen
  den Ausgangscommit `578a6dd` klassifiziert (Abschnitt
  „Pflichtprüfungen"): 2396 Tests, 107/132 Module grün, 25 Rotmodule
  sämtlich vorbestehende Baseline, kein durch B4 rot gewordenes Modul,
  neues B4-Modul grün.
- Review: Runde 3 der Kennung PASS ohne Befunde; keine
  Implementierungsänderungen nach dem PASS.
- Commit: zusammenhängender Paket-Commit mit Präfix `B4:` auf
  `feature/korbat/b4` (Implementierung, Tests des Test-Agenten,
  Manifest, Berichte und diese Doku). Die verbindliche Commit-Kennung
  steht in der Nachweiszeile des FEEDBACK-Eintrags B4 (git-excluded,
  Bestandteil des Pakets); die Übernahme ins Projektordner-FEEDBACK
  erfolgt über den Läufer/Eigentümer (`vibe_packages.py sync-proof`,
  Muster wie B3).
- Arbeitskopie nach dem Commit sauber (FEEDBACK.md/TICKETS.md sind
  gitignoriert und gehören zum Laufzeitstand der Arbeitskopie).
