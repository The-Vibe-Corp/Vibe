# Review-Ablage: Arbeitspaket B6 (Review Runde 2)

Grundlage: Gleiche Basis wie Runde 1 (`docs/reviews/B6-review-1.md`:
Produkt-Diff gegen `db45bd7` im Worktree `vibe-B6-KbOl3S`, Branch
`vibe/vibe-B6-1794257245505672696-360176-25507`) plus die in Runde 1
beanstandeten Lücken: echter Pi-Smoke-Nachweis, AK-Abschnitt,
Grenzenerweiterungen (`docs/features/B6.md`), `verify.sh full`-Vergleich
gegen den Baselinelauf am Ausgangscommit `db45bd7` (detached Git-Worktree
`/dev/shm/vibe-b6-base`, identisches Verfahren). Reviewer: `code-reviewer`
(Subagent, Modell GLM-5.3-Flash Free, Provider opencode), Datum 2026-11-09.

Nachfolgend das unveränderte Reviewergebnis des Reviewers:

---

# Review result – B6 (Review Runde 2)

## Header / Review-Metadaten
- Ticket: B6 (FEEDBACK.md Zeile 348) — „F24 funktioniert nicht richtig … darf nicht opencode spezifisch sein (pi harness muss funktionieren)"
- Reviewer: code-reviewer (Subagent, Modell GLM-5.3-Flash Free, Provider opencode), Datum 2026-11-09
- Arbeitsbasis: Ausgangs-Commit `db45bd7`, Branch `vibe/vibe-B6-1794257245505672696-360176-25507` (Worktree `vibe-B6-KbOl3S`), Reviewtyp Runde 2, nur lesend; Grundlage Runde 1 (`docs/reviews/B6-review-1.md`) unverändert gelesen

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Prüfung der fünf Runde-1-Befunde

