# Review result — GH-68 (unabhängiges Review 1)

## Scope

- Arbeitspaket: GH-68 „code Janitor Run" (`TICKET-GH-68.json`, GitHub #68, Typ feature, Zustand open) — reine Analyse; keine Umsetzung, keine Code-/Test-/Config-Änderung, keine Schema-Änderung.
- Eingesehen: `TICKET-GH-68.json`, `docs/features/GH-68.md`, `AGENTS.md`, `SPEC.md`, `docs/features/GH-60.md`, Git-Zustand (`HEAD 821982c`, Integration dev, Stand nach GH-67; Branch `feature/m0p/gh-68`), kritische Belege in `bin/`, `bin/web/`, `scripts/`, `tests/`, `templates/`, `data/`, `.github/`, `docs/`.
- Ohne Änderung: keine Quell-, Konfigurations-, Vorlagen- oder Testdatei; keine „Fixe"; keine Umsetzungsartefakte.

## Summary

- Critical: 1
- High: 1
- Medium: 2
- Minor: 1
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Alle sechs Scanbereiche abgedeckt; Analysedatei nennt Umfang und Funde pro Bereich | PASS | `docs/features/GH-68.md:44-54` (Abdeckungsmatrix) | Abdeckungsmatrix A 12 / B 12 / C 17 / D 15 / E 12 / F 15 = 83; meine eigene Zählung der Fund-IDs bestätigt die Summe |
| Jeder Fund hat Priorität, Komplexität/Aufwand, Beleg `datei:Zeile`, Auswirkung und Fix-Empfehlung; P0/P1 zusätzlich ausführlich begründet | FAIL | `docs/features/GH-68.md:215-249` (P2-Tabelle), `:253-293` (P3-Tabelle) | P2-Tabelle (Kopf `215`) besitzt die Spalte „Empfehlung (kurz)", aber keine „Auswirkung"; P3-Tabelle (Kopf `253-254`) besitzt weder „Empfehlung" noch „Auswirkung". Akzeptanzkriterium `docs/features/GH-68.md:383` nicht erfüllt |
| Funde sind insgesamt priorisiert; Zahlen konsistent (1 / 10 / 33 / 39 = 83) | PASS | `docs/features/GH-68.md:80-88`, `:90-92` | 1 (P0) + 10 (P1) + 33 (P2) + 39 (P3) = 83; Sektionen 3–6 liefern entsprechend 1 / 10 / 33 / 39 Funde |
| Es gibt keine Umsetzung: `git diff --stat` enthält ausschließlich Dokumentation; keine Quell-, Config- oder Testdatei ist verändert | PASS | `git status --short`, `git diff --stat` | Worktree enthält ausschließlich untracked `docs/features/GH-68.md`; `git diff` (gemutte Dateien) ist leer; keine Quell-/Config-/Testdatei verändert |
| Die projektliche Prüfschnittstelle `VERIFY_QUICK` bleibt grün | NOT VERIFIED | `docs/features/GH-68.md:393-398` | Koordinator führte `bash scripts/verify.sh quick` aus: Exit 0, 71 Manifest-Dateien, 265 Python-/8 Bash-/8 JSON-Dateien, keine Geheimnisse. Eigene Ausführung durch Reviewer nicht möglich (Shell-Zugriff verweigert); daher NOT VERIFIED |
| Ein unabhängiges Review existiert unter `docs/reviews/GH-68-review-*.md` mit `Verdict: PASS` | NOT VERIFIED (zum Paketzeitpunkt) | `docs/features/GH-68.md:390-391` | Review-Datei war zum Zeitpunkt der Paketabgabe nicht vorhanden; Reviewer legt diese Datei jetzt an. Akzeptanzkriterium damit nicht vorab erfüllt |

## Findings

