# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

Grundlage ist der abgelegte Prüfstand `/tmp/f9-build/check` (detached HEAD `d464d5f`, F9-Änderungen gestaged, `git status --short` zeigt ausschließlich die 16 F9-Dateien). Die vorbestehenden F11-Änderungen im Hauptarbeitsbaum wurden nicht bewertet. Alle Dateien wurden im Volltext gelesen; `bin/vibe_guide.py` (748 Zeilen), beide Testdateien (36 Unit-/4 Browsertests) und die Trilium-Notiz habe ich selbst geprüft.

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Führung durch das fachliche Setup | PASS | `bin/vibe_guide.py:43-108` (8 feste Schritte mit Leitfrage/Hilfe), `:303-364` (`state`, `next`), UI-Karte `bin/vibe-web.py:626-657` (`guideCard`/`drawGuide`) | `tests/unit/test_project_guide.py:92` (`test_state_reads_filled_sections_and_reports_completion`, `next=="nutzer"`), `tests/browser/test_project_guide_ui.py:156` (`test_guide_lists_steps_and_writes_spec_and_missing_files`: 8 Schritte, 0/6, „vollständig“); beide grün in Log `verify-full2.log` (Zeilen 141-177, 414-418) |
| Alle notwendigen fachlichen Dateien werden angelegt | PASS | `bin/vibe_guide.py:110-117` (`FILES`), `:263-284` (`_ensure_files`), `:218-243` (`_new_spec`, `_readme`); Vorlagen `templates/{common,generic}/…` per `git ls-files` bestätigt | `tests/unit/test_project_guide.py:114` (`test_apply_creates_spec_and_all_missing_fachliche_files`: alle 6 Dateien, `{{NAME}}` ersetzt), `:225` (`test_apply_without_templates_still_writes_spec_and_readme`), Browsertest `:184-191` |
| Agentenunterstützung für fehlenden Input (Entwurf, erst nach Bestätigung) | PASS | `bin/vibe_guide.py:469-505` (`agent_prompt`, UNBEKANNT-Regel), `:595-650` (`start_agent`, eigene tmux-Sitzung), `:725-738` (`draft_apply`), `:741-748` (`draft_discard`); UI „Mit Agent entwerfen“/Entwurfsknöpfe `bin/vibe-web.py:632-640` | `tests/unit/test_project_guide.py:249,267,486,502,523` (Prompt, Argumentliste, Übernehmen, innerer Überschriftsschutz, Codeblock-Schutz), `tests/browser/test_project_guide_ui.py:226` (`test_agent_draft_is_only_applied_on_explicit_request`: `SPEC.md` entsteht erst nach Knopfdruck), API-Tests `:689-707` |
| Gezieltes Verbessern/Ersetzen vorhandener Abschnitte (replace-Semantik mit UI gekoppelt) | PASS | `bin/vibe_guide.py:385-395` (`_validate_replace`), `:413-429` (Abschnitt nur mit `replace`/wenn leer geschrieben; leere Antwort löscht nie), UI: `replace` wird exakt aus bearbeiteten Feldern berechnet (`bin/vibe-web.py:649-655`) | `tests/unit/test_project_guide.py:159` (ohne replace bleibt gefüllter Abschnitt), `:173` (nur `ziel` ersetzt, `umgebung` bleibt), `tests/browser/test_project_guide_ui.py:202` (`test_existing_filled_section_is_not_replaced_when_only_another_step_is_answered`) |
| Sauberes fachliches Projekt-Setup (kein stiller Overwrite vorhandener Dateien) | PASS | `bin/vibe_guide.py:271-273` (vorhandene Ziel-Dateien → `kept`), `:139-149` (`_safe_path`), Schreiben über `vibe_storage.write_text` (`bin/vibe_storage.py:329-331`, Staging+Sperre+`os.replace`) | `tests/unit/test_project_guide.py:139` (byte-gleich erhaltene Dateien), `:215` (`test_apply_rejects_spec_symlink_leaving_the_project`), `tests/browser/test_project_guide_ui.py:184-191` |

## Findings

- [Minor] `docs/features/F9.md:45` — Vorwärtsreferenz auf `docs/reviews/F9-review-7.md`
  - Evidence: F9.md nennt die aktuelle Reviewdatei (`„zuletzt docs/reviews/F9-review-7.md“`), die es zum Prüfzeitpunkt im Change-Set noch nicht gibt; der Verweis wird erst wahr, wenn diese Antwort unverändert dort gespeichert wird. Kein Codeeinfluss, dasselbe Muster wie in Runde 5.
  - Required fix: Diese Reviewantwort unverändert als `docs/reviews/F9-review-7.md` speichern, damit die Referenz stimmt.
