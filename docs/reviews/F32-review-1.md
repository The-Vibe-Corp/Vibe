# Review F32 „Subagenten-Parallelisierung" — Runde 1

**Paket:** FEEDBACK.md F32 „Subagenten Parralelisierung" — **Ausgangscommit:** `c1825a1` (AP19)
**Branch:** `vibe/vibe-F32-1795045520129299813-299324-27425` (Arbeitskopie `/home/nutzer/vibe-logs/worktrees/vibe-F32-IhzyyA`, Änderungen uncommitted)
**Geprüft:** `bin/vibe` (`agent_validate_hierarchy`), `bin/vibe-web.py` (`/api/agent` save/role), `bin/web/app.js` (`agentForm`), `docs/import-manifest.json`, `tests/unit/test_f32_subagent_self_spawn.py`, `tests/browser/test_f32_subagent_self_spawn_ui.py`, `tests/unit/test_ap03_agent_management.py` (Zeilen 485–544, 758–927), `docs/features/AP03.md`, `SPEC.md` (36–80, 300–329), `FEEDBACK.md:613`, `docs/reviews/` (Vollständigkeit), `docs/features/` (F1–F31, kein F32)
**Datum:** 2026-11-19
**Reviewer-Einschränkung:** Die Endphase der Prüfung lief mit gesperrten Werkzeugen (auch Shell → „Permission denied"); Manifest-Hashes konnten nicht nachgerechnet, Testläufe nicht selbst ausgeführt werden. Testergebnisse stammen aus den gelieferten Koordinator-Ausgaben.

## Summary

- Critical: 0
- High: 2
- Medium: 1
- Minor: 2
- Verdict: CHANGES REQUIRED

## Akzeptanzkriterien

Die AK-Texte stammen aus dem zu Beginn gelieferten Arbeitspaket. Im aktuellen Sitzungszustand lagen sie nur zusammengefasst vor; die Zuordnung AK1/AK2/AK3/AK4/AK6 ist durch die Test-Docstrings belegt (`tests/unit/test_f32_subagent_self_spawn.py:15-30`). AK5/AK7/AK8 sind aus dem dort beschriebenen Vertrag und dem Manifesteintrag (`docs/import-manifest.json:963-971`) rekonstruiert – als solche gekennzeichnet.

| Kriterium | Status | Implementierung (Datei:Zeile) | Test (Datei:Methode) / Nachweis |
|---|---|---|---|
| AK1: Gewöhnliche Subagenten dürfen sich selbst aufrufen (`mode: subagent`/`all`), auch bei noch nicht existierender Datei über `own_text` | PASS | `bin/vibe:3338-3358` (Selbstkante erlaubt, `own_text`-Modus), `bin/vibe:3380-3382` (Selbstkante kein Zyklus) | `tests/unit/test_f32_subagent_self_spawn.py::SelfSpawnAllowedTest`; laut gelieferter Ausgabe grün |
| AK2: Der Vibe-Agent darf sich nicht selbst aufrufen – auch nicht bei Rollenwechsel im selben Request | FAIL | Kernprüfung `bin/vibe:3342-3345`; Lücke: `bin/vibe-web.py:1769-1787` prüft nur im `task_allowed`-Zweig, `bin/vibe-web.py:1800-1804` (`action:'role'`) prüft gar nicht; UI sendet Rolle ohne `task_allowed` (`bin/web/app.js:1283-1285`) bzw. über `action:'role'` (`bin/web/app.js:1088`) | `tests/unit/test_f32_subagent_self_spawn.py::test_current_vibe_agent_cannot_self_spawn` und `::test_agent_becoming_vibe_in_the_same_request_cannot_self_spawn` – letzterer sendet künstlich `task_allowed` (Zeile 730) und bildet den echten UI-Flow nicht ab; Browser-Suite enthält keinen Rollenwechsel |
| AK3: Die Agentenvorlage enthält keine Selbstfreigabe | PASS | `bin/vibe` (Vorlagen-/Scaffold-Bereich; exakte Zeile nicht verifiziert) | `tests/unit/test_f32_subagent_self_spawn.py::AgentTemplateTest`; laut gelieferter Ausgabe grün |
| AK4: Nur `subagent`/`all` (leer zählt wie `all`), `primary` wird abgelehnt | PASS | `bin/vibe:3353-3357` | `tests/unit/test_f32_subagent_self_spawn.py::SelfSpawnModeTest`; grün |
| AK5 (rekonstruiert): `task_all` und Scope-Regel bleiben unverändert | PASS | `bin/vibe-web.py:1763-1771` | `tests/unit/test_f32_subagent_self_spawn.py::AgentSelfSpawnApiTest`; grün |
| AK6: Regeln für fremde Agenten unverändert (unbekannt, `primary`, projektlokal) | PASS | `bin/vibe:3359-3366` | `tests/unit/test_f32_subagent_self_spawn.py::ForeignAgentRulesTest`; grün |
| AK7 (rekonstruiert): UI-Opt-in-Checkbox „Subagenten des eigenen Typs erlauben“, standardmäßig ungehakt, Vibe- und `primary`-Hinweis, auch im Neuanlage-Formular | PASS | `bin/web/app.js:1169-1300` (Agentenformular inkl. Subagenten-Bereich) | `tests/browser/test_f32_subagent_self_spawn_ui.py` (6 Tests); laut gelieferter Ausgabe grün. Einschränkung: kein Test für Rollenwechsel per Liste/Editor (siehe High 1) |
| AK8 (rekonstruiert): Selbstkanten gelten nicht als Zyklus, echte Zwei-Agenten-Zyklen bleiben abgelehnt | PASS | `bin/vibe:3367-3386` | `tests/unit/test_f32_subagent_self_spawn.py::HierarchyCycleTest`; grün |

## Befunde

- **[High] `bin/vibe-web.py:1769-1787` — Vibe-Sperre greift nur, wenn `task_allowed` mitgesendet wird**
  - Beleg: `agent_validate_hierarchy` wird ausschließlich im `elif task_allowed is not None`-Zweig aufgerufen. Die UI sendet `task_allowed` nur bei geänderter Subagenten-Konfiguration (`bin/web/app.js:1282-1285`), die Rolle aber immer bei Änderung (`bin/web/app.js:1283`). Wer im Editor nur die Rolle auf `vibe` stellt, löst damit keine Hierarchieprüfung aus; ein Agent mit `task: [self: allow]` wird als Vibe-Agent gespeichert und darf sich danach selbst aufrufen – genau das von F32 ausgeschlossene Verhalten. Zusätzlich umgeht das Rollen-Dropdown der Liste (`bin/web/app.js:1083-1089`, `action:'role'`) mit `bin/vibe-web.py:1800-1804` jede Prüfung vollständig. Der vorhandene Test `test_agent_becoming_vibe_in_the_same_request_cannot_self_spawn` (`tests/unit/test_f32_subagent_self_spawn.py:716-737`) sendet künstlich `task_allowed` (Zeile 730) und deckt den realen UI-Pfad nicht ab; die Browser-Suite testet keinen Rollenwechsel.
  - Required fix: Die Invariante „Vibe-Agent darf keine Selbstkante besitzen“ bei jeder Rollenzuweisung zentral erzwingen – sowohl im `save`-Pfad mit `role` als auch in `action:'role'` (sinnvoller Ort: `agent_role_set` in `bin/vibe:2977-3006`) und unabhängig davon, ob `task_allowed` gesendet wurde. Dazu Tests ergänzen: Editor-Speichern mit ausschließlich Rollenwechsel und Listen-Dropdown-Rollenwechsel, jeweils mit bestehender Selbstfreigabe.
- **[High] `tests/unit/test_f32_subagent_self_spawn.py:1-37` — Kein konservierter Failing-first-Nachweis**
  - Beleg: Die Rotphase wird nur im Docstring behauptet („Rotphase (bewusst): …“). Im Change Set und unter `docs/reviews/` liegt kein `F32-test-agent-report.md` und keine Rohausgabe (Verzeichnisliste zeigt Berichte für AP*, B*, F* – nicht für F32). Damit fehlt der von den globalen Arbeitsanweisungen (§5 „Run it and confirm it fails …“, §7 „Never fabricate … results“) und von `SPEC.md:320` („Testprotokolle nennen Befehl, Ergebnis und Grenzen des Nachweises“) verlangte Nachweis. Statisch sind die Kernfälle am alten Code zwar zwingend rot (alte Signatur ohne `own_text`/`vibe_agent` → `TypeError`; Selbstaufruf → `ValueError`), das ersetzt aber keinen belegten Lauf.
  - Required fix: Test-Agentenbericht mit Rohausgabe der Rot- und Grünphase (Befehl, Ergebnis, Grenzen) unter `docs/reviews/` ablegen und im F32-Dokument verlinken.
- **[Medium] `docs/features/AP03.md:57-58,94` — Fehlende F32-Dokumentation und veraltete AP03-Aussage**
  - Beleg: `SPEC.md:321` verlangt je Ticket „Tests, fachliche und technische Dokumentation sowie unabhängigen Review“. `docs/features/` enthält F1–F31, aber kein `F32.md`. Gleichzeitig behauptet `docs/features/AP03.md:57-58` weiterhin „Selbstbezug und Zyklen werden abgelehnt“, Zeile 94 nennt „Selbstbezug“ als Prüfumfang von `agent_validate_hierarchy` – beides widerspricht dem F32-Verhalten (`bin/vibe:3338-3358`).
  - Required fix: `docs/features/F32.md` mit Auftrag, Verhalten, Grenzen (Pi-Harness, `task: allow`, Rohtexteditor), Validierung und Nachweisen anlegen und die betroffenen AP03-Aussagen auf den neuen Stand bringen.
- **[Minor] `bin/vibe-web.py:1781-1782` — Toter Zweig mit irreführendem Kommentar**
  - Beleg: Die Prüfung `bin/vibe-web.py:1756-1762` bricht bereits ab, wenn kein anderer Vibe-Agent existiert und die Rolle entfernt würde. Der Zweig `if not others: effective_vibe = an  # Rolle bleibt faktisch; …` ist damit unerreichbar und suggeriert eine Behandlung, die nie eintritt.
  - Required fix: Den unerreichbaren Zweig entfernen oder die Bedingung so umbauen, dass die Semantik eindeutig ist.
- **[Minor] `tests/browser/test_f32_subagent_self_spawn_ui.py:~100-115` — `VIBE_STORAGE_LOCK_DIR` wird nicht aus der Umgebung entfernt (Zeilen ungefähr, nicht verifiziert)**
  - Beleg: Anders als die Unit-Test-Isolierung (`tests/unit/test_f32_subagent_self_spawn.py:90`) und andere Browser-Tests (z. B. `tests/browser/test_f31_agents_file_ui.py:127`) wird die Variable beim Start des Testservers nicht bereinigt; dadurch können Lock-Dateien außerhalb des Temp-Verzeichnisses entstehen.
  - Required fix: Die Variable im Browser-Test-Setup genauso wie in den bestehenden Tests aus der Umgebung entfernen.

## Verifikation

- Change set reviewed: `c1825a1..working tree`; 5 geänderte Dateien (`bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `docs/features/AP03.md`, `docs/import-manifest.json`) plus 2 neue Testdateien. `git diff --check HEAD` war sauber.
- Git commands run by me: `git status --short`, `git diff HEAD`, `git diff --check HEAD`, `git log --oneline -1`. In der Endphase wurden weitere Shell-Aufrufe (`git status`, `sha256sum`, `wc`) mit „Permission denied“ abgewiesen.
- Checks with supplied output: 24 Unit-/API-Tests in `tests/unit/test_f32_subagent_self_spawn.py` und 6 Playwright-Tests in `tests/browser/test_f32_subagent_self_spawn_ui.py` laut gelieferter Ausgabe grün; Manifest-Prüfung (`check-import-manifest.py`) laut gelieferter Ausgabe OK mit 57 Dateien. Diese Ergebnisse habe ich **nicht selbst** erzeugt.
- Checks not independently run: alle Build-, Lint- und Testläufe. Die SHA-256-Werte in `docs/import-manifest.json:973-997` konnte ich mangels Shell-Rechten nicht nachrechnen.
- Important areas inspected: `bin/vibe-web.py` (1725–1834), `bin/web/app.js` (1060–1306), `bin/vibe` (3318–3387), beide neuen Testdateien (vollständig gelesen), `tests/unit/test_ap03_agent_management.py` (485–544, 758–927), `docs/features/AP03.md`, `docs/import-manifest.json` (955–997), `SPEC.md` (36–80, 300–329), `FEEDBACK.md:613`, `docs/reviews/` (Vollständigkeit der Nachweise), `docs/features/` (F1–F31, kein F32).
- Remaining risks: Die unter High 1 beschriebene Lücke erlaubt in der laufenden Anwendung einen Vibe-Agenten mit Selbstfreigabe; die Manifest-Hashes sind ungeprüft; die bekannten vorbestehenden Baseline-Fehler (u. a. `VibeRunGateTest`, `test_project_agents`) wurden nicht erneut ausgeführt und sind nicht als F32-Befund gewertet.

**Verdict: CHANGES REQUIRED**

---

*Koordinator-Anmerkung (nicht Teil des Originalberichts): Der Reviewer konnte die Datei selbst nicht anlegen (Rolle strikt lesend); der Bericht wurde vom Koordinator unverändert übernommen. Ein nachweisbarer Versprecher des Originaltexts: Die fünfte geänderte Datei im Change Set ist `tests/unit/test_ap03_agent_management.py` (umbenannter Bestandstest), nicht `docs/features/AP03.md` — laut `git status --short` zum Review-Zeitpunkt.*