1. **[Medium] Abnahme gegen echtes Pi** — **behoben.** `docs/features/B6.md:150-186` dokumentiert den echten 1.5.0-Smoke exakt wie verlangt. Ich habe die Rohdaten **selbst gelesen** und bestätigt:
   - `/tmp/opencode/pi-b6-smoke/pi-events.jsonl`: echter Session-Header mit `{"type":"session","version":3,"id":"01a1c22d-…","cwd":"/tmp/opencode/pi-b6-smoke"}` — deckt sich mit den von Runde 1 verifizierten Pi-Doku-Formen (`PI_EVENT_TYPES`, `id` im Header). `--no-session` unterdrückt den Header nicht; die Designentscheidung „Header nie in state" ist an der echten Umgebung bestätigt.
   - `filtered.txt`: `[Session] 01a1c22d-…` plus unverändert durchgereichte Klartextzeile „No API key found for the selected model." — der reale Filter erkennt den echten Strom und verhält sich auf Nicht-JSON korrekt.
   - `exitinfo.txt`: `PIPE-EXIT pi=1`, „pi stdout bytes: 148" — Agentenexit maßgeblich (AK5-Semantik).
   - `agent/auth.json` und `agent/models-store.json` sind leer (`{}`): keine Anmeldung, keine Secrets, keine Modellkosten in den Nachweisen; die Nachweise dürfen existieren.
   - Kein `*.state.json` im Smoke-Verzeichnis — „keine Zustandsdatei erzeugt" ist belegt.
   - Die dokumentierte Grenze („No API key" schließt Text-/Werkzeug-/Subagentenebene des echten Laufs aus) ist ehrlich ausgeführt und mit der Pflichtregel in `docs/compatibility.md` (Pi 1.5.0, Abschnitte Zeilen 35 ff.) verknüpft. Diese Restattrappenabdeckung ist im Rahmen des Tatbestands (Kostenfreiheit, keine OAuth) die maximal mögliche Prüftung und vom Required fix ausdrücklich so akzeptiert.
2. **[Minor] Grenzen-/Feldschema** — **behoben:** `docs/features/B6.md:190-198` nennt das konkrete Pi-1.5.0-Werkzeugschema (`agent, task, tasks, chain, cwd, agentScope, confirmProjectAgents`, kein `prompt`/`description`), die Tab-Label-Fallback-Konsequenz und den Folgepaketvorschlag über den Test-Agenten. Keine Codeänderung verlangt.
3. **[Minor] `changed=True` ohne Differenz** — **behoben:** `docs/features/B6.md:199-202` hält die Grenze als dokumentierte spätere Optimierung fest. Gemäß Required fix keine zwingende Änderung.
4. **[Minor] Web-Fallback an opencode-Server** — **behoben:** `docs/features/B6.md:203-207` dokumentiert den Vorfallback als unveränderten Altcode mit Folgepaketvorschlag (Aussetzen für Kennungen ohne `ses_`).
5. **[Minor] AK-Abschnitt** — **behoben:** `docs/features/B6.md:72-97` enthält „## Akzeptanz" mit AK1–AK5; die Nummerierung stimmt mit den Testdatei-Dokstrings überein (eigener grep: AK1–AK5 in `tests/unit/test_b6_*.py`, z. B. `test_b6_pi_runner_events.py:320,419`, `test_b6_harness_events_flag.py:71,166`, `test_b6_pi_events.py:131`).

## Produktcode und Testintegrität (Runde 2)

- `git diff --stat db45bd7` ist **exakt identisch zu Runde 1** (`bin/vibe-run.sh +8/-…`, `bin/vibe_harness.py 18`, `bin/vibe_runs.py 203`, `bin/web/app.js 2`, `docs/import-manifest.json 16`); `scripts/` ist unverändert (kein Treffer in `git diff --name-only db45bd7 -- scripts/`). Kein Produktcode nodded seit Runde 1 — die Fundstellen aus Runde 1 bleiben gültig.
- Full-Lauf-Nachweise **selbst gelesen** und mit der Differenzanalyse abgeglichen:
  - `b6-full-run.log:1887-1889`: `Ran 1274 tests`, `FAILED (failures=15, errors=8)`; `b6-base-full-run.log:1867-1869`: `Ran 1240 tests`, `FAILED (failures=14, errors=10)`. Differenz 1274−1240 = **34** — exakt die drei neuen B6-Suiten.
  - Fail-Listen einzeln abgeglichen: **22 Einträge identisch in Name, Modus und Reihenfolge**; einzige Abweichungen `test_every_checked_entry…` (B6-Lauf FAIL, Baseline ERROR, in beiden failend — Kopierartefakt der unversionierten FEEDBACK.md) und `test_f7_continuation…` (nur Baseline, FEEDBACK.md abwesend). Keine neue Fail-Klasse, keine verschobenen/weiterlaufenden B6-Tests.
  - Alle **34 B6-Tests** stehen im full-Lauf mit `... ok` (`b6-full-run.log:181-214`); keine Skip-/xfail-/assume-Marker in den B6-Testdateien (eigener grep: „No matches found").
- Test-Agent-Voraussetzung: `TESTER=test-agent` in `.vibe/project.env:12` vorhanden; die als Runde-1-Nachweis behandelten Testauthentiken (Rotphase, AK-Dokstrings) sind konsistent.

## Akzeptanzkriterien
| Kriterium | Status | Implementierung (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: Pi-Ereignisse automatisch erkannt, Klartext, Header nie in state | PASS | `bin/vibe_runs.py:104-117, 405-490` (Runde 1, unverändert: diff-stat identisch) | `test_b6_pi_events.py` PiEventTranslationTest/PiStreamFormTest; full-Lauf `b6-full-run.log:187-202` ok; **echter Pi-Smoke**: Header + Filterausgabe gelesen, keine state-Datei |
| AK2: opencode-Verhalten byte-identisch | PASS | `bin/vibe_runs.py:487-490` | OpencodeRegressionTest (`b6-full-run.log:187-191` ok); Rotphase dokumentiert `docs/features/B6.md:111-112` |
| AK3: Subagentenerfassung Pi, UI-API unverändert | PASS | `bin/vibe_runs.py:322-402, 422-426` | PiSubagentCaptureTest/PiSubagentApiTest (`b6-full-run.log:203-210` ok); Smoke: `id` nur als `[Session]`-Zeile, keine state-Datei |
| AK4: `run_argv(events=True)` fügt bei Pi `--mode json` ein | PASS | `bin/vibe_harness.py` (Runde 1 unverändert) | `test_b6_harness_events_flag.py` (`b6-full-run.log:182-186` ok) |
| AK5: Läufer-Pi-Zweig, Agentenexit maßgeblich | PASS | `bin/vibe-run.sh` (Runde 1 unverändert) | `test_b6_pi_runner_events.py` (`b6-full-run.log:211-214` ok); Smoke `exitinfo.txt`: `PIPE-EXIT pi=1` |
| Gesamt: F24 mit **echtem** Pi-Harness | PASS (Restrisiko sauber dokumentiert) | — | echter 1.5.0-Smoke, `docs/features/B6.md:150-186`; Rohdaten von mir gelesen; Grenze für Text-/Werkzeug-/Subagentenkontrakt mit `docs/compatibility.md`-Pflicht festgehalten |

## Findings
- [Minor] `docs/features/B6.md:176` — Filter-Exit-Code im Smoke-Artefakt nicht erfasst
  - Evidence: `exitinfo.txt` hält nur `PIPE-EXIT pi=1` und die Bytezahl fest; der Exit-Code des Filters selbst ist weder als Artefaktdatei noch im Abschnitt dokumentiert (der Behebungstext nennt „Exit 0 des Filters"). Die Substanz (Filter lieferte vollständige Ausgabe, `filter-err.txt` leer, state-Datei abwesend) ist durch die vorhandenen Artefakte belegt — der Buchhaltungslücke obliegt nur der Feldnachweis zur Wiederholbarkeit.
  - Required fix: Beim nächsten Smoke-Artefakt einfach eine Zeile `FILTER-EXIT <n>` in `exitinfo.txt` ergänzen; keine Codeänderung am Paket.
- [Minor] `docs/features/B6.md:134-138` — Prüfabschnitt zur Full-Vergleichsrunde leicht unpräzise
  - Evidence: „Nur im B6-Lauf FAIL `test_every_checked_entry…`" ist streng genommen ungenau — der Test failt in **beiden** Läufen, nur der Modus divergiert (Baseline: ERROR, weil FEEDBACK.md in der Baseline-Kopie fehlt); der anschließende Satz verschachtelt Klammern und Zitate ungelenk. Beeinträchtigt die Nachvollziehbarkeit der Äquivalenzaussage leicht.
  - Required fix: Formulierung präzisieren („in beiden Läufen failend; FAIL-Modus nur im B6-Lauf, ERROR am Baseline-Worktree mangels unversionierter FEEDBACK.md") und Formatglitch (`F\`A…\``) glätten — reine Doku-Kosmetik, kein Blocker.

## Verification
- Change set reviewed: `db45bd7..working tree`; `docs/features/B6.md` vollständige Fassung (214 Zeilen), `docs/reviews/B6-review-1.md` unverändert, Smokes- und Full-Lauf-Artefakte in `/tmp/opencode/` gelesen.
- Git commands run by me: `git status --short`, `git diff --stat db45bd7`, `git diff --name-only db45bd7 -- scripts/`; Shell-Zugriff weiter eingeschränkt (einzelne Simple-Aufrufe erlaubt, keine Kombis).
- Checks with supplied output (Artefakte, die ich **gelesen und abgeglichen** habe): Full-Lauf-Logzeilen (1274/1240 Tests, 34 B6-Suiten `ok`), Fail-Listen (23/24 Zeilen, Äquivalenz verifiziert), Smoke-Rohdaten (`pi-events.jsonl`, `filtered.txt`, `filter-err.txt` leer, `exitinfo.txt`, leere `auth.json`/`models-store.json`, keine state-Datei), `verify.sh`-Konfig `.vibe/project.env`, `TESTER=test-agent`.
- Checks not independently run: alle Build-/Test-/Smoke-Kommandos selbst (nur gelesen); `docs/import-manifest.json`-Prüfsummen nicht unabhängig nachgerechnet (Werkzeuge reichen bis `sha256sum` nicht).
- Wichtig durchgesehene Bereiche: `docs/features/B6.md` komplett, B6-Testdateien strukturell (AK-Dokstrings, skip-frei), Produkt-Diff-Statistik gegen `db45bd7`, `scripts/`-Ordnung.
- Remaining risks (keine Befunde, nur Abschlussvoraussetzungen): Trilium-Dokumentation ist in diesem Review nicht nachprüfbar — Ticketabhaken erst mit echtem `Trilium`-Nachweis; F24-Feedback-Kontraktteile (Text/Werkzeug/Subagent) am echten Pi bleiben Attrappen-basiert mit `docs/compatibility.md`-Pflicht; das F27-Strukturproblem der unversionierten FEEDBACK.md („Nachweis:"- statt `Commit:`-Zeile) ist ein **vorbestehender** fachübergreifender Defekt und gehört in `F27`/`Fehlermeldung`, nicht in `B6`.

**Verdict: PASS**
