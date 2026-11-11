# AP12 — Test-Agent-Bericht (Rotphase)

Autor: unabhängiger Test-Agent (TESTER aus .vibe/project.env).
Datum: 2026-11-11. Arbeitskopie/Feature-Branch:
`vibe/vibe-AP12-1794373989612791687-2529435-22572` (Basis: `cd05345`, AP11-Abschluss).

## Umfang

Neue Testdatei: `tests/unit/test_ap12_github_readiness.py` (11 Testfälle,
unittest). Abgeleitet aus TICKETS.md (AP12), SPEC.md und AGENTS.md —
unabhängig von der Implementierung (die zum Testzeitpunkt nicht existierte).
Keine Produktionsdateien, keine bestehenden Tests und keine Prüfskripte
geändert; nichts committet.

## Testbefehl

    python3 -m unittest tests.unit.test_ap12_github_readiness -v

Exit-Code Rotphase: 1 (8 Fehler, 3 ok).

## Testfälle und Zuordnung zu Akzeptanzkriterien

| Testfall | Vorbedingung | Aktion | Erwartung | AK |
|---|---|---|---|---|
| `GitignoreLocalSettingsTest.test_local_settings_are_ignored` | Projekt-Wurzel, .gitignore versioniert | `git check-ignore` je Pfad aus `LOCAL_SETTINGS` (TICKETS.md, FEEDBACK.md, opencode.json, .vibe/*, .opencode/*) | jeder Pfad wird ignoriert | AK1 |
| `GitignoreLocalSettingsTest.test_existing_runtime_ignores_are_kept` | wie oben | `git check-ignore` für bestehende Laufzeitregeln (web.token, _secrets.env, *.log, config-backups/, agent-backups/, vibe-storage-locks-*/, __pycache__) | weiterhin ignoriert | AK1 (Regression) |
| `GitignoreLocalSettingsTest.test_templates_stay_versioned_and_not_ignored` | mind. eine versionierte Vorlage unter templates/ | alle `git ls-files templates/`-Pfade gegen `git check-ignore` | keine Vorlage ignoriert | AK1 |
| `SystemArtifactsTest.test_os_and_editor_artifacts_are_ignored` | — | `git check-ignore` für .DS_Store, Thumbs.db, desktop.ini, .directory, `*~`, `*.swo`, `*.swp`, .idea/, .vscode/ (Wurzel und verschachtelt) | alle ignoriert | AK2 |
| `UntrackedLocalSettingsTest.test_local_config_files_are_untracked_but_present` | Dateien lokal vorhanden | `git ls-files --cached` | opencode.json und .opencode/agents/test-agent.md nicht versioniert | AK3 |
| `UntrackedLocalSettingsTest.test_no_opencode_or_vibe_paths_are_tracked` | — | `git ls-files --cached` | kein versionierter Pfad unter .opencode/, .vibe/ oder opencode.json | AK3 |
| `UntrackedLocalSettingsTest.test_local_config_files_still_exist_locally` | — | Dateisystemprüfung | beide Dateien existieren lokal weiterhin | AK3 |
| `TrackedContentHygieneTest.test_no_tracked_file_contains_personal_home_paths_or_secrets` | build-release-Regeln ladbar | alle versionierten Dateien mit `scan_text` (HOME_PATH_RE + Geheimnismuster aus check-no-secrets.py) prüfen | keine Treffer | AK4 |
| `TrackedContentHygieneTest.test_github_documents_exist_and_are_tracked` | — | Dateisystem + `git ls-files` | LICENSE (nennt MIT), CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md vorhanden, nicht leer, versioniert | AK4 |
| `TrackedContentHygieneTest.test_pull_request_and_issue_templates_exist` | — | Dateisystem + `git ls-files` | PR- und Issue-Vorlagen unter .github/ vorhanden, nicht leer, versioniert | AK4 |
| `MergePushPlanTest.test_merge_and_push_plan_is_documented` | — | docs/features/AP12.md lesen | vorhanden, > 200 Zeichen, nennt M0P/Vibe, Push und Merge | AK5 |

AC6 („bestehende Prüfungen bleiben grün: bash scripts/verify.sh quick“) ist kein
Unit-Testfall (verify.sh quick startet selbst Prüfungen; Einbetten würde
rekursiv sein). Er wird nach der Implementierung als separater Befehl
nachgewiesen.

## Rotphase (Befehl, Ausgabe, Exit-Code)

Befehl: `python3 -m unittest tests.unit.test_ap12_github_readiness -v`
Exit-Code: 1 — `Ran 11 tests ... FAILED (failures=8)`.

Rote Testfälle (Kurzfassung der Meldungen):

