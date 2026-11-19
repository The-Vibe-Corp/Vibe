# F32 — Test-Agenten-Bericht (Rot- und Grünphase)

**Paket:** FEEDBACK.md F32 „Subagenten Parralelisierung"
**Branch:** `vibe/vibe-F32-1795045520129299813-299324-27425`, Ausgangsstand `c1825a1`
**Datum:** 2026-11-19
**Autoren:** unabhängiger Test-Agent (Testfälle, Rotphasen) und Koordinator
(Rotreproduktion am unveränderten Ausgangsstand, Grünverifikation)

Dieser Bericht konserviert den Failing-first-Nachweis, den Runde 1 des Reviews
(`docs/reviews/F32-review-1.md`, High 2) fordert. Alle Läufe liefen in
isolierten temporären VIBE-/HOME-Umgebungen mit Ersatz-`opencode`
(`--version` → `opencode 2.1.4`, `models` → feste Liste); kein Modellaufruf,
kein Netzzugriff außer Loopback. Browsertests mit Playwright/Chromium gegen
das echte Dashboard auf einem freien Loopback-Port.

## Testdateien (Besitz des Test-Agenten)

- `tests/unit/test_f32_subagent_self_spawn.py` — Unit- und API-Tests
  (Klassen `SelfSpawnAllowedTest`, `VibeSelfSpawnRejectedTest`,
  `SelfSpawnModeTest`, `HierarchyCycleTest`, `ForeignAgentRulesTest`,
  `AgentTemplateTest`, `AgentSelfSpawnApiTest`; Runde 2 ergänzte
  `VibeInvariantApiTest`).
- `tests/browser/test_f32_subagent_self_spawn_ui.py` — Browsertests
  (test_01–test_06 Runde 1; test_07/test_08 Runde 2; Isolation um
  `VIBE_STORAGE_LOCK_DIR` bereinigt).
- `tests/unit/test_ap03_agent_management.py` — ein Bestandstest wurde
  umbenannt (`test_agent_validate_hierarchy_rejects_unknown_self_and_cycles`
  → `…_rejects_unknown_and_cycles`) und um die Selbstaufruf-Erwartung
  erleichtert; Begründung: F32 ändert genau dieses Verhalten, die vollständige
  Neuabdeckung (erlaubt UND abgelehnt) liegt in der F32-Datei. Unbekannt-
  und Zyklus-Ablehnungen bleiben dort unverändert asserts.

## Runde 1 — Selbstaufruf als Opt-in

### Rotphase am unveränderten Produktcode (c1825a1)

