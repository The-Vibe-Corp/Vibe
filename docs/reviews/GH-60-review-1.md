# Review result — GH-60 (Runde 1)

## Kurzfazit

Der Changeset `5502fe1..76ba372` (16 Dateien, +358/−179) wurde vollständig lesend geprüft: 14 Code-Dateien (+58/−159), `docs/import-manifest.json` (+37/−20) und die neue Fachdoku `docs/features/GH-60.md` (+263). Keine Testdatei, keine Vorlage, kein Hook-/DOM-Vertrag und keine Prüf-Werkzeugkette wurde angefasst.

Alle 27 in der Fix-Tabelle kennzeichneten Änderungen sind im Diff vorhanden; umgekehrt enthält der Diff keine undokumentierte Code-Änderung. Die drei Konsolidierungen (Preisvalidierung, Register-Sperre, Zielpfad-Map) sind semantisch identisch: identische `ValueError`-Texte, identische Prüfreihenfolge inkl. `_known_project(name)` vor der Validierung, identische `flock`-/`suppress(OSError)`-Reihenfolge, identische Dict-Schlüssel/-Werte, unveränderte Signaturen. Alle entfernten Symbole habe ich mit eigenen, Repo-weiten Suchen nachgeprüft — null lebende Referenzen, auch nicht in `tests/`, `templates/`, `bin/vibe-run.sh` oder extensionlosen Dateien.

Die Manifest-Digests konnte ich nicht selbst nachrechnen (keine Ausführung von Skripten in meiner Rolle); die Byte-Felder stimmen jedoch für vier stichprobenartig zeilengenau nachgerechnete Dateien exakt (`vibe-web.py` −207, `vibe_github.py` −102, `vibe_packages.py` −61, `vibe_opencode.py` −107), und genau die zehn geänderten manifestüberwachten Dateien wurden aktualisiert — konsistent mit einem Regenerierungslauf.

- Critical: 0
- High: 0
- Medium: 0
- Low: 2

