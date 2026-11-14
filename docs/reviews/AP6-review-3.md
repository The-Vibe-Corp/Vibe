# AP6 Review Runde 3

Datum: 2026-11-09
Reviewer: code-reviewer (unabhängig, Session ses_e3e7393ceffeLTZ6qYixC3Mvj2)
Ausgangscommit: f44d8d6 · Verdict: **PASS** (0 Critical, 0 High, 0 Medium, 1 Minor)
Der Bericht wurde unverändert übernommen (inklusive der einem Modellsubstrat
entschuldbaren Tippfehleräußerungen in der Wiederherstellung der Zellen).
Orchestrator-Anmerkungen sind als solche markiert.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: **PASS**

## REVIEW-REPORT

### Acceptance criteria

| Prüfpunkt | Status | Implementation (file:line) | Test (file:method) / Nachweis |
|---|---|---|---|
| R2-1/Medium: Punkt-Slugs (`owner/my.repo`) zulässig, `./..`-Abschnitte abgelehnt | PASS | `bin/vibe_github.py:91-102` — Suffix-Strip nur für `.git` (Z. 95-96), Ablehnung exakt für Abschnitte `.`/`..` (Z. 99), danach `RE_REPO`-Garde (Z. 102) | Unit `GithubSlugDotNameTest` (3 Tests, tests/unit/test_ap06_github.py:1043-1073, URL- und scp-Form), `LinkDotSlugTest` (2 Tests, :1076-1105, byteidentischer Vorher-Zustand); Browser `test_github_link_button_keeps_dot_in_the_repository_name` (test_ap06_github_ui.py:383). Rotphasenlog /tmp/opencode/ap6-r2-unit-red.log (3 subTest-ERROR „owner/name erwartet“, :27-30, :37) und -browser-red.log (:4-22) gelesen; Grünlogs 54/9 OK gelesen. |
| R1.1-Randfälle des Punkt-Checks (eigene Zusatzprüfung) | PASS | | `owner/../name`, `owner/./name`, `./name` → `..`/`.` erfasst (Z. 99); `owner/..git` → Strip zu `..` → abgelehnt; `owner/.git` → Strip zu „owner/“+„“ → `RE_REPO` verweigert; mehrfach-Suffix `name.git.git` → strippt rekursiv zu `name`; scp mit zwei Abschnitten `git@github.com:owner/my.repo.git` → `owner/my.repo` (Test :1054). Kein lokaler Pfadtraversierungs-Sink: Slug dient nur als REST-URL-Anteil und Konfigurationswert. |
| R2-2/Medium: MR ohne Vorarbeit (link → origin/HEAD; Nachversuch im confirmed-Zweig) | PASS | `bin/vibe:1011` (`set_head_default` nach Remote-Set, best effort), `bin/vibe_github.py:447-450` (`remote set-head origin --auto`); Nachversuch exklusiv im Bestätigungspfad `bin/vibe:1063-1066` vor `create_pull_request`; Fallback-Fehler verständlich in `vibe_github.py:469-475` | Unit `DefaultBaseAfterLinkTest` (3 Tests, tests/unit/test_ap06_github.py:1108-1182; setUp beweist Vorbedingung „kein origin/HEAD“, :1122-1126); Browser `LinkOnlyMergeRequestUiTest` (test_ap06_github_ui.py:543-739, echter Dashboard-Prozess mit Fake-Token, PR-POST mit `base=="main"` verifiziert, :729-731, Sackgassen-Toast explizit negiert :733-735). Rotphase: `Ran 54 tests — FAILED (failures=3, errors=5)` inkl. exakter Sackgassen-Meldung (Protokoll :203-205, :171) gelesen; Grün 54 OK. |
| Seiteneffekte set-head (eigene Zusatzprüfung) | PASS | | Bereits bestehendes origin/HEAD wird bei bewusstem (Re-)link auf den echten Fern-Default gesetzt — keine Datenzerstörung (nur Symbol-Ref); Scheitern (unerreichbares Remote) ist best effort: die MR-Fehlermeldung nennt bleibenden Ausweg („base angeben oder origin/HEAD setzen“); in Doku als „beste Bemühung“ ausgewiesen (docs/features/AP6.md:169-171). |
| R2-3/Minor: Maskierung der link-Erfolgsmeldungen, Umbenennung vollständig | PASS | `bin/vibe_github.py:188` (`mask_url` öffentlich), Aufrufer `vibe_github.py:181`, `bin/vibe:1100`, `bin/vibe-web.py:739`; keine Restreferenz auf `_mask_credentials` im Code (nur in historischen Berichts-/Doku-Dateien) | `LinkMessageMaskingTest` (tests/unit/test_ap06_github.py:1017-1032) — Rotphase belegt Klartext in Ausgabe, Grünphase maskiert. Web-msg-Maskierung nur Unit-nahe Lücke (Testreport :760-765 dokumentiert, strukturell begründet: Karten-Knopf erzeugt nie Kontodaten). |
| R2-4/Minor: docs/features/AP6.md aktualisiert | PASS | docs/features/AP6.md:102-103 (54/9 — durch eigene Zählung bestätigt), Rundenverlauf :156-174, Verbatim-Anmerkung zu review-1 :158-161 | Entsprechende Inhalte gelesen; Zahlen stimmen mit grep-Zählung (54 Unit-Test-Methoden, 9 Browser-Tests). |
| R2-5/Minor: docs/baseline.md `/api/github`-Liste mit `push` | PASS | docs/baseline.md:250 (Aktionen settings/link/unlink/fetch/pull/**push**/issues/import/pr, `confirm`-Pflicht genannt) | Zeile gelesen; Push ist implementiert (`bin/vibe-web.py:749`, `bin/vibe:1119-1122`). |
| Gesamtwerk (Ticket AP6, AGENTS/SPEC, KISS, V-003/V-004/V-005, Manifest) | PASS | UI-Karte (app.js:570-614, zweistufige Bestätigung :594-596), Token nur aus env (vibe_github.py:46-52), Import über V-005-Storage (vibe_github.py:501-542), Argumentlisten überall (git()-Helfer Z. 150-164) | Suite-Grün durch übernommene Protokolle; TICKETS.md AP6 stand korrekt unbehaftet bis zur Abschlussschicht. |
| Manifest/Endstand konsistent | NOT VERIFIED (durch den Reviewer, Laufrechte) — bestätigt durch übertragene Ausgaben | 57 Dateieinträge gezählt, inkl. `bin/vibe_github.py` (Z. 47-50); docs/features/AP6.md:176-180 | check-import-manifest OK und verify.sh quick Exit 0 auf Endstand nur als übermittelte Ergebnisse der Orchestrierung; SHA-256-Nachrechnung nicht von ihm (Shell-Zugriff verweigert). |
| verify.sh full Endstand 1226 Tests, 3 paketfremde Failures | NOT VERIFIED (durch den Reviewer) | — | Orchestrierungsnachweis (Endstand + Reproduktion am Klon / unter TMPDIR-Report); die 3 Failures bestehen an `f44d8d6` identisch — von ihm nicht wiederausgeführt, Protokollpfade geprüft. |

