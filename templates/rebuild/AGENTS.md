# Projekt: {{NAME}} (Rebuild)

- `SPEC.md` ist maßgeblich. Keine Rückfragen: Lücken nach „Decisions Locked“ entscheiden.
- Ziel: eine bestehende Anwendung analysieren und plattformübergreifend neu erstellen.
  Die fachliche Funktionsweise wird **1:1** übernommen. Technische Abweichungen sind
  erlaubt, müssen aber begründet und in `docs/parity.md` nachgewiesen werden.
- Speicherstände sind ein Vertrag: Originalformate müssen gelesen **und** geschrieben
  werden. Unbekannte Felder bleiben erhalten. Keine Migration ohne Sicherung und
  Roundtrip-Test mit echten Beispieldateien. Ein Test mit Attrappen genügt nicht.
- Rechte klären: Nur Anwendungen analysieren und neu erstellen, für die eine
  Berechtigung vorliegt. Fremde Kopierschutz- oder Lizenzmechanismen nicht umgehen.
- Umgebung: Distrobox `android-dev`. Werkzeuge prüfen mit
  `python3 scripts/rebuild-env.py --check`; Installationsplan mit
  `python3 scripts/rebuild-env.py --plan`; Einrichtung nur nach ausdrücklicher
  Bestätigung mit `python3 scripts/rebuild-env.py --setup --yes`.
  Das Profil fordert standardmäßig die Gruppen `core` und `analyse`
  (`REBUILD_REQUIRED_GROUPS` in `.vibe/project.env`). Ghidra, Packaging und CI
  sind optionale Gruppen, bis die Anwendung sie tatsächlich braucht.
- Werkzeuge und ihr Zweck:
  - Discovery: `file`, `strings`, `objdump`, `readelf`, Installer und Dateiablage.
  - Verhalten: Wine, Screenshots, Datei-/Registry-Beobachtung, `strace`, `ltrace`, `gdb`.
  - Reverse Engineering: Ghidra headless (`analyzeHeadless`), nur wenn Quellen fehlen.
  - Paketierung: `linuxdeploy`, `appimagetool`, `patchelf`; Zielsysteme und Formate
    stehen in `SPEC.md`.
  - CI/Test: reproduzierbare Tests auf mehreren Distributionen, Screenshot-Vergleich.
- Arbeitsweise (Orchestrator koordiniert, ein Agent je Phase):
  1. **Discovery**: Bestand, Plattformen, Abhängigkeiten, Datei- und Speicherformate
     erfassen. Ergebnis: `docs/reverse-engineering.md`.
  2. **Reverse Engineering**: nur bei fehlenden Quellen; Beobachtungen mit Werkzeug,
     Eingabe und Ausgabe belegen. Ergebnis: `docs/reverse-engineering.md`.
  3. **Spezifikation**: fachliche Funktionen, Randfälle und Speichervertrag in
     `SPEC.md`; Paritätsmatrix in `docs/parity.md` anlegen.
  4. **Architektur**: Plattformgrenzen kapseln; gemeinsame Kernlogik, austauschbare
     Plattformadapter und kompatible Dateiformate festlegen.
  5. **Implementierung**: kleinste zusammenhängende Änderung, Tests zuerst, keine
     unbegründete Funktionserweiterung gegenüber dem Original.
  6. **Verifikation/Parität**: Original und Neuversion mit denselben Eingaben
     vergleichen; jede Zeile der Paritätsmatrix erhält einen echten Nachweis.
  7. **Packaging**: startfähige Artefakte je Zielsystem; Installation, Update und
     Deinstallation ohne Datenverlust prüfen.
  8. **CI/Test**: Matrix aus Distributionen und Speicherformat-Versionen; rote Läufe
     werden nicht als bestanden erklärt.
- Projektagenten liegen unter `.opencode/agents/`:
  `rebuild-orchestrator`, `rebuild-discovery`, `rebuild-reverse`,
  `rebuild-spec`, `rebuild-architecture`, `rebuild-implementation`,
  `rebuild-parity`, `rebuild-packaging`, `rebuild-ci`.
- Nachweise: Paritätsmatrix, Speicherfixtures, Screenshots, CI-Logs. Eine Aussage
  „funktioniert“ gilt nur mit ausgeführtem Befehl und beobachtetem Ergebnis.
- Umgebung ist FUSE/NTFS: Skripte mit `bash datei.sh` starten, Rechte nicht als
  wirksam voraussetzen. Shell-Befehle laufen höchstens etwa 2 Minuten; Längeres im
  Hintergrund mit Log starten und das Log abfragen.
- Nach jedem Arbeitspaket: Tests grün, `git commit`.

<!-- vibe:general-rules -->
## Projektordner sauber halten

- Im Projektordner nur Quellcode, Konfiguration, Tests und die vereinbarten Nachweise ablegen.
- Temporäre Dateien, Protokolle, Sicherungen und Arbeitskopien nach Abschluss des Arbeitspakets entfernen und nicht committen.
- Laufzeitdaten, persönliche Konfiguration und Geheimnisse gehören nicht ins Repository.

## Ordnung im Git halten

- Änderungen auf einem Feature-Branch umsetzen, nicht direkt auf main, master oder einem geschützten Branch.
- Jedes abgeschlossene Arbeitspaket als zusammenhängenden Commit sichern; keine Zwischenstände oder fremden Änderungen mitcommitten.
- Vor jedem Commit `git status` und den relevanten Diff prüfen und ausschließlich Dateien des eigenen Arbeitspakets stagen.
- Keine temporären Dateien, Protokolle, Build-Artefakte, Arbeitskopien oder Screenshots ohne Nachweiswert committen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben, stashen oder mitcommitten.
- Keine Historie umschreiben, keine Force-Pushes und kein Push ohne ausdrückliche Freigabe.
<!-- /vibe:general-rules -->
