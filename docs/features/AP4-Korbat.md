# AP4-Korbat — Arbeitspaket-Abschlussprozess für GitHub-verknüpfte Projekte überarbeiten

Stand: 2026-11-21
Branch: `feature/korbat/ap4-korbat` (Ausgangscommit `212d97d`, auf `dev`)
Spezifikation: TICKETS.md AP4-Korbat; detaillierte, vom Nutzer freigegebene
Vorgabe: Audit-Dokument `AP3.md` (Abschnitte §3–§8) des Audit-Arbeitsbereichs
(`vibe-audit`, `docs/features/`) mit Kontext aus `AP2.md` (§4, §5) und
`AP1.md` (gleicher Ordner).
Umfang: T-G0, T-G7, T-G1, T-W2, T-W1, T-G2, T-G3, T-G4, T-G5, T-I1, T-I2,
T-S1. Bewusst descoped (Nutzerentscheidung): T-G6 (In-product working-copy
repair).

---

## 1. Zusammenfassung

Der Abschluss eines Arbeitspakets war widersprüchlich geregelt: SPEC.md enthielt
zwei einander ausschließende Git-Workflows (Agent mergt selbst vs. Mensch
mergt), der generierte AGENTS.md-Regelblock enthielt einen Abschnitt dreifach,
der Läufer mergte den Paketbranch lokal per Fast-Forward in den
Integrationsbranch, während GitHub denselben PR per Squash merge — der
Integrationsstand driftete danach permanent. Es gab keinen Wiederverbindungs-
pfad für unterbrochene Arbeitskopien, keine Session-↔-Worktree-Bindung und
keinen Schalter für automatische PR-Merges.

AP4 macht den Runner zum alleinigen Eigentümer des Abschlusses (AP3 §3.1:
Agenten mergen nie, in keinem Projekt) und ersetzt die widersprüchlichen
Texte durch je eine kanonische Quelle. Die Abschlussfolge ist jetzt:

1. Paketprüfung + Abschlussschranke (wie bisher),
2. **`ensure-mergeable`** (neu, T-G7): fetch `--prune`, `git merge
   --no-ff --no-edit origin/<base>` in der Arbeitskopie; bei Konflikt bleibt
   der konfliktbehaftete Baum stehen, der Agent löst in einer Reparaturrunde
   (`git add`, `git merge --continue`), ein zweiter Konflikt bricht ab und
   blockiert das Paket. Kein Push in diesem Schritt.
3. `github-complete` (Push + Merge-Request, wie bisher; jetzt idempotent
   gegenüber bereits bestehendem PR),
4. **Verzweigung nach `GITHUB_AUTO_MERGE`** (neu, T-G0/T-G1):
   - **PR-only (Standard, Schalter aus):** der Lauf hält an, ohne lokal zu
     mergen. Die Arbeitskopie bleibt registriert (T-W2), das Ticket erhält
     einen Blockievermerk (verhindert erneute Auswahl), der Bericht nennt
     „wartet auf Merge“ und den nächsten Schritt
     (`vibe package close <projekt> <id>`).
   - **Auto-Merge („1“):** der Runner mergt den freigegebenen PR per REST
     (Squash) — mit genau EINEM begrenzten Reparaturdurchlauf bei
     Wettrennungs-Konflikten (ensure-mergeable → Push → Merge-Wiederholung),
     danach Rückfall auf PR-only. Nach erfolgreichem Merge: Integrationsbranch
     per `fetch --prune` + `merge --ff-only origin/<base>` auf die Fernspitze
     (T-G1: keine lokalen Feature-Commits mehr), Nachweis-Sync aus der
     Arbeitskopie, worktree-bewusstes Aufräumen (T-G4), Registry- und
     Session-Bereinigung.