### Findings
- [Minor] `docs/baseline.md:160` — veraltete Zeilenreferenzen für die GitHub-CLI
  - Evidence: Die Baseline nennt `bin/vibe:1068-1162` (`cmd_github`), `bin/vibe:1163` (`github_cli`) und Dispatch `bin/vibe:4830`; aktuell liegen `def cmd_github` bei `bin/vibe:1075`, `def github_cli` bei `bin/vibe:1170` und der Dispatch bei `bin/vibe:4841` (+7/+7/+11 Versatz durch die Runde-2-Codeergänzungen). Bloße Dokumentenungenauigkeit, kein Code- oder Verhaltensdefekt.
  - Required fix: Zeilenreferenzen auf den Endstand angleichen (oder auf Symbolnamen umstellen, um solchen Versatz künftig zu vermeiden).

*(Orchestrator-Anmerkung: Dieser Minor wurde nach dem PASS rein dokumentarisch behoben — docs/baseline.md nennt jetzt Symbolnamen mit fester Zeile als Anhalt statt fehleranfälliger Zeilenbereiche. Keine Codeänderung; keine erneute Reviewrunde erforderlich.)*

### Verification
- Change set reviewed: Arbeitsbaum von Branch `vibe/vibe-AP6-1794238201536384312-14374-6010` gegen Referenz `f44d8d6` (Base-Klon /tmp/opencode/ap6-base gelesen: enthält weder `vibe_github.py` noch einen GitHub-Abschnitt in `bin/vibe` — passt zu „AP6 alle Änderungen uncommitted“). Ein direkter `git diff f44d8d6` war möglich-nicht (Shell-Berechtigungen verweigert); die Vorher-Nachher-Belege stammen stattdessen aus den gelesenen Rot-/Grünprotokollen und dem Base-Klon.
- Git commands run by reviewer: `git status --short`, `git branch`, `git diff` — nicht ausführbar (permission.rejected auf shell); Ersatzaussagen durch Dateivergleich (Arbeitsbaum vs. /tmp/opencode/ap6-base).
- Checks mit übernommenen Ausgaben: `unittest tests.unit.test_ap06_github` (54 OK) und `tests.browser.test_ap06_github_ui` (9 OK), `verify.sh quick` Exit 0, `check-import-manifest.py` OK (57 Dateien), `verify.sh full` Endstand 1226 Tests mit 3 paketfremden Failures am unveränderten `f44d8d6` reproduziert — übernommen aus der Orchestrierungsangabe und, soweit Protokolldateien (Rot-/Grünphase-Log), direkt gelesen.
- Checks not independently run: alle Build-/Test-Läufe (verify.sh quick/full, unittest, Playwright, SHA-256-Nachrechnung des Manifests, Trilium-Schreibprüfung).
- Important areas inspected: `bin/vibe_github.py` (komplett), `bin/vibe:990-1180` (GitHub-CLI), `bin/vibe-web.py:690-781` (`/api/github`), `bin/web/app.js` (confirm-Flow), `tests/unit/test_ap06_github.py` (komplett, 54 Methoden), `tests/browser/test_ap06_github_ui.py` (9 Tests), `docs/features/AP6.md`, `docs/baseline.md:160,250`, `docs/import-manifest.json`, `docs/reviews/AP6-review-2.md`, `docs/reviews/AP6-test-agent-report.md` (Abschnitt Review Runde 2), Rot-/Grünprotokolle unter /tmp/opencode/ap6-r2-*.log.
- Remaining risks: Manifest-SHA-Abgleich und die drei paketfremden full-Suite-Failures sind nur vom Orchestrierungsnachweis gestützt; die Verbatim-Datei `docs/reviews/AP6-review-1.md` bleibt konservativ als Artefakt der Historie in der `docs/features/AP6.md`-Anmerkung erfasst.
