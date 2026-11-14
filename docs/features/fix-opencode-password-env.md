# Fix — Geerbtes `OPENCODE_PASSWORD` blockierte den privaten opencode-Server

Stand: 2026-11-14
Ausgangscommit: `10dca46` (`B14: Subagenten-Ausgabe live über den privaten Laufserver`)
Arbeitsbranch: `fix/stale-opencode-password` (Implementierung), `fix/f31-tests-docs` (Tests und Doku)
Implementierungscommit: `88509a0` (`F31: Geerbtes OPENCODE_PASSWORD vor dem Serverstart entfernen`)
Anlass: Läufer-Defekt beim Lauf `vibe-20261114-192106-c11f59` (Paket F31, „Der private opencode-Server konnte nicht gestartet werden“)

## Fehlerbild

Der Lauf für Paket F31 brach unmittelbar nach dem Start ab:

```
ABBRUCH: Der private opencode-Server konnte nicht gestartet werden
```

Belegt aus den Protokollen (opencode-Log, run `ca1385bb`, Port 38315):

| Zeit | Ereignis |
| --- | --- |
| 19:21:07 | `opencode serve --hostname 127.0.0.1 --port 38315` startet |
| 19:21:07–22 | 71 Gesundheitsanfragen im 0,2-s-Takt — **alle mit HTTP 401** beantwortet |
| 19:21:22 | Server wird sauber per SIGTERM beendet (Health-Fenster von 15 s abgelaufen) |
| 19:21:23 | Lauf bricht mit „nicht gesund“ ab |

Der Server war erreichbar und lief die vollen 15 Sekunden — er lehnte nur die
Authentifizierung ab. Es lag weder am Modelllimit noch am Start-Timing.

## Ursache (experimentell nachgewiesen)

1. **Veraltete Kennwortvariablen in der Startumgebung.** Die
   Dashboard-/Container-Umgebung enthielt `OPENCODE_PASSWORD` und
   `OPENCODE_SERVER_PASSWORD` mit einem 16-Zeichen-Wert, während die
   Kennwortdatei `$RUNTIME/opencode.password` 32 Zeichen hat
   (`secrets.token_urlsafe(24)`, Stand 8. Nov). Die Werte wurden während der
   gesamten Analyse nie ausgegeben (nur Längen- und Hashvergleich).
2. **opencode v2.3.0 honor `OPENCODE_PASSWORD` und lässt sie vor
   `OPENCODE_SERVER_PASSWORD` gelten.** Serientests:
   * Server mit Datei-Kennwort in `OPENCODE_SERVER_PASSWORD` **plus** geerbtem
     `OPENCODE_PASSWORD` → curl mit Datei-Kennwort: **401**, curl mit
     geerbtem Wert: **200**.
   * Nur `OPENCODE_PASSWORD` gesetzt → curl mit Datei-Kennwort: **401**.
   * Nur `OPENCODE_SERVER_PASSWORD` gesetzt (jede Transportvariante: direkt,
     setsid-Kette, tmux-Kette, bwrap-Sandbox) → **200**.
3. **Injektionsweg.** Der Lauf läuft in einer tmux-Sitzung (`bash -lc`,
   sourced `~/.bashrc`), deren Umgebung vom Dashboard-Prozess erbt. Der Läufer
   überschrieb nur `OPENCODE_SERVER_PASSWORD` aus der Kennwortdatei —
   `OPENCODE_PASSWORD` blieb unangetastet und erreichte den Serverprozess
   unverändert. Die Gesundheitsprüfung sendete das Datei-Kennwort (32
   Zeichen), der Server erwartete den geerbten Alt-Wert (16 Zeichen) —
   dauerhaft 401.

Frühere Läufe waren nicht betroffen: Der vorherige Lauf lief noch mit dem
alten Läufer im `--standalone`-Modus ohne privaten Server; die B13-Logik war
um 19:20:28 installiert worden, 19:21 war ihr erster produktiver Einsatz.

## Umsetzung

| Datei | Änderung |
| --- | --- |
| `bin/vibe-run.sh` | `unset OPENCODE_PASSWORD` vor der Kennwortbehandlung des privaten Servers; Kommentar erklärt den Vorrang-Mechanismus |
| `bin/vibe` | derselbe Schutz im tmux-Innenbefehl des gemeinsamen Servers (`vibe server start`, F19) |
| `docs/import-manifest.json` | Bytes und SHA-256 für `bin/vibe` und `bin/vibe-run.sh` aktualisiert |

Das Kennwort kommt in beiden Pfaden weiterhin ausschließlich aus der
Laufzeitdatei; der geerbte Wert wird nicht „korrigiert“, sondern entfernt.
Damit ist die Server-Auth unabhängig davon, welche Alt-Exporte die
Startumgebung (Dashboard, Container, Sitzung) mitführt.

## Akzeptanzkriterien und Testherkunft

Die Testfälle stammen vom unabhängigen Test-Agenten
(`tests/unit/test_f31_inherited_opencode_password.py`, Ergänzung der
opencode-Attrappe in `tests/unit/runner_support.py`: das `listening`-Ereignis
notiert Anwesenheit und Länge beider Kennwortvariablen, nie den Wert). Der
Test-Agent wurde durch das Free-Limit zweimal unterbrochen; die Testfälle
wurden vollständig von ihm angelegt und vom Coding-Agenten gemäß Projektregel
nur ausgeführt und berichtet.