5. **`vibe package close <projekt> <id>`** (neu): zweite Abschlussphase für
   PR-only — verifiziert per REST, dass der PR tatsächlich gemergt ist
   (`state=closed` und `merged=true`), holt den Integrationsstand auf die
   Fernspitze, übernimmt `[x]`/Nachweis aus dem registrierten Worktree
   (einschließlich Entfernen der BLOCKIERT-Marke), räumt Arbeitskopie/Branch
   auf und vergisst die zugehörigen Sessions.

Lokale Projekte ohne GitHub-Verknüpfung behalten das bisherige Verhalten
(lokaler Fast-Forward-Merge durch den Runner), ergänzt um Registry- und
Session-Pflege.

## 2. Untertickets und Umsetzung

| ID | Umsetzung (Kurzform) |
|---|---|
| T-G0 | `GITHUB_AUTO_MERGE` in `.vibe/project.env` (read_config-Schlüssel `auto_merge`, nur exakt „1“ gilt); `merge_pull_request` (REST PUT …/pulls/<n>/merge, Squash) + Subkommando `github-merge`; Checkbox in beiden Oberflächen; `status()` meldet `auto_merge`. |
| T-G7 | `ensure_mergeable` + Subkommando `ensure-mergeable` (fetch `--prune`, merge `--no-ff --no-edit`, Konflikt stehen lassen + `KONFLIKT:`-Pfade, `--abort` für den zweiten Fehlversuch); Läufer-Reparaturanweisung nach AP3 §4.2. |
| T-G1 | Kein lokales `merge_package` mehr im GitHub-Fall; Integrationsstand nur noch über `fetch --prune` + `merge --ff-only origin/<base>` auf die Fernspitze; PR-only-Halten mit Blockievermerk; `vibe package close` als zweite Phase. |
| T-W2 | `WorktreeRegistry` in `bin/vibe_runs.py` (`<runtime>/worktrees.json`, Sperrdatei, atomar); CLI `worktree-get/-register/-unregister`; `create_worktree` verbindet wieder (RECONNECT) mit gültigem Eintrag (Pfad existiert, erscheint in `git worktree list`, Branch existiert) und überspringt dann copy-notes. |
| T-W1 | `SessionRegistry.observe` um `worktree_path`/`package_id`/`branch` erweitert; `stream`-Optionen; Läufer setzt sie je Paket; `vibe sessions resume` und Dashboard-Fortsetzung reichern den Lauf um `VIBE_RESUME_PACKAGE` an; `select --prefer <id>` wählt das Paket des re-attachten Sessions vorrangig; `sessions-forget-worktree` bereinigt beim Aufräumen. |
| T-G2 | `--prune` in `fetch`, `pull_integration`, `integration_state` (und ensure-mergeable). |
| T-G3 | `github_link` setzt best-effort Upstream für lokale Branches mit existierendem `origin/<branch>` (nicht fatal, Meldung in der Ausgabe). |
| T-G4 | `cleanup_worktree` prüft `git worktree list --porcelain`, entfernt/prüft Arbeitskopie vor dem Branch-Löschen (`-d`; nach verifiziertem Squash-Merge erlaubter `-D`-Fallback mit Begründung); `checkout_branch` verweigert in anderer Arbeitskopie ausgecheckte Branches verständlich. |
| T-G5 | `package_branch_name` Kollisionsprüfung inkl. `refs/remotes/origin/…` und in Arbeitskopien ausgecheckter Branches. |
| T-I1 | SPEC.md: die beiden „Strictly Enforced“-Blöcke ersetzt durch EINEN kanonischen Abschnitt „Git & work-package closing (runner-owned)“ (AP3 §6.1); „Nicht im Umfang“-Zeile nach AP3 §6.2; `GENERAL_RULES`-Zeile nach AP3 §7.3 (B16-Inhaltsmarker Push/Merge-Request/„aktivier…“ bleiben erhalten); `vibe_github`-Docstring nennt Auto-Merge. |
| T-I2 | Abschnitt „Laufende Instanz nicht verändern (verbindlich)“ steht nicht mehr 3× direkt hintereinander: `bin/vibe` `GENERAL_RULES` und alle fünf `templates/*/AGENTS.md` (android, docker, generic, rebuild, web) enthalten ihn jetzt genau 1×; Vorlagen-Blöcke bleiben bytengleich zu `GENERAL_RULES`. |
| T-S1 | `sessions-finish` persistiert den Laufendzustand auf allen Session-Einträgen des Laufs (Läufer ruft es in `register_finish`); `session_overview` zieht den persistierten Zustand heran, wenn der Lauf-Eintrag fehlt; Alterspflege (30 Tage) entfernt beim `sessions-finish` nur Einträge ohne (noch existierenden) Worktree-Anhang. |

