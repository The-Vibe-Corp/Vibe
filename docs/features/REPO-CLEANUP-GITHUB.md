# REPO-CLEANUP — Repository aufräumen und für die Veröffentlichung auf GitHub vorbereiten

Stand: 2026-11-14
Arbeitsbranch: `feature/m0p/repo-cleanup-github-publication`
Ausgangszustand: Branch `fix/preflight-autonome-selbstreparatur` @ `a47d156`, Arbeitsbaum sauber
Auftrag des Nutzers: Repository aufräumen und für einen öffentlichen GitHub-Push vorbereiten; es dürfen keine Features/Commits verloren gehen; Push und Pull-Request führt der Nutzer manuell durch.

## Ausgangslage

Das Repository enthielt rund 160 lokale Branches und 17 registrierte Worktrees,
entstanden aus einem mehrwöchigen, agentengestützten Entwicklungsprozess mit
Rebases und Cherry-Picks. Drei auseinanderlaufende Integrationslinien trugen
jeweils exklusiven Inhalt:

| Linie | Tip | Exklusiver Inhalt |
|---|---|---|
| F31-Linie | `a47d156` (`fix/preflight-autonome-selbstreparatur`) | F31: AGENTS.md-Editor, Kennwort-Fix, Tests und Nachweise |
| master | `bc798b2` | F31: Manifestsync nach der Vorlagenüberarbeitung (`0af96c7`) |
| AP12/AP13-Linie | `10aef9e` (`feature/v-026-lauf-isolation`) | GitHub-Vorbereitung (AP12), Dashboard für lokales Netzwerk (AP13) |

122 Branch-Tips waren vollständig in einer dieser Linien enthalten; 22 weitere
waren nirgends enthalten. Für alle 22 ergab die Auditierung (Baumvergleich,
Patch-IDs, Betreff-Vergleich, Quellenlage in `docs/features/AP12.md`), dass es
sich um überholte Entwürfe handelt, deren Inhalt später über Rebase/Cherry-Pick
in integrierte Linien weitergeführt wurde (dokumentiertes Beispiel: AP12-Entwurf
`6674310` → Cherry-Pick `8245358`).

## Entscheidungen

- **Integration statt Auswahl:** Alle drei Linien wurden in einen gemeinsamen
  Stand gemerged; kein Änderungssatz wurde verworfen. Konflikte wurden durch
  Kombination beider Seiten gelöst, nie per `--ours`/`--theirs`.
- **22 überholte Entwürfe werden nicht gelöscht, sondern gesichert:** Die
  Branch-Spitzen liegen unter `refs/archive/prepublish/<Branchname>` und
  bleiben lokal abrufbar. Sie werden nicht gepusht; die Fachlichkeit ist
  vollständig im integrierten Stand enthalten.
- **Keine Historien-Umschreibung:** Alle Merges sind echte Merge-Commits.
  Bestehende Commits wurden weder geändert noch umgeschrieben.
- **Lokale Konfiguration bleibt beim Nutzer:** `.opencode/agents/test-agent.md`
  und `AGENTS.md` wurden aus der Versionierung genommen und sind über
  `.gitignore` (Anker am Wurzelverzeichnis) lokal ignoriert; die Arbeitskopien
  auf der Festplatte blieben erhalten (Nutzerentscheid, Build auf AP12).

## Durchgeführte Merges (auf `feature/m0p/repo-cleanup-github-publication`)

1. `8b6e1a1` — Merge master (`bc798b2`): F31-Manifestsync.
   Konflikt in `docs/import-manifest.json`: die F31-Linie hatte zwei
   Arbeitspaket-Einträge (AGENTS.md-Editor, Kennwort-Fix), die master-Linie den
   Vorlagen-Sync-Eintrag. Auflösung: alle drei Einträge kombiniert.
2. `b72319f` — `.opencode/agents/test-agent.md` aus der Versionierung genommen
   (lokale Datei bleibt erhalten; Vorbereitung auf den AP12-Merge, der die
   Datei ebenfalls unversioniert führt).
