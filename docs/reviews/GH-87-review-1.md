# Review — GH-87 „fritzbox reconnect entfernen" (Runde 1)

> Hinweis des Koordinators: Der im Bericht genannte absolute Arbeitskopie-Pfad
> wurde beim Speichern durch eine Platzhalterangabe ersetzt (Regel „keine
> privaten Pfade in Dokumenten"). Inhalt und Urteil sind unverändert.

**Geprüfte Änderungsmenge:** Paket-Arbeitskopie auf Branch `feature/m0p/gh-87`, Start-Commit `31667f5`, HEAD unverändert; Änderungen liegen uncommittet im Arbeitsbaum. 34 veränderte/gelöschte Dateien (+116/−2715) zuzüglich der neuen `docs/features/GH-87.md`. Laufzeitstand (`TICKET-GH-87.json`) und die gitignored, unverändert vom Integrationsstand kopierte `.vibe/project.env` gelten als nicht zum Paket gehörig.

## Zusammenfassung

Die Entfernung der Altintegration ist in Code, UI, Tests und aktiver Dokumentation weitgehend vollständig und verhaltensbewahrend. Ein Befund mittlerer Schwere betrifft die Rückstandsbeseitigung im Quota-/Anmeldefehler-Guard: dort sind zwar die fritz-spezifischen Aufrufe entfernt, die Bezeichner und Ausgabe-Marker des alten Reconnect-Pfads aber noch enthalten. Damit ist das Kriterium „jegliche Referenz entfernen" nicht vollständig erfüllt und die Aussage in `docs/features/GH-87.md` nur teilweise belegt.

Befundzählung: Kritisch 0 · Hoch 0 · Mittel 1 · Niedrig 2 · Klein 1.

## Abnahmekriterien

| Kriterium | Status | Beleg |
|---|---|---|
| (1) Entfernung aller Funktionen/Referenzen in Code, UI, Doku, Tests | **Teilweise erfüllt** | `grep` über `bin/`, `bin/web/`, `scripts/`, README, aktive Doku und `tests/` ohne Treffer; Delete von Hilfsskript, CLI-Block, `/api/fritz`, UI-Karten, i18n-Keys, drei Testsuiten, F5/F18 + Screenshot und Setup-Listen bestätigt. Restbefund 1. |
| (2) Läufer-Fehlerpfad / Quota-Auth-Verhalten gemäß SPEC.md:154 | **Erfüllt** | `bin/vibe-run.sh:1837-1886`: `quota|auth` behält Stop-Semantik oder fällt per `;&` in den Wiederholungspfad; Retry-Gate bei `:1859` intakt; kein CLI-Aufruf mehr in diesem Pfad. |
| (3) Manifest-Hashes, Baseline-Inventar, Prüfskripte | **Gestützt** | Gelieferte Ausgaben: `check-import-manifest.py` → 70 Dateien, Exit 0; `verify.sh quick`/`package` → Exit 0; `tests/verify-baseline.json` unverändert. Eigene Nachführung in dieser Sitzung nicht möglich (Shell verweigert). |
| (4) Tests reduziert ohne Abschwächung der Gates | **Erfüllt** | Baseline-Datei und Konfiguration unverändert; Löschungen kohärent; keine neuen Test-Signaturen; Quota/Auth-Guard-Prüfungen inhaltlich intakt. |
| (5) Historische Ausnahmen dokumentiert und vertretbar | **Erfüllt** | Review-/Feature-Historie, Installations-Snapshot, SPEC-Invariante und entfallene Migration sind in GH-87.md begründet. |
| (6) Aussagen in `docs/features/GH-87.md` | **Teilweise erfüllt** | Diff-Zahlen und Prüfausgaben stimmen mit gelieferten Belegen überein; Aussage zur „markenunabhängigen" Sicherheitsprüfung durch Restbefund 1 nur teilweise gedeckt; Review-Link zunächst noch nicht vorhanden. |

## Befunde

**1. [Mittel, erforderlich] Reconnect-spezifische Bezeichner im generischen Sicherheits-Guard.**
Ort: `tests/unit/test_limits.py:39-46` (`RECONNECT_OUTPUT_MARKERS` und Kommentar), `:378-424` (`assert_no_router_reconnect`, `assert_continue_without_reconnect`, `test_continue_quota_does_not_trigger_a_router_reconnect`, `test_continue_auth_does_not_trigger_a_router_reconnect`). Die fritz-spezifischen Aufrufe sind entfernt, aber Ausgabe-Marker und Namen des alten Reconnect-Pfads bleiben. Folge: unvollständige_cleanup und Documentation-Mismatch. Korrektur: Marker und Bezeichner neutral fassen; die Aussage in `docs/features/GH-87.md` entsprechend präzisieren. Die Assertions selbst sind nicht geschwächt.

**2. [Niedrig, vom Koordinator übernommen] Veraltete Dateianzahl in zwei Dokumenten.**
`docs/features/README.md:234` und `docs/features/current/install-release.md:40` nennen 71 Dateien; nach Entfernung des Hilfsskripts sind es 70. Korrektur: 71 → 70 in beiden Dateien.

**3. [Niedrig / informativ, akzeptiert] Historische Manifest-Einträge.**
In `docs/import-manifest.json` (F5/F28) wurden gelöschte Pfade aus den strukturierten `dateien`-Listen entfernt, während die historische `grund`-Prosa erhalten blieb. Unter der dokumentierten Historien-Regel akzeptabel, sofern GH-87.md den Unterschied zwischen strukturierten Listen und Prosa erläutert.

**4. [Klein, optional] Review-Link.**
`docs/features/GH-87.md` verweist auf `GH-87-review-1.md`; das Dokument wird mit Ablauf dieser Runde angelegt.

## Grenzen der Prüfung

Die Review-Sitzung hatte keinen Shell-Zugriff; Prüfausgaben des Koordinators wurden als Belege behandelt, nicht unabhängig nachgeführt. Code- und Diff-Analyse erfolgten direkt an den Dateien.

Verdict: CHANGES REQUIRED