## 3. Getroffene Entscheidungen

- **PR-only hält den Lauf an** (nicht nur das Paket): Nach AP3 §5 Schritt 9
  („else stop“) endet der Lauf nach dem Merge-Request mit klarer Anweisung
  (merge auf GitHub, dann `vibe package close`, dann neuer Lauf). Das
  verhindert gestapelte PRs und Basis-Abweichungen; der Bericht listet
  „Wartet auf Merge“ mit MR-URL.
- **`git branch -d` nach Squash-Merge:** Squash erzeugt einen neuen Basis-
  Commit ohne Abstammung vom Feature-Branch, `-d` scheitert daher zwangsläufig.
  Nach per REST verifiziertem Merge ist `-D` zulässig und wird mit Begründung
  protokolliert (AP2 §7: „never -D unless the branch is confirmed merged“ —
  hier: verifiziert).
- **Session-Bereinigung asymmetrisch (dokumentierte Abweichung vom AP2-Entwurf
  „tie to cleanup_worktree“):** Im GitHub-Abschluss (Auto-Merge und
  `package close`) werden die Sessions des Worktrees beim Aufräumen vergessen;
  im lokalen Modus bleiben sie als Verlauf mit persistiertem Endzustand
  erhalten (T-S1-Fall „Zustand überlebt das Laufregister“) und werden über
  die 30-Tage-Alterspflege entfernt, da ihr Worktree dann nicht mehr
  existiert. Beides ist über Tests belegt und begrenzt (Limit + Alterspflege).
- **`ensure-mergeable` merged, nie rebased** (AP3 §4.1): Merge-Commits sind
  auf bereits gepushten Branches sicher; Force-Push bleibt verboten.
- **Nova-Feature-Defaults (Nutzerentscheidung Option B, Rückfrage
  `q409cd6f04517`, 2026-11-21):** Alle Feature-Bereiche bleiben standardmäßig
  ausgeblendet (AP22 unverändert); ergänzt wurden nur die fehlenden
  GitHub-Aktionen (link/unlink/fetch) und die neue Funktionalität hinter den
  bestehenden Gattern.
- **`complete_package` idempotent:** existiert bereits ein offener PR für den
  Branch, wird dessen URL übernommen statt ein zweiter PR erzeugt (nötig für
  Reattach/Reparaturläufe desselben Pakets).

## 4. Geänderte Schnittstellen

- CLI `vibe`: neu `vibe package close <projekt> <id>`;
  `vibe github … status` zeigt Auto-Merge; `vibe sessions resume …` startet
  im selben registrierten Worktree (Umgebung `VIBE_RESUME_PACKAGE`);
  `github link` setzt Upstream best-effort.
- `vibe_packages.py`-Subkommandos: neu `ensure-mergeable` (Exit 0 ok/Skip,
  2 Konflikt mit `KONFLIKT:`-Zeilen, 1 Fehler, `--abort`),
  `github-merge` (Exit 0/2/1), `github-push`; `select` mit `--prefer`.
- `vibe_runs.py`-CLI: neu `worktree-get/-register/-unregister`,
  `sessions-finish`, `sessions-forget-worktree`; `stream` mit
  `--session-worktree/-package/-branch`.
