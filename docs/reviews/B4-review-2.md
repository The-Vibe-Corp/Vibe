# Review B4 — Runde 2

Datum: 2026-11-08
Reviewer: unabhängiger Code-Reviewer (`code-reviewer`, Model `GLM-5.3-Flash Free`; keine Delegation)
Geprüfte Commits: Runde-2-Differenz `c139f84..d9ac8f1` vollständig, totaler Change-Set `11817c3..d9ac8f1`; HEAD = `d9ac8f1`, Arbeitskopie sauber (`git status --short` leer). Geprüfte Dateien: `bin/vibe_harness.py` (+7/−3), `docs/import-manifest.json` (+4/−3), `docs/features/B4.md` (+7/−4), `docs/reviews/B4-review-1.md` (neu, 66 Zeilen) — Runde-1-Diff `11817c3..c139f84` weiterhin bestätigt. Keine Änderungen an `bin/vibe_sandbox.py` (seit `c139f84` unverändert, die Runde-1-Zeilenverweise bleiben gültig), an Tests, compatibility.md, vibe-run.sh oder Prüfskripten.

## Ergebnis

Verdict: **PASS**

- Critical: 0
- High: 0
- Medium: 0
- Minor: 1 (neu, nicht blockierend — Archivierungstreue)

## Status der Runde-1-Befunde

### Medium 1 — `bin/vibe_harness.py:325–327` falscher `--no-session`-Kommentar: BEHOBEN

- Eigenständig gelesen (bin/vibe_harness.py:325–331): Der Kommentar nennt jetzt die korrekten Fakten (Pi schreibt/liest sein Verzeichnis `~/.pi/agent` auch mit `--no-session`, inkl. `trust.json.lock`; Sandbox stellt über `PI_CODING_AGENT_DIR` den beschreibbaren Ordner). Der neue Text ist mit der korrigierten `docs/compatibility.md:45–56` und `bin/vibe_sandbox.py:13–23` konsistent.
- Diff bestätigt: reine Kommentaränderung — die funktionalen Zeilen (argv-Bau :332 ff.) sind unverändert; kein Verhaltensdelta, damit bleiben alle Runde-1-AK-, Log- und Folgerungs-Bestätigungen in Kraft.
- Manifest: `docs/import-manifest.json` — sha256/bytes für `bin/vibe_harness.py` aktualisiert (Bytes 20911), Änderungseintrag B4 nennt beide Dateien (`bin/vibe_sandbox.py`, `bin/vibe_harness.py`). Die Hash-Übereinstimmung beruht auf dem mitgelieferten `check-import-manifest.py`-OK/`verify.sh quick`-Exit 0 (nicht selbst ausgeführt — Muster wie in Runde 1, dort artefaktisch durch b4-verify-full.log:5 gestützt).

### Minor 1 — Trilium-Referenz in `docs/features/B4.md`: BEHOBEN (Formulierung)

- Eigenständig gelesen (docs/features/B4.md:172–178): Die Sektion formuliert jetzt „Trilium folgt nach Review-PASS (siehe FEEDBACK-Eintrag B4)“ — keine Behauptung einer bereits existierenden Notiz mehr; der FEEDBACK-Eintrag B4 (Zeilen 313 ff.) ist weiterhin ohne Nachweiszeilen, unverändert. Das entspricht der vorgeschlagenen B5-Vorbild-Lösung. Der tatsächliche Trilium-Eintrag mit Notiz-ID bleibt verbindlicher Post-PASS-/pre-Finalcommit-Schritt (wie in Runde 1 vermerkt; Abschlussbedingung, kein neuer Befund).

### Minor 2 — Rotphasen-/Pi-Lauf-Nachweise ohne Artefakte: als Prozesshinweis angenommen, nicht blockierend

- Die generisch genannte Prozessverbesserung ist im Runde-2-Diff bislang nicht im Repo dokumentiert (kein Absatz in B4.md/doku dazu). Empfehlung: vor dem Abschluss-Commit eine knappe Zeile (B4.md „Tests“ oder Projektregeln) hinterlegen, dass künftige Rotphasen-/Integration-Nachweise als Protokolldateien unter `/tmp/opencode/…` abgelegt werden. Nicht blockierend, keine Zahlenänderung.

## AK-Bestätigung (Runde 1 gilt fort)