Verdict: **PASS** — alle fachlichen Akzeptanzkriterien sind mit Implementierungs- und (geliefertem) Testbeleg erfüllt; die zwei Low-Auflagen (Abschlussformalien, Summenangabe in der Doku) blockieren die fachliche Abnahme nicht, müssen aber vor Paketabschluss erledigt werden.

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Inventur des Produktstands liegt belegt vor (Fundkatalog mit Datei:Zeile, verhaltensrelevante Funde nur gemeldet) | PASS | `docs/features/GH-60.md:114-177` (Medium-/Low-Katalog), `:249-263` (Grenzen) | Eigene Stichprobe der Zeilenbelege: `vibe_packages.py:1329/1362` (`mark_blocked`/`mark_waiting_merge`), `setup-vibe.py:389` (`default_target`), `vibe_gates.py:78/114`, `vibe_limits.py:41`, `bin/vibe:6781` (`except (KeyError, IndexError)`), `vibe-web.py:2645-2676` (`page`/`classic_page`) — alle exakt |
| Fix-Mandat eingehalten: nur tote/unbenutzte/duplizierte Altlasten entfernt | PASS | 27 Kennungen A1–G4, siehe `docs/features/GH-60.md:60-112` | Eigene Repo-weite Suchen (worktree-weit, inkl. extensionloser Dateien): `_feedback_block`, `CHECKBOX_ANY`, `_pr_field`, `KEY_RE`, `_looks_like_server`, `nvpIssueStateLabel`, `NV_EVAL_LIVE_STATES`, `is_python`, `qLast`, `LAST_LANG` → 0 lebende Treffer; `_feedback_block` erscheint nur als Test-*Name* (`test_b6_ticket_marker_states.py:874`, Rumpf geprüft: nutzt es nicht) |
| CSS-Entfernungen ohne DOM-Wirkung; lebende Compound-Partner und `data-nv-*`-Hooks erhalten | PASS | `bin/web/nova.css` (`.nv-brand`, `.nv-agent-head`, `.nv-ticket-actions`, `.nv-feedback-item`, `.nv-access-signin`, `.nv-feature-text`, `.nv-input`/`.nv-select`, `.nv-accent-*`), `nova.css:1037` (`[data-nv-feedback-item][hidden]` erhalten) | `grep` nach allen acht Klassen repo-weit → 0 Treffer außerhalb `nova.css`; Akzent-UI nutzt `data-nv-accent` + Inline-Farbe (`nova-settings.js:470-491`), `.nv-swatch` hat keine CSS-Regel — Entfernung wirkungslos; CSS-Struktur an den Schnittstellen gelesen (`nova.css:590-636`, `808-826`, `1222-1237`) |
| Konsolidierungen semantisch identisch (Fehlertexte, Prüfreihenfolge, Signatur, `flock`) | PASS | `bin/vibe:5271-5287` + `5290-5298` + `5332`, `bin/vibe_runs.py:810-827` + `839-840/984-985/1230-1231`, `scripts/vibe-desktop.py:63-77` + `230/273/332` | Diff-Abgleich: Validierungsblock und Meldungen wortgleich; `_known_project(name)` weiterhin vor der Validierung; die drei `_locked()`-Körper byte-identisch übernommen, `os.makedirs`/`open` weiterhin erst beim `with`-Eintritt (Generator erzeugt Ressourcen erst in `__enter__`); alle 10 Aufrufstellen nutzen `with self._locked():`; Dict der Zielpfade in gleicher Schlüssel-/Wertfolge |
| Keine Testdatei angelegt/geändert/gelöscht (Test-Agent-Eigentum) | PASS | — | `git diff --name-only 5502fe1 76ba372`: 16 Pfade, davon kein `tests/`-Pfad, keine Umbenennung, keine Baseline (`tests/verify-baseline.json` unverändert) |
| Keine Schnittstellen-/Hook-/Vorlagenänderung (GENERAL_RULES, `templates/`, `data-nv-*`) | PASS | Diff umfasst ausschließlich `bin/*`, `bin/web/*`, `scripts/*` (außerhalb der Manifest-Bereiche) und zwei `docs/`-Dateien | `git diff --name-only`: kein `templates/`-Treffer, `bin/vibe:GENERAL_RULES` unberührt (Änderungen nur bei `_feedback_block` und den Preis-Funktionen) |
| Keine neuen Geheimnisse/Umgebungsangaben | PASS | `docs/features/GH-60.md`, `docs/import-manifest.json:1419-1438` | Muster aus `scripts/check-no-secrets.py:22-44` und `HOME_PATH_RE` (`build-release.py:72`) manuell gegen die neuen Textstellen geprüft: keine `/home/<user>/`, keine Schlüssel-/Zugangsdatenform; im Manifest keine IP/Host/Pfad-Angaben |
| Caching-Regel nicht verletzt, nichts Neues gecacht | PASS | Kein Cache hinzugefügt; `page.cache`/`classic_page.cache` (`bin/vibe-web.py:2645-2676`) unverändert und nur katalogisiert (`GH-60.md:121-124`) | Diff-Abgleich; im gesamten Changeset keine neue Cache-Variable |
| Manifest-Sync: Digests der 10 geänderten Dateien + `aenderungen`-Eintrag | PASS (Digest-Werte nicht selbst nachgerechnet) | `docs/import-manifest.json:1419-1438` (Eintrag), `:1451-1634` (10 Digest-Paare), `scopes` (`:1805-1813`) | Genau die 10 geänderten überwachten Dateien wurden aktualisiert, keine weiteren; Byte-Deltas zeilengenau nachgerechnet für 4 Dateien (exakt); `scripts/*` liegt nachweislich außerhalb der Scopes (`scopes` enthält nur `scripts/setup-vibe.py`) |
| Doku-Konsistenz: jede dokumentierte Änderung im Diff, keine undokumentierte Änderung, Zeilenbelege korrekt | PASS | `docs/features/GH-60.md:60-112` | Jede der 18 Tabellenzeilen im Diff gefunden (eigene Gegenprobe je Symbol/Block); Zeilenbelege stichprobenartig exakt; `+95/−179` = Diff ohne die Doku selbst (58+37 / 159+20) — rechnerisch korrekt; einzige Abweichung: Summenangabe „25 Fixes" (Low-Befund 2) |
| Vorbestands-Disziplin: Baseline unangetastet, drei Module nicht als GH-60-Regression | PASS | `tests/verify-baseline.json` nicht im Diff; `GH-60.md:48-53, 227-247` | Baseline-Datei unverändert (Diff-Pfadliste); Vorbestands-Signaturen (`test_release`, `test_bazzite_starter`, `test_f28_pylint_quality`) als gelieferter Beleg dokumentiert, nicht von mir reproduziert |
| Prüfschnittstelle: `verify.sh quick` Exit 0, `package/full` beim Runner | PASS (geliefert) | `GH-60.md:222-225` | Gelieferte Angabe: Manifest 72 Dateien OK, Syntax 253/8/4 OK, keine Geheimnisse, Exit 0; `verify.sh package|full` laut SPEC.md:301 Runner-Gate — von mir nicht ausgeführt |

