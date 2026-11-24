# vibe — Produktspezifikation

Status: Verbindliche Zielbeschreibung  
Ausgangsbasis: installierter vibe-v5-Stand plus vorhandener Desktop-Starter  
Sprache der Web-Oberfläche: Englisch
Sprache der Dokumentation: Deutsch

## Produktziel

vibe ist eine lokale Entwicklungszentrale für KI-gestützte Softwareprojekte. Es verbindet Projektverwaltung, Agenten, Modelle, MCP-Server, Agentenläufe, Prüfungen und Diagnose in einer Weboberfläche und einer CLI.

vibe ist nicht kein AI Harness. Vibe kann mit verschiedenen Harnessen wie z.b. opencode zusammenarbeiten. Diese sind austauschbare gekapselte externe Ausführungs- und Konfigurationsschnittstellen.

Die funktionierende Installation wird übernommen und schrittweise verbessert. Ein vollständiger Rewrite ist nur mit einem ausdrücklich beschlossenen Migrationsticket zulässig.

### Produktversprechen

- Fachliche Nutzer können Projekte anlegen, Arbeitspakete beschreiben, Feedback geben und Ergebnisse nachvollziehen.
- Entwicklungsteams können Agenten, Modelle, Prüfungen und MCP-Server zentral konfigurieren.
- Alle sicherheitsrelevanten Aktionen sind transparent, begrenzbar und nachvollziehbar protokolliert.
- Lokale Daten, Zugangsdaten und Projektquellcode bleiben unter Kontrolle der Nutzerin oder des Nutzers.

## Zielumgebung

vibe ist auf Linux, Windows und macOS in einer Python-Umgebung lauffähig. Die Anwendung startet Agenten optional in einer Sandbox, um den Zugriff auf das Hostsystem zu begrenzen.

Die konkrete Unterstützung von Betriebssystemen, Containern, Python-Versionen und optionalen Werkzeugen wird durch die Diagnose geprüft. Fehlende optionale Komponenten dürfen Kernfunktionen nicht still beschädigen.

## Begriffe und Trennung

- **Projektquellcode:** dieses Git-Repository.
- **Installation:** ausführbarer, bereitgestellter Programmstand.
- **Laufzeitdaten:** Einstellungen, Logs, Tokens, Sicherungen und Status.
- **Globaler Agent:** in allen Projekten verfügbar.
- **Projektagent:** nur im jeweiligen Projekt verfügbar.
- **MCP-Server:** liefert zusätzliche Werkzeuge über MCP.
- **Modellprofil:** Zuordnung von Modellen zu Rollen.
- **Agentenlauf:** Ausführung eines Arbeitspakets über opencode.
- **Dashboard:** vibe-Webanwendung.
- **Runner:** von vibe gesteuerter Prozess, der Arbeitspakete, Git-Arbeitsbereiche, Prüfungen und Abschlussaktionen koordiniert.

Quellcode, Installation und Laufzeitdaten dürfen nicht miteinander verwechselt oder beim Aktualisieren gegenseitig überschrieben werden.

## Ausgangsstand und Nachweisstatus

Vorhandene Programmdateien werden unverändert importiert und durch ein SHA-256-Manifest dokumentiert.

Die bisherige Nutzerbestätigung belegt grundsätzliche Nutzbarkeit, nicht vollständige Konformität aller Funktionen.

## Funktionsumfang

### Projekte und Entwicklungsordner

- Entwicklungsordner anzeigen, hinzufügen, entfernen und erneut einlesen.
- Projekte mit Git-Metadaten oder vibe-Projektkonfiguration erkennen.
- Gleichnamige Projekte in unterschiedlichen Ordnern eindeutig identifizieren.
- Das Entfernen eines Entwicklungsordners löscht keine Projektdateien.
- Ungeeignete, allgemeine oder unzulässige Pfade verständlich ablehnen.
- Die Projektliste zeigt Name, Typ, Branch, Änderungen, offene Arbeitspakete, Laufstatus und letzten Commit.
- Das Projektdetail zeigt Pfad, Feedback, Tickets, Logs und verfügbare Aktionen.
- Das Einlesen führt keine Builds, Installationen oder Projektbefehle aus.

### Projektvorlagen

- Vibe enthält vordefinierte Projektvorlagen für gängige Softareprojekte (z.B. generic, Android, Web, etc.)
- Neue Typen sind über Vorlagen ergänzbar.
- Vorhandene Projekte können vorbereitet werden.
- Vorhandene Dateien werden dabei nicht still überschrieben.
- Projekterzeugung und Git-Initialisierung liefern verständliche Fehler.
- Projekttypen besitzen eigene Prüfadapter.

