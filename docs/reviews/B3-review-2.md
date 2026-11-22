# Review-Bericht: Arbeitspaket B3 — Completed and merged work package still marked as waiting for merge

- **Arbeitspaket:** B3 (neuer FEEDBACK-Eintrag „Completed and merged work package still marked as waiting for merge“, Art: Bug)
- **Ausgangscommit:** `d53efa4` (`d53efa46ed1feada9803a91eeb8b673be59c116d`, Branch `feature/korbat/ap3-korbat`)
- **Geprüfter Änderungssatz:**
  - Modifiziert: `bin/vibe`, `bin/vibe_packages.py`, `bin/web/app.js`, `bin/web/i18n.js`, `docs/import-manifest.json`
  - Neu (untracked): `tests/unit/test_b3_merged_waiting.py`, `docs/reviews/B3-test-agent-report.md`, `docs/features/B3-wartet-auf-merge.md`

---

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor / Low: 0
- Verdict: PASS

---

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **Teil 1 (AK1/AK2):** Abgehakte Pakete/Feedback-Einträge mit gültigem Nachweis gelten überall als erledigt, auch wenn der Blocktext wörtlich zitierte `WARTET AUF MERGE:`- oder `BLOCKIERT:`-Zeilen enthält | PASS | `bin/vibe:589-590`, `bin/vibe:643-648`, `bin/vibe_packages.py:1406-1413` | `tests/unit/test_b3_merged_waiting.py` (Fälle 1–9), Rotphase (15/26 rot am Bestand `d53efa4`) in `docs/reviews/B3-test-agent-report.md` belegt; Grünlauf (`Ran 26, OK`) und Sanity `status_report('.')` vom Koordinator ausgeführt + Quelltextprüfung durch mich |
| **Teil 1 (AK3/AK4/AK7):** Bestandsverträge bleiben gewahrt (`BLOCKIERT` gewinnt vor `WARTET AUF MERGE` bei nicht-erledigten Einträgen; „ohne Nachweis“ bzw. Markenzustand für abgehaktes Feedback ohne gültigen Nachweis; `not root` bleibt `erledigt`; `priority_view`/`standard` und `test_ap5_korbat_waiting_state.py` unverändert) | PASS | `bin/vibe:589-594`, `bin/vibe:643-648`, `bin/vibe_packages.py:1406-1413`, `bin/vibe_packages.py:1445-1492` | `tests/unit/test_b3_merged_waiting.py` (Fälle 10–19) + `tests/unit/test_ap5_korbat_waiting_state.py` (unverändert, `Ran 23, OK`) |
| **Teil 2 (AK5/AK6):** Klassische UI (`app.js`) bietet den Knopf „Paket abschließen“ in `ticketCard` nur für `BLOCKIERT`/`WARTET AUF MERGE` (kein Knopf auf Feedback-Karten, kein Knopf für `offen`/`ohne Nachweis`/`erledigt`), ruft `/api/package` mit `{name, id: i.id, action: 'close'}` auf, zeigt Toast und lädt `detail(name)` neu; i18n EN (`Close work package`) + DE-Identitätspaar | PASS | `bin/web/app.js:633-681` (insb. `:666`), `bin/web/i18n.js:1023`, `bin/web/i18n.js:2036`, Backend: `bin/vibe-web.py:1484-1494`, `bin/vibe:2412-2466` | `tests/unit/test_b3_merged_waiting.py` (Fälle 20–26) + Quelltextprüfung der UI-, i18n- und Backend-Verträge |
| **Teil 3:** Prozessfrage zum weitergezogenen `dev`-Branch gemäß Nutzerentscheidung `qc35c59a5c341` (Variante C: bestehender Prozess bleibt unverändert und wird mit Fehlerpfaden klar dokumentiert) | PASS | `docs/features/B3-wartet-auf-merge.md:96-144` (gegen `bin/vibe-run.sh:787-810`, `:1369-1378`, `:1628-1702`) | Quelltextabgleich von `docs/features/B3-wartet-auf-merge.md` §4 gegen `bin/vibe-run.sh` und `bin/vibe_packages.py` |
| **Manifest & Hygiene:** `docs/import-manifest.json` für alle geänderten `bin/**`-Dateien aktualisiert, keine Geheimnisse, keine unautorisierten Änderungen | PASS | `docs/import-manifest.json:1252-1255`, `:1312-1315`, `:1352-1355`, `:1362-1365` | `check-import-manifest.py`, `check-syntax.py`, `check-no-secrets.py`, `verify.sh quick` (Exit 0 laut Koordinator-Nachweis) + vollständige Diff-/Dateiinspektion durch mich |

