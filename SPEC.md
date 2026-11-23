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

## Leistungsumfang

- Projekte und Entwicklungsordner verwalten, inklusive Projektvorlagen für verschiedene Projekttypen.
- Arbeitspakete (Tickets) und Feedback als versionierbare Arbeitsgrundlage führen.
- Globale und projektspezifische Agenten verwalten.
- Modelle und Anbieter übersichtlich darstellen und vergleichen.
- Modellprofile mit frei konfigurierbaren Rollen (mindestens Coder und Reviewer) anlegen und anwenden.
- MCP-Server verwalten und testen.
- Agentenläufe starten, beobachten und stoppen; Prüfungen ausführen.
- Dashboard und opencode getrennt beenden.
- Benutzerbezogener Startmenüeintrag zum bequemen Starten.
- Diagnose der Anwendungsvoraussetzungen mit konkreten Lösungsvorschlägen.

## Leitprinzipien

- Sicherheit und Datenintegrität haben Vorrang vor Komfortfunktionen.
- vibe ist ein lokales System. Der Webserver ist standardmäßig nur lokal erreichbar und schreibende Zugriffe sind authentisiert.
- Geheimnisse, Laufzeitdaten und persönliche Konfigurationen gehören nicht ins Repository und werden nie durch Defaults ersetzt.
- Es entstehen keine Kosten oder Seiteneffekte ohne vorherigen Hinweis und Zustimmung.
- Ungeprüfte Informationen gelten als unbekannt. Keine Funktion gilt als erledigt, bevor sie geprüft wurde.
- Benutzerdaten gehen bei Änderungen nicht still verloren. Änderungen sind nachvollziehbar und umkehrbar.

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

- Die Installation erfolgt aus dem Repository. Aktualisierung und Rollback erhalten persönliche Einstellungen.
- Vor einer Migration gibt es Vorschau und Sicherung.
- Ein Uninstall entfernt keine Projekte und standardmäßig keine Nutzerdaten.
- Änderungen an vibe selbst werden zunächst separat getestet. Die produktive Instanz wird nicht während eines Agentenlaufs überschrieben.
- Der Runner verantwortet Worktrees, Branches, Push, PR und Merge. Agenten arbeiten nur im zugewiesenen Worktree.
- Ein Ticket gilt erst nach Tests, Dokumentation und unabhängigem Review als abgeschlossen.

## Nicht im Umfang

- Eigener Modellhost oder eigene Zahlungsabwicklung.
- Öffentlicher Remotezugriff auf das Dashboard.
- Mehrbenutzerbetrieb oder Cloud-Synchronisation.
- Vollständiger Ersatz für coding harness.
- Automatische Veröffentlichung, Push, Merge oder Release ohne Freigabe.
- Vollständiger Frameworkwechsel als Voraussetzung für weitere Entwicklung.
