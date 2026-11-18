# Projekt: {{NAME}} (Rebuild)

- `SPEC.md` ist maßgeblich. Keine Rückfragen: Lücken nach „Decisions Locked“ entscheiden.
- Ziel: eine bestehende Anwendung analysieren und plattformübergreifend neu erstellen.
  Die fachliche Funktionsweise wird **1:1** übernommen. Technische Abweichungen sind
  erlaubt, müssen aber begründet und in `docs/parity.md` nachgewiesen werden.
- Speicherstände sind ein kompromisslos: Originalformate müssen gelesen **und** geschrieben
  werden. Unbekannte Felder bleiben erhalten. Keine Migration ohne Sicherung und
  Roundtrip-Test mit echten Beispieldateien. Ein Test mit Attrappen genügt nicht.
- Rechte klären: Nur Anwendungen analysieren und neu erstellen, für die eine
  Berechtigung vorliegt. Fremde Kopierschutz- oder Lizenzmechanismen nicht umgehen.
- Umgebung: Werkzeuge prüfen mit
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

# Projekt: {{NAME}}
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL).
- Nach jedem Arbeitspaket: Tests grün, git commit.

<!-- vibe:general-rules -->
## Projektordner sauber halten

- Im Projektordner nur Quellcode, Konfiguration, Tests und die vereinbarten Nachweise ablegen.
- Temporäre Dateien, Protokolle, Sicherungen und Arbeitskopien nach Abschluss des Arbeitspakets entfernen und nicht committen.
- Laufzeitdaten, persönliche Konfiguration und Geheimnisse gehören nicht ins Repository.

## Ordnung im Git halten

- Änderungen auf einem Feature-Branch umsetzen, nicht direkt auf main, master oder einem geschützten Branch.
- Jedes abgeschlossene Arbeitspaket als zusammenhängenden Commit sichern; keine Zwischenstände oder fremden Änderungen mitcommitten.
- Commit-Meldungen sind für Menschen verständlich, auf das Wesentliche reduziert und erläutern das Warum der Änderung.
- Vor jedem Commit `git status` und den relevanten Diff prüfen und ausschließlich Dateien des eigenen Arbeitspakets stagen.
- Keine temporären Dateien, Protokolle, Build-Artefakte, Arbeitskopien oder Screenshots ohne Nachweiswert committen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben, stashen oder mitcommitten.
- Keine Historie umschreiben, keine Force-Pushes und kein Push ohne ausdrückliche Freigabe.

## Effizienz der Prüfungen (verbindlich)

- Für betroffene Testmodule gilt während der Bearbeitung: gezielter unittest-Aufruf und die Paketprüfung VERIFY_PACKAGE, nicht die gesamte Suite.
- Die vollständige Prüfung (VERIFY_FULL) läuft pro Arbeitspaket genau einmal vor der Abnahme; erneut nur nach echten Änderungen an Code oder Tests seit dem letzten Lauf.
- Der Nachweisumfang der Abnahme wird nicht abgeschwächt: Die Stufen sparen Wiederholungen unveränderter Volläufe, nicht den Nachweis selbst.

## Leitlinien für Coding-Agenten (verbindlich)

- KISS ist verpflichtend: Wähle die einfachste Lösung, die das Problem vollständig löst. Keine spekulativen Abstraktionen, Funktionen oder Optimierungen auf Vorrat und keine Komplexität ohne belegten Bedarf.
- Clean Code ist der verbindliche Code-Stil: sprechende Namen, kleine Funktionen mit einer klaren Aufgabe, explizite Schnittstellen, keine unnötige Duplizierung und nachvollziehbare Fehlerbehandlung. Verhalten wird durch Tests abgesichert, nicht durch Kommentare.
- Caching ist eine begründete Performance-Optimierung und nur mit funktionierender Invalidierung zulässig. Jeder Cache braucht einen eindeutigen Schlüssel, eine definierte Lebensdauer und eine benannte Invalidierung (Zeit, Änderungsereignis oder Version). Ohne korrekte Invalidierung wird nicht gecacht. Sicherheits-, Berechtigungs- und Geheimnisdaten werden nicht ungeprüft zwischengespeichert.
- Diese Leitlinien gelten für alle neuen und bestehenden Projekte unabhängig vom Projekttyp.

## Unabhängiger Test-Agent (verbindlich)

- Tests werden ausschließlich vom Test-Agenten geschrieben, geändert und gelöscht.
- Coding- und Review-Agent dürfen keine Testdateien anlegen, ändern, löschen oder abschwächen. Sie dürfen die vom Test-Agenten geschriebenen Tests ausführen und deren Ergebnisse melden.
- Vor der Implementierung fordert der Coding-Agent die Tests beim Test-Agenten an und übergibt Arbeitspaket, Akzeptanzkriterien und den vorgesehenen Testbefehl. Der Test-Agent leitet die Fälle unabhängig aus Arbeitspaket und `SPEC.md` ab, nicht aus dem Implementierungsdiff.
- Der Test-Agent beschreibt jeden Testfall (Name, Vorbedingung, Aktion, erwartetes Ergebnis), schreibt ihn vor der Implementierung und führt ihn tatsächlich aus. Ein nicht ausgeführter Test ist kein Nachweis.
- Nur Tests, die nachweislich vom Test-Agenten stammen, zählen für die Abnahme. Vom Coding-Agenten geschriebene oder nachträglich abgeschwächte Tests sind kein Nachweis; der Reviewer weist sie zurück.
<!-- /vibe:general-rules -->
