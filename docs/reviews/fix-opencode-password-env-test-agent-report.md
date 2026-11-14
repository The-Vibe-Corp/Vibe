# Test-Agent-Bericht — Fix: Geerbtes OPENCODE_PASSWORD

Projekt: vibe · Arbeitspaket: Defekt-Fix „Geerbtes OPENCODE_PASSWORD blockierte den privaten opencode-Server" (Anlass: Lauf `vibe-20261114-192106-c11f59`)
Testdatei: `tests/unit/test_f31_inherited_opencode_password.py` · Attrappe: `tests/unit/runner_support.py` (`listening`-Ereignis notiert Anwesenheit/Länge, nie den Wert)

## Herkunft und Durchführung

- Die Testfälle wurden vom unabhängigen Test-Agenten aus Arbeitspaket und
  vereinbartem Verhalten abgeleitet und **vor** der jeweiligen
  Implementierungsänderung angelegt. Die Erstabnahme (AK1–AK4, drei Fälle)
  entstand in der Sitzung `ses_e24920f17ffefNDPvj4gtC6crU`, die Ergänzung
  AK1b (Restpfad `.vibe/project.env`, Review-Befund M1) in der Sitzung
  `ses_e2451adbdffeZZm3bsesV6yWi0`. Beide Sitzungen wurden zweimal durch das
  Free-Nutzungslimit unterbrochen; der Test-Agent legte die Fälle jeweils
  vollständig an.
- Ausgeführt wurden die Läufe vom Coding-Agenten (Projektregel: Tests ausführen
  und Ergebnisse melden ist zulässig); die Rohausgaben sind unten und in den
  konservierten Protokollen wortgleich. Der Coding-Agent hat keine Testdatei
  angelegt, geändert oder abgeschwächt.
- Konservierte Rohausgaben: Rotphase am Fix-vorher-Stand `10dca46` (3
  Failures, siehe unten) und Grünlauf am Fix-Stand (4/4 OK) als Klartext
  dauerhaft im Repository unter
  `docs/reviews/fix-opencode-password-env-evidence-red-10dca46.txt` und
  `docs/reviews/fix-opencode-password-env-evidence-green-fix.txt`; die
  wesentlichen Ausschnitte sind in diesem Bericht zitiert.

## Testfälle

| Fall | AK | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- | --- |
| `test_inherited_opencode_password_is_absent_from_the_server_env` | AK1+AK4 | Kennwortdatei nichtleer (Attrappe: 15 Zeichen); Startumgebung des Läufers mit veraltetem `OPENCODE_PASSWORD` (Attrappe: 18 Zeichen) | `vibe-run.sh <projekt>` | Lauf FERTIG; genau ein `serve`-Aufruf; `OPENCODE_PASSWORD` im Serverprozess abwesend; `OPENCODE_SERVER_PASSWORD` mit Datei-Länge; Gesundheitsprüfung gültig; Agent mit `--server` ohne `--standalone`; kein Kennwort im Klartext |
| `test_project_env_opencode_password_is_absent_from_the_server_env` | AK1b+AK4 | Kennwortdatei nichtleer; **kein** `OPENCODE_PASSWORD` in der Prozessumgebung; `.vibe/project.env` des Testprojekts definiert `OPENCODE_PASSWORD="…"` (genau eine Zeile, doppelt quotiert, damit `set -a; . file; set +a` ihn exportiert) | `vibe-run.sh <projekt>` | wie AK1: der Projektdatei-Wert erreicht den Serverprozess nicht |
| `test_without_inherited_password_b13_behaviour_is_unchanged` | AK2 | Kennwortdatei nichtleer; kein `OPENCODE_PASSWORD` in der Startumgebung | `vibe-run.sh <projekt>` | B13-Verhalten unverändert (Regressionsschutz) |
| `test_server_start_does_not_inherit_opencode_password` | AK3+AK4 | Kennwortdatei nichtleer (33 Zeichen); Startumgebung mit veraltetem Wert; echter tmux auf isoliertem Socket (`TMUX_TMPDIR`); opencode-Attrappe zeichnet ihre eigene Prozessumgebung auf | `vibe server start` | Serverprozess der tmux-Sitzung ohne `OPENCODE_PASSWORD`, `OPENCODE_SERVER_PASSWORD` mit Datei-Länge; kein Kennwort im Klartext in Record oder Ausgabe |

Kennwortwerte in den Tests sind Attrappenliterale; die Größe des
Produktionsfalls (Datei 32 Zeichen, Alt-Export 16 Zeichen) wurde auf
unterscheidbare Attrappenlängen (15/18/33) abgebildet, damit ein geerbter Wert
anhand der Länge vom Datei-Kennwort unterscheidbar ist. Die Assertions prüfen
nur Anwesenheit und Länge, nie den Klartext (AK4).

## Rotphase (Fix-vorher-Stand `10dca46`, separater Weggewerk-Worktree)