- `test_local_settings_are_ignored`: opencode.json, .vibe/sitzung.json,
  .opencode/agent-testdatei.md, .opencode/agents/test-agent.md werden nicht erfasst.
- `test_os_and_editor_artifacts_are_ignored`: alle 12 Prüfpfade
  (.DS_Store, Thumbs.db, desktop.ini, .directory, Backup/Swap, .idea, .vscode)
  werden nicht ausgeschlossen.
- `test_local_config_files_are_untracked_but_present`:
  opencode.json und .opencode/agents/test-agent.md sind weiterhin versioniert.
- `test_no_opencode_or_vibe_paths_are_tracked`: dieselben beiden Pfade.
- `test_no_tracked_file_contains_personal_home_paths_or_secrets`:
  10 Fundstellen „absoluter Home-Pfad eines Benutzers (marc)" in
  docs/features/B4.md (15, 36), B5.md (218), F23.md (114),
  docs/reviews/AP7-test-agent-report.md (25, 181, 225, 253, 316),
  docs/reviews/V-023-review-2.md (24). Keine Geheimnistreffer.
- `test_github_documents_exist_and_are_tracked`: „GitHub-Dokument fehlt: LICENSE".
- `test_pull_request_and_issue_templates_exist`:
  „Keine Pull-Request-Vorlage unter .github/ vorhanden".
- `test_merge_and_push_plan_is_documented`: „Merge-/Push-Plan fehlt:
  docs/features/AP12.md".

Grün im Rotphasenlauf (bewusst als Vorbedingungs-/Regressionsschutz):
`test_templates_stay_versioned_and_not_ignored`,
`test_existing_runtime_ignores_are_kept`,
`test_local_config_files_still_exist_locally`.

Korrektur während der Rotphase: Der Prüfpfad für
`vibe-storage-locks-*/` wurde von der nackten Datei
`vibe-storage-locks-test` auf `vibe-storage-locks-test/sperre.json`
geändert, weil das bestehende Muster nur Verzeichnisse erfasst. Der erste
Lauf (vor der Korrektur, Exit 1, 9 Fehler) ist protokolliert; die Änderung
stärkt keinen Test ab, sondern richtet den Regressionsschutz an der
bestehenden Regel aus.

## Bestehende Prüfungen (Basiszustand vor Implementierung)

- `bash scripts/verify.sh quick` → Exit-Code 3:
  „FEHLT: .../.vibe/project.env fehlt. Prüfbefehle müssen dort stehen."
  Die Arbeitskopie enthält als isoliertes Worktree-Checkout keine lokale
  Laufzeitkonfiguration (.vibe/ ist lokale Einstellung). Das ist ein
  Konfigurationsfehler der Umgebung, kein fachlicher Testversagen.
  Nach Umsetzung von AK1–AK5 muss der Befehl in einer Umgebung mit
  vorhandener lokaler .vibe/project.env erneut laufen und grün sein
  (AK6); der Coding-Agent führt dies aus und dokumentiert es.

## Grenzen des Nachweises

- Die Tests prüfen den Repository-Zustand (Versionierung, Ignore-Regeln,
  Dokumente); sie ersetzen keinen echten Push (SPEC: kein Push ohne
  Freigabe) und keine GitHub-Plattformprüfung.
- Die Heuristik für persönliche Pfade/Geheimnisse entspricht exakt der
  bestehenden Projektregel (scripts/build-release.py, HOME_PATH_RE mit
  Platzhalter-Nutzerliste; Muster aus scripts/check-no-secrets.py).
  Andere Formate werden damit nicht erkannt.
- AK4 „persönliche Home-Pfade" ist streng ausgelegt: jede
  `/home/<name>/`- oder `/Users/<name>/`-Fundstelle außerhalb der
  Platzhalterliste (user, nutzer, alice, bob, example, test, name)
  gilt als Verstoß — konsistent zur Release-Regel des Projekts.
  Betroffene dokumentarische Fundstellen müssen bei der Umsetzung
  verallgemeinert werden (z. B. `$HOME` oder Platzhalter).
- Exit-Code 3 von verify.sh quick blockiert den AC6-Nachweis bis zur
  Umsetzung in einer Umgebung mit lokaler .vibe/project.env.

## Verbleibende Lücken (nach Umsetzung durch den Coding-Agenten zu prüfen)

- Grüner Lauf der neuen Tests (Glückphase) nach Umsetzung.
- `bash scripts/verify.sh quick` in einer Umgebung mit lokaler
  .vibe/project.env.
- Reviewer-Prüfung der Umsetzung (nicht Aufgabe des Test-Agenten).