- Web-API: `/api/github` `settings` akzeptiert `auto_merge`;
  neu `/api/package` (`{name, id, action:"close"}`, guarded wie die übrigen
  projektebezogenen Endpunkte); `start_continue` reichert die Fortsetzung um
  das Session-Paket an.
- GUI: Auto-Merge-Checkbox (klassisch + Nova); Nova-GitHub-Karte mit
  link/unlink/fetch; Session-Zeilen zeigen Paket-/Worktree-Anhang;
  „Paket abschließen“ je blockiertem Ticket (Nova-Arbeiten-Reiter).
- `.vibe/project.env`: neuer Schlüssel `GITHUB_AUTO_MERGE` (Standard leer =
  PR-only).

## 5. Nachweise

- **Rotphase vor Implementierung:** 66 neue Testfälle (vier Module
  `tests/unit/test_ap4_korbat_*.py`), Fallbeschreibungen und echte
  Rot-Ergebnisse in `docs/reviews/AP4-Korbat-test-agent-report.md`
  (einschließlich dreier dort dokumentierter und korrigierter
  Test-Setup-Defekte, §§8–9).
- **Fortgeschriebene Bestandstests** (vom Test-Agenten, nicht abgeschwächt):
  `test_b16_runner_wiring.py` (GitHub-Erfolgsfall = PR-only mit gestärkten
  Assertions; Auto-Merge-Erfolg in `test_ap4_korbat_github`),
  `test_ap9_runner_wiring.py` (Reihenfolgeprüfung auf dem Paketbranch).
- `bash scripts/verify.sh quick` → Exit 0 (211 Python-, 8 Bash-, 3 JSON-Dateien
  syntaktisch geprüft); `python3 scripts/check-no-secrets.py` → OK;
  `bash -n bin/vibe-run.sh` → OK.
- `bash scripts/verify.sh package` → **Ran 403 tests, failures=2** — beide
  vorbestehend und am Ausgangscommit `212d97d` verifiziert
  (`test_ap06_github.CliPushTest…`: Push-Fehlermeldung ohne „Remote“-Wortlaut;
  `test_ap9_github…clone…`: `NameError agent_note` in
  `_adopt_checked_out_project`, am Basiscommit Zeile 2828 identisch vorhanden,
  AP4-Diff berührt die Funktion nicht). Alle 66 AP4-Fälle, die
  fortgeschriebenen Fälle und alle übrigen betroffenen Bestandsmodule grün;
  Prüf-Exit 5 allein wegen der zwei vorbestehenden Baseline-Fehler.
- `bash scripts/verify.sh package` → **Ran 403 tests, failures=2** — beide
  vorbestehend und am Ausgangscommit `212d97d` verifiziert
  (`test_ap06_github.CliPushTest…`: Push-Fehlermeldung ohne „Remote“-Wortlaut;
  `test_ap9_github…clone…`: `NameError agent_note` in
  `_adopt_checked_out_project`, am Basiscommit Zeile 2828 identisch vorhanden,
  AP4-Diff berührt die Funktion nicht). Alle 66 AP4-Fälle, die
  fortgeschriebenen Fälle und alle übrigen betroffenen Bestandsmodule grün;
  Prüf-Exit 5 allein wegen der zwei vorbestehenden Baseline-Fehler.
