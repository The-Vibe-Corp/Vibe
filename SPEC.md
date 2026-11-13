# vibe — Produktspezifikation

Status: Verbindliche Zielbeschreibung
Ausgangsbasis: installierter vibe-v5-Stand plus vorhandener Desktop-Starter
Sprache der Oberfläche und Dokumentation: Deutsch

## Produktziel

vibe ist eine lokale Entwicklungszentrale für KI-gestützte Softwareprojekte.
Es verbindet Projektverwaltung, Agenten, Modelle, MCP-Server, Agentenläufe,
Prüfungen und Diagnose in einer Weboberfläche und einer CLI.

vibe ist nicht opencode. opencode ist eine austauschbar gekapselte externe
Ausführungs- und Konfigurationsschnittstelle.

Die funktionierende Installation wird übernommen und schrittweise verbessert.
Kein vollständiger Rewrite ohne ausdrücklich beschlossenes Migrationsticket.

## Zielumgebung

Das system ist sowohl auf Linux/Win/Mac in einer python umgebung lauffähig. Vibe selbst startet agenten wahlweise in einer sandbox, um den zugriff auf das system zu schützen.

## Begriffe und Trennung

- Projektquellcode: dieses Git-Repository.
- Installation: ausführbarer, bereitgestellter Programmstand.
- Laufzeitdaten: Einstellungen, Logs, Tokens, Sicherungen und Status.
- Globaler Agent: in allen Projekten verfügbar.
- Projektagent: nur im jeweiligen Projekt verfügbar.
- MCP-Server: liefert zusätzliche Werkzeuge über MCP.
- Modellprofil: Zuordnung von Modellen zu Rollen.
- Agentenlauf: Ausführung eines Arbeitspakets über opencode.
- Dashboard: vibe-Webanwendung.
- opencode-Server: eigener externer Prozess.

Quellcode, Installation und Laufzeitdaten dürfen nicht miteinander verwechselt
oder beim Aktualisieren gegenseitig überschrieben werden.

## Ausgangsstand und Nachweisstatus

Vorhandene Programmdateien werden unverändert importiert und durch ein
SHA-256-Manifest dokumentiert.

Die bisherige Nutzerbestätigung belegt grundsätzliche Nutzbarkeit, nicht
vollständige Konformität aller Funktionen.

Jede Funktion erhält nach der Bestandsaufnahme einen Status:
- vorhanden und automatisiert geprüft,
- vorhanden und manuell geprüft,
- vorhanden, noch nicht geprüft,
- teilweise vorhanden,
- fehlt.

Alte Modellbewertungen, Preise, API-Annahmen und Versionsaussagen sind
ungeprüfte Altdaten, bis eine aktuelle Quelle oder ein reproduzierbarer Test
vorliegt.

## Funktionsumfang

### Projekte und Entwicklungsordner

- Entwicklungsordner anzeigen, hinzufügen, entfernen und erneut einlesen.
- Projekte mit Git-Metadaten oder vibe-Projektkonfiguration erkennen.
- Gleichnamige Projekte in unterschiedlichen Ordnern eindeutig identifizieren.
- Entfernen eines Entwicklungsordners löscht keine Projektdateien.
- Ungeeignet allgemeine oder unzulässige Pfade verständlich ablehnen.
- Projektliste zeigt Name, Typ, Branch, Änderungen, offene Arbeitspakete,
  Laufstatus und letzten Commit.
- Projektdetail zeigt Pfad, Feedback, Tickets, Logs und verfügbare Aktionen.
- Einlesen führt keine Builds, Installationen oder Projektbefehle aus.

### Projektvorlagen

- Bestehende Typen erhalten: generic, web, android, docker und openwrt,
  soweit im importierten Stand vorhanden.
- Neue Typen sind über Vorlagen ergänzbar.
- Vorhandene Projekte können vorbereitet werden.
- Vorhandene Dateien werden dabei nicht still überschrieben.
- Projekterzeugung und Git-Initialisierung liefern verständliche Fehler.
- Projekttypen besitzen eigene Prüfadapter.
- Android-spezifische Prüfungen sind keine globale Voraussetzung.

