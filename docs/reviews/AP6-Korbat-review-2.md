# Review AP6-Korbat — Runde 2 (Prüfung der Behebungen)

**Wichtiger Hinweis zur maximalen Schrittzahl:** Das Maximum der für diesen Agenten erlaubten Schritte wurde erreicht; die Tools sind deaktiviert. Ich kann keine weiteren Prüfungen mehr ausführen. Der folgende Reviewtext basiert ausschließlich auf den bis zu diesem Punkt tatsächlich erhobenen Befunden. Er kann unverändert als `docs/reviews/AP6-Korbat-review-2.md` gespeichert werden.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- **Verdict: PASS**

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| B1 (Runde-1-Medium behoben): Test-Agent-Bericht existiert und deckt die geforderten Inhalte ab | PASS | `docs/reviews/AP6-Korbat-test-agent-report.md` (neu, 427 Zeilen, vollständig gelesen) | Enthält: Umgebung (kontaminiertes Runner-Env, §„Umgebung der Nachweise“), komplette Dateiliste (30 tests/unit-Module + `env_support.py` + `tests/browser/test_b18_harness_ui.py`, Tabelle §„Geänderte Testdateien“), Baseline-Tabelle am Ausgangscommit `4db1b78` mit Rotzahlen/-ursachen (§1, deckungsgleich mit AP10 §4.1/§4.2), Testfalllisten je Auftragsteil A–I/J2 mit Vorbedingung/Aktion/Erwartung (§3), tatsächlich ausgeführte Rot-/Grünphasen-Belege mit Befehlen (§4), Skip-Verifikation mit/ohne Marker (§3 B), Grenzen (§5, ehrlich: `test_feedback_entries`-Rotlauf nicht selbst ausgeführt; Vollläufe/Browser/Verify beim Runner) |
| B1-Konsistenz mit Volllauf-Nachweis (2396 Tests, 128/132 Module, 4 Vorabstände) | PASS | Bericht §3 B + §4 | Modulzahlen stimmen mit den gelieferten Nachweisen überein: `test_ap06_github` 54 OK, `test_f27_keep_changes` 14 OK, `test_install_lifecycle` 43, `test_setup_vibe` 50, `test_ticket_feedback_processing` 28, `test_feedback_entries` 3; Skips `test_sandbox` 9, b4 1, b5 3, b13 1, project_guide 2; `test_b17_sandbox_argv` Ran 5 OK; `test_release`+`test_ap12` Ran 25 FAILED(2) vor der B4-Neutralisierung → nach B4 FAILED(1) (nur ap12) — kohärent |
| B2 (Runde-1-Minor 1 behoben): persistenter Vertragstest für den T-BR2-Marker | PASS | `tests/unit/test_b17_sandbox_argv.py:93-124` (`test_nested_sandbox_marker_is_set_once_before_the_command`), Hilfsfunktion `setenv_pairs` (:86-91) | Vollständig gelesen: verlangt genau ein Tripel `('--setenv','VIBE_SANDBOX_ACTIVE','1')`, Position vor dem `--`-Trenner (`assertLess(index, separator)`) und Abwesenheit aus der Kommandoliste (`assertNotIn`); Docstring enthält Vorbedinung/Aktion/Erwartung/Fehlerfall. Die 4 bestehenden Fälle (:126-177) sind byte-identisch zur Basis (bereits in Runde 1 gegen `4db1b78` verglichen, erneut gelesen) — **keine Abschwächung**. Nachweis: Ran 5 OK (Koordinator, tatsächlich ausgeführt) |
| B3 (Runde-1-Minor 3 behoben, Doku-Grenze Rename-Quellen) | PASS | `docs/features/AP6-Korbat.md:382-389` (§5 „Rename-Quellen im Abschluss-Merge (Review-Befund, Doku-Grenze)“) | Gelesen: beschreibt exakt den Runde-1-Befund (`diff HEAD..$BRANCH` listet Rename-Quellpfade nicht; dirty Rename-Quelle blockiert ff-Merge fail-closed „would be overwritten“; kein Datenverlust) und verweist korrekt auf die Nutzerentscheidung (nur überschriebene Dirty-States verwerfen) |
| B4 (Hygiene-Nachschuss: Home-Pfad in review-1 neutralisiert) | PASS | `docs/reviews/AP6-Korbat-review-1.md:22` | Gelesen: Zeile 22 nennt jetzt `/home/nutzer/…` statt des zitatweisenden absoluten Home-Pfads; Verdict-Struktur und Inhalte sonst unverändert (mit dem Runde-1-Originaltext abgeglichen). Nachweise: `test_release`+`test_ap12` Ran 25, FAILED (1) — nur der bekannte ap12-Vorabstand; `verify.sh quick` Exit 0; `test_b17_sandbox_argv` Ran 5 OK; `test_f27_keep_changes` Ran 14 OK; Home-Pfad-Scan 0 Treffer (vom Test-Agenten gemeldet) |
| Keine neuen Dateien/Änderungen außer den genannten | PASS | — | `tests/unit`-Listing identisch zu Runde 1 (`env_support.py` vorhanden, keine neuen/gelöschten Module); `docs/reviews` 282 → 284 Einträge, Differenz exakt `AP6-Korbat-review-1.md` + `AP6-Korbat-test-agent-report.md`; `docs/features` enthält als einzige neue Ticketsache `AP6-Korbat.md`; Produktcode-Stichproben unverändert zu Runde 1 (`bin/vibe-run.sh:47` VIBE_CLEAN_ENV, `:817-858` merge_package — byte-gleich zu meinen Runde-1-Volltextvergleichen) |
| Getragene Runde-1-Kriterien (T-BR1..T-BR8, F27, F6, Vorabstände) | PASS (unverändert) | wie Runde 1 | Produktseite seit Runde 1 unverändert (Stichproben oben); Testseite durch den Bericht nachgewiesen; 4 rote Module bleiben als dokumentierte Vorabstände (AP10 §4.2) klassifiziert — keine Regressionen |

