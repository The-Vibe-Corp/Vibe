# Review F31 — Runde 3 (unabhängiger code-reviewer, 2026-11-14)

Delta-Review zum Port des abgenommenen F31-Stands (9006814) auf die neue Basis 086397d (Merge-Commit 2b1839c). Runde 1/2: docs/reviews/F31-review-1.md (CHANGES REQUIRED, behoben) und docs/reviews/F31-review-2.md (Verdict: PASS).

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 0
- Verdict: CHANGES REQUIRED

## Acceptance criteria (Delta-Review-Gegenstände)
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| D1 Merge-Korrektheit: 13 F31-Dateien, keine Scope-Drift | PASS | `git diff 086397d 2b1839c --stat` exakt 13 Dateien (+1349/-7); `git diff 9006814 2b1839c` zeigt ausschließlich die Basis-Änderungen (templates/*, AGENTS.md, SPEC.md) — alle F31-Dateien inkl. `bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `docs/import-manifest.json`, `docs/handbuch.md`, `docs/baseline.md`, beide Testdateien und die Review-/Testberichte sind byte-identisch zu `9006814` | Vom Reviewer selbst verifiziert (leerer Diff für die geprüften Dateien); `2b1839c` als Tip des Paketbranches `refs/heads/vibe/vibe-F31-1794687059321717955-1217480-8600` per `git log --graph` bestätigt |
| D2 Runde-2-PASS-Anker im Port unverändert | PASS | Marker-Prüfreihenfolge `bin/vibe:2462-2470`, Digest-Schutz `bin/vibe:2480` (`write_text(expected=digest)`), Symlink-Ablehnung `bin/vibe:2423,2457,2513`, Speichern-Button nur bei `v.exists` `bin/web/app.js:342` | Byte-Identität zum Runde-2-PASS-Stand + Stichproben im Arbeitsbaum des Ports; `templates/generic/AGENTS.md` enthält weiterhin `# Projekt: {{NAME}}` (Browser-Anker Fall 14) |
| D3 Semantische Kompatibilität mit neuer Basis (openwrt entfernt) | PASS | `agents_file_create` (`bin/vibe:2503-2510`): Typ über `ptype()`, Fallback `generic` falls `typ not in types()`; `types()` (`bin/vibe:2332-2333`) listet reale Vorlagenordner — fehlendes `openwrt` führt damit korrekt zum generic-Fallback | `test_create_unknown_type_falls_back_to_generic` deckt die Fallback-Mechanik mit beliebig unbekanntem Typ ab (Klasse des openwrt-Problems); `ddd1d4d`-Diff bestätigt Entfernung von `templates/openwrt/AGENTS.md` |
| D4 Doku-Konsistenz des Ports | FAIL | `docs/features/F31.md` — Port-Dokumentation (Kopf Z. 4-8, Abschnitt „Port auf die neue Basis" Z. 12-25, Prüfungs-Absatz Z. 156-165) existiert nur uncommitted im Paket-Worktree; der committete Stand `2b1839c` enthält den Vor-Port-F31.md (Kopf verweist auf Ausgangscommit `88509a0` und den alten Branch, kein Port-Absatz) | Siehe Finding 1 |

## Findings

- [Medium] `docs/features/F31.md:164-165` (uncommitted im Worktree `vibe-F31-8eXWTg`; Merge-Commit `2b1839c` enthält diesen Stand nicht) — Port-Dokumentation ist nicht committet, unvollständig und enthält eine falsche Verweis-Zusicherung
  - Evidence: `git status --short` im Paket-Worktree zeigt genau `M docs/features/F31.md`; `git show 2b1839c:docs/features/F31.md` endet vor dem Port-Absatz, d. h. der committete Paketstand dokumentiert den Port nicht (Kopf nennt weiterhin `88509a0`/alten Branch). Der uncommittete Absatz behauptet „der Fail-Mengen-Vergleich ist unten in dieser Datei dokumentiert" — die Datei endet aber bei Zeile 165; ein Fail-Mengen-Vergleich existiert dort nicht. Die Port-Testergebnisse (Unit 14 OK/Browser 4 OK am Port, tmpfs-Discover an Basis und Port) sind weder im Testbericht (`docs/reviews/F31-test-agent-report.md`, byte-identisch zum Merge, endet bei Z. 207 ohne Port-Läufe) noch sonstwo committet. Der agentenseitig gelieferte Inhalt stimmt mit den Verifikationen des Reviewers überein (Byte-Identität, Manifest an Basis unverändert), doch die dokumentierte Nachweisstelle ist leer — derselbe Dokumentationsmangel-Typ wie Review Runde 1, Finding 1.
  - Required fix: Den Fail-Mengen-Vergleich tatsächlich in F31.md einfügen (oder die Zusicherung entfernen und den Vergleich dokumentiert im Testbericht/Abschlussbericht verankern); die vervollständigte F31.md im Paketbranch committen, sodass der Nachfolgecommit von `2b1839c` den Port-Kopf und den Port-Absatz enthält. Inhaltlich nichts erfinden — nur die bereits belegten Ergebnisse (tmpfs-Discover, 3 Umgebungs-Flakes mit Wiederholungsläufen OK, 23 Manifest-Abweichungen) niederschreiben.

## Verification
- Change set reviewed: `086397d..2b1839c` (Merge auf Paketbranch) sowie der Arbeitsbaum des Paket-Worktrees `vibe-F31-8eXWTg`.
- Git commands run by reviewer: `git status --short` (beide Worktrees), `git log --oneline/-graph/-all`, `git diff 086397d 2b1839c --stat` und je Datei, `git diff 9006814 2b1839c --stat` und je Datei (Byte-Identitätsnachweis), `git diff 2b1839c --stat` (Arbeitsbaumvergleich), `git diff 88509a0 086397d --stat` und `git log 88509a0..086397d -- docs/import-manifest.json` (Basisdefekt: Manifest zwischen 88509a0 und 086397d unverändert, Templates doch geändert), `git diff 086397d 2b1839c -- docs/baseline.md`, `git show 2b1839c:docs/features/F31.md`, Commit-Metadaten für 9006814/2b1839c/086397d/ddd1d4d.
- Checks with supplied output (agentenseitig, vom Reviewer nicht wiederholt): Unit 14 OK und Browser 4 OK am Port (Arbeitskopie und tmpfs-Klon), tmpfs-Discover Basis 1766 (29F+17E) / Port 1780 (29F+17E) Unit und Browser 153/157 mit identischer normierter Fail-Menge bis auf 3 dokumentierte tearDownClass-Umgebungs-Flakes (Errno 39, Wiederholungsläufe OK), `node --check`/Syntax/Secrets OK, `check-import-manifest.py` mit 23 Abweichungen ausschließlich templates/* (bin-Hashes korrekt). Strukturell bestätigt: Manifest im Basisbereich unverändert bei geänderten Templates (Basisdefekt-Einordnung korrekt, F31 hat nichts verschleiert); F31s Manifest-Einträge (3 bin-Dateien + aenderungen) sind byte-identisch zum Runde-2-geprüften Stand.
- Checks not independently run: alle Testläufe, Hash-Berechnungen, merge-tree-Proben.
- Important areas inspected: Merge-Diff komplett, `agents_file_create`/`types()`/`ptype` im Port-Baum, beide Testdateien (Skip-Muster unverändert), F31.md (committed vs. Arbeitsbaum), Testbericht, Manifest-Basisdefekt, `docs/baseline.md`-Nachpflege (korrekt, in Scope).
- Remaining risks: (1) Der committete Paketstand dokumentiert den Port nicht — Finding 1 muss vor dem Abschluss behoben sein; (2) Testergebnisse und Hashes weiterhin nur agentenseitig belegt; (3) die 46 vorbestehenden Basis-Fails sind agentenseitig dokumentiert und durch den strukturell bestätigten Basisdefekt plausibilisiert, aber nicht vom Reviewer ausgeführt.

## Verdict: CHANGES REQUIRED