### Arbeitspakete und Feedback

- Tickets (Arbeitspakete, Bugs und Feedback) liegen einheitlich in einer lokalen, nicht versionierten, maschinenlesbaren Datei (`.vibe/tickets.json`) vor.
- Entwürfe, offene, in Arbeit befindliche, blockierte, auf Merge wartende und erledigte Tickets werden unterschieden; die Zustände gelten auch ohne GitHub-Verbindung.
- Feedback kann über die Oberfläche ergänzt werden.
- Arbeitspakete können über die Oberfläche definiert, bearbeitet und gelöscht werden; bei neuen Arbeitspaketen wird die ID automatisch vergeben, eine eigene ID bleibt möglich.
- IDs sind eindeutig; parallele Schreibvorgänge erzeugen keine Doppelungen.
- Erledigt bedeutet: Akzeptanzkriterien erfüllt und Nachweise vorhanden.
- Ein Commit allein beweist keine fachliche Erfüllung.
- Blockierte Einträge werden nicht automatisch als erledigt interpretiert.

### Agenten

- Globale und projektspezifische Agenten anzeigen und filtern.
- Agenten anlegen, lesen, bearbeiten, kopieren und löschen.
- Beschreibung, Modus, Modell, Rechte und Prompt bearbeiten.
- Strukturierte Eingabe und Rohtextbearbeitung anbieten.
- Ungültige Eingaben verändern die bestehende Datei nicht.
- Namenskonflikte und Überschattungen sichtbar machen.
- Unbekannte Felder möglichst verlustfrei erhalten.
- Vor Änderungen Sicherungen erzeugen und Wiederherstellung ermöglichen.
- Keine fest eingebauten Agentennamen für die Produktlogik.
- Coder und Reviewer werden über konfigurierbare Rollen zugeordnet.

### Modelle und Anbieter

- Modelle verfügbarer Anbieter anzeigen, nicht nur `opencode/*`.
- Modellwahl im Agenteneditor ermöglichen.
- Kostenlose und kostenpflichtige Modelle unterstützen.
- Zugangsdaten gehören nicht in Agentendateien oder dieses Repository.
- Modellliste und tatsächliche Nutzungsberechtigung sind getrennte Zustände.
- Keine kostenpflichtige Testanfrage ohne vorherigen Hinweis und Zustimmung.
- Keine erfundenen Modell-IDs oder Fähigkeiten.

### Modelltabelle

- Vibe bietet ein Modelltabelle um dem Nutzer ein Übersicht und Einschätzung der verfügbaren Modelle zu geben.
- Felder: Modell-ID, Anbieter, Verfügbarkeit, Kontext, Bildfähigkeit, Stärken, Schwächen, Tempo, Aufwand, Datenbedingungen und Preis.
- Unbekannt ist ein zulässiger und sichtbarer Wert.
- Fakten, Messungen, Nutzerberichte und Einschätzungen klar unterscheiden.
- Jede Bewertung nennt Quelle, Datum und gegebenenfalls Testmethodik.
- Preise enthalten Währung, Einheit, Eingabe- und Ausgabetarif sowie Gültigkeitsdatum.
- Cachepreise, Staffelungen und Zusatzgebühren getrennt ausweisen.
- Veraltete Daten markieren; keine ungeprüfte Übernahme früherer Tabellen.

### Modellprofile

- Profile anlegen, bearbeiten, kopieren, löschen und anwenden.
- Rollen frei konfigurierbar, mindestens Coder und Reviewer.
- Rollen können globalen oder projektspezifischen Agenten zugeordnet werden.
- Vor Anwendung eine genaue Änderungsvorschau anzeigen.
- Alle Zielagenten und Modelle vor dem ersten Schreibvorgang validieren.
- Die Anwendung ist transaktional oder bei Teilfehlern vollständig rückrollbar.
- Leere Profile gelten nicht als erfolgreich angewendet.
- Der Profilstatus zeigt Abweichungen durch spätere manuelle Agentenänderungen.
- Kostenpflichtige Profile werden deutlich markiert.
- Kein automatischer Wechsel von kostenlos auf kostenpflichtig.

### MCP-Verwaltung