### Arbeitspakete und Feedback

- TICKETS.md und FEEDBACK.md sind versionierbare Arbeitsgrundlagen.
- Offene, blockierte und erledigte Einträge werden unterschieden.
- Feedback kann über die Oberfläche ergänzt werden.
- Arbeitspakete können über die Oberfläche definiert, bearbeitet und gelöscht
  werden; bei neuen Arbeitspaketen wird die ID automatisch vergeben, eine
  eigene ID bleibt möglich.
- Bugs können über die Oberfläche als Feedback mit ``Art: Bug`` gemeldet
  werden.
- IDs sind eindeutig; parallele Schreibvorgänge erzeugen keine Doppelungen.
- Erledigt bedeutet: Akzeptanzkriterien erfüllt und Nachweise vorhanden.
- Ein Commit allein beweist keine fachliche Erfüllung.
- Markdown-Kommentare und Vorlagen gelten nicht als offene Arbeitspakete.
- Blockierte Einträge werden nicht automatisch als erledigt interpretiert.

### Agenten

- Globale und projektspezifische Agenten anzeigen und filtern.
- Agenten anlegen, lesen, bearbeiten, kopieren und löschen.
- Beschreibung, Modus, Modell, Temperatur, Schritte, Rechte und Prompt bearbeiten.
- Strukturierte Eingabe und Rohtextbearbeitung anbieten.
- Validierung muss zur unterstützten opencode-Version passen.
- Ungültige Eingaben verändern die bestehende Datei nicht.
- Namenskonflikte und Überschattungen sichtbar machen.
- Prioritätsregeln anhand der unterstützten Version prüfen und dokumentieren.
- Unbekannte Felder möglichst verlustfrei erhalten.
- Vor Änderungen Sicherungen erzeugen und Wiederherstellung ermöglichen.
- Keine fest eingebauten Agentennamen für die Produktlogik.
- Coder und Reviewer werden über konfigurierbare Rollen zugeordnet.

### Modelle und Anbieter

