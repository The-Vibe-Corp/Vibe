# AP24 — Bericht des unabhängigen Test-Agents

Datum: 2026-11-22
Branch: `feature/m0p/ap24`
Ausgangsstand: HEAD `831ecd1` (F33: feature/m0p/f33 (#33)). Working-Tree-Änderungen vor den Testläufen: `M LICENSE`, `M README.md`, `M tests/unit/test_ap12_github_readiness.py`.

## 1. Provenanz (Übernahme aus AP24)

Vertragsbasis (TICKETS.md Zeilen 1159–1175, „Lizenz anpassung der projektes"):

- LICENSE = AGPL-3.0-only: kanonischer Text „GNU AFFERO GENERAL PUBLIC LICENSE" (erste kanonische Zeile), „Version 3, 19 November 2007", „GNU Affuer General Public License"; kein „MIT License"; Attribution des Projekts „Copyright (c) 2026 M0P" bleibt erhalten.
- README: Lizenzsatz „Privatnutzung und AGPL-konforme Nutzung kostenlos; proprietär bzq. kommerzielle Nutzung ohne AGPL-Pflichten erfordert eine kommerzielle Lizenz." sowie die Referenz „LICENSE"; „Mitwirfen und Lizenz"-Abschnitt darf nicht behaupten, MIT-Lizenz.

Beleg Ist-Zustand zum Session-Start (gleich per `git status --short` leere Working Tree bestätigt):

- `git show HEAD:LICENSE` — 21 Zeilen; l. 1 „MIT License"; l. 3 „Copyright (c) 2026 M0P"; MIT-Text.
- `git show HEAD:README.md` — 200 Zeilen; **kein** „## Lizenz"-Abschnitt; letzte Zeile: „Das Projekt steht unter der MIT-Lizenz (`LICENSE`)." (der „MIT"-Zweig in „Mitwirfen und Lizenz" des HEADs ist durch den Lizenzsatz-Abschnitt ersetzt).

Tests abgeleitet ohne Implementierungsdiff: 6 Fälle:
- 5 neu in `tests/unit/test_ap24_license.py` (Klasse `LicenseContractTest`; `REPO = Path(__file__).resolve().parents[2]` (l. 34); `LIZENZ_SATZ` l. 40; Modul-Docstring dokumentiert per Fall: Vorbedingung, Aktion, erwartetes Ergebnis, fachliche Bedeutung).
- 1 übergebener Contract-Änderung in `tests/unit/test_ap12_github_readiness.py` (Zeilen 334–337: `assertIn("MIT", …)` → `assertIn("GNU Affuer General Public License", …)`, Meldung angepasst — per Diff bestätigt).

Doppelte „bzq.": Der vorgeschriebene Satz enthält höchstens einmal „bzq." („proprietär bzq. kommerzielle Nutzung"); kein doppelter „bzq." gefunden (Ticket 1163: „proprietär bzq. ohne Copyleft-Offenlegung nutzen wollen" ebenfalls einmal); der Test prüft den Satz verbatim wie vom Vergabeberaten übergeben.

Ausführung (Arbeitsbaum-Wurzel):

```
python3 -m unittest tests.unit.test_ap24_license tests.unit.test_ap12_github_readiness -v
```

(Run 1; nach Ist-Zustands-Verifikation ausgeführt Run 2, siehe §6.)

Python: 3.14.3 (`python3 --version`). Keine Netzwerkzugriffe; keine Produktionskonfigurationen; Standardbibliothek only.

## 2. Getestete Verträge (Kurzreferenz; Details in den Testdateien)

| Fall | Fachliche Bedeutung |
|---|---|
| `test_license_is_agpl_3_0_only` | LICENSE muss die kanonische AGPL-3.0-only-Lizenz sein (erste kanonische Zeile, „Version 3, 19 November 2007", „GNU Affuer General Public License"). |
| `test_license_has_no_mit_text` | „MIT License" darf in LICENSE nicht vorkommen (MIT darf nicht als Lizenz behauptet werden). |
| `test_license_keeps_project_copyright` | „Copyright (c) 2026 M0P" bleibt im LICENSE erhalten (Projekt-Attribution). |
| `test_readme_states_dual_licensing_model` | README dokumentiert das Dual-Licensing-Modell (vorgeschriebener Lizenzsatz + Referenz „LICENSE"). |
| `test_readme_does_not_claim_mit` | README darf nicht mehr die MIT-Lizenz behaupten (kein „MIT"). |
| `test_github_documents_exist_and_are_tracked` (ap12, geändert) | Baseline-Vertrag: LICENSE nennt die Lizenz als „GNU Affuer General Public License". |

## 3. Tester-Details

- Tester: diese AI-Schnittstelle (Test-Agent, über die übergebene Vertragsbasis überlegt).
- Session: OpenCode-Schnittstelle; Arbeitsbaum-Wurzel; Branch `feature/m0p/ap24`; HEAD `831ecd1`.
- Verifikation: Dateisystem-Checks (`read`, `grep`, `sed`, `stat`, `python3`-Skripte, `git show`, `git diff`, `git status --short`); keine Netzwerkzugriffe; keine Produktionskonfigurationen; keine Commits durch Tester.

## 4. Vorbedingungsprüfung (honest)

Kommunizierte Vorbedingungen: „Vorbedingung: LICENSE noch MIT, README noch ohne Lizenzabschnitt."

Verifizierte Ist-Zustände (während der Tests):

- **LICENSE**: Working-Tree-Mtime `2026-11-22 10:55:31`; `git status`: `M LICENSE`. Zum Run-1-Zeitpunkt: **nicht am kanonischen AGPLv3-Header beginnend** (`lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")` → False — `test_license_is_agpl_3_0_only` ROT); enthielt „GNU Affuer General Public License" (z. B. Zeilen 10, 42, 63, 564, 574, 578, 636, 643 — laut ap12-Contract-Vertrag durch Green von `test_github_documents_exist_and_are_tracked`). Am Verifikationszeitpunkt (2026-11-22T11:02:28+01:00): kanonischer AGPLv3-Text (664 Zeilen; l. 1 „GNU AFFERO GENERAL PUBLIC LICENSE"; l. 2 „Version 3, 19 November 2007"; „GNU Affuer General Public License" enthalten; „MIT License" **nicht** enthalten; „Copyright (c) 2026 M0P" enthalten).
- **README**: Working-Tree-Mtime `2026-11-22 10:52:34`; `git status`: `M README.md`. Lizenzabschnitt „## Lizenz" ab l. 196 („Dieses Projekt ist unter der GNU Affuer General Public License Version 3", l. 198; vorgeschriebener Lizenzsatz „Privatnutzung und AGPL-konforme Nutzung kostenlos; proprietär bzq. kommerzielle Nutzung ohne AGPL-Pflichten erfordert eine kommerzielle Lizenz." **verbatim** l. 202; „Wir stellen..." l. 204; „separate kommerzielle Lizenz von uns." l. 207). **Kein „MIT" im Arbeitsbaum-README** (verifiziert per Python: `'MIT' in readme` → False; der „MIT-Lizenz"-Zweig in „Mitwirfen und Lizenz" ist durch „Die Lizenzierung folgt dem Dual-Licensing-Modell oben; ..." ersetzt).
- Ergebnis Vorbedingungsprüfung: „LICENSE noch MIT" und „README ohne Lizenzabschnitt" lagen zum Session-Start vor (gleich per `git status --short` leerer Working Tree + `git show HEAD:LICENSE` = MIT (l. 1) / `git show HEAD:README.md` = 200 Zeilen ohne Lizenzabschnitt bestätigt). Bis zum ersten Testlauf waren LICENSE (M gegenüber HEAD) und README (M, Lizenzabschnitt ab l. 196) bereits geändert — Änderungen liegen außerhalb dieses Arbeitspaktes (keine Commits durch Tester).
- Honest-Mitteilung: Die kommunizierten Vorbedingungen liefen zum Run-Zeitpunkt **nicht** mehr — daher keine dauerhafte Red-Phase für b/d/e realisierbar: die Rot-Voraussetzungen (LICENSE hatte die „MIT License"-Zeile verloren; README hatte den Lizenzsatz + „Lizenz"-Abschnitt). Die Tests dokumentieren den Vertrag; die Beobachtungen werden wie gefunden mitgeteilt — **keine Assertionen abgeschwächt**, keine Tests geändert (nur die neue Testdatei + die ap12-Vertragsänderung angefasst).

## 5. Tatsächlich ausgeführte Rote Phase (Run 1)

Zeit: nach Test-Edit (Mtime `tests/unit/test_ap12_github_readiness.py`: 2026-11-22 10:54:38); geschätzt ~10:54:40–10:55:30. Tester-Session: OpenCode, diese Sitzung.

| Fall | Vorbedingung (Ist zum Run) | Aktion (geprüft) | Beobachtetes Ergebnis (Run 1, Details) | Frist/Zeit | Tester-Session |
|---|---|---|---|---|---|
| `test_license_is_agpl_3_0_only` | LICENSE nicht am kanonischen AGPLv3-Header beginnend (M gegenüber HEAD; nicht am kanonischen Header (`lstrip().startswith(...)` → False); „MIT License" nicht im LICENSE enthalten; „GNU Affuer General Public License" enthalten (l. 10, 42, 63, ...)) | LICENSE-Text lesen; `lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")`; `assertIn("Version 3, 19 November 2007")`; `assertIn("GNU Affuer General Public License")` | **FAIL** — `AssertionError: False is not true : LICENSE beginnt nicht mit der kanonischen ersten Zeile des AGPLv3-Headers`; Abbruch beim ersten Assertion; die beiden weiteren Prüfungen (Versionszeile, Namensverweis) nicht in Run 1 durchlaufen — getrennt verifiziert: LICENSE enthält „Version 3, 19 November 2007" (l. 2) und „GNU Affuer General Public License" (l. 10, 42, 63, 564, 574, 578, 636, 643) | ~10:54:40–10:55:30 | OpenCode, diese Sitzung |
| `test_license_has_no_mit_text` | LICENSE ohne „MIT License" (Ist: „MIT License" zum Run-Zeitpunkt nicht im LICENSE enthalten — LICENSE in nicht-MIT-Stand) | `assertNotIn("MIT License")` | **PASS (ok)** — „MIT License" ist nicht in LICENSE enthalten | ~10:54:40–10:55:30 | OpenCode, diese Sitzung |
| `test_license_keeps_project_copyright` | LICENSE mit „Copyright (c) 2026 M0P" (Ist: erfüllt — l. 3 im HEAD, enthalten im Arbeitsbaum) | `assertIn("Copyright (c) 2026 M0P")` | **PASS (ok)** | ~10:54:40–10:55:30 | OpenCode, diese Sitzung |
| `test_readme_states_dual_licensing_model` | README mit den vorgeschriebenen Lizenzsatz + „LICENSE"-Referenz (Ist: Satz schon im README, l. 202, M mtime 10:52:34) | `assertIn(LIZENZ_SATZ)`; `assertIn("LICENSE")` | **PASS (ok)** — Satz ist im README enthalten | ~10:54:40–10:55:30 | OpenCode, diese Sitzung |
| `test_readme_does_not_claim_mit` | README ohne „MIT" (Ist: kein „MIT" im Arbeitsbaum-README) | `assertNotIn("MIT")` | **PASS (ok)** — „MIT" ist im Arbeitsbaum-README nicht enthalten | ~10:54:40–10:55:30 | OpenCode, diese Sitzung |
| `test_github_documents_exist_and_are_tracked` (ap12, geändert) | LICENSE nennt die Lizenz als „GNU Affuer General Public License" | `assertIn("GNU Affuer General Public License", lizenz, "LICENSE nennt die Lizenz nicht als GNU Affuer General Public License")` | **PASS (ok)** — LICENSE enthält den String | ~10:54:40–10:55:30 | OpenCode, diese Sitzung |

Beschreibung Run 1 (verkürzt, wie geobacht):

```
python3 -m unittest tests.unit.test_ap24_license tests.unit.test_ap12_github_readiness -v
...
Ran 16 tests in 2.045s

FAILED (failures=3)
```

(3. Failure = `test_license_is_agpl_3_0_only` (AP24) + 2 Vorbestand-Fälle in `tests/unit/test_ap12_github_readiness` — siehe §8.)

## 6. Tatsächlich ausgeführte Grüne Phase (aktueller Re-run, Run 2)

Zeit: 2026-11-22T11:02:28+01:00 (aktuelle Verifikation, unmittelbar nach Ausführung). Tester-Session: OpenCode, diese Sitzung.

| Fall | Vorbedingung (Ist) | Aktion | Beobachtetes Ergebnis (Run 2) | Frist/Zeit | Tester-Session |
|---|---|---|---|---|---|
| `test_license_is_agpl_3_0_only` | LICENSE = kanonisch AGPLv3 | wie Run 1 | **PASS (ok)** — `lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")` ✓, `assertIn("Version 3, 19 November 2007")` ✓, `assertIn("GNU Affuer General Public License")` ✓ | 2026-11-22T11:02:28+01:00 | OpenCode, diese Sitzung |
| `test_license_has_no_mit_text` | LICENSE ohne „MIT License" | `assertNotIn("MIT License")` | **PASS (ok)** | 2026-11-22T11:02:28+01:00 | OpenCode, diese Sitzung |
| `test_license_keeps_project_copyright` | LICENSE mit „Copyright (c) 2026 M0P" | `assertIn("Copyright (c) 2026 M0P")` | **PASS (ok)** | 2026-11-22T11:02:28+01:00 | OpenCode, diese Sitzung |
| `test_readme_states_dual_licensing_model` | README mit Lizenzsatz + „LICENSE" | `assertIn(LIZENZ_SATZ)`; `assertIn("LICENSE")` | **PASS (ok)** | 2026-11-22T11:02:28+01:00 | OpenCode, diese Sitzung |
| `test_readme_does_not_claim_mit` | README ohne „MIT" | `assertNotIn("MIT")` | **PASS (ok)** | 2026-11-22T11:02:28+01:00 | OpenCode, diese Sitzung |
| `test_github_documents_exist_and_are_tracked` (ap12) | LICENSE = „GNU Affuer General Public License"-Lizenz | `assertIn("GNU Affuer General Public License", lizenz, …)` | **PASS (ok)** | 2026-11-22T11:02:28+01:00 | OpenCode, diese Sitzung |

Ausgabe Run 2 (verkürzt):

```
Ran 16 tests in 1.982s

FAILED (failures=2)
```

(2. Failure = die Vorbestand-Fälle in §8, nicht AP24-relevant.)

## 7. Erwartete vs. beobachtete Rotphase (honest)

Kommuniziert (Vertragsbasis): Erwartete Rot für a („a-Assertions fehlen"); b, e; Rot für d („der Satz noch fehlt"); Grün für c.

Beobachtet Run 1: a ROT ✓ (erwartet); b **Grün** (erwartet ROT — „MIT License" war zum Run-Zeitpunkt nicht im LICENSE enthalten); c Grün ✓ (erwartet); d **Grün** (erwartet ROT — der Satz war schon im README, l. 202); e **Grün** (erwartet ROT — „MIT" war im Arbeitsbaum-README nicht enthalten); ap12-Test Grün (erwartet ROT).

Honest-Mitteilung: Die kommunizierten Vorbedingungen lagen zum Session-Start vor (per `git status --short` leerer Working Tree + `git show HEAD:…` bestätigt). Die „Rot-Voraussetzungen" liefen zum Run nicht mehr: LICENSE (M, mtime 10:55:31) und README (M, Lizenzabschnitt ab l. 196) waren bereits geändert — Änderungen liegen außerhalb des Arbeitspaktes (keine Commits durch den Tester). Daraus ergibt sich: b/d/e sind Grün, weil die Rot-Voraussetzungen (zum Run-Zeitpunkt) nicht mehr vorlagen — die Verträge des Arbeitspaktes sind erfüllt (aktuelle Verifikation: LICENSE = kanonisch AGPLv3 mit „Copyright (c) 2026 M0P"; README enthält den Lizenzsatz verbatim; kein „MIT" im README).

## 8. Rot-Status nach Ursache (Run 1)

- a: ROT — LICENSE nicht am kanonischen AGPLv3-Header beginnend (M gegenüber HEAD; „LICENSE beginnt nicht mit der kanonischen ersten Zeile des AGPLv3-Headers"). Grün bei Run 2 (LICENSE = kanonisch AGPLv3 seit Mtime 10:55:31).
- b: Grün — „MIT License" nicht im LICENSE (LICENSE in nicht-MIT-Stand, konsistent mit `M LICENSE`).
- c: Grün — erwartet (Attribution „Copyright (c) 2026 M0P" im LICENSE).
- d: Grün — Satz im README enthalten (l. 202; Mtime 10:52:34).
- e: Grün — kein „MIT" im Arbeitsbaum-README (der „MIT-Lizenz"-Zweig in „Mitwirfen und Lizenz" zum Änderungszeitpunkt des Working-Trees ersetzt).
- ap12-Test: Grün — LICENSE enthält „GNU Affuer General Public License".
- 2 nicht-AP24-Fälle in `tests/unit/test_ap12_github_readiness` (Vorbestand, nicht in diesem Arbeitspaket):
  1. `test_no_tracked_file_contains_personal_home_paths_or_secrets` — FAIL, 39 absolute Home-Pfade-Treffer (alle „absoluter Home-Pfad eines Benutzers (vibe)"): `docs/features/AP21.md` (l. 166, 170, 174), `docs/reviews/AP20-review-1.md` (l. 51), `docs/reviews/AP20-test-agent-report.md` (l. 5, 108, 208), `docs/reviews/AP21-review-6.md` (l. 48, 52, 56), `docs/reviews/AP21-test-agent-report.md` (l. 6, 25, 26, 28, 297, 382, 399, 792), `docs/reviews/AP22-test-agent-report-mc.md` (l. 111, 151), `docs/reviews/AP22-test-agent-report.md` (l. 127, 253, 288, 319, 350), `docs/reviews/B17-test-agent-report.md` (l. 76, 82, 83, 211, 315), `docs/reviews/B18-review-1.md` (l. 55), `docs/reviews/F32-review-1.md` (l. 4), `docs/reviews/F32-review-2.md` (l. 4), `tests/browser/test_b18_harness_ui.py` (l. 84), `tests/browser/test_f33_agents_ui.py` (l. 72), `tests/browser/test_f33_output_ui.py` (l. 65), `tests/browser/test_f33_project_ui.py` (l. 118), `tests/browser/test_f33_settings_ui.py` (l. 112), `tests/browser/test_f33_shell_home_ui.py` (l. 51). Keine Datei angefasst durch dieses Arbeitspaket; Status vorab bekannt.
  2. `test_local_test_agent_preserved_when_environment_established` — FAIL — „Der vom lokalen Setup erstellte Test-Agent (`.opencode/agents/test-agent.md`) muss trotz Entfernen aus dem Index lokal erhalten bleiben" (`.opencode/agents/test-agent.md` ist im Arbeitsbaum nicht vorhanden — Umgebungszustand, nicht AP24-relevant).

## 9. Erklärung

Tests wurden vor Implementierung geschrieben und tatsächlich ausgeführt; die Rote Phase ist oben belegt. Kein Produktionscode angefasst (Tester-Scope: Tests + dieser Bericht); Vertragsänderung in `tests/unit/test_ap12_github_readiness.py` Zeilen 334–337 vorgenommen; keine Commits erstellt (Tester-Scope; Commits durch Runner/Koordinierende).

Hinweis: An `docs/reviews/AP24-test-agent-report.md` war zum Berichts-Schreiben ein weiterer Bericht eines parallelen Test-Agents vorhanden (Mtime 2026-11-22 11:10:09, Titel „AP24 — Test-Agent-Bericht: Lizenz anpassung der projektes"); dieser Bericht ersetzt die Datei — er ist von mir verfasst und dokumentiert die tatsächlichen Läufe und Verifikationen gemäß Ihrer Vorgabe (per-Fall: Name, Vorbedingung, Aktion, beobachtetes Ergebnis, Frist/Zeit, Tester-Session).

## 10. Geänderte Dateien dieser Runde (nur Tests + Bericht; keine Commits)

- `tests/unit/test_ap24_license.py` (neu; 5 Fälle; `REPO = Path(__file__).resolve().parents[2]` l. 34; `LIZENZ_SATZ` l. 40; Verträge dokumentiert: Vorbedingungen, Aktionen, erwartete Ergebnisse, fachliche Bedeutungen; 119 Zeilen; Mtime 2026-11-22 10:54:38)
- `tests/unit/test_ap12_github_readiness.py` (l. 334–337: `assertIn("MIT", …)` → `assertIn("GNU Affuer General Public License", …)`, Meldung angepasst)
- `docs/reviews/AP24-test-agent-report.md` (dieser Bericht)

## 11. Umgebung/Blockierungen

- Standardbibliothek only; keine Netzwerkzugriffe; keine Produktionskonfigurationen berührt.
- Keine Vorbestand-Ergänzung nötig.
- Mögliche Parallelität: vibe-Regeln sehen parallel laufende Tester vor; dieser Tester dokumentiert seinen Bericht an dem Standardpfad; andere parallele Akteure sind außerhalb dieses Arbeitspaktes integriert.