- Globale und projektbezogene Server anzeigen, anlegen, bearbeiten und löschen.
- Server aktivieren und deaktivieren.
- Lokal: Programm und Argumente als Liste sowie Umgebungsvariablen verwalten.
- Remote: URL, Header und unterstützte Authentisierung verwalten.
- Weitere Felder nur anbieten, wenn die installierte Version sie unterstützt.
- Tatsächliche Konfigurationsdateien und deren Prioritäten dokumentieren.
- Unbekannte Einstellungen und Kommentare soweit möglich erhalten.
- Bei nicht verlustfrei unterstützten Dateien abbrechen oder eine konkrete Änderungsvorschau verlangen; niemals still Daten verwerfen.
- Geheimnisse maskieren und beim Speichern unverändert erhalten.
- Keine Geheimnisse in Antworten, Fehlermeldungen, Befehlsanzeigen oder Logs.

### MCP-Tests

- Vor dem Test erklären, dass Programme gestartet oder Netzverbindungen hergestellt werden; ein Verbindungscheck ist nicht garantiert nebenwirkungsfrei.
- `initialize` und `tools/list` prüfen.
- Serveridentität und Werkzeugliste anzeigen.
- Keine fachlichen Werkzeuge automatisch aufrufen.
- Fehler trennen: fehlendes Programm, Timeout, DNS/TLS, HTTP, Authentisierung, Protokoll und ungültige Konfiguration.
- Unterstützte Transportarten explizit ausweisen.
- Nicht unterstützte Transporte nicht als defekten Server darstellen.
- Tests besitzen Zeit-, Ausgabe- und Ressourcenlimits.
- Testprozesse einschließlich gestarteter Kindprozesse zuverlässig beenden.
- Testresultate sind keine Garantie, dass ein Agent alle Werkzeuge nutzen darf.
- Werkzeugfreigaben pro Agent müssen sichtbar oder nachvollziehbar sein.

### Agentenläufe und Prüfungen

- Lauf starten, beobachten, anhängen und gezielt stoppen.
- Projekt, Agent, Startzeit, Session anzeigen und zu dem jeweils aktuellen Arbeitspaket in Bezug setzen.
- Gleichzeitige Läufe verschiedener Projekte unterstützen.
- Gleiche Namen oder gleich normalisierte Namen dürfen keine Kollision erzeugen.
- Live-Logs und separate Prüfprotokolle bereitstellen.
- Eine fehlende Prüfkonfiguration ist ein Fehler, kein erfolgreicher Test.
- Wiederholungs- und Durchgangslimits konfigurierbar machen.
- Das Durchgangslimit ist kein Geldbudget und muss so beschriftet werden.
- Ein äußeres Signal (HUP, TERM, INT) beendet einen Lauf nicht spurlos: Signal, Protokollzeile und Registerzustand werden festgehalten. Eine Startprüfung kennzeichnet verwaiste `running`-Einträge des eigenen Projekts als extern beendet; fremde Projekte, laufende und nicht prüfbare Sitzungen bleiben unverändert, und es wird nie eine fremde Sitzung beendet.
- Quota- und Anmeldefehler halten einen Lauf standardmäßig sofort an. Das Verhalten ist eine ausdrückliche, globale Einstellung (`vibe limits stop|continue`, `<Zustand>/limits.json`) für alle Projekte, nicht je Projekt. `continue` behandelt den Fehler im Rahmen der vorhandenen Wiederholungslimits und protokolliert einen Hinweis. Eine fehlende oder defekte Einstellung gilt als `stop` und wird gemeldet, nie still als `continue`. Quota- und Anmeldefehler lösen weder eine Router-Neuverbindung noch eine manuelle IP-Abfrage aus.

### App beenden

- Das Beenden des Dashboards beendet sowohl vibe als auch alle bestehenden Agentenläufe.
- Das Stoppendes Harness ist eine getrennte Aktion.
- Nur eindeutig von vibe verwaltete Prozesse stoppen.
- Das Schließen eines Browser-Tabs beendet keine Hintergrundprozesse.
- Die Oberfläche erläutert diese Unterschiede.
- Tests prüfen ausdrücklich, dass kein unbeabsichtigtes Stoppen erfolgt.

### Startmenü

- Einen benutzerbezogenen Menüeintrag installieren und entfernen.
- Läuft vibe nicht: benötigte Container starten, vibe starten, Bereitschaft abwarten und Standardbrowser öffnen.
- Läuft vibe: nur die Weboberfläche öffnen.
- Mehrfachklicks erzeugen keine mehrfachen Dashboard-Prozesse.
- Eine fremde Anwendung auf dem Port gilt nicht als laufendes vibe.
- Die Instanzprüfung erfolgt über einen eindeutigen Health-Endpunkt.
- Token wird nicht protokolliert.
- Pfade mit Leerzeichen und Sonderzeichen funktionieren.
- Kein Terminalfenster im Normalbetrieb erforderlich.
- Fehler werden verständlich gemeldet und mit bereinigtem Log dokumentiert.
- Benutzerdefinierte Pfade, Ports und Container gelten konsistent.
- Die Startmenüaktion zum Beenden betrifft nur vibe.

