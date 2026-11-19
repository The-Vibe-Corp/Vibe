# Projekt: {{NAME}} (Docker: Client/Server)
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL).
- Nach jedem Arbeitspaket: Tests grün, git commit.
- Server und Client getrennt testen (Unit-Tests je Teil), danach Integrationstest über compose. Ports und Zugangsdaten nur über Umgebungsvariablen/.env (nicht committen).
- Beim Aufräumen nur Container/Images dieses Projekts löschen (Label oder Präfix `{{NAME}}`), nie ` system prune`.

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
- Paket-Branches folgen den Repository-Regeln (`feature/<owner>/<kennung>`); das Muster ist über `PACKAGE_BRANCH_PATTERN` konfigurierbar.
- Bei aktivierter GitHub-Verknüpfung gilt ein Arbeitspaket erst mit gepushtem Branch und gestelltem Merge-Request als geschlossen; ohne Push und Merge-Request kein Häkchen und kein lokaler Merge.

## Laufende Instanz nicht verändern (verbindlich)

- Entwicklung, Tests und Verifikation verändern die laufende Instanz nicht: bereinigte VIBE_*-Umgebung, explizite Temp-Pfade und ein Update nur mit autorisierter Quelle (`--source`).

## Laufende Instanz nicht verändern (verbindlich)

- Entwicklung, Tests und Verifikation verändern die laufende Instanz nicht: bereinigte VIBE_*-Umgebung, explizite Temp-Pfade und ein Update nur mit autorisierter Quelle (`--source`).

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
