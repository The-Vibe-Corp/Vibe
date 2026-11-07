# Review result — Runde 2

> **Provenienz-Hinweis:** Die Rohausgabe des Reviewers aus Runde 2 konnte nach
> einem Abbruch und der Fortsetzung dieser Sitzung nicht byte-genau gesichert
> werden; sie war im Sitzungszustand nur als Zusammenfassung vorhanden. Der
> folgende Inhalt gibt diese Zusammenfassung wieder und ist **nicht wörtlich**.
> Die Antworten der Runden 1 und 3 sind unverändert gespeichert.

## Verdict

**CHANGES REQUIRED**

## Summary (aus dem Sitzungsprotokoll)

- Critical: 0
- High: 1
- Medium: 0
- Minor: 2

## Findings

- [High] Entwurfsordner ist im Sandbox-Lauf read-only
  - Evidence (laut Protokoll): Der Sandbox-Lauf bindet `.vibe` read-only.
    `start_agent()` schreibt den Entwurf nach `.vibe/guide/<schritt>.md`;
    damit konnte der Agent bei `SANDBOX=on` den Entwurf nicht anlegen.
  - Required fix (laut Protokoll): `.vibe/guide` nach dem Read-only-Bind
    gezielt schreibbar binden, ohne `.vibe/project.env` und
    `.vibe/permissions.json` zu öffnen, und dies mit einem echten
    Sandbox-Lauf testen.

- [Minor] Veralteter Manifest-Text in `docs/features/F9.md`
  - Evidence (laut Protokoll): Die Dokumentation nannte noch einen älteren
    Teststand bzw. ältere Prüfsummen.
  - Required fix: Testzahlen und Prüfsummen gegen den Endstand abgleichen.

- [Minor] Fehlende positive Sandbox-Tests
  - Evidence (laut Protokoll): Es fehlte ein Test, der bei eingeschalteter
    Sandbox den tatsächlichen Schreibzugriff auf den Entwurf belegt.
  - Required fix: Positiven bwrap-Test für den Entwurfspfad ergänzen.

## Behandlung

- `.vibe/guide` wird in `_sandbox_command()` nach dem Read-only-Bind von
  `.vibe` als einziges zusätzliches Verzeichnis schreibbar gebunden.
- `test_sandboxed_command_can_write_the_draft_but_not_the_configuration`
  führt einen echten bwrap-Lauf aus und prüft Entwurf schreibbar sowie
  `.vibe/project.env` unverändert read-only.
- Testzahlen und Prüfsummen in `docs/features/F9.md` wurden auf den Endstand
  gebracht (318 Unit-Tests, 17 Browser-Tests, `verify.sh full` Exit 0).
