# Review F14 — Runde 1

Reviewer: code-reviewer_glm (Task-Aufruf in dieser Sitzung)
Ausgangscommit: e286309
Geprüfter Stand: Arbeitsbaum mit F14-Änderungen (Diff `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/f14-full.diff`)

## Antwort des Reviewers (unverändert)

# Review-Ergebnis

## Zusammenfassung
- Kritisch: 0
- Hoch: 0
- Mittel: 0
- Gering: 3
- Urteil: **PASS** (mit 3 Gering-Einstufungen als Restbefunde)

Der vollständige Diff (`/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/f14-full.diff`, 1573 Zeilen) wurde vollständig gelesen, und alle im Diff enthaltenen Dateien wurden direkt im Arbeitsbaum verifiziert (Identität mit dem Diff stichproben- und abschnittsweise bestätigt, kein Auseinanderfallen). Die Shell-Berechtigung wurde mir in dieser Sitzung verweigert („Permission denied: shell“); Git-Befehle und Testläufe konnte ich daher nicht selbst ausführen — sämtliche Test- und Prüf-Ergebnisse sind Nachweise des Coding-Agenten, nicht meine eigenen Beobachtungen. Die Trilium-Dokumentation habe ich dagegen selbst über die MCP-Schnittstelle geprüft.

## Abnahmekriterien

| Kriterium | Status | Umsetzung (Datei:Zeile) | Test (Datei:Methode) / Nachweis |
| --- | --- | --- | --- |
| Neuer Projekttyp „Rebuild“ zur Analyse und plattformübergreifenden Neuerstellung | PASS | `templates/rebuild/.vibe/project.env:1` (`TYPE=rebuild`), `templates/rebuild/AGENTS.md:4-8`, dynamische Erkennung über bestehenden Code `bin/vibe.py:1229-1230, 1280-1295` (typgesteuert per `templates/<typ>`, keine Codeänderung) | `tests/unit/test_rebuild_profile.py` `ProfileTest.test_rebuild_type_creates_agents_parity_rules_and_toolcheck` (assertet `rebuild` in `cli.types()`); `tests/browser/test_rebuild_project_ui.py` `RebuildProjectBrowserTest.test_rebuild_type_is_selectable_and_creates_the_profile` — beide laut geliefertem Testoutput OK |
| Fünf dem Paketvorschlag entsprechende Agentenrollen (Elucidation/Orchestrator + acht Subagenten, Parität, Paketierung, CI) | PASS | Neun Dateien unter `templates/rebuild/.opencode/agents/rebuild-*.md` (Orchestrator `mode: primary`, Rest `mode: subagent`, jeweils mit Artefakt-/Nachweisbindung) | Derselbe Unit-Test: `EXPECTED_AGENTS` exakt gleich sein und jeder Agent durch `cli.agent_validate()` prüft |
| Fachliche Funktionsweise 1:1; technische Abweichungen begründet | PASS | `templates/rebuild/docs/parity.md:1-12` (Zitat 1:1-Regel), `templates/rebuild/AGENTS.md:6-10`, `templates/rebuild/.opencode/agents/rebuild-spec.md:13` | Unit-Test assertet `"1:1"` und `"Speicherstände"` in `docs/parity.md` / `AGENTS.md` |
| Kompatibilität mit originalen Speicherständen (lesen + schreiben, unbekannte Felder, Migration nur mit Backup/Rückweg) | PASS | `templates/rebuild/docs/parity.md:18-39` (Regeln), `templates/rebuild/.opencode/agents/rebuild-parity.md:12-13` (Original lesen, speichern, erneut lesen, Felder erhalten, gegenseitig öffnen), `templates/rebuild/AGENTS.md:11-13` | Unit-Test (Inhalt von parity.md), Parallelitäts-Agent regelt dieselben Regeln |
| Werkzeugumgebung prüfen und bei Fehlen aufsetzen | PASS | `templates/rebuild/scripts/rebuild-env.py` (check/plan/setup: 92-146, 227-232 / 248-266), `REBUILD_REQUIRED_GROUPS="core analyse"` in `.vibe/project.env:16`, `--setup` nur mit `--yes`, erst re-check, Manual-Werkzeuge werden nicht als installiert deklariert | 11 Unit-Tests u.a. `test_missing_required_tool_is_reported_and_blocks`, `test_cli_setup_without_confirmation_changes_nothing` (Exit 2, dnf nicht aufgerufen); Grenze „Ghidra/linuxdeploy/appimagetool werden nicht automatisch heruntergeladen“ ist ehrlich in `docs/features/F14.md` (Grenzen-Abschnitt, Zeilen 213-220) disclosed |
| Keine UI-Codeänderung; Typ dynamisch auswählbar | PASS | Kein Commit von `bin/vibe-web.py`; Dynamik über `bin/vibe.py:1229-1230` bestätigt (liest Ordner unter TPL) | Browser-Test (echtes Dashboard, isoliertes temp VIBE, eigener Port, Playwright-Assertion auf `rebuild`-Option) — laut geliefertem Output OK |
| Manifest, Projekt- und Trilium-Dokumentation aktuell | PASS | `docs/import-manifest.json` (`bin/vibe_sandbox.py` neu 20552 Bytes, 14 neue Vorlagedateien, F14-Eintrag), `docs/baseline.md:272`, `docs/trilium-index.md:37` | Manifest zählt exakt 46 `sha256`-Einträge = „46 Dateien“-Aussage; **Trilium-Notiz `ajp3HtOEv9k1` „F14 Project Type: Rebuild“ von mir selbst via MCP geprüft**: existiert, Inhalt deckt Profil, Werkzeugprüfer und Parität/Speicherstände ab (Stand/UTC-Modified 2026-10-31) |
| Konventionen: Isolation, keine Vorab-Commit-Pflichtdateien | PASS | Template entspricht `web`/`openwrt`-Konvention (`AGENT=coding-agent_deepseek`, `REVIEWER=code-reviewer_glm`, MAX_PACKAGES-Hinweis); Tests nutzen keine produktive HOME/VIBE-Konfiguration, kein Netz im Prüfmodus | `scripts/verify.sh quick` (geliefert): „keine Geheimnisse erkannt“, 46/46 Manifests stimmen |

