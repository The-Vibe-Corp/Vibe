# AGENTS — vibe

## Auftrag

SPEC.md ist die fachliche Wahrheit.
Bearbeite genau das ausdrücklich beauftragte Ticket aus TICKETS.md.
Keine vollständige Neuimplementierung und kein ungefragter Frameworkwechsel.

## Bestehenden Zustand respektieren

- Vor Änderungen Git-Status und Ausgangscommit erfassen.
- Fremde oder vorbestehende Änderungen nicht überschreiben oder mitcommitten.
- Importierte Dateien sind der Ausgangsstand, kein automatisch geprüfter Code.
- Frühere Aussagen über Modellpreise, Fähigkeiten und opencode-Versionen
  nicht ungeprüft übernehmen.
- Keine persönlichen Konfigurationen oder Geheimnisse ins Repository kopieren.

## Umgebung

- Host: Bazzite; Standardcontainer: android-dev.
- $VIBE ist der Arbeitsbereich, nicht automatisch dieses Repository.
- Projektcode liegt im Repository, produktive Installation unter _toolchain.
- Entwicklung und Tests verwenden isolierte Verzeichnisse und eigene Ports.
- Produktive Installation während der Entwicklung nicht überschreiben.
- Keine echten Modellkosten, OAuth-Anmeldungen oder produktiven MCP-Aufrufe
  ohne ausdrückliche Freigabe.
- Auf FUSE/NTFS Skripte mit bash ausführen; Rechte nicht als wirksam voraussetzen.

## Arbeitsablauf

1. Ticket, SPEC.md und betroffene Implementierung vollständig lesen.
2. Bestehenden Zustand und relevante Abhängigkeiten prüfen.
3. Kleinste zusammenhängende Änderung implementieren.
4. Erfolgs-, Fehler- und relevante Sicherheitsfälle testen.
5. Tatsächliche Prüfungen ausführen; keine Ergebnisse erfinden.
6. Fachliche und technische Dokumentation unter docs/features/<ticket>.md pflegen.
7. Diese Dokumentation zusätzlich über den vorhandenen Trilium-MCP-Zugang
   dokumentieren. Fehlt der Zugang, BLOCKIERT melden; keine lokale Datei als
   angeblich erfolgte Trilium-Dokumentation ausgeben.
8. Unabhängigen Reviewer über Task aufrufen. Reviewername wird aus der
   Projektkonfiguration ermittelt, nicht geraten.
9. Reviewer erhält Ticket, Ausgangscommit, vollständigen relevanten Diff,
   neue Dateien und tatsächliche Prüfergebnisse.
10. Reviewantwort unverändert unter docs/reviews/<ticket>-review-<runde>.md speichern.
11. Beanstandungen beheben, Prüfungen wiederholen und erneut reviewen.
12. Nach finalem PASS keine Implementierungsänderungen ohne erneuten Review.
13. Erst dann Ticket mit echten Nachweisen abhaken und zugehörige Dateien committen.
14. Nicht pushen, mergen oder das nächste Ticket beginnen.

## Abbruchbedingungen

- Reviewer nicht verfügbar: blockiert, kein Abschlusscommit.
- Pflichtprüfung nicht möglich: blockiert, kein vorgetäuschter Erfolg.
- Widerspruch zwischen Ticket und SPEC: Konflikt erläutern.
- Zehn abgeschlossene Reviewrunden ohne PASS: stoppen.
- Geheimnis entdeckt: nicht in Logs oder Antworten ausgeben; Fundort bereinigt melden.

## Definition of Done

- Alle Akzeptanzkriterien erfüllt.
- Relevante automatisierte Prüfungen grün.
- Erforderliche manuelle Nachweise vorhanden oder Ticket weiterhin offen.
- Fachliche und technische Dokumentation vorhanden.
- Trilium-Dokumentation tatsächlich durchgeführt.
- Unabhängiger Review: PASS, keine offenen Critical/High/Medium-Befunde.
- Commit enthält ausschließlich dieses Arbeitspaket und dessen Nachweise.
- Ticket nennt Commit, Testbefehle, Review und Dokumentation.

