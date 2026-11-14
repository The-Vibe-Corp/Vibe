# Review F26 — Runde 2

- Arbeitspaket: F26 Opencode integration
- Datum: 2026-11-10
- Reviewer: code-reviewer (unabhängiger Subagent, read-only; Folgesitzung zu Runde 1)
- Basis: Ausgangscommit 9210a38; vollständiger Diff /dev/shm/f26-review2.diff (1055 Zeilen, inkl. neuer Datei docs/features/F26.md)

## Zusammenfassung

- Critical: 0, High: 0, Medium: 1, Minor: 0
- Verdict: CHANGES REQUIRED
- Bewertung Runde-1-Befunde: M1 und M2 vollständig und sauber behoben; M3 mit einem verbleibenden Dokumentationswiderspruch.

## Akzeptanzkriterien (Auswertung des Reviewers)

| Kriterium | Status |
| --- | --- |
| Neuere lesbare opencode-Versionen blockieren nicht mehr (Serverstart, Modelllisting, MCP-Schreiben mit Fallback-Profil) | PASS |
| Fallback-Auswahl: höchste geprüfte Version ≤ erkannt, sonst ältestes Profil (M1) | PASS (inkl. neuer Test `test_version_below_all_checked_profiles_is_assumed_with_the_oldest_profile`) |
| Annahme wird nie stillschweigend getroffen (M2) | FAIL — siehe Befund: `doctor_checks` bewertet eine assumed-Version über `version.supported` als bestanden; `cmd_doctor` gibt den Hinweis nur bei `not ok` aus (`bin/vibe:4598-4599, 4631`): für 2.2.6 erscheint ein glattes OK ohne jede Warnung |
| Fail-closed ohne lesbare Version | PASS |
| Flexibilität für pi-Alternative ohne Eingriff | PASS |
| Manifest-Sync mit Begründung (bin/* deckt alle 4 Programmdateien ab) | PASS |
| Dokumentation konsistent mit Implementierung (M3) | FAIL — zwei Widersprüche, siehe Befund |

## Befunde

1. [Medium] `docs/compatibility.md:103-105, 319-322, 335-338` — Dokumentation behauptet Warnpfade, die die Implementierung nicht hat: (1) Doctor zeigt bei assumed glatt OK ohne Hinweis (`bin/vibe:4598-4599, 4631`); vor F26 zeigte Doctor dieselbe Situation als FEHL mit Meldung. (2) Die Profiltabelle (`docs/compatibility.md:130`) sagt weiterhin „Profil nur für leere Dateien der geprüften Version", während Implementierung und Reihenfolge-Liste Punkt 5 der selben Datei das Fallback-Profil auch bei assumed verwenden. Erforderlich: entweder Richtung Code (Doctor-Hinweis bei nicht exakt geprüfter Version, eigener Warneintrag; mit Testfall für Doctor bei assumed) oder Richtung Doku (Doctor aus der Liste streichen); zwingend zusätzlich Tabellenzeile MCP-Schema aktualisieren; danach die behaupteten Meldewege gegen den Code abgleichen.

## Verifikation

- Change set reviewed: `9210a38..working tree`; diff-Stand stimmte an allen geprüften Stellen mit der Arbeitskopie überein.
- Wichtige geprüfte Bereiche: Adapter (probe, _closest_profile, VersionInfo, require_supported, list_models, detect_mcp_layout), bin/vibe (agent_version/agent_version_warning, cmd_server, doctor, agent_write), bin/vibe_mcp (load/_require_known_layout/save), bin/vibe_harness, beide Testdateien (inkl. aller Hunks; keine leeren Assertions, keine Skips, Fail-closed erhalten), docs/compatibility.md, Manifest, FEEDBACK.md:357-358, SPEC.md, TICKETS.md.
- Gemeldete (nicht vom Reviewer ausgeführte) Checks: Rotphase der drei Fixfälle (3 failures) und danach Grün durch den Test-Agenten (54 + 28 Tests OK, Wiederholungslauf OK); quick Exit 0; full 1291 Tests/7 Failures identisch zur Baseline 9210a38; Browser 106/1 vorbestehend; Manifest OK.
- Hinweis des Reviewers: Shell-Befehle waren durch Berechtigungen gesperrt; Git-Prüfung erfolgte über den gelieferten Diff plus direkte Arbeitsbaumlektüre.

## Verdict

CHANGES REQUIRED — 1 Medium-Befund (Doctor-Widerspruch); M1 und M2 vollständig behoben.