---

## Findings

- No findings.

---

## Prüfauftrags-Abgleich im Detail

### 1. Korrektheit der Zustandssemantik
- **`bin/vibe` (`_parse_entry`, Zeilen 642–648):**
  - `checked = item["checked"]`
  - `done = checked and (not need_proof or not root or _proof_ok(root, block))`
  - `if done: state = "erledigt"` steht jetzt vor `elif "BLOCKIERT:" in block:` und `elif "WARTET AUF MERGE:" in block:`.
  - **Bestandsverträge gewahrt:**
    - Für `TICKETS.md` (`need_proof=False`) genügt `checked == True` (`done = True` → `"erledigt"`).
    - Für `FEEDBACK.md` (`need_proof=True`) ist `done` nur wahr, wenn `checked` und (`not root` oder `_proof_ok(root, block)`). Der `not root`-Bestandsvertrag bleibt exakt erhalten.
    - Ist ein Feedback-Eintrag abgehakt (`checked=True`), hat aber **keinen** gültigen Nachweis (`done=False`), greifen zuerst `BLOCKIERT:` (gewinnt vor `WARTET AUF MERGE:`), dann `WARTET AUF MERGE:`, und ohne Marker der `else`-Zweig `"ohne Nachweis"`.
    - Ist ein Eintrag nicht abgehakt (`checked=False`), greifen `BLOCKIERT:` vor `WARTET AUF MERGE:`, sonst `elif not checked: state = "offen"`.
- **`bin/vibe` (`open_items`, Zeilen 589–594):**
  - `if item and item["checked"] and (not need_proof or _proof_ok(root, b)): continue` überspringt vollständig erledigte Einträge vor der Marker-Auswertung.
  - Nicht erledigte Einträge werten weiterhin `"BLOCKIERT:"` vor `"WARTET AUF MERGE:"` aus; danach folgen `not item or not item["checked"]` → `"offen"` und `need_proof and not _proof_ok(root, b)` → `"ohne Nachweis"`.
- **`bin/vibe_packages.py` (`status_report`, Zeilen 1406–1413):**
  - Prüft jetzt `if is_done(block) and proof_ok(project, block)[0]: report["done"].append(pid)` vor `elif is_blocked(block):`, `elif is_waiting_merge(block):`, `else: report["open"].append(pid)`.
  - Damit stimmt die Reihenfolge in `status_report` exakt mit `priority_view` (`bin/vibe_packages.py:1445-1452` und `:1482-1491`) sowie `done_ids` (`:647-655`) überein.
- **Unangetastete Bestandstests:**
  - `tests/unit/test_ap5_korbat_waiting_state.py` (659 Zeilen) wurde vollständig gelesen und geprüft: Die Datei ist unverändert.

### 2. GUI und Backend-Vertrag
- **`bin/web/app.js` (`ticketCard`, Zeilen 657–681, insb. Zeile 666):**
  - Der Knopf wird über `...(i.state==='BLOCKIERT'||i.state==='WARTET AUF MERGE'?[el('button',{class:'b',type:'button',on:{click:async()=>{const r=await api('/api/package',{name,id:i.id,action:'close'});toast(bt(r.message));if(r.ok)detail(name).catch(showErr)}}},tr('Paket abschließen'))]:[])` gerendert.
  - Er erscheint ausschließlich in `ticketCard` und nur für die Zustände `BLOCKIERT` und `WARTET AUF MERGE` (somit weder für `offen`, `ohne Nachweis`, `erledigt` noch in `feedbackCard`, Zeilen 633–656).
- **`bin/web/i18n.js`:**
  - `DICTS.en` (Zeile 1023): `"Paket abschließen": "Close work package"`.
  - `DICTS.de` (Zeile 2036): `"Paket abschließen": "Paket abschließen"`.
- **Backend-Vertrag (`bin/vibe-web.py:1484-1494` & `bin/vibe:2412-2466`):**
  - `/api/package` akzeptiert `action == "close"` und delegiert an `vibe.package_close(name, str(body.get("id") or ""))`.
  - `package_close` verweigert ohne registrierten Worktree (`WorktreeRegistry.get`), ohne aktive GitHub-Verknüpfung, ohne Remote `origin` oder ohne per REST verifizierten gemergten Merge-Request (`merged_pull_request` → `found` und `merged`) gefahrlos mit `(False, <verständliche Meldung>)`.

