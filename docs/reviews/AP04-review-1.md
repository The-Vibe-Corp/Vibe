# Review AP04 — Austauschbares Coding-Harness und Pi (Runde 1)

- Datum: 2026-11-07
- Prüfer: unabhängiger `code-reviewer` (read-only)
- Arbeitsbaum: `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/data/opencode/worktree/2c4a62/ap04-harness`
- Branch: `feature/ap04-harness-alternatives`
- Ausgangsstand: `3be48de` (AP02: Nachweis)
- Ergebnis: **CHANGES REQUIRED** (0 Critical, 0 High, 1 Medium, 3 Minor)

## Zusammenfassung

Alle fachlichen Akzeptanzkriterien sind umgesetzt: Harness-Abstraktion,
Auswahl im Setup und in der Oberfläche, Wechsel, opencode als Default, Pi als
startbarer Alternativ-Harness sowie verständliche Diagnose. Die Umsetzung ist
sicher (Argumentlisten statt Shell, Validierung, kein stiller Fallback) und
die Pi-Grenzen sind ehrlich dokumentiert.

## Befunde

### [Medium] Falsche Testherkunft in der Dokumentation

- Datei: `docs/features/AP04.md:107-109` (Stand vor der Korrektur)
- Evidenz: Die Doku behauptete, die Tests stammten aus dem unabhängigen
  Test-Agenten. Das Laufprotokoll belegt, dass der Umsetzungsagent die drei
  Testdateien selbst angelegt hat, weil `subagent` mit `permission.rejected`
  verweigert wurde.
- Korrektur (Runde 1, umgesetzt): Die Doku weist die Herkunft jetzt offen als
  nicht unabhängig aus. Der Test-Agent-Nachweis bleibt eine dokumentierte
  Umgebungsgrenze; die fachliche Abnahme stützt sich auf die beobachtete
  Rot-Phase und die grünen Tests.

### [Minor] Doppelte Harness-Prüfung im Läufer

- Datei: `bin/vibe-run.sh:83-86`
- Bewertung: keine Funktionsstörung; als Sicherheitsnetz akzeptiert.

### [Minor] Parser für `pi --list-models`

- Datei: `bin/vibe_harness.py:337-358`
- Bewertung: `docs/compatibility.md` nennt bereits beide akzeptierten Formen.
  Keine Änderung erforderlich.

### [Minor] Node-Prüfung im Doctor nur für Pi

- Datei: `bin/vibe:3666-3684`
- Bewertung: bewusst asymmetrisch, da Pi Node.js zwingend im PATH benötigt.
  Keine Änderung erforderlich.

## Geprüfte Bereiche

`bin/vibe_harness.py` (Registry, Auswahl, Diagnose, Setup-Plan, Agentenprompt,
Startbefehl, Modellliste, CLI), `bin/vibe`, `bin/vibe-run.sh`,
`bin/vibe-web.py`, `bin/web/app.js`, `scripts/setup-vibe.py`,
`docs/compatibility.md`, `docs/features/AP04.md` und die Testdateien.

## Prüfungen

- `bash scripts/verify.sh quick` → Exit 0 (Manifest, Syntax, Geheimnisse).
- `python3 -m unittest tests.unit.test_ap04_harness tests.unit.test_ap04_setup_harness` → 27 Tests OK.
- `python3 -m unittest tests.browser.test_ap04_harness_ui` → 2 Tests OK.
- `env -u SANDBOX -u SANDBOX_TOOLS bash scripts/verify.sh full` → 902 Unit-
  und 60 Browsertests; 1 Fehlschlag
  (`test_real_sandbox_allows_questions_but_not_the_web_token`), der auf
  `3be48de` identisch auftritt und ein Artefakt des Worktree-Ortes unter
  `/tmp/opencode` ist. Keine AP04-Regression.

## Merge-Empfehlung

**Merge nach Korrektur der falschen Testherkunft zulässig.** Die
verbleibenden Minor-Befunde sind dokumentierte Wartbarkeitshinweise.