Umfang/Exklusivität: Der Diff enthält ausschließlich die 5 nebenbefohlenen/geänderten + 17 neuen Paketdateien; die als vorbestehend deklarierten Dateien (`.vibe/project.env`, `SPEC.md`, `TICKETS.md`, 8 PNGs) sind **nicht** im Diff — die Ausschlussvorgabe ist erfüllt.

## Ergebnisses

- [Gering] `templates/rebuild/scripts/rebuild-env.py:288` — `--plan` gibt überall Erfolg (Exit 0) zurück, auch wenn kein unterstützter Paketmanager gefunden wurde
  - Nachweis: Der `--plan`-Zweig von `main()` endet mit `return 0`, obwohl vorher `plan.get("error")` gesetzt und nur als Text ausgedruckt worden war. Skripte, die auf den Exit-Code von `--plan` abfragen, können den Fehler „Kein unterstützter Paketmanager“ nicht erkennen. Der Informationswert bleibt erhalten, aber die Fehlermeldung ist eine falsche Erfolgssignalisierung.
  - Vorgeschlagene Korrektur: Definiere und dokumentiere einen abweichenden Exit-Code (z.B. 3) für „kein Paketmanager / Plan unvollständig” und ergänze einen Test (`ValueError`-Pfad für `--check` und `--setup` ist inzwischen abgedeckt, `--plan` nicht).

- [Gering] `templates/rebuild/scripts/rebuild-env.py:274` — Exit-Regel für `--setup --yes` bei verbleibenden manuellen Werkzeugen hat keinen test
  - Nachweis: Die ehrliche Erfolgssignalisierung im CLI um „`return 0 if after["ok"] and not plan["manual"] else 1`“ (Erfolg nur, wenn nach re-check alles grün und keine manuellen Werkzeuge übrig) wird nur auf Funktionsebene (`setup()`) geprüft; ein CLI-Test für `--setup --yes` existiert nicht. Die zentrale Zusage „nicht bestanden, solange manuelle Schritte übrig“ könnte durch Regression unbemerkt brechen.
  - Vorgeschlagene Korrektur: ergänze einen CLI-Test mit Fake-`dnf` und einem manuellen Werkzeug: Exit bleibt 1, solange MANUELL-Schritte offen sind und keine Installationsbehauptung erscheint.