### 3. Tests und Test-Integrität
- **`tests/unit/test_b3_merged_waiting.py` (733 Zeilen, 26 Testfälle in 5 Testklassen):**
  - Stammt vom unabhängigen Test-Agenten (`docs/reviews/B3-test-agent-report.md`).
  - Deckt Teil 1 (`TicketEntryDonePrecedenceTest` mit 9 Fällen, `OpenItemsDonePrecedenceTest` mit 3 Fällen, `StatusReportDonePrecedenceTest` mit 7 Fällen inkl. `priority_view`-Schutzwachen) und Teil 2 (`ClassicGuiPackageCloseTest` mit 5 Fällen, `I18nPackageCloseTest` mit 2 Fällen) vollständig ab.
  - Für Teil 3 (reine Prozessdokumentation nach Variante C) wurden keine künstlichen oder erfundenen Verhaltenstests behauptet (`docs/reviews/B3-test-agent-report.md:152-153`).
  - Alle Zustandsfälle nutzen echte temporäre Git-Repositories (`init_git_repo`) mit realen Commit-Hashes für `proof_ok`/`_proof_ok` und isoliertem `VIBE`/`HOME`.
  - Keine bestehenden Tests wurden geändert oder abgeschwächt. Die Rotphase vor Implementierung (15 Failures, 11 Schutzwachen grün) ist im Test-Agenten-Bericht mit konkreten Assertion-Outputs nachvollziehbar dokumentiert.

### 4. Technische Dokumentation (`docs/features/B3-wartet-auf-merge.md`)
- Alle faktischen Angaben wurden gegen den Quelltext verifiziert:
  - Nutzerzitat `qc35c59a5c341` in §4 (Zeilen 98–104) ist wörtlich wiedergegeben; Variante C (keine Prozessänderung an `bin/vibe-run.sh`, klare Dokumentation der bestehenden Kette) ist sauber eingehalten.
  - Die Prozesskette in §4 stimmt mit `bin/vibe-run.sh` und `bin/vibe_packages.py` überein:
    - `ensure_mergeable_package` in `bin/vibe-run.sh:787-810` (Aufruf in `:1628`): Exit 0 → mergebar/Skip; Exit 2 → genau eine Reparaturrunde (`:792-805`) und bei fortbestehendem Konflikt `--abort` + `BLOCKIERT`; Exit 1 → kein Block vorab (`:806-809`), sondern Weiterleitung an die echte Schranke `github-complete`.
    - `github-complete`-Gate in `bin/vibe-run.sh:1637-1650`: Push + Merge-Request; Fehlschlag blockiert das Paket mit konkreter Ursache.
    - Auto-Merge-Konfliktreparatur in `bin/vibe-run.sh:1665-1698`: bei `GH_MERGE_RC = 2` genau ein begrenzter Reparaturdurchlauf (`ensure_mergeable_package` + `github-push` + `github-merge`), bei Misserfolg Rückfall auf `pr_only_fallback` (`:1697`).
    - `pr_only_fallback` in `bin/vibe-run.sh:1369-1378`: ruft `mark-waiting` auf, füllt `WAITING_MERGE` und hält den Lauf an (`STOP=1`).

### 5. Import-Manifest (`docs/import-manifest.json`)
- Die vier geänderten Dateien unter `bin/**` sind in `docs/import-manifest.json` aktualisiert:
  - `bin/vibe` (Zeilen 1252–1255)
  - `bin/vibe_packages.py` (Zeilen 1312–1315)
  - `bin/web/app.js` (Zeilen 1352–1355)
  - `bin/web/i18n.js` (Zeilen 1362–1365)
- Die neuen Dateien unter `tests/unit/` und `docs/` liegen außerhalb der Manifest-`scopes` (`["install-vibe.sh", "bin", "data/models.json", "templates", "scripts/setup-vibe.py", "setup-vibe.cmd", "VERSION"]`).

### 6. Umfang und Geheimnisschutz
- Alle geänderten und neuen Dateien wurden vollständig bzw. in allen relevanten Abschnitten gelesen.
- Es gibt keine unautorisierten Änderungen, kein Scope-Creep und keine Geheimnisse, Tokens oder persönlichen Pfade in den neuen oder geänderten Dateien.