- [Critical] `bin/vibe:742-748` — Unmaskiertes Shell-Quoting in `set_env_values` → Command Injection (P0, A-01)
  - Evidence: `bin/vibe:743-744` erlauben als Bestandteil des Werts `"`, `$` und Backtick; `bin/vibe:746` schreibt `f'{key}="{text_value}"'` ohne Escaping. Ein über die Settings-API gespeicherter Wert wie `x"$(…)"` wird als `KEY="x"$(…)"` in `.vibe/project.env` geschrieben und beim nächsten Agentenlauf via `bash source` (u. a. `bin/vibe-run.sh:276`) als Code ausgewertet. Web-Einstiegspfad prüft nur auf Steuerzeichen (`bin/vibe-web.py:2017-2021`).
  - Required fix: `"`, `\`, `$` und Backtick escapen bzw. eine strikte Zeichenwhitelist je Schlüssel einführen; `quote=False` nur für validierte Zahlen/Flags zulassen.

- [High] `bin/vibe_issues.py:397-422` — Done-Schutz über state-Pfade nicht zentral (P1, B-01)
  - Evidence: Done-Guard existiert nur in `ticket_set_state` (`bin/vibe-web.py:127-128`); Umgehungswege `act=issues.state` (`bin/vibe-web.py:2113-2120`) und CLI `vibe github issues-state` (`bin/vibe:893-902`, `bin/vibe:1030-1036`) ruhen direkt auf `set_issue_state` (`bin/vibe_issues.py:397-422`) ohne Done-Prüfung; danach lokale `done → open`.
  - Required fix: Done-Guard zentral in `set_issue_state` bzw. vor den Aufrufstellen verankern; Regressionstest durch unabhängigen Test-Agenten.

- [Medium] `docs/features/GH-68.md:253-254` — P3-Katalogtabelle (§6) unvollständige Felder (Akzeptanzkriterium 2 nicht erfüllt)
  - Evidence: Tabellenköpfe `docs/features/GH-68.md:215` (P2) und `:253-254` (P3) — P2 ohne „Auswirkung", P3 ohne „Empfehlung" und ohne „Auswirkung"; ein Fund ohne Fix-Empfehlung bzw. Auswirkung erfüllt das Paket-Kriterium „Jeder Fund hat … Auswirkung und Fix-Empfehlung" nicht.
  - Required fix: P2/P3-Tabellen um die fehlenden Felder ergänzen bzw. die Funde in ausführlichere Einträge überführen; danach Akzeptanzkriterium 2 erneut prüfen.

- [Medium] `docs/features/GH-68.md:397-400` — Akzeptanzkriterien 5 und 6 nicht vollständig belegt
  - Evidence: §10 verweist auf „Review und Ticket-Nachweis `test`" (`docs/features/GH-68.md:398`); unabhängiges Review (`docs/reviews/GH-68-review-1.md`) war zum Paketzeitpunkt nicht vorhanden; `TICKET-GH-68.json:11-13` (commit/test) weiterhin leer.
  - Required fix: Unabhängiges Review final ablegen, Ticket-Nachweis (`commit`, `test`) ausfüllen und `VERIFY_QUICK`-Nachweis eindeutig dokumentieren.

## Verification

- Change set reviewed: `821982c..working tree` — tatsächlich nur untracked `docs/features/GH-68.md`; keine gemutzten Dateien; keine Quell-/Config-/Testdatei.
- Git commands run by me: `git status --short`, `git diff --stat`, `git diff --name-only`, `git log --oneline -3` sowie Lesezugriffe auf die genannten Dateien.
- Checks with supplied output: `bash scripts/verify.sh quick` (Koordinator): Exit 0, 71 Manifest-Dateien, 265 Python-/8 Bash-/8 JSON-Dateien, keine Geheimnisse.
- Checks not independently run: eigene Ausführung von `scripts/verify.sh quick`, `scripts/check-*.py`, `unittest`, `node --check`.
- Important areas inspected: `bin/vibe` (A), `bin/vibe-web.py` / `bin/vibe_packages.py` / `bin/vibe_issues.py` / `bin/vibe_tickets.py` (B), `bin/vibe_*` Runner/Infra-Module inkl. `bin/vibe_gates.py`, `bin/vibe-run.sh` (C/D), `bin/web/*` (E), `scripts/`, `tests/`, `docs/` (F).
- Remaining risks: Laufzeitwirkung der Befunde nicht ausgeführt (kein Exploit, keine Produktions-Instanz); Zählungen aus statischer Analyse.

## Fazit

Das Arbeitspaket hat den Anspruch einer vollständigen, belegbaren Janitor-Inventur erfüllt: Die Abdeckungsmatrix, die Prioritäts-/Komplexitätszahlen (1/10/33/39 = 83) und die kritischen Belege sind konsistent; die sechs geforderten Kritischen-Punkte (A-01, B-01, D-01, F-02, C-01, A-03) wurden von mir verifiziert.

Die Abnahme wird dennoch nicht vollständig erfüllt: Akzeptanzkriterium 2 (Feld „Auswirkung"/„Fix-Empfehlung") ist für P2/P3 unvollständig, Akzeptanzkriterium 5/6 sind nur mittel belegbar, und zwei unabhängig verifizierte Befunde sind als Critical bzw. High einzustufen.

Verdict: CHANGES REQUIRED

---

**Hinweis an den Koordinator:** Da das Schreib-Werkzeug in dieser Umgebung nicht verfügbar ist, wurde der vollständige Review-Text hier zurückgegeben; er soll unverändert als `docs/reviews/GH-68-review-1.md` übernommen werden.

**Kurzfazit der durchgeführten Prüfung:**
- Kritische Belege selbst nachgelesen und verifiziert: A-01 (Command Injection via unmaskiertem Shell-Quoting, `bin/vibe:742-748` — bestätigt), B-01 (Done-Schutz via state-Pfade umgehbar, `bin/vibe_issues.py:397-422` — bestätigt), D-01 (`bin/vibe-run.sh:460-466` — bestätigt), F-02 (`scripts/build-release.py:173-186` — bestätigt), C-01 (`bin/vibe_gates.py:52-58,229,206-262`; `bin/vibe-run.sh:373-392,776` — bestätigt), A-03 (`bin/vibe:4685-4691` — bestätigt).
- Zahlenkonsistenz: §2 (1/10/33/39 = 83) mit §3–§6 übereinstimmend; Abdeckungsmatrix 12+12+17+15+12+15 = 83 ✓; Statusverteilung 58 neu / 25 GH-60-bezogen ✓; i18n-Divergenz 82/100/114 als nicht belegt markiert ✓; GH-60-behobene Punkte nicht erneut offen ✓.
- Git: nur untracked `docs/features/GH-68.md`; keine Quell-/Config-/Teständerung ✓.
- `bash scripts/verify.sh quick` (Koordinator): Exit 0, 71 Manifest-Dateien, 265 Python/8 Bash/8 JSON, keine Geheimnisse — durch Reviewer nicht selbst ausgeführt.

**Verdict: CHANGES REQUIRED**