- Modelle verfügbarer Anbieter anzeigen, nicht nur opencode/*.
- Modellwahl im Agenteneditor.
- Kostenlose und kostenpflichtige Modelle unterstützen.
- Zugangsdaten gehören nicht in Agentendateien oder dieses Repository.
- Anbieteranmeldung bleibt über die unterstützten opencode-Verfahren möglich.
- Modellliste und tatsächliche Nutzungsberechtigung sind getrennte Zustände.
- Keine kostenpflichtige Testanfrage ohne vorherigen Hinweis und Zustimmung.
- Keine erfundenen Modell-IDs oder Fähigkeiten.

### Modelltabelle

- Gesamte Modellübersicht ist ein- und ausklappbar.
- Jede Modellzeile zeigt bei Bedarf weitere Details.
- Felder: Modell-ID, Anbieter, Verfügbarkeit, Kontext, Bildfähigkeit,
  Stärken, Schwächen, Tempo, Aufwand, Datenbedingungen und Preis.
- Unbekannt ist ein zulässiger und sichtbarer Wert.
- Fakten, Messungen, Nutzerberichte und Einschätzungen klar unterscheiden.
- Jede Bewertung nennt Quelle, Datum und gegebenenfalls Testmethodik.
- Preise enthalten Währung, Einheit, Eingabe-/Ausgabetarif und Gültigkeitsdatum.
- Cachepreise, Staffelungen und Zusatzgebühren getrennt ausweisen.
- Veraltete Daten markieren; keine ungeprüfte Übernahme früherer Tabellen.

### Modellprofile

- Profile anlegen, bearbeiten, kopieren, löschen und anwenden.
- Rollen frei konfigurierbar, mindestens Coder und Reviewer.
- Rollen können globalen oder projektspezifischen Agenten zugeordnet werden.
- Vor Anwendung genaue Änderungsvorschau anzeigen.
- Alle Zielagenten und Modelle vor dem ersten Schreibvorgang validieren.
- Anwendung ist transaktional oder bei Teilfehlern vollständig rückrollbar.
- Leere Profile gelten nicht als erfolgreich angewendet.
- Profilstatus zeigt Abweichungen durch spätere manuelle Agentenänderungen.
- Kostenpflichtige Profile werden deutlich markiert.
- Kein automatischer Wechsel von kostenlos auf kostenpflichtig.

### MCP-Verwaltung

- Globale und projektbezogene Server anzeigen, anlegen, bearbeiten und löschen.
- Aktivieren und deaktivieren.
- Lokal: Programm und Argumente als Liste, Umgebungsvariablen.
- Remote: URL, Header und unterstützte Authentisierung.
- Weitere Felder nur anbieten, wenn die installierte Version sie unterstützt.
- Tatsächliche Konfigurationsdateien und deren Prioritäten dokumentieren.
- JSON und JSONC sicher lesen.
- Unbekannte Einstellungen und Kommentare soweit möglich erhalten.
- Bei nicht verlustfrei unterstützten Dateien abbrechen oder eine konkrete
  Änderungsvorschau verlangen; niemals still Daten verwerfen.
- Geheimnisse maskieren und beim Speichern unverändert erhalten.
- Keine Geheimnisse in Antworten, Fehlermeldungen, Befehlsanzeigen oder Logs.

### MCP-Tests

- Vor dem Test erklären, dass Programme gestartet oder Netzverbindungen
  hergestellt werden; ein Verbindungscheck ist nicht garantiert nebenwirkungsfrei.
- initialize und tools/list prüfen.
- Serveridentität und Werkzeugliste anzeigen.
- Keine fachlichen Werkzeuge automatisch aufrufen.
- Fehler trennen: fehlendes Programm, Timeout, DNS/TLS, HTTP,
  Authentisierung, Protokoll und ungültige Konfiguration.
- Unterstützte Transportarten explizit ausweisen.
- Nicht unterstützte Transporte nicht als defekten Server darstellen.
- Tests besitzen Zeit-, Ausgabe- und Ressourcenlimits.
- Testprozesse einschließlich gestarteter Kindprozesse zuverlässig beenden.
- Testresultate sind keine Garantie, dass ein Agent alle Werkzeuge nutzen darf.
- Werkzeugfreigaben pro Agent müssen sichtbar oder nachvollziehbar sein.

### Agentenläufe und Prüfungen

- Lauf starten, beobachten, anhängen und gezielt stoppen.
- Projekt, Agent, Startzeit und eindeutige Lauf-ID anzeigen.
- Gleichzeitige Läufe verschiedener Projekte unterstützen.
- Gleiche Namen oder gleich normalisierte Namen dürfen keine Kollision erzeugen.
- Live-Logs und separate Prüfprotokolle.
- quick und full liefern echte Exitcodes.
- Fehlende Prüfkonfiguration ist ein Fehler, kein erfolgreicher Test.
- Nicht-Android-Projekte funktionieren ohne Android-Prüfinfrastruktur.
- Wiederholungs- und Durchgangslimits konfigurierbar.
- Durchgangslimit ist kein Geldbudget und muss so beschriftet werden.
- Keine automatische Router-Neuverbindung oder Umgehung von Dienstlimits.
  Vorhandene entsprechende Altintegration nur nach ausdrücklicher Entscheidung
  weiterverwenden; standardmäßig deaktivieren.
- Jeder Agentenlauf nutzt einen eigenen tmux-Server; Socket- und Sitzungsname
  sind der Laufsitzungsname. Dashboard und opencode-Server bleiben auf dem
  Standard-Server. Ein fremdes `tmux kill-server` auf dem Standard-Server
  beendet damit weder Dashboard noch laufende Läufe.
- Ein äußeres Signal (HUP, TERM, INT) beendet einen Lauf nicht spurlos:
  Signal, Protokollzeile und Registerzustand werden festgehalten. Eine
  Startprüfung kennzeichnet verwaiste `running`-Einträge des eigenen Projekts
  als extern beendet; fremde Projekte, laufende und nicht prüfbare Sitzungen
  bleiben unverändert, und es wird nie eine fremde Sitzung beendet.
- Quota- und Anmeldefehler halten einen Lauf standardmäßig sofort an. Das
  Verhalten ist eine ausdrückliche, globale Einstellung (`vibe limits
  stop|continue`, `<Zustand>/limits.json`) für alle Projekte, nicht je
  Projekt; `continue` behandelt den Fehler im Rahmen der vorhandenen
  Wiederholungslimits und protokolliert einen Hinweis. Eine fehlende oder
  defekte Einstellung gilt als `stop` und wird gemeldet, nie still als
  `continue`. Quota- und Anmeldefehler lösen weder eine Router-Neuverbindung
  noch eine manuelle IP-Abfrage aus.

### App und opencode beenden

- Dashboard beenden beendet ausschließlich vibe.
- Bestehende Agentenläufe bleiben standardmäßig aktiv.
- opencode stoppen ist eine getrennte Aktion.
- Nur eindeutig von vibe verwaltete Prozesse stoppen.
- Browser-Tab schließen beendet keine Hintergrundprozesse.
- Die Oberfläche erläutert diese Unterschiede.
- Tests prüfen ausdrücklich, dass kein unbeabsichtigtes Stoppen erfolgt.

### Startmenü

- Benutzerbezogenen Menüeintrag installieren und entfernen.
- Läuft vibe nicht: nötigen Container starten, vibe starten, Bereitschaft
  abwarten und Standardbrowser öffnen.
- Läuft vibe: nur Weboberfläche öffnen.
- Mehrfachklicks erzeugen keine mehrfachen Dashboard-Prozesse.
- Eine fremde Anwendung auf dem Port gilt nicht als laufendes vibe.
- Instanzprüfung über einen eindeutigen Health-Endpunkt.
- Token wird nicht protokolliert.
- Pfade mit Leerzeichen und Sonderzeichen funktionieren.
- Kein Terminalfenster im Normalbetrieb erforderlich.
- Fehler werden verständlich gemeldet und mit bereinigtem Log dokumentiert.
- Benutzerdefinierte Pfade, Ports und Container gelten konsistent.
- Startmenüaktion zum Beenden betrifft nur vibe.

### Diagnose

- Anwendungsvoraussetzungen getrennt von optionalen Projektwerkzeugen prüfen.
- Tatsächliche opencode-Version und unterstützte Funktionen anzeigen.
- Keine pauschale Ableitung eines Konfigurationsschemas allein aus einer
  angenommenen Hauptversionsnummer.
- Host-/Container-Verwechslungen erkennen.
- Schreibbarkeit, Portbelegung und benötigte Programme prüfen.
- Konkrete, kopierbare Lösungsvorschläge anbieten.

## Sicherheit und Datenintegrität

- Webserver bindet standardmäßig nur an Loopback; eine ausdrückliche
  Netz-Bindung erfolgt nur als IP-Adressliteral (DNS-Hostnamen werden
  abgelehnt, gegen DNS-Rebinding). Eine IP-Allowlist kann Clients je IP/CIDR
  einschränken; Loopback bleibt immer zugelassen. Die Anmeldung erfolgt per
  Token oder Kennwort mit Session-Cookie statt dauerhaftem Token im Browser.
- Schreibende API-Aufrufe verlangen gültige Authentisierung.
- Host-/Origin-Prüfung und CSRF-Schutz.
- Keine Tokens in Zugriffslogs oder Fehlermeldungen.
- Eingaben und Requestgrößen begrenzen.
- Pfad-Traversal und unerlaubte Symlink-Ziele verhindern.
- Externe Befehle mit Argumentlisten statt Shellverkettung aufrufen,
  soweit keine explizit konfigurierte Shellausführung erforderlich ist.
- Projektprüfbefehle und MCP-Programme als vertrauensbedürftige Ausführung behandeln.
- Dateien atomar schreiben, konkurrierende Änderungen erkennen.
- Sicherungen sind kollisionsfrei und können sensible Daten enthalten.
- Sensible Laufzeitdaten gehören auf ein geeignet geschütztes Dateisystem.
  Bei FUSE/NTFS nicht fälschlich wirksame Unix-Dateirechte behaupten.
- Keine API-Schlüssel, Tokens, globalen Konfigurationen oder persönlichen
  Agenten automatisch in Git übernehmen.

## Architekturziel

Schrittweise Entkopplung:

- CLI und Web-API als dünne Zugriffsschichten.
- Gemeinsame fachliche Dienste für Projekte, Agenten, Profile und MCP.
- Adapter für opencode, Distrobox, tmux und Projektprüfungen.
- Dateizugriffe über testbare Repository-/Storage-Funktionen.
- Geschäftslogik liefert strukturierte Ergebnisse statt stdout umzuleiten.
- Statische Frontenddateien von Python trennen.
- Import von Modulen startet weder Server noch Container oder Programme.

Zielstruktur, nicht Voraussetzung für den unveränderten Erstimport:

bin/
src/vibe/
web/
data/
templates/
scripts/
tests/unit/
tests/integration/
tests/browser/
docs/
.vibe/

## Konfiguration und Migration

- $VIBE bleibt der Arbeitsbereich und ist nicht der Quellcodepfad.
- Standardcontainer android-dev; vollständig überschreibbar.
- Bestehende _toolchain- und _logs-Daten bleiben bei der Übernahme unverändert.
- Persönliche Konfiguration niemals durch mitgelieferte Defaults ersetzen.
- Vor Migration: Vorschau und Sicherung.
- Installation aus dem Repository, ohne manuelles Kopieren einzelner Dateien.
- Aktualisierung und Rollback ohne Verlust persönlicher Einstellungen.
- Uninstall entfernt keine Projekte und standardmäßig keine Nutzerdaten.
- Self-Development: Änderungen an vibe zunächst separat testen; die laufende
  produktive Instanz nicht während eines Agentenlaufs überschreiben.

## Qualität und Abnahme

- Unit-Tests für fachliche Logik und Validierung.
- Integrationstests für API, Storage und Prozessadapter.
- Browsertests für zentrale Workflows.
- Attrappen allein ersetzen keine Browser- oder Systemabnahme.
- Tests verwenden temporäre Verzeichnisse und eigene Ports.
- Keine Tests gegen persönliche Projekte oder produktive Konfigurationen.
- Testprotokolle nennen Befehl, Ergebnis und Grenzen des Nachweises.
- Jedes Ticket benötigt Tests, fachliche und technische Dokumentation sowie
  unabhängigen Review vor dem Abschluss.

## Nicht im Umfang

- Eigener Modellhost oder eigene Zahlungsabwicklung.
- Öffentlicher Remotezugriff auf das Dashboard.
- Mehrbenutzerbetrieb oder Cloud-Synchronisation.
- Vollständiger Ersatz für coding harniss.
- Automatische Veröffentlichung, Push, Merge oder Release ohne Freigabe.
- Vollständiger Frameworkwechsel als Voraussetzung für weitere Entwicklung.

## Decisions Locked

- Bestehenden Quellcode importieren, nicht neu generieren.
- Keine Funktion als erledigt markieren, bevor sie geprüft wurde.
- Lokale Webanwendung plus CLI beibehalten.
- Funktionen inkrementell entkoppeln.
- Laufzeitdaten und Geheimnisse nicht ins Repository aufnehmen.
- Ungeprüfte Modellinformationen als unbekannt behandeln.
- Sicherheits- und Datenintegritätsfehler vor neuen Komfortfunktionen beheben.

## Zielgruppe und Nutzung

Die zielgruppe von vibe sind berater, product ower oder projektmanager. alle, welche schnell eine solide software erstellen wollen, aber keine tiefen entwicklungskenntnisse haben. vibe dient im unternehmen dazu interne, solide anwendungen schnell und einfach, durch fachliche steuerung zu entwickeln.