## Findings

- [Low] `TICKETS.md:1462`, `docs/trilium-index.md`, `docs/features/GH-60.md` — Abschlussformalien des Pakets noch offen
  - Evidence: Der Ticket-Eintrag ist weiterhin `- [ ] GH-60 Code Janitor Runde` ohne `Commit:`/`Test:`-Zeile, obwohl `SPEC.md:294` und der GitHub-Workflow-Abschnitt in `AGENTS.md` („Tick the ticket (`[x]`) and add `Commit: <hash>; Test: <method or file>`") beides verlangen. `docs/features/GH-60.md` nennt keine Trilium-Notiz, und `docs/trilium-index.md` ist nicht Teil des Changesets (die globale `AGENTS.md`-Regel „Always document through Trilium MCP" und `SPEC.md:295` verlangen den Abschlussnachweis); der Review-Bericht selbst liegt erwartungsgemäß noch nicht im Repo.
  - Required fix: Vor dem Paketabschluss das Ticket auf `[x]` setzen und `Commit: 76ba372; Test: <Modul/Datei>` ergänzen, die Trilium-Notiz für GH-60 anlegen und in `docs/trilium-index.md` eintragen und diesen Review als `docs/reviews/GH-60-review-1.md` ablegen. Keine Codeänderung nötig.

