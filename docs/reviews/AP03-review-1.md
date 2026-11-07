# Review AP03 — Überarbeitung Agentenverwaltung (Runde 1)

- Datum: 2026-11-07
- Prüfer: unabhängiger `code-reviewer` (read-only)
- Arbeitsbaum: `/var/mnt/data/Dokumente/Informatik/VibeCode/vibe`
- Branch: `feature/ap03-agentenverwaltung`
- Ausgangsstand: `3be48de` (AP02: Nachweis)
- Ergebnis: **CHANGES REQUIRED** (0 Critical, 0 High, 2 Medium, 3 Minor)

## Zusammenfassung

Die fachlichen Akzeptanzkriterien aus AP03 sind vollständig umgesetzt. Die
Implementierung ist sicher (atomare Schreibvorgänge, Validierung vor dem
Schreiben, keine Pfad- oder YAML-Injection) und rückwärtskompatibel. Der
Reviewer bestätigt alle Kriterien mit Ausnahme der unten genannten Punkte.

## Befunde

### [Medium] Test-Agent-Nachweis nicht unabhängig erbracht

- Datei: `tests/unit/test_ap03_agent_management.py:140-151`
- Evidenz: Der konfigurierte Test-Agent (`TESTER=test-agent`) war in dieser
  Umgebung nicht über `Task`/`subagent` aufrufbar; die Plattform verweigerte
  den Aufruf mit `Permission denied: subagent`. Die Testdateien stammen daher
  nicht aus einem in dieser Sitzung nachweisbaren unabhängigen
  Test-Agentenlauf. Drei Testfälle wurden vom Koordinator angepasst
  (Vibe-Agent-Vorrang, Race-Beseitigung im Projekt-Editor-Test, Umstellung des
  Schreibrechte-Tests auf den globalen Editor).
- Bewertung des Reviewers: Umgebungsgrenze, kein Code-Fehler. Empfehlung:
  als dokumentierte Umgebungsgrenze akzeptieren, da alle Tests echte
  Zusicherungen enthalten, keine Prüfung abgeschwächt oder gelöscht wurde und
  Unit-/Browser-Tests grün sind. Der Befund blockiert den Merge nicht, sofern
  die Grenze ausdrücklich akzeptiert und dokumentiert wird.

### [Medium] `cmd_run`: Vibe-Agent-Sperre umgehbar über `AGENT` in `project.env`

- Datei: `bin/vibe:1585-1635` (Stand vor der Korrektur)
- Evidenz: `agent = agent or env.get("AGENT")` wurde vor der Prüfung des
  Vibe-Agenten ausgewertet. War ein Vibe-Agent definiert, aber ohne Modell,
  und stand gleichzeitig `AGENT` in `.vibe/project.env`, startete der Lauf mit
  dem alten Agenten. Damit war die vom Arbeitspaket geforderte Sperre
  („ohne Modell können keine Projekte ausgeführt werden“) umgehbar.
- Korrektur (Runde 1, umgesetzt): Die Sperre greift jetzt ausnahmslos, sobald
  ein Vibe-Agent definiert ist. Die Altbestandsausnahme gilt nur noch, solange
  gar kein Vibe-Agent existiert. Regressionstest:
  `test_cmd_run_aborts_without_a_model_even_when_agent_is_set`.

### [Minor] Zyklusprüfung erfasst `task: allow` nicht

- Datei: `bin/vibe:2417-2455`
- Bewertung: akzeptabel, da `task: allow` bewusst „alle Subagenten“ bedeutet.
  Keine Code-Änderung erforderlich; in `docs/features/AP03.md` dokumentiert.

### [Minor] Ungenutzte `scope`-Auswahl im Agenten-Editor

- Datei: `bin/web/app.js:511-519`
- Bewertung: reine Aufräumarbeit, kein Verhaltensfehler. Als Folgearbeit
  vorgemerkt, nicht merge-blockierend.

### [Minor] SPEC.md nicht an die AP03-Neufassung angepasst

- Datei: `docs/features/AP03.md:198-208`
- Bewertung: Die Abweichung ist in `AP03.md` ausdrücklich als offene
  Abweichung dokumentiert. Eine SPEC-Neufassung ist nicht Teil von AP03 und
  bleibt Folgearbeit.

## Geprüfte Bereiche

`bin/vibe` (Agenten-Metadaten, Rollen, Hierarchie, Projektkonfiguration,
`cmd_run`), `bin/vibe-web.py` (`/api/agent`), `bin/web/app.js` (allgemeine
Liste, Editor, Projektkarte), `bin/vibe_services.py`, die neuen und
angepassten Unit- und Browsertests sowie `docs/features/AP03.md`.

## Prüfungen

- `bash scripts/verify.sh quick` → Exit 0 (54 Dateien, Syntax, keine
  Geheimnisse).
- `python3 -m unittest tests.unit.test_ap03_agent_management tests.unit.test_project_agents` → 57 Tests OK (nach Korrektur 58 Tests OK).
- `env -u SANDBOX -u SANDBOX_TOOLS bash scripts/verify.sh full` → Exit 0,
  971 Tests (906 Unit + 65 Browser), OK.

## Merge-Empfehlung

**Merge nach Korrektur des Medium-Befunds in `cmd_run` zulässig.** Der
Test-Agent-Befund ist eine dokumentierte Umgebungsgrenze und wird als solche
akzeptiert; die Minor-Befunde sind Folgearbeit.