## Findings

- [Minor] `docs/reviews/AP6-Korbat-test-agent-report.md:23` — konkrete LAN-Bind-Adresse im Bericht
  - Evidence: Der Bericht dokumentiert das kontaminierte Runner-Environment mit `VIBE_UI_BIND=<LAN-IP>` (Zeile 23). Die Projektregel in `AGENTS.md` lautet: „Do not copy personal configurations (including bind addresses in the local network) or secrets into the repository.“ Die Datei wird mit dem Paket committet; damit gelangt die konkrete private LAN-Adresse in das Repository. Diagnostisch nötig ist nur die Tatsache der geerbten LAN-Bindung, nicht ihr konkreter Wert. (Ob die Adresse an anderer Stelle bereits getrackt ist, konnte ohne Textsuche nicht geprüft werden; im gelesenen `docs/baseline.md` steht sie nicht.)
  - Required fix: Vor dem Commit die konkrete Adresse im Bericht durch einen Platzhalter ersetzen (z. B. `VIBE_UI_BIND=<LAN-IP>` oder `192.0.2.x`), analog zur etablierten `/home/nutzer/`-Praxis; die Aussage (Test-Server band an die geerbte LAN-Adresse statt 127.0.0.1) bleibt vollständig erhalten. Nicht blockierend für dieses Verdict; idealerweise vor dem Commit erledigt.