### 7. Baseline-Behauptungen
- **`test_project_management` (F22-Vorbaseline):** Gegen `tests/unit/test_project_management.py` (`:397-399`, `:402-411`, `:540-584`) und `docs/features/AP5-Korbat.md` (§4 Zeile 153, §5 Zeilen 220–230) abgeglichen. Die exakt 6 Failures und 1 Error (`FileNotFoundError` für `templates/common/.opencode/agents/test-agent.md`) stammen aus der in Commit `35233ff` entfernten hardcoded Test-Agent-Vorlage und sind in AP5-Korbat identisch dokumentiert.
- **`env -u GITHUB_AUTO_MERGE`:** Gegen `docs/features/AP5-Korbat.md` (§3 Punkt 5, Zeilen 120–125) und `tests/unit/test_b16_runner_wiring.py` (`PrOnlyClosureTest`, Zeilen 114–174) abgeglichen. Die Runner-Umgebung exportiert `GITHUB_AUTO_MERGE=1`; für PR-only-Tests muss die Variable in der Testumgebung unset sein.

---

## Verification

- **Change set reviewed:** Arbeitsbaum und neue Dateien gegen Ausgangscommit `d53efa4` (`d53efa46ed1feada9803a91eeb8b673be59c116d` auf Branch `feature/korbat/ap3-korbat`, verifiziert über `.git` Worktree-Metadaten `/opt/custom/vibe-dev/workspaces/vibe/.git/worktrees/vibe-AP3-Korbat-KtK7Jv/HEAD` und `logs/HEAD`).
- **Git commands run by me:** keine (in dieser Agenten-Sitzung ist kein Shell-/Bash-Werkzeug registriert; Git-Zustand und Commit-Historie wurden direkt über die `.git`-Metadaten und `read` geprüft).
- **Checks evidenced by supplied raw output:**
  - `python3 -m unittest tests.unit.test_b3_merged_waiting -v` (Rotphase im Test-Agenten-Bericht `docs/reviews/B3-test-agent-report.md`: `Ran 26 tests in 0.333s`, `FAILED (failures=15)`)
  - Live-Reproduktion am Ausgangsstand `status_report('.')` (`waiting: ['AP5-Korbat']`) in `docs/reviews/B3-test-agent-report.md`
- **Checks reported by the coding agent / coordinator:**
  - `python3 -m unittest tests.unit.test_b3_merged_waiting` → `Ran 26, OK`
  - `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state` → `Ran 23, OK`
  - `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_b16_runner_wiring` → `Ran 6, OK`
  - `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap4_korbat_gui tests.unit.test_ap4_korbat_github` → `Ran 35, OK`
  - `python3 -m unittest tests.unit.test_project_management` → `Ran 36, FAILED (failures=6, errors=1)` (vorbestehende F22-Baseline)
  - `python3 scripts/check-import-manifest.py` → Exit 0
  - `python3 scripts/check-syntax.py` → Exit 0
  - `python3 scripts/check-no-secrets.py` → Exit 0
  - `bash scripts/verify.sh quick` → Exit 0
  - Sanity `status_report('.')` → `waiting` leer, `AP5-Korbat` unter `done`
- **Checks not independently run:** Alle Build-, Test- und Skriptbefehle (strikter Read-Only-Reviewer ohne Shell-Tool).
- **Important areas inspected:** `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe-run.sh`, `bin/vibe-web.py`, `bin/web/app.js`, `bin/web/nova-project.js`, `bin/web/i18n.js`, `docs/import-manifest.json`, `tests/unit/test_b3_merged_waiting.py`, `tests/unit/test_ap5_korbat_waiting_state.py`, `tests/unit/test_b16_runner_wiring.py`, `tests/unit/test_project_management.py`, `docs/reviews/B3-test-agent-report.md`, `docs/features/B3-wartet-auf-merge.md`, `docs/features/AP5-Korbat.md`, `FEEDBACK.md`, `TICKETS.md`.
- **Remaining risks:**
  - Wie in `docs/features/B3-wartet-auf-merge.md` §8 ehrlich dokumentiert, ist kein Browser/Playwright in der Umgebung verfügbar; die GUI-Prüfung für `app.js` und `i18n.js` erfolgt analog zu AP4/AP5 über Quelltext- und Strukturassertionen, während der Backend-Endpunkt `/api/package` (`action: 'close'`) durch Unit-Tests abgedeckt ist.

Verdict: PASS