- AK1–AK5 unverändert PASS: Implementierung im unveränderten `bin/vibe_sandbox.py:536–537, 580–593, 616–621`; Testorte wie in `docs/reviews/B4-review-1.md` (tests/unit/test_b4_pi_agent_dir.py:165, :191, :218, :263, :291, :322); Logeinstiege b4-verify-full.log:5–7/:103–109/:1800–1804, b4-baseline-verify.log:1830–1835, FAIL-Listen-Teilmengenabgleich — alles aus der Runde 1, Dateien seit `c139f84` nicht geändert.
- Mitgeliefert und kritisch übernommen (nicht selbst ausgeführt): der Nachkorrektur-Testlauf — `unittest tests.unit.test_ap04_harness tests.unit.test_ap04_setup_harness` → `Ran 27 tests, FAILED (failures=1)` mit ausschließlich `test_dry_run_explains_pi_and_its_install_command`; dieser Befund ist eigenständig in den Runde-1-Artefakten belegt (`b4-baseline-fails.txt` Zeile 8 und `b4-full-fails.txt` Zeile 6 — echter Umgebungs-Vorbefund, keine B4-Regression), und sämtliche B4-Tests in demselben Batch (33 gesamt) weiterhin OK; `verify.sh quick` Exit 0.

## Befunde

### Minor 1 (neu) — `docs/reviews/B4-review-1.md`: Archivierung nicht 1:1 zur abgegebenen Runde-1-Antwort

- Evidence: Abgleich der abgelegten Datei mit meinem (im Protokoll vorliegenden) Runde-1-Text zeigt kleinere Normalisierungen statt 1:1-Kopie — z. B. :34 („…gilt: … funktionalen Befehlszeile bleibt unverändert“ statt Originalformulierung), :51 („Temporärordner (`.b4-*`) unter `REPO` werden per Cleanup entfernt“ statt „werden normalisiert weggeräumt“) und leichte Umformulierungen im Abschnitt „Restrisken“. Verdict, Befundanzahlen, Fundstellen, Nachweise und Maßnahmen sind inhaltlich vollständig identisch; keinerlei sachliche Änderung. Dennoch verstößt die glättende Übernahme gegen die Ablage-Regel „Reviewantwort unverändert speichern“ (AGENTS Arbeitsablauf Schritt 10).
- Required fix: Nicht blockierend für dieses Arbeitspaket. Künftig die Reviewantwort exakt archivieren (unmittelbar nach dem Schreiben `git diff` gegen die abgegebene Fassung prüfen); Glättungen auch bei Übertragungsartefakten vermeiden bzw. als eigene Anmerkung ausweisen. Optional vor dem Abschlusscommit: bestehende Differenzformulierungen so lassen, da sachidentisch.

## Freibleibende Folgerungen

- Alle Runde-1-Folgerungen bleiben bestehen: Der Kompromiss settings.json/models-store.json nicht binden (dokumentiert in compatibility.md:62–69) inkl. Präzisionshinweis „vibe setzt `--model` ausdrücklich“ nur mit einem festgelegten Modell (bin/vibe-run.sh:238); bewusster setenv-Override (bin/vibe_sandbox.py:576–584), Argumentreihenfolge in bwrap_argv() ohne Wechselwirkung mit /tmp-Remount, `.vibe`-ro-bind, `--dev-bind-try` oder opencode-auth-ro-bind; Testqualität der 6 B4-Tests (B4Fixture, Aufräumbeweis, Digest-Attribution, festes FAIL ohne bwrap).
- Offen zum Abschluss (bekannt): Trilium-Eintrag mit Notiz-ID in B4.md und FEEDBACK.md schreiben (Minor 1, Runde 1), FEEDBACK-Eintrag B4 abhaken, dann Abschluss-Commit — gemäß B5-Vorbild.
- Checks von mir nur gelesen abgeglichen (keine eigenständige Ausführung): unittest-Batch nach Korrektur und `verify.sh quick` sind mitgeliefert; die Runde-1-verify-Protokolle (b4-verify-full.log / b4-baseline-verify.log / FAIL-Listen, /tmp/opencode/vibe-sandbox/vibe-B4-a98BaT-174aaca080/tmp/) wurden erneut gelesen und unverändert gültig gefunden.

## Verify-Abschnitt (des Reviewers)

- Git-Kommandos eigenständig: `git status --short`, `git log --oneline -4`, `git diff c139f84..d9ac8f1` (vollständig) und `--numstat`, Runde-1-Diff erneut angesehen.
- Wichtigste gelesene Bereiche: aktueller Harness-Kommentar (bin/vibe_harness.py:318–338), Manifest-Änderungseinträge, docs/features/B4.md:100–110 und :168–183, docs/reviews/B4-review-1.md (komplett, Fidelity-Abgleich), FEEDBACK.md B4-Abschnitt, die Runde-1-Verify-Logeinstiege und FAIL-Listen.
- Nicht unabhängig ausgeführt: alle Tests/Verify-Läufe (regelkonforme Begrenzung), Manifest-Hashberechnung (nur mitgeliefertes quick-OK).