### Diagnose

- Anwendungsvoraussetzungen getrennt von optionalen Projektwerkzeugen prüfen.
- Keine pauschale Ableitung eines Konfigurationsschemas allein aus einer angenommenen Hauptversionsnummer.
- Host- und Container-Verwechslungen erkennen.
- Schreibbarkeit, Portbelegung und benötigte Programme prüfen.
- Konkrete, kopierbare Lösungsvorschläge anbieten.

## Sicherheit und Datenintegrität

- Der Webserver bindet standardmäßig nur an Loopback. Eine ausdrückliche Netz-Bindung erfolgt nur als IP-Adressliteral; DNS-Hostnamen werden abgelehnt, um DNS-Rebinding zu verhindern.
- Eine IP-Allowlist kann Clients je IP/CIDR einschränken; Loopback bleibt immer zugelassen.
- Die Anmeldung erfolgt per Token oder Kennwort mit Session-Cookie statt dauerhaftem Token im Browser.
- Schreibende API-Aufrufe verlangen gültige Authentisierung.
- Host-/Origin-Prüfung und CSRF-Schutz sind erforderlich.
- Keine Tokens in Zugriffslogs oder Fehlermeldungen.
- Eingaben und Requestgrößen begrenzen.
- Pfad-Traversal und unerlaubte Symlink-Ziele verhindern.
- Externe Befehle mit Argumentlisten statt Shellverkettung aufrufen, soweit keine explizit konfigurierte Shellausführung erforderlich ist.
- Projektprüfbefehle und MCP-Programme als vertrauensbedürftige Ausführung behandeln.
- Dateien atomar schreiben und konkurrierende Änderungen erkennen.
- Sicherungen sind kollisionsfrei und können sensible Daten enthalten.
- Sensible Laufzeitdaten gehören auf ein geeignet geschütztes Dateisystem. Bei FUSE/NTFS dürfen nicht fälschlich wirksame Unix-Dateirechte behauptet werden.
- Keine API-Schlüssel, Tokens, globalen Konfigurationen oder persönlichen Agenten automatisch in Git übernehmen.

## Architekturziel

Schrittweise Entkopplung:

- CLI und Web-API als dünne Zugriffsschichten.
- Gemeinsame fachliche Dienste für Projekte, Agenten, Profile und MCP.
- Dateizugriffe über testbare Repository- und Storage-Funktionen.
- Geschäftslogik liefert strukturierte Ergebnisse statt stdout umzuleiten.
- Statische Frontend-Dateien von Python trennen.
- Der Import von Modulen startet weder Server, Container noch Programme.

Zielstruktur, nicht Voraussetzung für den unveränderten Erstimport:

```text
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
```

## Konfiguration und Migration

- `$VIBE` bleibt der Arbeitsbereich und ist nicht der Quellcodepfad.
- Bestehende `_toolchain`- und `_logs`-Daten bleiben bei der Übernahme unverändert.
- Persönliche Konfiguration wird niemals durch mitgelieferte Defaults ersetzt.
- Vor einer Migration: Vorschau und Sicherung.
- Installation aus dem Repository, ohne manuelles Kopieren einzelner Dateien.
- Aktualisierung und Rollback ohne Verlust persönlicher Einstellungen.
- Deinstallation entfernt keine Projekte und standardmäßig keine Nutzerdaten.
- Self-Development: Änderungen an vibe zunächst separat testen; die laufende produktive Instanz nicht während eines Agentenlaufs überschreiben.

## Qualität und Abnahme

- Unit-Tests für fachliche Logik und Validierung.
- Integrationstests für API, Storage und Prozessadapter.
- Browsertests für zentrale Workflows.
- Attrappen allein ersetzen keine Browser- oder Systemabnahme.
- Tests verwenden temporäre Verzeichnisse und eigene Ports.
- Keine Tests gegen persönliche Projekte oder produktive Konfigurationen.
- Testprotokolle nennen Befehl, Ergebnis und Grenzen des Nachweises.
- Jedes Ticket benötigt Tests, fachliche und technische Dokumentation sowie einen unabhängigen Review vor dem Abschluss.

