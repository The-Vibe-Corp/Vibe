# AP7 Review — Runde 3

Reviewer: code-reviewer (unabhängig, read-only)
Datum: 2026-11-10
Grundlage: Ausgangsstand `28cf66d` → Arbeitsbaum, Ticket AP7 (TICKETS.md:693),
nach Behebung der Runde-2-Medium-Befünde; Ablagen der Vorrunden:
`docs/reviews/AP7-review-1.md`, `docs/reviews/AP7-review-2.md`.

Die Antwort des Reviewers wird inhaltlich unverändert wiedergegeben
(lesbar normierte Kodistrate der Agentenrückgabe):

---

# Review result — AP7, Runde 3

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Info: 2
- Verdict: **PASS**

## Nachrechnungen / eigene Prüfungen (diese Runde tatsächlich ausgeführt)
1. **Shell-Berechtigungen:** erneut nur Git-Lesebefehle erlaubt (`git status --short`, `git diff HEAD --stat`, `git diff HEAD --` für styles.css, docs/import-manifest.json, docs/trilium-index.md, tests/browser/test_sandbox_ui.py). `bash scripts/verify.sh quick` wurde wieder verweigert (`Permission denied: shell`); node/python-Checks blieben damit ausgeschlossen — Syntax-, Prüfsummen- und **alle Testausführungen sind weiterhin Agent-Angaben** (wie in Runde 1/2 dokumentiert).
2. **Git-Status gegen erwartete Liste (M3):** exakt identisch — 10 modifizierte Dateien (app.js, styles.css, F13-einstellungen.png, import-manifest.json, trilium-index.md, 5 Testdateien) plus 5 neue Nachweis-/Testdateien. **Kein** wiedergeneriertes Nebenprodukt-PNG mehr im Baum (F13-uebersicht, F3, F7, AP03-*, F15/F16/F27/V-011 sind weg). Stat-Vergleich zu Runde 2: app.js unverändert 84 Zeilen (Runde 3 fasst app.js nicht an — zutreffend), styles.css 18 (56→78 px + Kommentar), test_sandbox_ui.py +7 (Titel-Assertion).
3. **Trilium-Ablesung (MCP, nur lesend):** `utcDateModified` jetzt `2026-11-10 02:18:01.938Z` (vorher 01:06:49). Nachtrag enthält: beide Runden mit Verweisen auf die Review-Ablagen, `scroll-margin-top:78px` samt Messwerten (`.detailbar` 76.06 px, Bindungsnachweis ohne Margin 1.25/0.625/43.17 px, mit 56 px ≈57 px), finale 7-Fälle-Liste („5 ursprüngliche + test_chip_jump... + test_agents_chip..."), finale Discovery-Zahlen (1226/84, Baseline-Vergleich „AP7-Stand besser"), `sandboxStatus`-/`onPill`-Fixes.

## Sachlage der Runde-2-Befunde