- [Gering] `docs/features/F14.md:232` — veraltete, in der Formulierung ungenaue Referenz zur Trilium-Notiz-ID
  - Nachweis: Der Abschnitt „Dokumentation“ schreibt „(die Notiz-ID wird in `docs/trilium-index.md` ergänzt)“, obwohl derselbe Arbeitspaket die ID `ajp3HtOEv9k1` bereits in `docs/trilium-index.md:37` einträgt. Die Trilium-Notiz selbst verweist vorläufig auf „wird nach dem Commit ergänzt“ (korrekt für die nachfinale Abnahme-Rituals). Reine Dokumentations-Genauigkeit; kein Morphings.
  - Vorgeschlagene Korrektur: Formulierung in `docs/features/F14.md` in der Indikativ-Form („ist in `docs/trilium-index.md` eingetragen: `ajp3HtOEv9k1`“) ändern; nach dem finalen Commit den Commit-Verweis in der Trilium-Notiz nachziehen.

## Verifikation
- Durchgesehener Änderungsumfang: `e286309..Arbeitsbaum` — beurteilt anhand des gelieferten vollständigen Diffs `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/f14-full.diff` (komplett gelesen) **und** durch direkte Kontrolle des Arbeitsbaums. `git status`/`git diff`/`git log` konnte ich selbst nicht ausführen (Shell-Berechtigung verweigert); die Identität der 18 Arbeitspaketdateien wurde stichprobenweise durch Dateilesen verifiziert und keine Abweichung vom Diff festgestellt.
- Von mir ausgeführte Git-Befehle: **keine** — Berechtigung verweigert; kein eigenes Status-/Diff-Ergebnis verfügbar.
- Übermittelte Prüfungen (gelieferte Ausgaben, nicht von mir wiederholt): rote Phase (4 Tests, 1 failure + 4 errors), Fokusrung (11 Unit-Tests, 10 Sandbox-Tests, 1 Browser-Test OK), vollständige Browser-Suite (48 Tests, 1 vorbestehender `test_agents_ui`-Fehler, am Basis-Commit identisch reproduziert), `verify.sh quick` (Exit 0, 46/46 Manifeste, Syntax, Geheimnis-Check), `verify.sh full` (655 Tests, exit 5; identische Fehlermenge am Basis-Commit: 644 Tests, die 15 = 8 failures + 7 errors).
- Selbst tatsächlich durchgeführte Prüfungen: Trilium-Notiz `ajp3HtOEv9k1` via MCP `get_note` geprüft (Titel, Inhalt, Einordnung passen). Zusätzliche Querverweise: `bin/vibe.py:1229-1295` (dynamische Typenerkennung, copy_tree mit `{{NAME}}`-Ersetzung), `bin/vibe_sandbox.py:75-79,116-120` (rebuild-Defaults + Caches), 对照 `templates/web|openwrt` Kilometer enable.
- Nicht gerechtfertigt: Manifest-sha256 selbst neu berechnet; Skripte und Tests selbst ausgeführt; `verify.sh quick/full` nicht wiederholt; vorbestehende Fehler-Baseline nicht durch eigene Läufe bestätigt.
- Kern inspections-Standorte: `templates/rebuild/**` (14 Dateien), `templates/rebuild/scripts/rebuild-env.py` (inkl. install_plan/setup/parse- und sudo-Logik, Werte-Kontrollliste), `tests/unit/test_rebuild_profile.py`, `tests/browser/test_rebuild_project_ui.py`, `tests/unit/test_sandbox.py`, `bin/vibe_sandbox.py`, `bin/vibe.py`, `docs/import-manifest.json`, `docs/features/F14.md`.
- Restliche Risiken: (1) 15 vorbestehende Fehlzustände in `verify.sh full` verhindern auf beiden Commits die Browserstufe — der Ersatznachweis über die separate Browsersuite ist geliefert, nicht von mir wiederholt; (2) Sachaussagen über Wine/Ghidra-Funktion sind ausdrücklich als Grenze im Feature-Dokument markiert (kein echtes Beispielprojekt); (3) `--plan`/`--setup --yes`-Exitcode-Semantik als Gering-Befunde oben.