## Projektordner sauber halten

- Im Projektordner nur Quellcode, Konfiguration, Tests und die vereinbarten
  Nachweise ablegen.
- Temporäre Dateien, Protokolle, Sicherungen, Screenshots ohne Nachweiswert
  und Arbeitskopien nach Abschluss des Arbeitspakets entfernen; nicht committen.
- Vor jedem Commit `git status` prüfen und ausschließlich Dateien des eigenen
  Arbeitspakets stagen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben, stashen
  oder mitcommitten.
- Laufzeitdaten, persönliche Konfiguration und Geheimnisse gehören nicht ins
  Repository.

## Ordnung im Git halten

- Änderungen auf einem Feature-Branch umsetzen, nicht direkt auf main, master
  oder einem geschützten Branch.
- Jedes abgeschlossene Arbeitspaket als zusammenhängenden Commit sichern; keine
  Zwischenstände oder fremden Änderungen mitcommitten.
- Vor jedem Commit `git status` und den relevanten Diff prüfen und
  ausschließlich Dateien des eigenen Arbeitspakets stagen.
- Keine temporären Dateien, Protokolle, Build-Artefakte, Arbeitskopien oder
  Screenshots ohne Nachweiswert committen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben, stashen
  oder mitcommitten.
- Keine Historie umschreiben, keine Force-Pushes und kein Push ohne
  ausdrückliche Freigabe.

## Leitlinien für Coding-Agenten (verbindlich)

- KISS ist verpflichtend: Wähle die einfachste Lösung, die das Problem
  vollständig löst. Keine spekulativen Abstraktionen, Funktionen oder
  Optimierungen auf Vorrat und keine Komplexität ohne belegten Bedarf.
- Clean Code ist der verbindliche Code-Stil: sprechende Namen, kleine
  Funktionen mit einer klaren Aufgabe, explizite Schnittstellen, keine
  unnötige Duplizierung und nachvollziehbare Fehlerbehandlung. Verhalten wird
  durch Tests abgesichert, nicht durch Kommentare.
- Caching ist eine begründete Performance-Optimierung und nur mit
  funktionierender Invalidierung zulässig. Jeder Cache braucht einen
  eindeutigen Schlüssel, eine definierte Lebensdauer und eine benannte
  Invalidierung (Zeit, Änderungsereignis oder Version). Ohne korrekte
  Invalidierung wird nicht gecacht. Sicherheits-, Berechtigungs- und
  Geheimnisdaten werden nicht ungeprüft zwischengespeichert.
- Diese Leitlinien gelten für alle neuen und bestehenden Projekte unabhängig
  vom Projekttyp.

## Prüfungen

Zuerst V-002 implementieren.
Danach verbindlich:
- bash scripts/verify.sh quick
- bash scripts/verify.sh full

Fehlende Skripte oder leere Tests sind kein bestandener Test.
Syntaxchecks allein sind keine fachliche Abnahme.

## Besondere Sicherheitsregeln

- Keine Shellverkettung mit unvalidierten Eingaben.
- Keine produktiven HOME-/VIBE-Konfigurationen in Tests.
- Keine automatischen Router-Neuverbindungen oder Limitumgehungen.
- Keine kostenpflichtigen Fallbacks.
- MCP-Verbindungstest ruft keine fachlichen Werkzeuge auf.
- App beenden darf nicht opencode oder Agentenläufe beenden.
- Installation und Rollback dürfen keine Nutzerdaten verlieren.

## Abschlussantwort

Nenne Ticket, Commit, tatsächliche Prüfungen, Reviewpfade,
Dokumentationspfade und verbleibende Grenzen.
Keine pauschale Aussage „alles getestet“, wenn nur Attrappen verwendet wurden.