3. `0876861` — Merge AP12/AP13-Integrationsstand (`10aef9e`): GitHub-Dokumente
   (`LICENSE` MIT, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
   `.github/*`), angeankerte Ignore-Regeln und Dashboard für lokales Netzwerk.
   - Konflikt `bin/vibe-web.py`: AP14-Version (steer mit `session`-Parameter
     plus `/api/continue`) ist die Obermenge der AP13-Version; gelöst mit der
     AP14-Signatur, die `session=None` = altes Verhalten abbildet. Beide
     Feature-Sätze bleiben funktionsfähig.
   - Konflikt `docs/import-manifest.json`: alle 67 AP12/AP13-Einträge waren
     bereits im neueren Stand enthalten (geprüft); der `files`-Teil wurde
     gegen den gemergten Baum neu abgeglichen (`bin/vibe-web.py` +39 Zeilen
     durch die sauber gemergten AP13-Zugänge), Prüfsumme/Größe aktualisiert und
     mit dem Eintrag `REPO-AUFRÄUMEN` begründet.
   - Konflikt `docs/trilium-index.md`: Union beider Seiten.
4. `93b5b85` — Merge `Github/dev` (Initial-Commit) mit
   `--allow-unrelated-histories`: verbindet die lokale Historie mit dem
   entfernten Repository-Root, damit ein Pull-Request auf `dev` mergebar ist.
5. `50a45c7` — Nutzeränderungen übernommen: `AGENTS.md` aus der Versionierung
   genommen, `/AGENTS.md` in `.gitignore` ergänzt, Inhalt der lokalen
   Arbeitsanweisung angepasst (bleibt lokal, wird nicht gepusht).

## Aufräumen

- **117 Branches gelöscht** (116 via `git branch -d`, ausschließlich sicher
  enthaltene Tips — Beweis über `git merge-base --is-ancestor` gegen den
  Integrationsstand; dazu `feature/f9-projektguide` nach Archivierung seiner
  Arbeitskopie). `git fsck --no-dangling` ist sauber.
- **22 Branches archiviert** unter `refs/archive/prepublish/`
  (`git for-each-ref refs/archive/prepublish/` listet sie):
  `feature/b10-f24-sichtbarkeit`, `feature/f10-automatischer-stop`,
  `feature/f11-weniger-modale-dialoge`, `feature/f12-kostenermittlung`,
  `feature/f7-nachweis`, `feature/f9-projektassistent(-v2)`,
  `feature/v-002-verify-env`, `feature/v-006-pfade`,
  `feature/v-014-mcp-test`, `feature/v-018-installation-rollback`,
  `feature/v018-installer-modules`, `vibe/vibe-AP10-…9863`,
  `vibe/vibe-AP12-…22572`, `vibe/vibe-AP14-…17447/-…30331`,
  `vibe/vibe-F26-…17167`, `vibe/vibe-F28-…18112`,
  `vibe/vibe-F31-…1767`, `vibe/vibe-V-001-…25531/-…29005/-…28211`.
- **Nie committete Arbeitskopie des F9-Guide-Worktrees archiviert:** Der
  Worktree `~/.local/share/opencode/worktree/2c4a62/f9-projektguide` hielt
  einen nie committeten Vor-Commit-Entwurf des Projektassistenten
  (`bin/vibe_guide.py`, Tests, Reviews, Screenshots), der inhaltlich vom
  neueren integrierten F9-Stand überholt ist. Der Stand wurde verlustfrei als
  Commit gesichert und liegt unter
  `refs/archive/worktrees/f9-projektguide-arbeitskopie` (`8056887`); danach
  wurden Worktree und Branch entfernt.
- **Verbleibende lokale Branches:** `feature/m0p/repo-cleanup-github-publication`
  (Arbeitsbranch), `master` (alter Integrationsstand, vollständig enthalten —
  kann nach dem PR-Merge gelöscht werden), sowie 4 `vibe-B11`-Branches, die in
  Worktrees mit uncommitteten Änderungen ausgecheckt sind (siehe unten).
- **9 verwaiste Worktrees entfernt** (nachweislich 0 Änderungen je
  `git status --porcelain`): `vibe-f10`, `vibe-B11-hN3Hqr`, `vibe-B11-ICZVyR`,
  `vibe-B13-Hhu5Dm`, `vibe-F31-01ejSs/-8eXWTg/-Jr1Tep/-KRnv11/-N1npLh/-WT7b1t`.
  Auf FUSE schlug die eingebaute Validierung wegen Pfad-Aliasen
  (`/run/host/var/mnt/…` vs. `/var/mnt/…`) fehl; die Verzeichnisse wurden nach
  erneutem Leereitsnachweis manuell entfernt und `git worktree prune` ausgeführt.

## Verbleibende Worktrees mit uncommitteten Änderungen (Nutzerentscheid offen)

Diese wurden nicht angetastet (keine fremden Änderungen verwerfen):