Vom Test-Agenten gemeldet: 24 Unit-/API-Fälle → 10 Failures, 9 Errors fachlich
rot (alte Signatur ohne `own_text`/`vibe_agent` → `TypeError`; Selbstaufruf →
alte Meldung „Ein Agent darf sich nicht selbst als Subagent aufrufen.");
6 grüne Anker (task_all, Scope-Regel, Fremdagentenregeln, Zwei-Agenten-Zyklus,
Vorlage ohne Selbstfreigabe). Browser: 6 Fälle → 1 Failure, 4 Errors
(Eigen-Checkbox fehlt; Vibe-/Modus-Hinweise fehlen), 1 grüner Anker
(„keine"/„alle" ohne Eigen-Checkbox).

Vom Koordinator reproduziert am sauberen Ausgangsstand (`git archive c1825a1`
nach `/tmp/opencode/f32-baseline`, Testdateien hineinkopiert):

```text
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_f32_subagent_self_spawn
Ran 24 tests … FAILED (failures=10, errors=9)
18 Testfälle fachlich rot (davon 2 Subtests der Modus-Schleife), 6 grüne Anker
Rohausgabe: /tmp/opencode/f32-r1-red-unit.err

$ env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_f32_subagent_self_spawn_ui
Ran 6 tests in 122.933s … FAILED (failures=1, errors=4)
Rohausgabe: /tmp/opencode/f32-r1-red-browser.log
```

Grenzen: Die Reproduktion kopiert die Testdateien in einen unveränderten
Ausgangsstand; sie belegt dieselben Fehlstellen wie der Originallauf des
Test-Agenten. `/tmp/opencode`-Artefakte sind flüchtig und dienen nur der
unmittelbaren Kontrolle; die Zahlen stehen hier dauerhaft.

### Grünphase nach Umsetzung Runde 1 (durch den Coding-Agenten)

```text
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_f32_subagent_self_spawn
Ran 24 tests … OK
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_ap03_agent_management.HierarchyTest tests.unit.test_ap03_agent_management.AgentApiTest
Ran 7 tests … OK
$ env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_f32_subagent_self_spawn_ui
Ran 6 tests … OK
```

Vom Koordinator unabhängig nachgelaufen und bestätigt (Ausgaben identisch).

## Runde 2 — Review-Befund High 1 (Vibe-Sperre nur bei task_allowed)

Der Review (`docs/reviews/F32-review-1.md`) zeigte: Die Vibe-Sperre griff nur,
wenn der Speicher-Request `task_allowed` enthielt. Drei reale Wege umgingen
sie: Rolle-im-Editor-Wechsel ohne Subagenten-Änderung, Rohtext-Selbstfreigabe
für den aktuellen Vibe-Agenten, Rollen-Dropdown der Liste (`action:'role'`).

### Rotphase am Stand nach Runde 1 (vom Test-Agenten)

```text
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_f32_subagent_self_spawn
Ran 29 tests … FAILED (failures=3)
rot: test_role_only_save_rejects_vibe_for_agent_with_self_allow
     test_raw_text_self_allow_for_the_current_vibe_agent_is_rejected
     test_role_action_rejects_vibe_for_agent_with_self_allow
Ist-Zustand: 200 „Gespeichert“/„Rolle gespeichert“ statt 400; tester wurde
Vibe-Agent bzw. profiles.json wurde geändert.
grüne Anker: Rollenzuweisung ohne Selbstfreigabe bleibt möglich (2 Fälle).
Rohausgabe: /tmp/opencode/f32-r2-red-unit.err

$ env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_f32_subagent_self_spawn_ui
Ran 8 tests in 24.575s … FAILED (failures=2)
rot: test_07_list_role_dropdown_rejects_vibe_for_self_spawn_agent
     test_08_editor_role_change_keeps_rejection_when_self_allow_exists
Ist-Zustand: Toast „rolle gespeichert“/„gespeichert“ statt Ablehnung.
Rohausgaben: /tmp/opencode/f32-r2-red-browser.log,
/tmp/opencode/f32-r2-red-browser-07-08.log (Toast-Historie)
```

Der Coding-Agent bestätigte vor dem Fix dieselbe Rotlage
(`FAILED (failures=3)` in `VibeInvariantApiTest`).

### Grünphase nach Fix Runde 2 (zentrale Invariante, `agent_role_set`)

```text
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_f32_subagent_self_spawn
Ran 30 tests … OK                    (Koordinator: EXIT=0; 29 nach Runde 2,
                                      +1 Abdeckungsergänzung nach Review
                                      Runde 2, siehe unten)
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_ap03_agent_management.HierarchyTest tests.unit.test_ap03_agent_management.AgentApiTest
Ran 7 tests … OK                     (Koordinator: OK)
$ env -u VIBE_RUNTIME python3 -m unittest tests.browser.test_f32_subagent_self_spawn_ui
Ran 8 tests in 4.043s … OK           (Koordinator: EXIT=0)
$ env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_agent_management tests.unit.test_ap17_agent_roles tests.unit.test_f21_agents_preflight
Ran 67 tests … OK                    (Koordinator: OK)
```

### Abdeckungsergänzung nach Review Runde 2 (Minor 3)

Der Review Runde 2 benannte als nicht blockierenden Minor den fehlenden
Test für den `agent_role_set`-Fallback bei unlesbarem Frontmatter. Der
Test-Agent ergänzte `VibeInvariantApiTest
.test_role_action_still_assigns_vibe_for_unreadable_frontmatter`: eine
Agentendatei ohne Frontmatter-Block bleibt rollenzuweisbar (200, `vibe`),
die Gegenprobe mit lesbarem Frontmatter und Selbstfreigabe wird abgelehnt
(400, profiles.json unverändert). Dies ist eine Abdeckungsergänzung für
bereits implementiertes Verhalten, keine TDD-Rotphase. Finale Suite:
`Ran 30 tests … OK` (zweimal ausgeführt).

## Vorbestehende Baseline-Fehler (nicht F32)

- `tests.unit.test_project_agents`: `Ran 26 … FAILED (failures=2, errors=1)`
  — `ensure_test_agent` fehlt (2 Fälle), `--model`-Flag in
  `RunnerModelTest.test_without_override_no_model_flag_is_sent`. Vom
  Koordinator am unveränderten Ausgangsstand (`git archive c1825a1`) identisch
  reproduziert: gleiche 3 Fälle, gleiche Meldungen → vorbestehend.
- `tests.unit.test_ap03_agent_management.VibeRunGateTest`: 5 Errors
  (`ensure_test_agent` fehlt am Modul) — vorbestehend, am unveränderten
  `bin/vibe` bestätigt.

## Statische Prüfungen

- `python3 scripts/check-import-manifest.py` → OK, 57 Dateien stimmen überein.
- `bash scripts/verify.sh quick` (mit temporärer, danach entfernter
  `.vibe/project.env` vom Integrationsstand) → Exit 0.
- `python3 -m py_compile bin/vibe bin/vibe-web.py`, `node --check
  bin/web/app.js` → OK.

## Grenzen des Nachweises

- Kein echter opencode-Lauf: ob opencode zur Laufzeit den Selbstaufruf
  tatsächlich anbietet, wurde nicht gegen ein echtes Modell geprüft; vibe
  schreibt und prüft ausschließlich die Konfiguration. Die Annahme folgt dem
  bestehenden, für 2.1.4 dokumentierten `permission.task`-Mechanismus (AP03).
- Pi erzwingt keine Rechte (dokumentierte Harness-Grenze,
  `docs/compatibility.md`); die F32-Konfiguration bindet nur opencode.
- `verify.sh full` wurde für dieses Paket nicht vollständig gelaufen; die
  paketrelevanten Suiten und `verify.sh quick` sind vollständig belegt, die
  Baseline-Fehlerliste ist am Ausgangsstand reproduziert.
