# Review GH-96 „Bugs from GH-89" — Runde 1 (korrigiert)

**Worktree:** `/var/log/custom/vibe-dev/worktrees/vibe-GH-96-CJejp7` (Branch `feature/korbat/gh-96`, HEAD = Start-Commit `f2dd725`; Änderungsset als Arbeitskopienänderung plus neue ungetrackte Datei). **Geprüftes Set:** 7 geänderte Dateien (`bin/vibe-run.sh`, `docs/features/B13.md`, `docs/features/B1.md`, `docs/import-manifest.json`, `tests/unit/test_agent_management.py`, `tests/unit/test_project_agents.py`, `tests/verify-baseline.json`) plus neu `docs/features/GH-96.md`; `TICKET-GH-96.json` ist Runner-State. Keine fremden Änderungen im Diff. Zusätzlich zur Runde 1 geprüft: die Wortsinn-Korrektur in `GH-96.md` („its CLI-evidence note names GH-89 explicitly") gemäß Vorschlag 1 — reine Wortlautkorrektur ohne Bedeutungsänderung, im Umfang der Review-Suggestion bleibend.

## Kurzfassung

Die AK9-Wiederherstellung ist korrekt und vollständig umgesetzt: Die neue Verzweigung (`HAS_PROJECT_MODELS != 1 && HAS_SERVER_PASSWORD = 1 && server_is_up`, `bin/vibe-run.sh:1264-1269`) erfüllt den B13/B1-Vertrag exakt; die Flag-Datei (`$LOG.projektmodelle`) ist fail-closed und bei Merge-Abbruch unschädlich; Sandbox und Pi sind unverändert; alle sieben gepinnten Testklassen decken den Vertrag ohne Schwächung ab; die Doku (B13/B1) deckt die neue Bedingung wörtlich ab; die Feedback-Antwort zu GH-89 ist sachlich richtig; die Manifest-Aktualisierung ist vollständig und konsistent. Die Baseline-Aktualisierung der drei Moduleinträge ist legitim, und **die Baseline lässt keine Lücke für die AK9-Regression: die Rücknahme von Befund 1 ist nach eigener Nachprüfung zwingend.** Keine Blocker/Schwer-Befunde; ein optionaler Vorschlag bleibt offen.

**Befunde:** 0 Blocker/High/Schwer, 1 offener Vorschlag (optional). Der Runde-1-Befund 1 wird zurückgezogen (Begründung unten).

## Akzeptanzkriterien

| Kriterium | Status | Ort / Evidenz |
|---|---|---|
| AK9: Erreichbarer gemeinsamer Server behält bisheriges Ziel (ohne wirksame Projektkonfiguration, nichtleeres Kennwort) | **ERFÜLLT** (statisch; Ausführung = gelieferter Nachweis) | `bin/vibe-run.sh:1264-1269`; Flag-Logik `959-960`, `1132-1140`, `1221-1225`; Test unverändert `tests/unit/test_private_server.py:875-910`. Rotursache am Start-Commit statisch bestätigt: altes `elif [ "$HAS_INLINE_CONFIG" != 1 ]` war für opencode unerreichbar, da `HAS_INLINE_CONFIG=1` stets gesetzt wurde (entfernte Diff-Zeilen); Rotnachweis vom Testagent am Start-Commit erbracht. |
| Auch nur deaktivierte opencode-Einträge zählen als wirksame Projektkonfiguration | **ERFÜLLT** | Flag-Bedingung `bin/vibe-run.sh:1135`; neuer Fall `tests/unit/test_agent_management.py:4072-4121` (nur `aktiv:false` + Kennwort + erreichbarer gemeinsamer Server → genau 1 `serve`, `--server` ≠ gemeinsamer Port). |
| Ohne Kennwort `--standalone` | **ERFÜLLT** | Bedingung verlangt `HAS_SERVER_PASSWORD = 1` (`vibe-run.sh:60-69`: Leerzeichen-Kennwort gilt als fehlend); gepinnt in `SharedServerTest` (nur Docstring geändert, Assertions unverändert) und `RunnerControlTest` (nur Docstring geändert). |
| Sandbox immer privat; Pi unverändert | **ERFÜLLT** | Sandbox-Zweig `1253-1258` vor dem `elif`; `PRIVATE_SERVER=1` nur bei `HARNESS = opencode` (`1276-1280`); Pi nutzt `SERVER_ARGS` nicht (`650-659`). |
| Doku B13/B1 deckt neue Bedingung exakt ab | **ERFÜLLT** | `B13.md` („Aktive Bedingungen", „Wiederverwendung … (GH-96)", AK9-Zeile) und `B1.md:296ff` entsprechen wörtlich der Implementierung. |
| Feedback zu Ticketteil 2 (GH-89-Doku) | **ERFÜLLT** | F6.md:94-111, F7.md:17-18/63-67, B4.md:53-79 gegengeprüft — Behauptungen zutreffend; `GH-89.md` ist deutsch (Lücke zutreffend benannt). Die Runde-1-Formulierung „status image caption" ist zur F7-Realität korrigiert (CLI-Evidenz-Anmerkung, `F7.md:426`). |
| Manifest | **ERFÜLLT** (indirekt verifiziert) | Nur `bin` ist hash-tracked (`scopes`, Manifest:2007-2015); `bin/vibe-run.sh` (88742 Bytes, neuer SHA-256) aktualisiert, neuer `aenderungen`-Eintrag, `stand 2026-11-26`. Direkte Hash-Neuberechnung verwehrt (s. u.); indirekt gedeckt: `test_import_manifest.RepositoryManifestTest` läuft den Checker gegen das Repo und bestand im grünen Bestätigungs-Volllauf (nicht in der Baseline). |
| Baseline-Aktualisierung | **ERFÜLLT** | Drei aktualisierte Einträge legitim (vorbestehend am Start-Commit nachgewiesen; keines der drei Module referenziert Änderungsset-Dateien); `min_tests 2500` unverändert, 17→14 Signaturen; **keine Lücke für AK9-Regression** (siehe unten). |

## Baseline-Bewertung (ausdrücklich, korrigiert)

**Die Baseline-Änderung ist legitim, keine Abnahmeschwächung — und der nicht entfernte Eintrag `tests.unit.test_private_server` ist korrekt belassen.**

1. **Modulliste korrigiert:** `tests/verify-baseline.json` (Label `pi-aarch64-py3.14-namespaces`) enthält **11 Module mit 14 Signaturen** (github_issues, github_runner, install_lifecycle, private_server, project_guide, project_management, rebuild_profile, release, repository_hygiene, sandbox, work_packages). Meine Runde-1-Zählung „12 Module" war falsch; die 11 im Bestätigungslauf fehlgeschlagenen Module sind exakt diese 11 — **einschließlich `test_private_server`**, dessen `SandboxPrivateServerTest` im Volllauf-Umfeld umgebungsbedingt (bubblewrap ohne User-Namespaces) mit der baseline-gedeckten Signatur scheitert, während AK9 grün ist (Testagent-Bericht; konsistent mit `GH-89.md:31`, das denselben 11-Module-Fehlbestand inkl. `7675639a…` bereits am GH-89-Start-Commit nachweist). Der Fokus-Lauf (275 OK, isolierte Umgebung) sagt nichts über das Volllauf-Umfeld — meine Runde-1-Schlusskette verwechselte die beiden Umgebungen.
2. **Signatur-Zuordnung korrigiert:** `docs/features/GH-89.md:36` dokumentiert ausdrücklich, dass AK9s Regressionssignatur `15391463…` lautet (stabil, am Start-Commit zweifach nachgewiesen) und der committete Baseline-Eintrag `7675639a…` zum `SandboxPrivateServerTest` (Modulkopf) gehört, **nicht zu AK9**. Eigene Nachprüfung: `15391463` steht **nicht** in `tests/verify-baseline.json` (grep: kein Treffer). Eine Wieder-Einführung der GH-76-Regression würde daher als neue, nicht gedeckte Signatur mit Exit 7 auftauchen — **das Vollgate ist für die behobene Regression nicht blind**; mein Runde-1-Szenario war widerlegt.
3. **Regellage korrigiert:** `docs/verification-baselines.md:9` („Remove an entry only after its module passes") ist die Bedingung, unter der Entfernen zulässig ist. Das Modul besteht im Volllauf-Umfeld (der durch die Baseline beschriebenen Umgebung) **nicht** — die Entfernung wäre nach der Regel gerade nicht zulässig und würde die umgebungsbedingte, akzeptierte `SandboxPrivateServerTest`-Signatur als unbekannt auffädeln (Exit 7): eine Abnahmeschwächung, keine Härtung. Einen Stand (Datei/Zeile), an dem hier etwas zu ändern wäre, gibt es damit nicht.
4. Die drei aktualisierten Einträge sind durch Testagent-Evidenz (identische First-Exception-Signaturen an `f2dd725` und HEAD) gedeckt und statisch plausibilisiert (keine der drei Module referenziert Änderungsset-Dateien; grep-geprüft).

## Befunde

**Zurückgezogen:** Runde-1-Befund 1 (Schwer/Medium, obsoleter Baseline-Eintrag) — Prämissen nach Aktenlage falsch (Modulzahl falsch gezählt; Signatur `7675639a…` fälschlich AK9 zugeordnet statt `SandboxPrivateServerTest`; „Modul besteht"-Prämisse galt nur für die Fokus-Umgebung; Maskierungsszenario durch fehlende Signatur `15391463…` in der Baseline widerlegt). Damit entfällt der einzige PASS-blockierende Befund.

**Schwer/Blockierend:** keine.

**Vorschläge (nicht blockierend) — 1 offen:**
1. `tests/unit/test_project_agents.py:1684` heißt weiterhin `test_shared_server_without_platform_instructions_is_not_reused`, während der Docstring nun zutreffend die fehlende Kennwortdatei als trennende Bedingung nennt. Optionaler kosmetischer Umbenennungsvorschlag; gemäß Projektrule zu kleinen Vorschlägen bewusst nicht umgesetzt — kein Handlungsbedarf.

(Ehemaliger Vorschlag 1 — „status image caption" → CLI-Evidenz-Anmerkung — wurde als reine Wortlautkorrektur in `docs/features/GH-96.md` umgesetzt und ist geprüft; kein Befund mehr.)

## Verifikationsgrenzen

- **Ausführung verwehrt:** Die Review-Session erlaubt nur `git log`/`git diff`; `python3`, `bash scripts/verify.sh`, `sha256sum` wurden abgelehnt. Nicht selbst ausgeführt: Fokus-Tests, `check-import-manifest.py`, `verify.sh`-Läufe, SHA-256-Neuberechnung. Diese Nachweise bleiben Coder-/Testagent-Evidenz (differenziert ausgewiesen, in sich konsistent, teilweise statisch unterbaut); Fokus-Test-Ausführung ist als **NICHT VERIFIZIERT (Eigenausführung)** markiert.
- Signatur-Gleichheit der drei Baseline-Module an `f2dd725` vs. HEAD: gelieferter Nachweis, statisch plausibilisiert, nicht reproduziert.
- Statisch voll geprüft: Verzweigung und Flag-Lebenszyklus (inkl. Merge-Abbruch-Randfall: unschädlich — einziger Konsument `vibe-run.sh:959`, `rm -f` davor, pfaduniqu je Lauf), alle sieben gepinnten Klassen (Assertions ungeschwächt), Doku-Verträge, Feedback-Behauptungen, Baseline-Schema/-Module/-Signaturen (inkl. Abwesenheit von `15391463`), Manifest-Struktur/Scopes, AK9-Rotursache, keine `HAS_INLINE_CONFIG`-Restverweise.
- Vollständige Auflistung ungetrackter Dateien verwehrt; gefunden: nur `GH-96.md` (erwartet) und `TICKET-GH-96.json` (Runner-State).

**Fazit:** Vertragstreue, vollständig dokumentierte Umsetzung mit passgenauer Test-Coverage; die Baseline-Änderung ist eng begründet und lässt die AK9-Regressionssignatur ungedeckt (Regressionsnachweis über Exit 7 intakt). Der Runde-1-Einwand entfällt nach Nachprüfung; keine blockierenden Befunde.

Verdict: PASS