- `_logs/worktrees/vibe-B11-HjVbKh` (20), `vibe-B11-Vh03X3` (28),
  `vibe-B11-a2hTGT` (18), `vibe-B11-gNwPON` (6, enthält ungetrackte
  Testdateien `tests/browser/test_b11_output_ui.py`, `tests/unit/runner_fixtures/`),
  `vibe-B11-baseline` (10) — alle B11/Fachlichkeit ist im Integrationsstand
  enthalten; die Änderungen sind vermutlich Experimentreste. Die zugehörigen
  Branches (`vibe/vibe-B11-…19010/-…9823/-…9095/-…20895`) bleiben solange
  bestehen, wie ihre Worktrees bestehen.
- `_logs/worktrees/Website-T-01-aOyzpN` (3) — anderes Projekt (T-01), gehört
  nicht zu diesem Repository-Inhalt.

## Prüfungen (tatsächlich ausgeführt)

- `bash scripts/verify.sh quick` — Exit 0 (nach jedem Eingriff erneut grün).
- `python3 scripts/check-no-secrets.py` — OK.
- `python3 scripts/check-import-manifest.py` — OK (57 Dateien stimmen).
- `python3 -m unittest tests.unit.test_repository_hygiene` — 11/11 OK
  (nach der `.gitignore`-Erweiterung erneut bestätigt).
- `python3 -m py_compile bin/*.py` — OK.
- `bash scripts/verify.sh full` — 1795 Tests, 16 Fehlschläge + 1 Error.
  **Klassifizierung: vorbestehend, keine Merge-Regression.** Beweis: die
  für die Fehlschläge maßgeblichen Inhalte (`tests/`, `templates/`,
  F28-pylint-Baseline) sind zwischen den Merge-Eltern (`a47d156`, `bc798b2`)
  und dem Merge-Stand bis auf zusätzlich hinzugekommene, grüne Testdateien
  identisch (`git diff` belegt das); beide Eltern zeigen im identischen
  Testmodul-Subset dasselbe Fehlerbild (je 14 Fehlschläge + 4 Errors).
  Die Fehlschläge betreffen veraltete Testerwartungen an den überarbeiteten
  Vorlagenstand (`ddd1d4d`: REVIEWER/TESTER-Zeilen, Sandbox-Preselects,
  Projekttyp openwrt entfernt) sowie die pylint- und Feedback-Blockregeln.
- Einzelne umgebungssensitive Tests (`test_real_sandbox…`,
  `test_every_checked_entry…`, `test_f7_continuation…`) schwanken zwischen
  Läufen (Error vs. FAIL vs. ok) — flaky, unabhängig vom Merge.

## Bekannte Grenzen und offene Punkte

- Die 17 vorbestehenden Fehlschläge der Vollprüfung sind Test-Debt aus der
  Vorlagenüberarbeitung. Tests dürfen nur vom Test-Agenten angefasst werden;
  die Behebung gehört in ein Folgeticket.
- Historie für den öffentlichen Push: keine Geheimnisse in der Historie
  (geprüft: `.vibe/project.env`-Standen enthalten leeres `GITHUB_API`, keine
  Token/Passwörter; `_secrets.env`/`web.token` wurden nie versioniert).
  Wohl aber persönliche Bezüge in alten Ständen (Home-Pfade in ca. 15
  Dokumenten bis `fc102b2` zurück, `GITHUB_LABEL=vibe_marc`) — von AP12
  dokumentiert. Der Push-Plan bietet dazu Option A (Historie wie sie ist)
  und Option B (bereinigter Erststand als Orphan-Commit).
- Remote-Abweichung: AP12 benannte historisch `M0P/Vibe`; der konfigurierte
  Remote `Github` zeigt auf `https://github.com/The-Vibe-Corp/Vibe`.
  `docs/features/AP12.md` bleibt als historischer Nachweis unverändert.

## Push-/PR-Plan (Nutzer führt aus)

1. Push des Arbeitsbranchs:
   `git push Github feature/m0p/repo-cleanup-github-publication`
2. PR von `feature/m0p/repo-cleanup-github-publication` auf `dev`
   öffnen (niemals auf `main`). Wegen des verbundenen Root-Commits ist der
   PR mergebar.
3. Für den Erst-Push ist ein normaler Merge zu empfehlen (kein Squash), damit
   die vollständige Historie erhalten bleibt; Squash-Merges bleiben den
   nachfolgenden Feature-PRs vorbehalten. Alternativ Option B (Orphan-Commit)
   aus AP12, wenn die Historie privat bleiben soll.
4. Vor dem Push erneut: `git status` sauber, `bash scripts/verify.sh quick`,
   `python3 scripts/check-no-secrets.py`.