## Verification
- Change set reviewed: `4db1b78..working tree` (Arbeitskopie `/var/log/custom/vibe-dev/worktrees/vibe-AP6-Korbat-cpr9Pv`, uncommitted; untracked jetzt: `docs/features/AP6-Korbat.md`, `tests/unit/env_support.py`, `docs/reviews/AP6-Korbat-test-agent-report.md`, `docs/reviews/AP6-Korbat-review-1.md` — wie erwartet).
- Methodeneinschränkung (wie Runde 1): In dieser Read-only-Sitzung waren keine Shell-/Git-Befehle verfügbar; der Abgleich erfolgte über Volltextvergleiche gegen den am Ausgangscommit `4db1b78` ausgecheckten Hauptarbeitsbaum (`/opt/custom/vibe-dev/workspaces/vibe`, `dev` = `4db1b78` laut Git-Log) und über vollständige Verzeichnislisten.
- Vollständig gelesen/geprüft (Runde 2): `AP6-Korbat-test-agent-report.md` (427 Zeilen), `test_b17_sandbox_argv.py` (181 Zeilen, gegen Basis und Runde-1-Fassung), `AP6-Korbat-review-1.md` (Zeilen 1-40, mit Runde-1-Originaltext abgeglichen), `AP6-Korbat.md` §5/§6, `tests/unit`- und `docs/reviews`-Listings, `docs/features`-Listing, Produktstichproben `bin/vibe-run.sh:43-52` und `:814-858`.
- Git commands run by me: keine (keine Git-/Shell-Berechtigung in dieser Umgebung).
- Checks evidenced by supplied raw output (Koordinator/Agenten, nicht von mir ausgeführt): `env -u SANDBOX python3 -m unittest tests.unit.test_release tests.unit.test_ap12_github_readiness` → Ran 25, FAILED (1) [nur ap12-Vorabstand]; `tests.unit.test_b17_sandbox_argv` → Ran 5 OK; `env -u SANDBOX bash scripts/verify.sh quick --project .` → Exit 0; `test_f27_keep_changes` Ran 14 OK; Home-Pfad-Scan über alle getrackten Dateien inkl. Bericht und review-1 → 0 Treffer (Test-Agent).
- Checks not independently run: alle Build-, Test- und Nicht-Git-Prüfungen; die konkreten SHA-256/Größen im Importmanifest wurden auch in Runde 2 nicht unabhängig nachgerechnet.
- Beobachtung (kein Befund): Der Bericht nennt 30 geänderte `tests/unit`-Module; die Runde-1-Koordinatorangabe lautete „24 Module“. Ohne `git diff --name-only` nicht entscheidbar; die Liste des Berichts ist in sich schlüssig (29 Module aus Aufträgen A–I + `test_b17_sandbox_argv` aus J2), alle 30 Namen existieren im `tests/unit`-Listing, und alle Stichproben (f27, ap06, sandbox, feedback_entries, ap03, storage, b18, b17) decken sich mit meinen eigenen Runde-1-Vergleichen. Hinweis: Dieses Dokument wurde am Maximum der erlaubten Schritte erstellt; der Abgleich der Modulzahl gegen die Basis wäre im Nachgang mit `git diff --name-only 4db1b78 -- tests/unit` zu bestätigen.
- Remaining risks: die 4 dokumentierten Vorabstände (AP10 §4.2) bleiben testseitig offen (Ticketumfang); Importmanifest-Prüfsummen nur über `check-import-manifest` (Koordinator) belegt; die konkrete LAN-Adresse im neuen Bericht (siehe Minor-Befund).

## Fazit

**Verdict: PASS**

| Schweregrad | Anzahl Befunde |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Minor | 1 |

1. **Minor — konkrete LAN-Bind-Adresse im Testbericht** (`docs/reviews/AP6-Korbat-test-agent-report.md:23`). Befund: Die AGENTS-Regel untersagt das Übernehmen persönlicher Konfigurationen inkl. LAN-Bind-Adressen; der Bericht nennt `VIBE_UI_BIND=<LAN-IP>`. Erwartung: Platzhalter statt konkreter Adresse. Vorschlag: vor dem Commit neutralisieren (nicht blockierend).

Alle drei Runde-1-Befunde sind wirksam behoben und nachgeprüft: das Medium (fehlender Test-Agent-Bericht) durch ein vollständiges, mit den bekannten Läufen konsistentes Berichtsartefakt (B1); Minor 1 durch einen persistenten, nicht abschwächenden Vertragstest für den `VIBE_SANDBOX_ACTIVE`-Marker mit belegtem Lauf Ran 5 OK (B2); Minor 3 durch die dokumentierte Rename-Quellen-Grenze in `AP6-Korbat.md` §5 (B3); der Hygiene-Nachschuss (Home-Pfad in review-1) ist verifiziert, `test_release` grün bis auf den dokumentierten ap12-Vorabstand (B4). Es sind keine neuen Dateien oder Änderungen außer den genannten vier untracked Artefakten entstanden; der Produktstand ist unverändert zu Runde 1. Das Paket kann damit in den Commit überführt werden; der Minor-Befund sollte vor dem Commit neutralisiert werden.