| Runde-2-Befund | Status | Evidence |
|---|---|---|
| [Medium] M1 — Chip-Sprung-Test ohne Align-Regime | **gelöst** | Test jetzt: Viewport 1280×400 nach `open_settings()` (tests/browser/test_ap7_settings_ui.py:627–628), je Chip `scrollY > 0` als Vorbedingung (:641–645, bei allen drei Chips), Invariante unverändert bindend (:662–678). Bindung belegt durch Probe-/Rot-Läufe im Report: ohne Margin `sumTop` 1.25/0.625/43.17 → Invariante fällt; **mit 56 px ebenfalls ROT** (57.25 < 74.0625, zweimal reproduziert, exakte Assertion-Meldung dokumentiert, docs/reviews/AP7-test-agent-report.md:289–320) — das bestätigt exakt meine Runde-2-Vorhersage, dass 56 px unzureichend wäre. Danach Anhebung auf `scroll-margin-top:78px` in bin/web/styles.css (AP7-Abschnitt, Kommentar mit Messwert 76.06 px); 78 px → `summary.top` ≈ 79 ≥ 74,06 ✓. Doku (AP7.md:131–135, 181–187) und Trilium-Nachtrag tragen dieselben Werte — CSS, Test, Report, Doku, Trilium konsistent. |
| [Medium] M2 — Trilium nicht synchronisiert | **gelöst** | Nachtrag vom 2026-11-10 02:18 UTC mit Rundenverlauf, 78 px-Messwerten, 7 Fällen, finalen Prüfergebnissen; Schreiberfolg per Re-Read belegt (nicht nur beansprucht — von mir abgelesen). Restliches Detail siehe Minor 1. |
| [Medium] M3 — 9 PNG-Nebenprodukte | **gelöst** | `git status` deckungsgleich mit der erwarteten Vor-Commit-Liste; nur `F13-einstellungen.png` (das Soll-Nachweis des AP7) bleibt als PNG diff; AP7.md:204–207 stimmt jetzt mit dem realen Baum überein. Commit-Hygiene-Hinweis bleibt: vor dem Commit `git status` prüfen und ausschließlich die gelisteten Dateien stagen. |
| [Info] Sandbox-Titel-Assertion | **umgesetzt, verstärkend** | Neue Assertion `assertIn("Sandbox (optional)", summary.inner_text())` in test_sandbox_ui.py (Diff, dokumentiert als „Runde 2 Info-Befund") — das Alt-Titel-Verfahren ist damit nicht ersatzlos gefallen, sondern auf den neuen Titel gewechselte Absicherung; keine Abschwächung. |

## Neue Befunde

- [Minor] `docs/features/AP7.md:167–171` (und analog Trilium-Nachtrag) — Bestandssuiten-Zahl ist der Endrunde hinterher: Doku meldet „Bestandssuiten-Runde 37/37 OK" (Runde-2-Stand, 6 Suiten ohne AP03), während die nach der 78-px-Anhebung gemeldete Gesamtrunde **43/43** (7 Suiten) laut Handoff gilt und in beiden Nachweisorten nicht eingepflegt ist. Konsequenz: keine fachliche; die Zahl ist rein nachweisbezogen.
  - Required fix vor dem Commit: die 37/37-Zeile in AP7.md (und den Trilium-Nachtrag) auf die post-Anhebung 43/43-Runde aktualisieren oder beide Zahlen mit Rundenbezug („pre/post CSS-Anhebung") sauber selbsterklären.
- [Info] Trilium-Notiz: der **ursprüngliche Runde-1-Körper** bleibt unverändert stehen („5 Fälle", „Ran 5 tests … OK", `projectAgentsCard(name, onCount)`), korrigiert erst durch den datierten Nachtrag („Tests final: 7 Fälle (5 ursprüngliche + …)"). Das ist eine nachvollziehbare Versionierung mit ausdrücklicher Übergabe; riskant wäre es nur, wenn der alte Abschnitt isoliert gelesen wird. Kein Muss-Behandlungsbedarf; optional könnte der alte „5 Fälle"-Satz mit einem Rückverweis auf den Nachtrag versehen werden.
- [Info] `docs/trilium-index.md` ergänzt neben AP7 auch die (bereits bestehenden) Trilium-Notizen AP05/AP6 in den Index — kleine, sinnvolle, aber nicht AP7-induzierte Ausbesserung des Index. Unschädlich; beim Commit enthält diese Datei diese zwei Extra-Zeilen transparent als Doku-Sync (im AP7-Commit sichtbar und plausibel).

## Acceptance-Kriterien (Kurzabgleich)
| Kriterium | Status | Evidence |
|---|---|---|
| Einstellungs-UI neu gegliedert/zugänglich | PASS | app.js (settingsPanel/settingsSection/settings-nav), Screenshot-Review Runde 1; unverändert |
| Wichtiges oben / Agenten offen / Optionales eingeklappt | PASS | app.js:206–208, test_cases 1/4, Screenshots |
| GitHub-Aktionen nur bei aktiv | PASS | app.js `actions=active?...`, Tests |
| Sprungziel-Fix (Runde-1-Medium) | PASS * | CSS 78px im Messwert-Nachweis bindend abgesichert (ROT@56 → GRÜN@78 laut Agent; Geometrie-Invariante von meiner Seite verifiziert und als bindend geprüft) |
| Fehlerzustand Agenten-Chip / sandboxStatus-Refactor / Sandbox-Titel | PASS | app.js + Tests (Runde-2/3 geprüft) |
| Manifest/Doku/Trilium nachgeführt | PASS | Manifest-Diff (app.js unverändert zur Runde 2 — zutreffend, styles.css neu resynct: sha `4f44d4e8…`, 9414 B), AP7.md, Trilium-Nachtrag |
| Sauberer Arbeitsbaum | PASS | git status exakt wie erwartet |

\* die Testdurchsätze (7/7, 43/43, quick Exit 0) sind Agent-Nachweise; die Ausführung war mir in allen drei Runden verwehrt. Die **Bindungskraft** des M1-Tests habe ich dagegen selbst über die Geometrie und die im Report dokumentierten Spreiz-Messwerte (0/56/78) bewertet — sie ist belegt, dass ohne CSS die Invariante fällt.

## Verification
- Change set reviewed: `28cf66d` → Arbeitsbaum über `git diff`/`git status` (app.js, styles.css, 5 Testdateien, Manifest, trilium-index) + vollständige Lektüre der beteiligten Dokumente und Nachweise.
- Git-Befehle von mir ausgeführt: `git status --short`, `git diff HEAD --stat`, `git diff HEAD --` (styles.css, import-manifest.json, trilium-index.md, test_sandbox_ui.py).
- Checks mit mitgelieferten Objekten von mir direkt belegt: Trilium-Lesung (Re-Read, Nachtrag-Inhalt), Review-Ablagen 1+2 (unverändert wiedergegebene Antworten), M1-Rot-Grün-Messwerte im Report, Manifest-Resync-Diff, Info-Umsetzung.
- Checks **nicht** unabhängig ausgeführt: `bash scripts/verify.sh quick` (Shell verweigert), `python3 -m unittest tests.browser.test_ap7_settings_ui` (Shell verweigert), node/check-syntax/check-import-manifest — weiterhin Agent-Angaben; Manifest-Hashes nicht nachrechenbar.
- Remaining risks: die verifizierenden Testläufe bleiben Agent-Nachweise (Umgebung verweigert mir die Ausführung); die 37/43-Doku-Nummer (Minor 1) vor dem Commit angleichen; beim Commit Blanko-Staging vermeiden (nur die gelisteten AP7-Dateien stagen).

## Verdict

**PASS** — keine Critical/High/Medium-Befunde; alle drei Runde-2-Medium-Befunde sind mit belegter Beweislage (Runtime-Messwerte, rot-grün-Protokoll, Re-Read, sauberer Baum) gelöst. Der verbleibende Minor-Befund (37/43-Doku-Nummer) ist vor dem Commit billig anzupassen, blockiert das Arbeitspaket nicht. Keine Implementierungsänderungen ohne erneuten Review. Ticket darf mit echten Nachweisen abgehakt werden (Commit, Testbefehle, Review-Pfade Runde 1–3, Doku- und Trilium-Pfade).
