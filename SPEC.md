# vibe – Produktbeschreibung

Status: Zielbeschreibung  
Sprache der Dokumentation: Deutsch

## Produktziel

vibe ist eine lokale Entwicklungszentrale für KI-gestützte Softwareprojekte. Es verbindet Projektverwaltung, Agenten, Modelle, MCP-Server, Agentenläufe, Prüfungen und Diagnose in einer Weboberfläche und einer CLI.

vibe ist nicht opencode. opencode ist eine austauschbar gekapselte externe Ausführungs- und Konfigurationsschnittstelle.

Die funktionierende Installation wird übernommen und schrittweise verbessert. Ein vollständiger Rewrite findet nur auf Basis eines ausdrücklich beschlossenen Migrationstickets statt.

## Zielgruppe und Nutzung

Zielgruppe sind Berater, Product Owner und Projektmanager. Sie wollen schnell eine solide Software erstellen, haben aber keine tiefen Entwicklungskenntnisse.

Im Unternehmen dient vibe dazu, interne Anwendungen schnell und einfach zu entwickeln. Die Steuerung erfolgt fachlich, nicht technisch.

## Zielumgebung

vibe läuft unter Linux, Windows und macOS in einer Python-Umgebung. Agenten können wahlweise in einer Sandbox gestartet werden, damit der Zugriff auf das Hostsystem geschützt bleibt.

## Begriffe und Trennung

- Projektquellcode: das Git-Repository von vibe.
- Installation: der ausführbare, bereitgestellte Programmstand.
- Laufzeitdaten: Einstellungen, Logs, Tokens, Sicherungen und Status.
- Globaler Agent: in allen Projekten verfügbar.
- Projektagent: nur im jeweiligen Projekt verfügbar.
- MCP-Server: liefert zusätzliche Werkzeuge über MCP.
- Modellprofil: Zuordnung von Modellen zu Rollen.
- Agentenlauf: Ausführung eines Arbeitspakets über opencode.
- Dashboard: die vibe-Webanwendung.
- opencode-Server: eigener, externer Prozess.

Quellcode, Installation und Laufzeitdaten werden strikt getrennt. Sie dürfen weder verwechselt noch beim Aktualisieren gegenseitig überschrieben werden.

## Projekte und Entwicklungsordner

vibe verwaltet lokale Entwicklungsordner und erkennt darin Projekte anhand von Git-Metadaten oder einer vibe-Projektkonfiguration. Projekte bleiben auch dann erhalten, wenn ein Entwicklungsordner aus der Verwaltung entfernt wird.

Die Projektübersicht zeigt den aktuellen Zustand der Projekte. Das Projektdetail bietet Zugriff auf Pfad, Feedback, Tickets, Logs und verfügbare Aktionen.

## Projektvorlagen

vibe unterstützt bestehende Projekttypen und ermöglicht die Ergänzung weiterer Typen über Vorlagen. Vorhandene Projekte können vorbereitet werden, ohne dass vorhandene Dateien still überschrieben werden.

Projekttypen können eigene Prüfadapter besitzen. Android-spezifische Prüfungen sind keine Voraussetzung für andere Projekttypen.

## Arbeitspakete und Feedback

TICKETS.md und FEEDBACK.md dienen als versionierbare Arbeitsgrundlage. vibe unterscheidet offene, blockierte und erledigte Einträge.

Arbeitspakete und Feedback können über die Oberfläche angelegt, bearbeitet und gelöscht werden. Bugs werden als Feedback mit der Art „Bug“ erfasst.

Erledigt bedeutet, dass Akzeptanzkriterien erfüllt sind und Nachweise vorliegen. Ein Commit allein belegt keine fachliche Erfüllung.

## Agenten

vibe verwaltet globale und projektspezifische Agenten. Agenten können angelegt, gelesen, bearbeitet, kopiert und gelöscht werden.

Für jeden Agenten lassen sich Beschreibung, Modus, Modell, Temperatur, Schritte, Rechte und Prompt festlegen. Die Eingabe erfolgt wahlweise strukturiert oder als Rohtext.

Änderungen werden vor dem Speichern validiert. Vorhandene Agentendateien werden durch Sicherungen geschützt und können wiederhergestellt werden.

## Modelle und Anbieter

vibe zeigt Modelle verfügbarer Anbieter an und ermöglicht deren Auswahl im Agenteneditor. Kostenlose und kostenpflichtige Modelle werden unterstützt.

Die Modellübersicht enthält relevante Eigenschaften wie Verfügbarkeit, Kontext, Bildfähigkeit, Stärken, Schwächen, Tempo, Aufwand, Datenbedingungen und Preis. Unbekannte Werte sind ausdrücklich zulässig.

Fakten, Messungen, Nutzerberichte und Einschätzungen werden getrennt ausgewiesen. Jede Bewertung nennt Quelle, Datum und gegebenenfalls Testmethodik.

## Modellprofile

Modellprofile ordnen Modellen Rollen zu. Rollen sind frei konfigurierbar; mindestens Coder und Reviewer werden unterstützt.

Profile können angelegt, bearbeitet, kopiert, gelöscht und angewendet werden. Vor der Anwendung zeigt vibe eine genaue Änderungsvorschau und validiert alle betroffenen Agenten und Modelle.

Die Anwendung ist transaktional oder bei Teilfehlern vollständig rückrollbar. Kostenpflichtige Profile werden deutlich markiert; ein automatischer Wechsel von kostenlos auf kostenpflichtig findet nicht statt.

