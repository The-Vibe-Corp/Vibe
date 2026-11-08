# V-025 — Testbericht des unabhängigen Test-Agenten

Datum: 2026-11-08
Testdatei: `tests/unit/test_v025_agent_start_repair.py`
Testbefehl: `python3 -m unittest tests.unit.test_v025_agent_start_repair -v`

Der Test-Agent hat die Fälle aus `TICKETS.md` (V-025), `SPEC.md` und
`AGENTS.md` abgeleitet und die Tests vor der Implementierung geschrieben. Er
hat keine Produktionsdateien, bestehenden Tests oder Konfigurationen geändert.

## Testfälle

| Test | Akzeptanz | Vorbedingung | Aktion | Erwartetes Ergebnis |
| --- | --- | --- | --- | --- |
| `test_missing_agent_falls_back_to_vibe_and_repairs_project_env` | 1 | `AGENT=alter-agent` ohne globale Agentendatei; Vibe-Agent aktiv | `cmd_run("proj")` | Start mit `vibe-agent`; `AGENT=vibe-agent`; übrige Zeilen unverändert |
| `test_repair_preserves_other_lines_verbatim` | 1 | wie oben, zusätzlich Kommentar- und Fremdzeilen | `cmd_run("proj")` | nur die `AGENT`-Zeile wird ersetzt |
| `test_global_but_inactive_agent_is_repaired` | 2 | `AGENT=tester` global vorhanden, im Projekt nicht aktiv | `cmd_run("proj")` | Start mit `vibe-agent`; `AGENT` korrigiert |
| `test_repair_message_names_old_and_new_agent` | 6 | wie AK1 | `cmd_run("proj")` | Ausgabe enthält `alter-agent` und `vibe-agent` |
| `test_active_agent_is_used_and_env_stays_unchanged` | 3 | `AGENT=tester` global und im Projekt aktiv | `cmd_run("proj")` | Start mit `tester`; Projektdatei unverändert |
| `test_explicit_inactive_agent_is_rejected_without_writing` | 4 | `cmd_run("proj", "tester")`, `tester` nicht aktiv | Aufruf wie angegeben | `SystemExit`, kein Start, Projektdatei unverändert |
| `test_write_error_still_starts_with_vibe_and_reports_error` | 5 | Schreibzugriff auf `.vibe/project.env` verweigert | `cmd_run("proj")` | Start mit `vibe-agent`, Fehlerhinweis, Datei unverändert |
| `test_shipped_project_templates_contain_no_agent_entry` | Vorlagen | Vorhandene `templates/*/.vibe/project.env` | Vorlagen zeilenweise prüfen | keine wirksame `AGENT=`-Zeile; mindestens eine Vorlage gefunden |
| `test_repair_preserves_crlf_line_endings` | Format | Projektdatei mit CRLF | `cmd_run("proj")` | nur die AGENT-Zeile ersetzt; alle CRLF und übrigen Bytes erhalten |
| `test_quoted_agent_value_is_replaced` | Format | `AGENT="alter-agent"` | `cmd_run("proj")` | `AGENT=vibe-agent` unquoted; übrige Zeilen unverändert |
| `test_repair_rejects_invalid_agent_names` | Namensschutz | Gültige Projektdatei; Namen mit Leerzeichen bzw. Shellzeichen | direkter Aufruf von `repair_project_agent` | Fehler mit Agentenbezug; Datei bytegleich unverändert |

Isolation: temporäres `VIBE`/`HOME`, leere Modellliste, Attrappen für
`tmux_has`, `run`, `run_registry`, `sandbox_status`,
`ensure_opencode_password` und die Regel-/Testagent-Ergänzung. Kein
Modellaufruf, kein tmux-Start und kein Netzzugriff.

## Rot-Zustand vor der Implementierung

```
python3 -m unittest tests.unit.test_v025_agent_start_repair -v
```

Ergebnis: `Ran 7 tests`, `FAILED (errors=5)`, Exit-Code 1.

Die fünf Fehler entsprachen der zu behebenden Lücke:
`SystemExit: Agent 'alter-agent'/'tester' ist für dieses Projekt nicht
ausgewählt oder nicht konfiguriert.`

Bereits grün waren die Regressionsfälle für AK3 (gültiger, aktiver Agent) und
AK4 (ausdrücklich übergebener, nicht aktiver Agent).

Der Vorlagentest wurde nach dem Entfernen der `AGENT`-Zeilen ergänzt. Der
Test-Agent hat die Prüfregel zusätzlich auf die Inhalte des Ausgangscommits
`ee20120` angewandt: Dort enthielten alle sechs Vorlagen
`AGENT=coding-agent_deepseek`, die Regel war also rot. Er weist ausdrücklich
darauf hin, dass er den neuen Test nicht mehr selbst gegen den unveränderten
Arbeitsbaum laufen sah, weil die Implementierung während seiner Nachtragsarbeit
bereits im Arbeitsbaum lag.

## Nachtrag nach Review-Runde 1

Der Reviewer benannte fehlende Tests für CRLF-Dateien, gequotete
`AGENT`-Werte und den Namensschutz der Reparaturfunktion. Der Test-Agent
ergänzte dafür drei Fälle. Der CRLF- und der Quoted-Test waren gegen den
damaligen Stand grün; der Namensschutztest war erwartungsgemäß rot:

```
Ran 11 tests, FAILED (failures=2), Exit-Code 1
AssertionError: (<class 'ValueError'>, <class 'SystemExit'>) not raised
```

Die beiden Subtest-Fehler betrafen `agent='mit leerzeichen'` und
`agent='boese;rm -rf /'`. Nach der Prüfung in `repair_project_agent` sind alle
Tests grün.

## Grün-Zustand nach der Implementierung

```
python3 -m unittest tests.unit.test_v025_agent_start_repair -v
```

Ergebnis: `Ran 11 tests`, `OK`, Exit-Code 0.

Zusätzlich ausgeführt:

```
python3 -m unittest tests.unit.test_ap03_agent_management \
  tests.unit.test_agent_management tests.unit.test_project_agents \
  tests.unit.test_v025_agent_start_repair -v
```

Ergebnis: `Ran 95 tests`, `OK`, Exit-Code 0.

`bash scripts/verify.sh quick`: Exit 0 (56 Manifestdateien, 110 Python-,
8 Bash- und 6 JSON-Dateien syntaktisch geprüft, keine Geheimnisse).

## Verbleibende Lücken

- Mehrfache `AGENT=`-Zeilen sind nicht abgedeckt; die Reparatur ersetzt nur den
  ersten Treffer. Das Ticket fordert keine Behandlung mehrfacher Einträge.
- Eine fehlende `AGENT`-Zeile (bestehender Vibe-Standardfall) ist nicht erneut
  getestet; ebenso wenig, dass `agents.json` beim Reparieren unverändert
  bleibt.
- Die exakte Formulierung des Schreibfehlerhinweises ist bewusst nicht wörtlich
  festgeschrieben; geprüft werden ein Hinweis, die unveränderte Datei und der
  erfolgreiche Start.
- Auskommentierte `# AGENT=...`-Zeilen gelten für die Vorlagenprüfung nicht als
  Verstoß, weil sie beim Anlegen keine Wirkung haben.