- [Minor] `docs/trilium-index.md:1` — Kopftext „Stand 2026-10-26“ in derselben Sitzung aktualisierter Datei
  - Evidence: Die F9-Zeile (Z. 22) und das Paket stammen vom 2026-10-29, das Dateikopfdatum blieb auf 2026-10-26. Rein kosmetisch, kein fachlicher bzw. technischer Ausspruch ist falsch.
  - Required fix: Beim nächsten redaktionellen Anlass das Stand-Datum aktualisieren (nicht gesondert commitpflichtig).

## Verification

- Change set reviewed: `d464d5f..gestaged working index` in `/tmp/f9-build/check` (16 Dateien, 2463+/4−; identisch zum vorgelegten `/tmp/f9-build/f9-final.diff` laut Kurzstatistik). Hauptarbeitsbaum bewusst nicht bewertet (vorbestehende F11-Änderungen).
- Git commands run by me: `git status --short`, `git diff --cached --stat`, `git diff --cached --shortstat`, `git log --oneline -2`, `git rev-parse HEAD`, `git ls-files templates` (durchgeführte `sha256sum`/Prozesssubstitutionen wurden von den Shell-Berechtigungen abgewiesen).
- Checks with supplied output: `verify.sh quick`/`full`, Unit- und Browser-Tests — ich habe die vorgelegten Logs selbst gelesen und per grep bestätigt: alle 36 Unit-Tests (`verify-full2.log:139-177`) und alle 4 F9-Browsertests (`verify-full2.log:414-418`) grün; `Ran 353 tests … OK` (:402-404), `Ran 18 tests … OK` (:426-428), `OK: Tests erkannt: 371` (:429), quick-Log mit Exit 0. Die Rot-Phasen (ModuleNotFoundError; `AssertionError: '`````\n## Beispiel\n``````' not found … : Codebeispiel wurde verfälscht`) stimmen wörtlich mit den Assertion-Strings in `tests/unit/test_project_guide.py:538` überein. Ich habe keine der Checks selbst neu ausgeführt (Berechtigungen).
- Checks not independently run: alle Build-/Test-/Verify-Läufe sowie die SHA-256-Nachrechnung der Manifest-Einträge (die grüne Manifestprüfung von `verify.sh quick` ist der einzige Prüfsummen-Nachweis). Trilium-Notiz `WIk1kdJ8vgom` habe ich dagegen selbst über MCP gelesen: vorhanden, enthält einen aktuellen Abschnitt „Stand 2026-10-29“ mit `_shift_inner_headings`, 36/4 Tests, Prüf- und Rot-Nachweisen. Screenshot `docs/features/F9-assistent.png` als Bild gelesen — echte UI-Aufnahme („vollständig“, 6× gefüllt, 2× offen, alle Pflichtdateien ✓), konsistent mit F9.md.
- Important areas inspected: `bin/vibe_guide.py` (Volltext: `replace`-Semantik 413-429, `_safe_path` 143-149, Agentenstart ohne Shellverkettung 618-626, Sandbox fail-closed 551-583 inkl. nachgeordneter, späterer `--bind folder folder` vor dem einzigen `--`, `_shift_inner_headings` 701-722 mit korrekter Fence-Erkennung für ``` und ~~~ und Fail-Safe bei ungeschlossenen Fences, `draft_apply`/`start_agent` entwurfschonend), `bin/vibe-web.py` (zentrale Token-/Host-/Origin-Prüfung 214-238, 287-328; `/api/guide` in `known()`-Whitelist :328; Meldungs-Redact :491; DOM-Hilfe ohne innerHTML :550-553), `vibe_storage.py` (V-005), `vibe_sandbox.py` (bwrap-Aufbau 405-465), beide Testdateien (Volltext: echte Assertionen, keine Skips/abgeschwächten bestehenden Tests, bwrap-Lauf testet ENV_DENIED/DRAFT_OK real), F9.md, Manifest-Diff, Reviertiefe 1–6.
- Remaining risks: (1) Bei erfolgreichem Agentenstart wird ein alter Entwurf ohne Sicherung beiseitegelegt (vibe_guide.py:627-633) — von Runde 6 als bewusste, getestete Grenze akzeptiert; kein neuer Beleg. (2) `apply()` übergibt keine erwartete Prüfsumme an `vibe_storage` (Lesen-Schreiben-Lücke）— in F9.md:343-349 und Trilium offen dokumentiert, seit Runde 5/6 akzeptiert. (3) Prompt-Exklusivität des Agenten („schreibe nur den Entwurf“) bleibt unverifizierbar — dokumentierte Grenze, ohne Sandbox technisch nicht erzwungen. (4) Namensbasierte Sitzung/Logpfad, gleiche Lücke wie bei Paketläufen (`bin/vibe:88,517`). Keines dieser Risiken trägt neuer Belege im F9-Code und damit kein Medium.