## Nicht im Umfang

- Eigener Modellhost oder eigene Zahlungsabwicklung.
- Öffentlicher Remotezugriff auf das Dashboard.
- Mehrbenutzerbetrieb oder Cloud-Synchronisation.
- Automatische Veröffentlichung, Push, Merge oder Release ohne Freigabe oder ohne gesetztes `GITHUB_AUTO_MERGE`.
- Vollständiger Frameworkwechsel als Voraussetzung für weitere Entwicklung.

## Decisions Locked

- Bestehenden Quellcode importieren, nicht neu generieren.
- Keine Funktion als erledigt markieren, bevor sie geprüft wurde.
- Lokale Webanwendung plus CLI beibehalten.
- Funktionen inkrementell entkoppeln.
- Laufzeitdaten und Geheimnisse nicht ins Repository aufnehmen.
- Ungeprüfte Modellinformationen als unbekannt behandeln.
- Sicherheits- und Datenintegritätsfehler vor neuen Komfortfunktionen beheben.

## Git & work-package closing (runner-owned)

- Der Runner besitzt Worktrees, Branches, Mergebarkeit, Push, PR, Merge und Cleanup. Agenten erstellen, wechseln, mergen, pushen, force-pushen, rebasen oder löschen keine Branches.
- Agenten arbeiten ausschließlich im in der Aufgabe angegebenen Worktree-Pfad (`$WT`) und berühren niemals das Integrationsverzeichnis (`$P`).
- Vor dem Abschluss macht der Runner den PR mergebar, indem er `origin/<base>` abruft und in den Feature-Branch mergt (`git merge origin/<base>`; Merge, niemals Rebase).
- Bei einem Konflikt lässt der Runner den Worktree im Konfliktzustand und startet den Agenten erneut, um den Konflikt zu lösen (`git add` + `git merge --continue`). Der Runner prüft einen sauberen Merge vor dem einzelnen Push in `github-complete`.
- Im Worktree mit dem Paketpräfix committen (`<ID>:`). Nur eigene Dateien stagen; vor dem Commit `git status` und Diff prüfen.
- Das aktuelle Ticket in der Arbeitskopie (`TICKET-<ID>.json`) auf `state: done` setzen und die Nachweisfelder `commit: <hash>` und `test: <Methode oder Datei>` ausfüllen; der Runner validiert und übernimmt den Abschluss in den Ticketspeicher (`.vibe/tickets.json`).
- `docs/features/<ID>.md` erstellen und einen unabhängigen Review als `docs/reviews/<ID>-review-*.md` mit `Verdict: PASS` erhalten.
- Den Worktree sauber hinterlassen. Nicht mergen, pushen oder Branches löschen.
- Der projektbezogene Abschlussmodus wird durch `GITHUB_AUTO_MERGE` in `.vibe/project.env` gesteuert:
  - Nicht gesetzt oder `""`: PR-only — der Runner pusht, öffnet den PR und stoppt. Der Worktree bleibt registriert, bis die Eigentümerin oder der Eigentümer merged und `vibe package close <id>` ausführt.
  - `"1"`: Auto-Merge — der Runner merged den genehmigten PR (Squash), nachdem alle Gates und `ensure-mergeable` erfolgreich sind, synchronisiert Notizen und entfernt Worktree und Branch.
- Im lokalen Modus (`GITHUB_ENABLED` leer oder ohne Origin) merged der Runner den Feature-Branch lokal in den Integrations-Branch und räumt anschließend auf.
- Verifikations-Gates (`VERIFY_PACKAGE`, `VERIFY_FULL`) werden vom Runner ausgeführt; die volle Suite wird nicht erneut ausgeführt, sofern nicht ausdrücklich verlangt.
- Bei einem Merge-Konflikt in einer Reparaturrunde im Worktree lösen und erneut committen; den Merge nicht abbrechen und nicht pauschal `--ours`/`--theirs` verwenden.

## Zielgruppe und Nutzung

Die Zielgruppe von vibe sind Berater, Product Owner und Projektmanager — alle Personen, die schnell eine solide Software erstellen möchten, aber keine tiefen Entwicklungskenntnisse besitzen.

vibe dient im Unternehmen dazu, interne, solide Anwendungen schnell und einfach durch fachliche Steuerung zu entwickeln. Fachliche Nutzer beschreiben Ziele, Anforderungen und Feedback; technische Konfiguration, Agentenläufe und Prüfungen bleiben transparent steuerbar.