- `bash scripts/verify.sh full` → **Ran 2244 tests (= 2178 am Basisstand +
  66 neue AP4-Fälle, alle grün), failures=59, errors=100, Prüf-Exit 5.**
  Regressionsschutz durch umgebungsgleichen Vergleich: derselbe Volllauf am
  Ausgangscommit `212d97d` (isolierter Basis-Worktree, identische
  Prüfumgebung) ergab **Ran 2178, failures=59, errors=100** —
  Per-Test-Abgleich der Fehlerlisten: genau **3** Differenzen, alle durch
  AP4 verursacht und behoben bzw. als Laufzeitartefakt bewiesen:
  1. `vibe package` (neues CLI-Kommando) und `POST /api/package` (neue
     Route) waren nicht im Bestandsinventar dokumentiert → um je eine Zeile
     in `docs/baseline.md` ergänzt; `test_baseline_inventory` danach grün
     bis auf die 10 am Basisstand bereits fehlenden AP22-Routen
     (Identität mit Basis-Fehlerliste geprüft).
  2. `test_repository_matches_committed_manifest`: die 13 von AP4 geänderten
     Programm-/Vorlagendateien wichen vom committeten Import-Manifest ab →
     `docs/import-manifest.json` nach der seit AP2 üblichen Konvention
     aktualisiert (Größen/SHA-256 der geänderten Dateien plus
     AP4-Korbat-Eintrag im Änderungsprotokoll);
     `python3 scripts/check-import-manifest.py` → OK (67 Dateien),
     `test_import_manifest` → 8/8 OK.
  3. `test_repository_agents_file_contains_the_test_agent_rule` hängt am
     Inhalt der Laufzeit-AGENTS.md (gitignorede Nutzerdatei im Wurzelordner,
     von AP4 nicht angetastet): mit derselben Datei schlägt der Test am
     Basiscommit identisch fehl (nachgestellt und bewiesen; am Basisvolllauf
     war er nur ein ERROR, weil dort die gitignorede Datei fehlt) — kein
     AP4-Verstoß.
  Alle übrigen Fehlerfamilien (u. a. `agent`-/`agent_note`-NameError-Kaskade
  aus `cmd_init`/`_adopt_checked_out_project`, TESTER/Test-Agent-Familien,
  bwrap-Kernel-Restriktion, AP22-Routen-Dokumentation, Push-/Clone-Fälle,
  run_autostop/feedback/ap12-Umgebungsfamilien) sind in beiden Vollläufen
  identisch rot und damit vorbestehende Baseline-Fehler — keine neuen
  Fehlschläge durch AP4. Nach den beiden Dokumentationsergänzungen
  (docs/baseline.md, docs/import-manifest.json — keine Code- oder
  Teständerung) wurden deren betroffene Module direkt nachgeprüft:
  `test_import_manifest` 8/8 OK, `test_baseline_inventory` nur noch der
  vorbestehende AP22-Routenfehler, `test_release` unverändert vorbestehend
  rot wie am Basisstand.
- Grenzen: kein Playwright und kein JS-Interpreter in der Umgebung —
  Browser-/JS-Prüfung als Quelltext-/Strukturassertion (Bestandsmuster);
  kein echtes GitHub — REST über lokale Attrappen (`RestFakeServer`,
  `PullFakeServer`); echte Läufe in `vibe-run.sh` über Fake-Agenten der
  Wiring-Fixtures. `test_web_api_security` läuft nur mit bereinigter
  Umgebung grün (Agenten-Shell erbt `VIBE_UI_BIND`); `verify.sh` bereinigt
  die Umgebung selbst, die Schranke ist davon nicht betroffen.

## 6. Vom Nutzer selbst vorzunehmende Schritte (nicht durch Agenten umgesetzt)