| Fall | AK | Vorbedingung | Aktion | Erwartung | Ergebnis |
| --- | --- | --- | --- | --- | --- |
| `test_inherited_opencode_password_is_absent_from_the_server_env` | AK1+AK4 | Kennwortdatei nichtleer; Startumgebung des Läufers mit veraltetem `OPENCODE_PASSWORD` | `vibe-run.sh <projekt>` | Lauf FERTIG; genau ein `serve`-Aufruf; `OPENCODE_PASSWORD` im Serverprozess abwesend; `OPENCODE_SERVER_PASSWORD` mit Datei-Länge; Gesundheitsprüfung gültig; Agent mit `--server` ohne `--standalone`; kein Kennwort im Klartext | **OK** auf `88509a0`, **FAIL** auf `10dca46` (geerbter Wert beobachtet) |
| `test_without_inherited_password_b13_behaviour_is_unchanged` | AK2 | Kennwortdatei nichtleer; kein `OPENCODE_PASSWORD` in der Startumgebung | `vibe-run.sh <projekt>` | B13-Verhalten unverändert | **OK** auf beiden Ständen |
| `test_server_start_does_not_inherit_opencode_password` | AK3+AK4 | Kennwortdatei nichtleer; Startumgebung mit veraltetem `OPENCODE_PASSWORD`; echter tmux auf isoliertem Socket; opencode-Attrappe | `vibe server start` | Serverprozess der tmux-Sitzung ohne `OPENCODE_PASSWORD`, mit Datei-Kennwort-Länge; kein Kennwort im Klartext | **OK** auf `88509a0`, **FAIL** auf `10dca46` |

Rotphasennachweis: Auf dem Fix-vorher-Stand `10dca46` (eigener Weggewerk-
Worktree) scheitern AK1 und AK3 exakt an der beobachteten Erbung
(`opencode_password_present: True`, Länge des veralteten Werts), während AK2
grün bleibt — die Fehlschläge betreffen also genau die Fixstellen.

Ergebnisse auf dem Fix-Stand (tatsächlich ausgeführt):

- `python3 -m unittest tests.unit.test_f31_inherited_opencode_password -v`:
  **3/3 OK**.
- Regression `tests.unit.test_b13_private_server_steering` (9 OK),
  `tests.unit.test_b14_subagent_output_live` (13 OK),
  `tests.unit.test_b13_private_server_runner` (8 OK, 1 Fehlschlag: AK6
  Sandbox-Test, siehe Bekannte Grenzen).
- `bash scripts/verify.sh quick`: Exit 0.

## Bekannte Grenzen

- **AK6-Sandbox-Test scheitert in dieser Umgebung (vorbestehend):**
  `test_sandboxed_run_starts_the_private_server_inside_the_sandbox` scheitert
  identisch am Fix-vorher-Stand `10dca46` — es ist also keine Regression des
  Fix. Ursachenanalyse: Innerhalb des bwrap-Namespaces ist das
  Fixture-`fakebin` nicht gebunden; die PATH-Auflösung von `opencode` trifft
  deshalb auf die echte Installation, der Test startet unbeabsichtigt einen
  echten Agentenlauf und erreicht sein Laufzeitlimit. Beim ersten
  Regressionlauf hinterließ das verwaiste echte-Agent-Prozesse; sie wurden
  gestoppt und alle Fixture-Reste entfernt (keine Commits, keine
  Trilium-Schreibvorgänge, nur das freie Modell `glm-5.3-flash-free`). Der
  B13-Dokumentation sind umgebungsabhängige Sandbox-Testgrenzen bereits
  bekannt; die hermetische Abschottung des Sandbox-Fixtures (Attrappe
  innerhalb des Namespace erreichbar machen) ist Folgearbeit für den
  Test-Agenten.
- Der Vorrang von `OPENCODE_PASSWORD` ist empirisch an opencode v2.3.0
  belegt (Serientests), nicht aus der opencode-Quelle verifiziert. Verhält
  sich eine künftige opencode-Version anders, bleibt der Fix dennoch
  korrekt: Ohne geerbte Belegung entscheidet ausschließlich die
  Kennwortdatei.
- Die Alt-Exporte (16 Zeichen) liegen weiterhin in der Sitzungs-/Container-
  Umgebung des Nutzers. Der Fix macht sie für die Server-Auth wirkungslos;
  sie müssen nicht entfernt werden, können aber bei Gelegenheit aufgeräumt
  werden.
- Beim Laufabbruch schreibt der Läufer den letzten HTTP-Status der
  Gesundheitsprüfung nicht ins Protokoll; die Diagnose „401 statt nicht
  erreichbar" erforderte manuelle Loganalyse. Verbesserungsvorschlag für
  Folgearbeit, nicht Teil dieses Fixes.

## Nachweise

| Nachweis | Stand |
| --- | --- |
| Funktionsnachweis des Fix | Kennwortblock aus der geänderten `vibe-run.sh` mit „infizierter“ Elternumgebung (Alt-`OPENCODE_PASSWORD`) ausgeführt → Serverstart über die originale setsid-Kette → Gesundheitscheck **200**. Ohne Fix war derselbe Aufbau **401**. |
| `bash scripts/verify.sh quick` | Exit 0 (Importmanifest, Syntax 164 Python-/8 Bash-/6 JSON-Dateien, keine Geheimnisse) nach Manifestaktualisierung. |
| Unit-Tests | 3/3 OK (`test_f31_inherited_opencode_password`); Regression 30/31 OK, 1 vorbestehender umgebungsabhängiger Sandbox-Fehlschlag (identisch am Fix-vorher-Stand, Details oben) |
| Unabhängiger Review | ausstehend (nach Abschluss des parallelen produktiven Laufs) |
| Trilium-Dokumentation | <!-- TRILIUM-BLOCK: wird ergänzt --> |