- [Low] `docs/features/GH-60.md:60` — Summenangabe „25 Fixes" widerspricht der eigenen Fix-Tabelle
  - Evidence: Die Tabelle führt 27 Kennungen (`A1,A2`, `B1–B4`, `C1,C2`, `D1`, `E1,E2`, `E3–E10` = 8, `F1–F4`, `G1–G4`); zählt man den CSS-Sammelposten als zehn Einzelselektoren, sind es 29. Weder 25 noch eine dokumentierte Zählregel ist aus dem Text ableitbar. Die übrigen Zahlen der Zeile sind korrekt: `14 Dateien` (die 14 Code-Dateien im Diff) und `+95/−179` (Diff ohne diese Doku selbst).
  - Required fix: Entweder die Anzahl auf die tatsächliche Kennungszahl korrigieren (27) oder die Zählregel (z. B. „8 CSS-Selektorgruppen") in derselben Zeile nennen. Reine Doku-Korrektur, keine Codeänderung.

## Verifikation

- Changeset selbst erhoben: `git status --short` (leer, Worktree sauber), `git log --oneline -3` (HEAD `76ba372`, Ausgang `5502fe1`), `git diff --stat 5502fe1 76ba372` (16 Dateien, +358/−179), `git diff --numstat` (Code 14 Dateien +58/−159; Manifest +37/−20; Doku +263/−0), `git diff --name-only` (keine `tests/`, `templates/`, `TICKETS.md`, `scripts/verify.sh`), vier dateiweise Voll-Diffs (`bin/vibe*`, `bin/vibe_runs.py`, `bin/web/*`, `scripts/*`) sowie der komplette Diff von `bin/web/nova.css` und `docs/import-manifest.json`. Branch bestätigt über den Worktree-Kopf (`refs/heads/feature/m0p/gh-60`).
- Vom Werkzeug abgelehnt (`permission.rejected`): `git -C <pfad> …`, `git branch --show-current` und eine Verbundkette `cd … && git status --short && echo … && git branch …`. Ersatzweise wurde der Branch über die Worktree-`HEAD`-Datei gelesen; alle Diffs waren über die `cd && git …`-Form verfügbar.
- Eigene Leseprüfungen (kein Test-/Build-/Skriptlauf): Repo-weite Suchen nach allen entfernten Symbolen und CSS-Klassen; `_locked`-Aufrufstellen (3 Definitionen, 10 `with`-Stellen); `re`-Restnutzung in `vibe_runs.py` (3 Stellen, Import bleibt berechtigt); `os.`/`Path`-Restnutzung in `build-release.py`/`vibe_starter.py` (keine); `is_python`-Restnutzung (keine); `nova-settings.js:470-491` (Akzent-UI ohne die entfernten Klassen); `check-syntax.py` (Entfernung ohne Funktionsverlust, `python_files()` nutzt eigene Suffixliste); `check-import-manifest.py:29-145` samt `scopes` (`docs/import-manifest.json:1805-1813`); `check-no-secrets.py:22-44` und `build-release.py:72-73` gegen die neuen Doku-Texte; `TICKETS.md:1457-1464`.
- Mit gelieferter Ausgabe (in `docs/features/GH-60.md` dokumentiert, von mir **nicht** ausgeführt): 127 Feedback-/Kostentests OK, 88+102 Paket-/GitHub-Tests OK, 91 Registry-Tests OK, 61 Adapter-Tests OK, Browser 15/29/34 OK, 776-Test-Sweep OK, `verify.sh quick` Exit 0, Vorbestands-Signaturen für `test_release`/`test_bazzite_starter`/`test_f28_pylint_quality`.
- Nicht unabhängig ausgeführt: alle `unittest`-Läufe, `node --check`, `scripts/check-*.py` und `scripts/verify.sh` — meine Rolle erlaubt ausschließlich lesende Git-Kommandos; die Zahlen oben sind daher Berichtsbelege des Coding-Agenten, keine von mir reproduzierten Messungen.
- Wichtige geprüfte Bereiche: `bin/vibe` (Preis-Validierung, `_feedback_block`), `bin/vibe_runs.py` (Register-Sperren), `bin/vibe_packages.py` (`select_package`, `CHECKBOX_ANY`), `bin/vibe_opencode.py` (MCP-Schema-Layout), `bin/vibe_github.py`, `bin/vibe-web.py` (`subagents_of`, `page.cache`), `bin/web/{app,nova-evals,nova-project}.js`, `bin/web/nova.css`, `scripts/{build-release,check-syntax,vibe-desktop,vibe_starter}.py`, `docs/import-manifest.json`, `docs/features/GH-60.md`, `TICKETS.md`, `SPEC.md`, `AGENTS.md`.

## Grenzen der Prüfung

- **Keine eigene Testausführung.** Alle Test-, Browser-, `node --check`- und `verify.sh`-Ergebnisse sind geliefert, nicht reproduziert. Damit bleibt offen: Manifest-Prüfsummen (`sha256`, nur Bytes stichprobenartig exakt nachgerechnet), die drei Vorbestands-Signaturen und die Behauptung „pylint-Befundmenge unverändert".
- **Zählungen beruhen auf Lesen, nicht auf Werkzeugen.** Die Null-Referenz-Belege habe ich über eigene Suchen bestätigt, aber nicht über AST-/Compiler-Läufe; dynamische Zugriffe (z. B. `getattr`) habe ich per Suche nach den konkreten Namen geprüft.
- **Nicht prüfbar:** die Behauptung „sieben parallele Janitor-Agenten mit disjunktem Dateibesitz", die Zahlen der Modultestläufe und die `git archive`-Extraktion am Ausgangscommit (temporärer Pfad existiert nicht mehr im Repo).
- **Restrisiko:** Sollte ein `sha256`-Wert im Manifest von Hand getippt worden sein, fiele das erst im Runner-Gate (`verify.sh quick`) auf; die Byte-Deltas stimmen, die Struktur (genau 10 geänderte Dateien, keine weiteren Digest-Änderungen) ist konsistent.
- Die zwei Low-Auflagen (Ticket-/Trilium-/Review-Ablage, Summenangabe) sind vor Paketabschluss zu erledigen; sie betreffen keine Codezeile des Changesets.

Verdict: PASS

## Ablage-Vermerk (Koordinator, 2026-11-24)

Dieser Bericht wurde vom unabhängigen Review-Agenten (nur lesend, ohne Dateizugriff) erstellt und vom Koordinator unverändert als `docs/reviews/GH-60-review-1.md` abgelegt. Die zwei Low-Befunde sind unmittelbar danach erledigt worden:

1. **Summenangabe:** `docs/features/GH-60.md` nennt jetzt „27 Fixes (Kennungen A1–G4; die Zeile E3–E10 fasst zehn tote Selektoren)".
2. **Abschlussformalien:** Ticket GH-60 in `TICKETS.md` (Lokaldatei, bewusst unversioniert) ist auf `[x]` gesetzt mit `Commit:`/`Test:`-Nachweis auf `76ba372`; die Trilium-Notiz ist angelegt und in `docs/trilium-index.md` eingetragen; dieser Review ist die vorliegende Datei.

Zur Klarstellung des Low-1-Wortlauts („temporärer Pfad existiert nicht mehr"): Die `git archive`-Extraktion am Ausgangscommit lag unter dem freigegebenen temporären Bereich `/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/gh60-base-check` (nicht im Repository) und wurde nach Belegerhebung wieder entfernt; die Belege sind in `docs/features/GH-60.md` (Abschnitt Nachweise) festgehalten.
