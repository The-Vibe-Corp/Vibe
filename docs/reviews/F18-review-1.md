# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: PASS

## Acceptance criteria
| Kriterium | Status | Implementierung (Datei:Zeile) | Test (Datei:Methode) / Nachweis |
|---|---|---|---|
| Nur ein Reconnect, zentral gesteuert, auch bei mehreren gleichzeitig laufenden Projekten | PASS | `bin/vibe:1127-1158` (flock-Sperre), `bin/vibe:1357-1391` (`_fritz_auto_coordinated`), `bin/vibe:1173-1195` (Zustand) | `tests/unit/test_fritz_coordination.py:test_simultaneous_projects_share_one_reconnect` — drei parallele Prozesse, `assertEqual(len(self.calls()), 1)`, `owner/b/c` Exit 0; grün laut `.f18-check/green-tests.log` (Ran 36 / OK) und `full2.log` (805 Tests, Exit 0) |
| Wartende Projekte starten keinen zweiten Reconnect | PASS | `bin/vibe:1331-1355` (`_fritz_wait_for_result`), `bin/vibe:1099-1125` (Warteliste) | `test_a_waiting_project_never_starts_a_second_reconnect` — Asserts: Exit 3, „kein zweiter Reconnect", `len(self.calls()) == 1` auch nach owner-Ende |
| Alle Projekte werden informiert (Ergebnis/Betroffene) | PASS | `bin/vibe:1184-1236` (publish done, adopt, Objektliste), `bin/vibe:1417` (Statuszeile), `bin/vibe-web.py:533` | `test_simultaneous_projects_share_one_reconnect` (Meldungen, `state["affected"]`), `test_a_failed_reconnect_is_reported_to_all_projects_and_not_repeated`, `test_status_reports_the_central_result` |
| Betroffene Projekte nach dem Reconnect wieder anstoßen (Läufe fortsetzen) | PASS | `bin/vibe-run.sh:195-205` (`VIBE_PROJECT="$P"`, Meldung, `sleep 20`, Schleife nimmt dasselbe Paket erneut); Interpretation dokumentiert in `docs/features/F18.md:28-41` | `tests/unit/test_fritz_reconnect.py:test_runner_tells_the_central_reconnect_which_project_continues` — Projektlog `[' projekt-pfad']`, „fortgesetzt" in stdout; rot: leerer Projektname gegen Ausgangsstand (Red-Kopie `bin/vibe-run.sh:195` ohne `VIBE_PROJECT` statisch bestätigt) |
| Fehlerfall: fehlgeschlagener Reconnect wird übernommen, nicht wiederholt | PASS | `bin/vibe:1073-1083`, `bin/vibe:1197-1220` | `test_a_failed_reconnect_is_reported_to_all_projects_and_not_repeated` — 1 Helferaufruf, Exit 1 für beide, `assertFalse(self.state()["ok"])` |
| Schonzeit: neuerliches Ergebnis wird übernommen und läuft ab | PASS | `bin/vibe:1085-1097`, env-Override `bin/vibe:1017-1033` | `test_a_recent_reconnect_is_reused_and_expires` — 1 Aufruf, „bereits", mit `VIBE_FRITZ_REUSE_SECONDS=0` dann 2. Aufruf |
| Manueller Reconnect nimmt an der zentralen Steuerung teil | PASS | `bin/vibe:1308-1329` | `test_a_manual_reconnect_participates_in_the_central_control` — 1 Aufruf, nachfolgendes Projekt übernimmt; Web-Pfad `vibe-web.py:527` nutzt dieselbe Funktion |
| Absturz/Timeout des Eigentümers br kein Kardinalfehler; Wartezeitlimit | PASS | `bin/vibe:1345-1354` (Deadline, Meldung, kein eigener Reconnect), Lock wird vom OS freigegeben | `test_a_waiting_project_never_starts_a_second_reconnect` (Deadline mit `VIBE_FRITZ_WAIT_SECONDS=0.2`); Absturzszenario selbst nicht direkt getestet (dokumentiert in `docs/features/F18.md`, Abschnitt Grenzen) — reine Abdeckungslücke, kein Befund gegen Akzeptanz |
| Projektnamen bereinigt, keine Shell, keine Geheimnisse im zentralen Zustand | PASS | `bin/vibe:1035-1046`, `bin/vibe:1039` (Steuerzeichen), Argumentliste ohne Shell `bin/vibe:1288`; Zustand ohne Zugangsdaten (`bin/vibe:1063-1306`) | `test_a_project_name_with_control_characters_is_published_cleanly` (`assertNotIn("\n"/"\x1b")`); `quick.log`: „keine Geheimnisse erkannt" (Exit 0) |
| Scope: nur F18-Änderungen | PASS | Diff umfasst ausschließlich die im Review-Input gelisteten Dateien; vorbestehende Änderungen (`scripts/setup-vibe.py`, `SPEC.md`, PNG u. a.) sind nicht Teil des Diffs | Sichtung des kompletten Diffs `.f18-check/review-diff-1.txt` (1246 Zeilen) und Gegenlesen der Arbeitsbaumdateien |
| Dokumentation | PASS | `docs/features/F18.md` (neu, vollständig), `docs/baseline.md:163` (Zeilenbereich 963–1443 verifiziert zutreffend), `docs/features/F5.md:486-494`, `docs/import-manifest.json` (Checksums + F18-Eintrag), `docs/trilium-index.md:41` | Trilium-Notiz `deX8hDMqAQ1k` habe ich selbst über den Trilium-MCP-Zugang gelesen (existiert, Titel „F18 Verbesserung Internet-Reconnect", aktualisiert 2026-11-02, Inhalt mit Sperre/Schonzeit) |

## Findings
- [Minor] `bin/vibe:1148-1149` — EINTR-Zweig umgeht die Deadline-Prüfung
  - Evidence: In `_fritz_lock_acquire` springt `continue` bei `errno.EINTR` direkt zum nächsten Sperrversuch, ohne den `deadline`-Vergleich auszuführen. Bei einem folgenreichen fortlaufenden Signal-Empfang könnte das Wartelimit überschritten werden; praktisch anarchisch unwahrscheinlich (kein Netzerzendradius).
  - Required fix: Deadline-Check vor oder im EINTR-Pfad ausdrücklich ausführen (kein Code von mir; nur als Korrekturhinweis).
- [Minor] `bin/vibe:1139-1151` — Degradationspfade der Sperre dokumentiert, aber ungetestet
  - Evidence: Der `fcntl is None`-Zweig und der Zweig für nicht-`EACCES`/`EAGAIN`-Fehler geben den Handle „best effort" als erworben zurück; das Verhalten ohne flock ist in `docs/features/F18.md` (Grenzen) sauber beschrieben, aber durch kein Test konzeptionell belegt (z. B. heuristisch simulate ohne flock).
  - Required fix: Bei Gelegenheit einen Test ergänzen, der den „kein flock"-Pfad zielsicher antéiligt (z. B. über Modul-Injektion), oder die Doku um den Testverweis ergänzen.
- [Minor] `bin/vibe:1308-1315` — Manueller Reconnect kann jetzt bis ca. 230 s lang blockieren (Zusatzinfo)
  - Evidence: Der manuelle Reconnect wartet mit `_fritz_wait_seconds(timeout)` (Standard 200+30) auf die Sperre; über das Dashboard (`vibe-web.py:527`) hält diese Anfrage damit bis zu ~6–7 Minuten mit Wartezeit + eigener Reconnect. Das ist gewollt („ausdrückliche Nutzeraktion"), jedoch in `docs/features/F5.md` (Dashboard-Anfrage „bis zu drei Minuten") und `docs/features/F18.md` nicht sichtbar ausgespielt.
  - Required fix: In der F18-Grenze (oder F5-Nachtrag) ergänzen, dass die Dashboard-/CLI-Anfrage im Wartefall bis zum Wartezeitlimit hängen kann; ggf. Hawk auf Dashboard-Client-Timeouts.

## Verification
- Change set reviewed: Ausgangscommit `7d4c630660ff42f01ad3a28d25d9094cfa39166e` → Arbeitsbaum, vollständig über `.f18-check/review-diff-1.txt` (je 1246 Zeilen, inkl. der beiden neuen Dateien) sowie durch Gegenlesen folgender Dateien im Arbeitsbaum: `bin/vibe` (Abschnitte 963–1443, Imports 41–47), `bin/vibe-run.sh` (1–60, 185–223), `tests/unit/test_fritz_coordination.py`, `tests/unit/test_fritz_reconnect.py`, `docs/features/F18.md`, `docs/baseline.md`, `docs/features/F5.md`, `docs/import-manifest.json`, `docs/trilium-index.md`, `FEEDBACK.md`, `SPEC.md`.
- Git commands run by me: keine. Shell-Befehle (auch nur-lesende Git-Befehle) wurden durch die Konfiguration verboten (`permission.rejected: shell`); ich habe dieselben Dateien stattdessen direkt gelesen und den Diff im Arbeitsbaum gegen die referenzierten Dateien verifiziert.
- Checks with supplied output: `.f18-check/red-coordination.log` (8 Tests, 6 Failures/1 Error, Konsistent mit Red-Kopie: `bin/vibe` ohne F18-Code, `bin/vibe-run.sh:195` ohne `VIBE_PROJECT`), `.f18-check/green-tests.log` (36 Tests OK), `.f18-check/quick.log` (Exit 0, 48 Manifestdateien, keine Geheimnisse), `.f18-check/full2.log` (749 Unit + 56 Browser, 805 erkannt, Exit 0).
- Checks not independently run: alle Build-/Test-/Verify-Aufrufe; die Manifest-Checksummen von `bin/vibe`/`bin/vibe-run.sh` habe ich nicht selbst berechnet; die rote Phase des Läufertests ist keine gespeicherte Log-Datei, sondern nur in Review-Input/F18.md zitiert (statisch bestätigt durch die Red-Kopie).
- Independent checks I performed myself: Trilium-Notiz `deX8hDMqAQ1k` über den Trilium-MCP-Zugang geprüft; statische Failing-First-Bestätigung des Läufertests gegen die Red-Kopie; Testdateien ohne Skip-/Ignore-Marker und ohne Assertions-Abschwächungen geprüft (keine Assertion-Entfernung im Diff).
- Important areas inspected: Sperre (`_fritz_lock_acquire`/`_fritz_lock_release`), Zustand/-Wartende/-Schonzeit-Veröffentlichung, Warteschleife, Übernahme, manueller Pfad, Exit-Codes in `cmd_fritz`, Läufer-Einbindung, Testqualität, Scope-Grenzen, Doku.
- Remaining risks: Zwei Installationen/profile mit getrennten Zustandsordnern koordinieren nicht (dokumentiert); keine echte FRITZ!Box getestet (Attrappe); Manifest-Checksummen nur über supplied-Log bestätigt; die drei Minor-Befunde oben blockieren nicht (per Regeln kein CHANGES REQUIRED).
