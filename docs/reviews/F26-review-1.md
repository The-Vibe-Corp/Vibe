# Review F26 — Runde 1

- Arbeitspaket: F26 Opencode integration
- Datum: 2026-11-10
- Reviewer: code-reviewer (unabhängiger Subagent, read-only)
- Basis: Ausgangscommit 9210a38, Arbeitskopie vibe-F26-IwrxSj, Stand uncommitted
- Geprüfter Umfang: vollständiger Diff 9210a38..Arbeitsbaum (543 Zeilen: bin/vibe, bin/vibe_opencode.py, docs/import-manifest.json, tests/unit/test_opencode_adapter.py, tests/unit/test_agent_management.py) plus Volllektüre der Arbeitsbaumdateien

## Zusammenfassung

- Critical: 0, High: 0, Medium: 3, Minor: 0
- Verdict: CHANGES REQUIRED

## Akzeptanzkriterien (Auswertung des Reviewers)

| Kriterium | Status |
| --- | --- |
| Neue lesbare opencode-Version blockiert nicht mehr (Status `assumed`, bestes geprüftes Profil) | PASS |
| Fail-closed ohne lesbare Version (missing/timeout/error/unlesbar) | PASS |
| Kein stillschweigendes Behandeln: alle Pfade melden die ungeprüfte Version | FAIL (siehe Befund 2) |
| `VersionInfo.supported` gilt für supported+assumed; `checked` nur exakt geprüft | PASS |
| Manifest aktualisiert (Prüfsummen, F26-Begründung) | PASS |
| Tests durch unabhängigen Test-Agenten, Rotphase belegt | NOT VERIFIED (nur gemeldet; TESTER-Konfiguration vorhanden) |
| `verify.sh quick`/`full` grün, keine F26-Regression | NOT VERIFIED (nur gemeldete Ausgaben; Reviewer darf keine Tests ausführen) |
| Dokumentation (docs/compatibility.md, docs/features/F26.md, Trilium) | FAIL (siehe Befund 3; laut Auftrag bewusst nach dem Review vorgesehen) |

## Befunde

1. [Medium] `bin/vibe_opencode.py:76-77` — `_closest_profile` verletzt die dokumentierte Auswahlregel im Fall „unter allen geprüften Versionen": Code liefert dort die **neueste** geprüfte Version (`(at_or_below or candidates)[-1][1]`), Docstring und Manifesttext schreiben „das älteste Profil". Mit einem Profil unbeobachtbar; mit einem zweiten Profil erhält eine ältere Version still das neueste Profil. Erforderlich: Regel angleichen (Code auf ältestes Profil oder Doku auf neuestes) plus Test für den Fall mit mindestens zwei Profilen (über den Test-Agenten).
2. [Medium] `bin/vibe:4439-4456` und `bin/vibe_mcp.py:198-199` — „assumed" wird im Serverstart und MCP-Speichern stillschweigend behandelt: `cmd_server("start")` behandelt nur `CompatibilityError`; `vibe_mcp.load` verwirft die von `detect_mcp_layout` erzeugte Kennzeichnungsmeldung. Vor F26 waren diese Pfade fail-closed mit namentlicher Meldung. Erforderlich: vorhandene Adaptermeldungen an den Nutzer weiterreichen (Hinweis vor dem Serverstart; Warnung in der MCP-Erfolgsmeldung), mit fachlicher Prüfung.
3. [Medium] `docs/compatibility.md:150-152, 311-312, 322` — Dokumentation widerspricht dem neuen Verhalten („Leere Konfiguration und ungeprüfte Version → Schema unbekannt", „Serverstart und versionabhängige MCP-Schreibvorgänge werden … abgelehnt", „Neue opencode-Versionen werden nicht automatisch als kompatibel behandelt"); veralteter Kommentar in `bin/vibe_mcp.py:194-197`; `docs/features/F26.md` fehlt; Trilium steht aus. Erfordernis: im selben Arbeitspaket nachholen.

## Verifikation

- Change set reviewed: `9210a38..working tree` (5 Dateien, keine untracked Dateien); Git-Befehle des Reviewers: `git status --short`, `git diff 9210a38 --stat`, `git diff 9210a38`.
- Wichtige geprüfte Bereiche: Adapter vollständig; Agentenverwaltungs- und Doctor-Warnpfade; `vibe_mcp` load/save; `vibe_harness`-Weiterleitung; beide Testdateien inkl. aller Diff-Hunks (keine leeren Assertions, keine Skips; verlagerte Refusal-Tests behalten die Meldungsassertion „2.1.4").
- Gemeldete (nicht vom Reviewer ausgeführte) Checks: realer Smoke opencode 2.2.6 → assumed; quick Exit 0; full 1288 Tests/7 Failures identisch zur Baseline; Browser 106/1 vorbestehend; Manifest-Check OK.

## Verdict

CHANGES REQUIRED — 3 Medium-Befunde (siehe oben), keine Critical/High.