## MCP-Verwaltung

vibe verwaltet globale und projektbezogene MCP-Server. Server können angelegt, bearbeitet, gelöscht, aktiviert und deaktiviert werden.

Lokale Server werden über Programm, Argumente und Umgebungsvariablen konfiguriert. Remote-Server verwenden URL, Header und unterstützte Authentifizierung.

Geheimnisse werden maskiert und beim Speichern unverändert erhalten. Sie erscheinen weder in Antworten, Fehlermeldungen, Befehlsanzeigen noch in Logs.

## MCP-Tests

vibe kann MCP-Server vor der Verwendung testen. Dabei werden die Serveridentität und die verfügbare Werkzeugliste geprüft.

Vor einem Test wird darauf hingewiesen, dass Programme gestartet oder Netzverbindungen hergestellt werden können. Fachliche Werkzeuge werden nicht automatisch aufgerufen.

Fehler werden nach Ursache getrennt dargestellt, etwa fehlendes Programm, Timeout, Netzwerk, Authentifizierung, Protokoll oder ungültige Konfiguration.

## Agentenläufe und Prüfungen

vibe startet, beobachtet, hängt sich an laufende Prozesse an und stoppt Agentenläufe gezielt. Gleichzeitige Läufe verschiedener Projekte werden unterstützt.

Jeder Lauf besitzt eine eindeutige ID sowie sichtbare Informationen zu Projekt, Agent und Startzeit. Live-Logs und separate Prüfprotokolle werden bereitgestellt.

Prüfungen liefern echte Ergebnisse. Eine fehlende Prüfkonfiguration ist ein Fehler und kein erfolgreicher Test.

## App und opencode beenden

Das Beenden des Dashboards betrifft ausschließlich vibe. Bestehende Agentenläufe bleiben standardmäßig aktiv.

Das Stoppen von opencode ist eine getrennte Aktion. Nur eindeutig von vibe verwaltete Prozesse werden beendet.

Das Schließen eines Browser-Tabs beendet keine Hintergrundprozesse. Die Oberfläche erläutert diese Unterschiede.

## Startmenü

vibe bietet einen benutzerbezogenen Startmenüeintrag. Dieser startet bei Bedarf erforderliche Container, wartet auf die Bereitschaft und öffnet die Weboberfläche im Standardbrowser.

Läuft vibe bereits, wird nur die Weboberfläche geöffnet. Mehrfachklicks erzeugen keine zusätzlichen Dashboard-Prozesse.

Im Normalbetrieb ist kein Terminalfenster erforderlich. Fehler werden verständlich gemeldet und in einem bereinigten Log dokumentiert.

## Diagnose

vibe prüft Anwendungsvoraussetzungen getrennt von optionalen Projektwerkzeugen. Es zeigt die tatsächliche opencode-Version und unterstützte Funktionen an.

Die Diagnose erkennt Host- und Container-Verwechslungen sowie Probleme mit Schreibrechten, Ports oder benötigten Programmen. Sie bietet konkrete, kopierbare Lösungsvorschläge.

## Sicherheit und Datenintegrität

Der Webserver ist standardmäßig nur lokal erreichbar. Schreibende API-Aufrufe erfordern eine gültige Authentifizierung.

Geheimnisse, Tokens und persönliche Konfigurationen werden nicht ins Repository übernommen. Eingaben und Requestgrößen werden begrenzt; Pfad-Traversal und unerlaubte Symlink-Ziele werden verhindert.

Dateien werden atomar geschrieben. Konkurrierende Änderungen werden erkannt, Sicherungen sind kollisionsfrei und können sensible Daten enthalten.

## Architekturziel

vibe wird schrittweise entkoppelt:

- CLI und Web-API sind dünne Zugriffsschichten.
- Gemeinsame Dienste bilden die Fachlogik.
- Adapter kapseln opencode, Container, tmux und Projektprüfungen.
- Dateizugriffe laufen über testbare Storage-Funktionen.
- Frontend und Python sind getrennt.

Zielstruktur, keine Voraussetzung für den Erstimport:

bin/, src/vibe/, web/, data/, templates/, scripts/, tests/, docs/, .vibe/

## Betrieb und Weiterentwicklung

Die Installation erfolgt aus dem Repository. Aktualisierung und Rollback erhalten persönliche Einstellungen.

Vor einer Migration gibt es Vorschau und Sicherung. Ein Uninstall entfernt keine Projekte und standardmäßig keine Nutzerdaten.

Änderungen an vibe selbst werden zunächst separat getestet. Die produktive Instanz wird nicht während eines Agentenlaufs überschrieben.

## Qualität und Abnahme

Jede Funktion wird durch Unit-, Integrations- und Browsertests geprüft. Attrappen ersetzen keine echte Browser- oder Systemabnahme.

Tests verwenden temporäre Verzeichnisse und eigene Ports. Sie laufen nicht gegen persönliche Projekte oder produktive Konfigurationen.

Ein Ticket gilt erst nach Tests, fachlicher und technischer Dokumentation sowie unabhängigem Review als abgeschlossen.

## Nicht im Umfang

- Eigener Modellhost oder eigene Zahlungsabwicklung.
- Öffentlicher Remotezugriff auf das Dashboard.
- Mehrbenutzerbetrieb oder Cloud-Synchronisation.
- Vollständiger Ersatz für coding harness.
- Automatische Veröffentlichung, Push, Merge oder Release ohne Freigabe.
- Vollständiger Frameworkwechsel als Voraussetzung für weitere Entwicklung.