Befehl: `python3 -m unittest tests.unit.test_f31_inherited_opencode_password -v`
Ergebnis: **4 Tests, FAILED (failures=3)** — AK2 bleibt grün, die drei
AK-Fälle scheitern exakt an der Erb-Beobachtung (Auszug der Fehlermeldungen):

```
AssertionError: True is not false : Der private Server-Prozess erbte ein OPENCODE_PASSWORD: {'opencode_password_present': True, 'opencode_password_len': 18, 'server_password_present': True, 'server_password_len': 15}
AssertionError: True is not false : Der private Server-Prozess erhielt ein OPENCODE_PASSWORD aus der Projektdatei: {'opencode_password_present': True, 'opencode_password_len': 18, 'server_password_present': True, 'server_password_len': 15}
AssertionError: True is not false : Der Serverprozess der tmux-Sitzung erbte ein OPENCODE_PASSWORD: {'opencode_password_present': True, 'opencode_password_len': 18, 'server_password_present': True, 'server_password_len': 33}
```

Der AK1b-Fall war zusätzlich am Zwischenstand `a0757d8` (vor der
Implementierungsänderung zum Befund M1) rot mit identischem Befund — der
Restpfad über das späte `set -a && . ./.vibe/project.env` besteht unabhängig
vom ersten Fix.

## Grünphase (Fix-Stand, inkl. zweitem `unset` nach dem `project.env`-Einlesen)

Befehl: wie oben. Ergebnis: **4 Tests, OK** (Exit 0), Laufdauer ~12,6 s.

## Regressionsläufe (Coding-Agent, tatsächlich ausgeführt)

- `tests.unit.test_b13_private_server_steering` → 9 OK
- `tests.unit.test_b14_subagent_output_live` → 13 OK
- `tests.unit.test_b13_private_server_runner` → 8 OK, 1 Fehlschlag:
  `test_sandboxed_run_starts_the_private_server_inside_the_sandbox` (AK6) —
  nachgewiesen vorbestehend: identischer Fehlschlag am Fix-vorher-Stand
  `10dca46` (Details in `docs/features/fix-opencode-password-env.md`,
  Bekannte Grenzen).
- Konservierte Rohausgabe der Runner-Suite am Fix-Stand (9 Tests, 1
  vorbestehender AK6-Fehlschlag):
  `docs/reviews/fix-opencode-password-env-evidence-regression-fix-stand.txt`.

## Verbindlicher Full-Lauf (`bash scripts/verify.sh full`)

Ausgeführt auf zwei tmpfs-Prüfständen mit identischer Methode
(`env -u TMPDIR -u VIBE_RUNTIME`, `PATH` mit einem sicheren
`opencode`-Stub vorangestellt, der mit Exit 2 abbricht — der
AK6-Sandbox-Test würde sonst unbeabsichtigt echte Agentenläufe starten;
Ursache und Vorfall in der Feature-Doku, Bekannte Grenzen):

- **Fix-Stand** (rsync-Kopie des Worktrees, HEAD `5128864`, plus
  `.vibe/project.env`): **Ran 1770 tests — FAILED (failures=5,
  errors=2)**, Prüf-Exit 5.
  Rohausgabe (Auszug):
  `docs/reviews/fix-opencode-password-env-evidence-full-fix-auszug.txt`.
- **Baseline-Stand `10dca46`** (Fix-vorher, gleiche Testdateien und
  gleiche `project.env`): **Ran 1770 tests — FAILED (failures=8,
  errors=2)**, Prüf-Exit 5.
  Rohausgabe (Auszug):
  `docs/reviews/fix-opencode-password-env-evidence-full-base-10dca46-auszug.txt`.

**Fail-Mengenvergleich:** Die Mengen sind identisch bis auf die drei
F31-Fälle. Die Baseline scheitert zusätzlich an
`test_inherited_opencode_password_is_absent_from_the_server_env` (AK1),
`test_project_env_opencode_password_is_absent_from_the_server_env`
(AK1b) und `test_server_start_does_not_inherit_opencode_password`
(AK3) — genau der behobene Defekt; AK2 ist an beiden Ständen grün.
Am Fix-Stand sind diese drei Fälle grün, und **keiner** der übrigen
Fehlschläge ist neu. Die übrigen 5 Failures + 2 Errors sind an beiden
Ständen gleich und in der Feature-Doku (Bekannte Grenzen) einzeln
eingeordnet: Prüfstandsartefakte (fehlendes ungetracktes `FEEDBACK.md`
in den beiden 2-Errors), der durch den Stub verursachte AK6-Modus sowie
umgebungsabhängige Behauptungen (`test_ap04` pi-Hinweis, `test_b4`
HOME-Berechtigungen, `test_release` Home-Pfad-Scan, `test_sandbox`
echtes bwrap), die Codepfade betreffen, die der F31-Fix nicht berührt.

## Aufräumen

Rotphasen-Weggewerke (`/tmp/opencode/f31-red2`) wurden nach jedem Nachweis
entfernt; keine Testprozesse oder Serverreste blieben bestehen.