1. **AGENTS.md — eigene Abschnitte des Nutzers anpassen (ausdrückliche
   Nutzervorgabe: kein Agent):** Die nutzergewarteten Abschnitte der
   Projekt-AGENTS.md (im eigenen Wording, z. B. der Abschnitt „GitHub
   workflow“ der vibe-Arbeitskopie, der Agenten das Mergen noch erlaubt)
   widersprechen der neuen Runner-eigenen Politik. Ersatz-Textvorschlag
   (AP3 §7.1, auf dieses Repo angewandt):
   > ## GitHub workflow (runner-owned)
   >
   > - The runner owns worktree, branch, mergeability, push, PR, merge and
   >   cleanup. You never create, switch, merge, rebase, force-push or
   >   delete branches.
   > - You work only in the worktree path given in the task (`$WT`); do not
   >   touch the integration directory (`$P`).
   > - Before close, the runner ensures the PR is mergeable by merging
   >   `origin/<integration_branch>` into your feature branch. If it reports
   >   a conflict, do not start a new merge and do not abort the runner's
   >   merge; resolve the conflicts in the working tree, `git add` the
   >   resolved files, and run `git merge --continue` (or `git commit`); do
   >   not use `--ours`/`--theirs` wholesale; never rebase or force-push.
   > - Commit with the package prefix (`<ID>:`). Stage only your own files.
   > - Tick the ticket (`[x]`) and add `Commit: <hash>; Test: <method or file>`.
   > - Leave the worktree clean. Do not merge, push or delete branches; the
   >   runner performs closing per `GITHUB_AUTO_MERGE` in `.vibe/project.env`.
   > - Verification gates are run by the runner; do not re-run the full suite
   >   unless asked.
2. **Verwalteten AGENTS.md-Block aktualisieren:** Der deduplizierte
   Regelblock (`GENERAL_RULES`) wird beim nächsten `vibe run` automatisch in
   bestehende Projekte übernommen — außer die AGENTS.md hat selbst
   uncommittete Änderungen (F27-Schutz). Dann: erst die eigenen Änderungen
   committen, dann Lauf starten; alternativ im Dashboard
   (Projekteinstellungen → AGENTS.md → Datei speichern) übernehmen. Das
   setzt eine aktualisierte Installation voraus (Punkt 4).
3. **Auto-Merge je Projekt einschalten (optional):** `GITHUB_AUTO_MERGE="1"`
   in `.vibe/project.env` des Projekts oder Dashboard-Checkbox
   (Projekteinstellungen → Git & GitHub → Auto-Merge). Standard bleibt aus
   (PR-only).
4. **Installation aktualisieren:** Dieses Paket ändert nur das Repository.
   Die laufende Installation (`_toolchain`) wird — wie verbindlich — nicht
   von Agentenläufen angetastet; Update wie gehabt mit autorisierter Quelle
   (`Setup --update --source <repo>`).
5. **PR-only-Alltag:** PR auf GitHub prüfen und mergen, danach
   `vibe package close <projekt> <id>` (CLI oder Dashboard-Taste
   „Paket abschließen“ im Arbeiten-Reiter des Projekts) und anschließend den
   nächsten Lauf starten.
6. **Nova-Bereiche freischalten:** Feature-Bereiche bleiben gemäß
   Nutzerentscheidung Option B standardmäßig ausgeblendet; Einschalten wie
   gehabt über Einstellungen → Funktionen (je Browser).
7. **Descoped (bewusst nicht umgesetzt):** T-G6 In-product working-copy repair
   (status/diff/stage/commit/discard in der Oberfläche) — vom Nutzer aus dem
   Umfang genommen.
8. **Außerhalb dieses Repos:** die Pendants `pi-infra/agent-instructions.md`
   und `pi-infra/vibe/agent-instructions.md` („git branch -D“, „Agent never
   merges“) gehören anderen Repositories und sind vom Nutzer anzupassen
   (Empfehlung: `-D` → `-d`, Merge-Autorität an den Runner/GITHUB_AUTO_MERGE).

## 7. Offene Punkte / bekannte Baseline-Defekte (nicht AP4)

- `bin/vibe` `cmd_init` verweist auf eine undefinierte Variable `agent`
  (NameError, am Ausgangscommit identisch vorhanden) — offener AP2-Restfehler,
  nicht Teil dieses Pakets.
- `bin/vibe` `_adopt_checked_out_project` verweist auf `agent_note`
  (NameError, Basiscommit Zeile 2828) — dito.
- Push-Fehlermeldung ohne Remote nennt git roh statt „Remote“-Wortlaut
  (`test_ap06_github.CliPushTest`, Basisfehler).
