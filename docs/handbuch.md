# Handbuch

Stand: 2026-11-03
Gilt für: vibe 0.18.0 (Repositorystand, siehe `VERSION`)

Dieses Handbuch beschreibt die tägliche Bedienung von vibe über die
Weboberfläche und die CLI. Technische Details zu Pfaden, Prozessen,
Installation und Diagnose stehen in `docs/betrieb.md`. Bekannte Grenzen und
nicht zugesagte Funktionen stehen in `docs/grenzen.md`.

## Was vibe ist

vibe ist eine lokale Entwicklungszentrale für KI-gestützte Projekte. Es
verwaltet Entwicklungsordner, Projekte, Arbeitspakete, Feedback, Agenten,
Modelle, MCP-Server, Agentenläufe und Prüfungen. Die Weboberfläche läuft nur
auf Loopback; opencode bleibt eine getrennte, austauschbare
Ausführungsschnittstelle.

## Voraussetzungen

- Bazzite-Host mit Distrobox und einem Steuerungscontainer
  (Standard: `android-dev`).
- Python 3 im Container, `git`, `tmux` und `flock`.
- Ein aktueller Browser (getestet mit Chromium 153).
- opencode für Agentenläufe; geprüft ist Version 2.1.4. Eine abweichende
  Version wird als ungeprüft gemeldet, nicht stillschweigend als kompatibel
  behandelt.

## Starten

Über das Bazzite-Startmenü oder direkt:

```
vibe ui            # Dashboard starten und URL mit Token ausgeben
vibe ui stop       # ausschließlich das Dashboard beenden
```

Läuft das Dashboard bereits, öffnet der Starter nur den Browser. Ein fremder
Dienst auf dem Dashboard-Port wird erkannt und nicht übernommen. Details:
`docs/features/V-017.md`.

Nach dem Start zeigt die Konsole eine URL der Form
`http://127.0.0.1:8787/#t=<token>`. Das Token wird nicht in Logs geschrieben.
Ein direkter Aufruf ohne Token wird abgewiesen.

## Orientierung in der Oberfläche

Die Kopfzeile hat fünf Bereiche:

| Bereich | Inhalt |
| --- | --- |
| Projekte | Projektliste, Entwicklungsordner, neues Projekt |
| Agenten & Modelle | globale und projektbezogene Agenten, Modellkatalog, Profile |
| MCP-Tools | MCP-Server anzeigen, bearbeiten, testen |
| Umgebung | Release, Umgebungsprüfung, Fritzbox-Reconnect |
| Kosten | Tokens und Kosten je Arbeitspaket und Projekt |

Rechts oben stehen opencode- und Dashboard-Zustand. Rückfragen erscheinen als
hervorgehobene Karte oberhalb des Arbeitsbereichs und bleiben sichtbar, bis sie
beantwortet sind.

## Projekte

### Entwicklungsordner und Projekte

- „Einlesen“ fügt einen Entwicklungsordner hinzu; „Neu einlesen“ aktualisiert
  die Liste. Das Einlesen führt keine Builds oder Projektbefehle aus.
- Gleichnamige Projekte in unterschiedlichen Ordnern bleiben getrennt.
- Das Entfernen eines Entwicklungsordners löscht keine Projektdateien.
- Ein Punkt ● neben dem Namen bedeutet: noch nicht für vibe vorbereitet.
  „Für vibe vorbereiten“ ergänzt fehlende Dateien, ohne vorhandene zu
  überschreiben.

### Neues Projekt

Name (a-z, 0-9, `-`), Typ und optional eine Android-Vorlage wählen. „Anlegen und
Assistent öffnen“ startet direkt den Projektassistenten. Typen:
`vibe types`. Eigene Typen entstehen über Vorlagen unter `templates/`.

### Projektdetail

Das Detail gliedert sich in vier Register:

| Register | Inhalt |
| --- | --- |
| Arbeit | offene Pakete, Feedback, Arbeitspakete, Bugmeldung, Pause, Prüfungen, Projektdaten |
| Ausgabe | Live-Log des Laufs oder der Prüfung, Pause, Fortsetzen, Vollbild |
| Assistent | fachliche Schritte für ein neues Projekt, Entwurf von SPEC und Agenten |
| Einstellungen | Projektagenten, Schreibrechte, Shell-Sandbox |

Die Register lassen sich mit Maus und Tastatur bedienen (Pfeiltasten, Home,
Ende). Kopfaktionen und Laufzustand bleiben in jedem Register sichtbar.

## Arbeiten mit Paketen und Feedback

- **Feedback** wird direkt im Projektdetail erfasst. Es gilt als offener Punkt
  und zählt in der Projektliste mit.
- **Arbeitspakete** werden im Register „Arbeit“ angelegt, bearbeitet und
  gelöscht. Die ID vergibt der Nutzer; die Reihenfolge bleibt erhalten.
- **Bugs** werden als Feedback mit `Art: Bug` gemeldet.
- Erledigte Einträge sind standardmäßig ausgeblendet. Ein erledigter Eintrag
  ohne Nachweis bleibt sichtbar und bearbeitbar.
- `BLOCKIERT` bleibt offen und wird nicht als erledigt interpretiert.

## Agentenläufe

```
vibe run <projekt> [agent]   # Lauf in tmux starten
vibe attach <projekt>        # an den Lauf anhängen
vibe logs <projekt>          # Lauf-Log verfolgen
vibe stop <projekt> [lauf]   # nur diesen Lauf beenden
vibe pause <projekt> [on|off]
vibe runs [list|prune]       # Läufe anzeigen; verwaiste Einträge aufräumen
```

- Ein Lauf hat eine eindeutige ID, ein eigenes Log und ein eigenes
  Prüfprotokoll. Gleichnamige Projekte kollidieren nicht.
- „Pause“ stoppt den laufenden Agenten nicht. Nach dem aktuellen Arbeitspaket
  wird kein neues begonnen; die Anforderung gilt einmalig.
- „Stoppen“ beendet ausschließlich den gewählten Lauf.
- `vibe runs` zeigt Registereinträge mit Zustand, Sitzungsstatus und
  Projektpfad. `vibe runs prune` markiert Einträge, deren tmux-Sitzung nicht
  mehr existiert, als beendet – auch wenn das Projektverzeichnis fehlt. Es
  werden dabei niemals Sitzungen beendet.
- „Dashboard beenden“ beendet weder Agentenläufe noch opencode. opencode wird
  getrennt über `vibe server stop` beendet.

### Rückfragen und autonomer Modus

Ein Agent kann mit `vibe ask "Frage" --option "A" --option "B"` eine Rückfrage
stellen. Sie erscheint im Dashboard und kann dort mit Option oder Freitext
beantwortet werden. Im autonomen Modus entscheidet der Agent selbst und
dokumentiert die Entscheidung:

```
vibe autonomous on|off|status [--projekt <p>]
vibe questions
vibe answer <id> --option 1 --by nutzer
```

## Prüfungen

Pro Projekt sind `quick` und `full` konfiguriert (`.vibe/project.env`). Die
Ausgabe erscheint im Register „Ausgabe“. Exitcodes werden unverändert
angezeigt; ein fehlender Prüfbefehl ist ein Fehler, kein Erfolg. Details zur
Prüfumgebung: `docs/betrieb.md`, Abschnitt „Prüfungen und Nachweise“.

## Agenten, Modelle und Profile

- Globale Agenten liegen unter `~/.config/opencode/agents`, Projektagenten
  unter `<projekt>/.opencode/agents`. Projektagenten überschreiben gleichnamige
  globale Agenten; die Oberfläche macht die tatsächliche Priorität sichtbar.
- Der Agenteneditor bietet strukturierte Felder und Rohtext. Ungültige Eingaben
  verändern die bestehende Datei nicht. Vor Änderungen entstehen Sicherungen;
  `vibe agent backups|restore` stellt sie wieder her.
- Der Modellkatalog trennt Fakten, Messungen und Einschätzungen und nennt
  Quelle und Datum. „Unbekannt“ ist ein zulässiger Wert.
- Modellprofile ordnen Modelle Rollen zu. Die transaktionale Anwendung mit
  vollständiger Vorvalidierung und Rollback ist noch nicht abgeschlossen
  (V-012); siehe `docs/grenzen.md`.

### AGENTS.md (Regeln für Agenten)

Jedes Projekt hat eine `AGENTS.md`. Sie entsteht beim Anlegen aus der Vorlage
des Projekttyps (`templates/<typ>/AGENTS.md`, bei unbekannten Typen
`templates/generic`). Darin stehen projektspezifische Hinweise und ein von vibe
verwalteter Block mit den gemeinsamen Regeln für Projektordner, Git-Ordnung,
Coding-Leitlinien und den unabhängigen Test-Agenten.

Den verwalteten Block bringt vibe bei jedem Agentenlauf auf den aktuellen
Stand. Inhalte außerhalb des Blocks bleiben dabei erhalten; nicht committete
Änderungen werden vor einem Lauf gemäß F27 geschützt.

Im Projektdetail unter „Assistent“ zeigt die Karte „AGENTS.md — Regeln für
Agenten“ den Inhalt:

- Die beiden Textfelder enthalten die freien Teile vor und nach dem
  verwalteten Block. Sie lassen sich bearbeiten; „Speichern“ schreibt die
  Datei.
- Der verwaltete Block steht schreibgeschützt zwischen den Textfeldern. Er
  wird nicht über die Oberfläche geändert, weil der nächste Agentenlauf ihn
  ohnehin ersetzt.
- Fehlt die Datei, legt „Aus Vorlage anlegen“ sie aus der Typvorlage an.
- Eine obere Textarea bleibt leer und ist deaktiviert, solange die Datei keinen
  verwalteten Block enthält.

## MCP-Server

```
vibe mcp list|show|test|on|off|rm|backups|restore [name] [global|<projekt>]
```

- Lokale Server: Programm und Argumente als Liste, Umgebungsvariablen.
- Remote Server: URL, Header, unterstützte Authentisierung.
- Vor dem Test wird erklärt, dass ein Programm gestartet oder eine
  Netzverbindung aufgebaut wird. Der Test prüft nur `initialize` und
  `tools/list`, keine fachlichen Werkzeuge.
- Maskierte Geheimnisse bleiben beim Speichern unverändert. Nicht
  unterstützte Felder werden nicht blind angeboten.

## Kosten

„Kosten“ zeigt Tokens und Kosten je Arbeitspaket und Projekt. Unbekannte Preise
bleiben unbekannt; eingegebene Preise überschreiben sie nachvollziehbar. Der
Katalog enthält keine erfundenen Preise.

## Umgebung und Release

„Umgebung“ zeigt:

- die Releasebasis: Version, Commit und Herkunft der Kennung (Installation oder
  Quelle),
- die Umgebungsprüfung (`vibe doctor`): Container, Schreibbarkeit, Werkzeuge,
  opencode-Version, KVM, Android-Umgebung, Prüfdateien, Katalog, freier Platz,
- den optionalen Fritzbox-Reconnect (standardmäßig aus).

`/api/health` liefert dieselbe Releasekennung ohne Geheimnisse und dient dem
Starter zur Erkennung einer echten vibe-Instanz.

## Beenden und Daten

- Dashboard: Knopf im Dashboard oder `vibe ui stop`.
- opencode: `vibe server stop`.
- Agentenlauf: `vibe stop <projekt> [lauf]`.
- Laufzeitdaten und Sicherungen bleiben bei einem Update und bei einem
  Uninstall erhalten. Wo sie liegen und wie sie gesichert werden, steht in
  `docs/betrieb.md`.

## Weiterlesen

- `docs/betrieb.md` — Betrieb, Diagnose, Installation, Release.
- `docs/grenzen.md` — bekannte Grenzen und nicht zugesagte Funktionen.
- `docs/checkliste.md` — Abnahmecheckliste mit Versionen und Ergebnissen.
- `docs/abnahme-bazzite.md` — dokumentierte manuelle Bazzite-Prüfung.
- `docs/features/V-020.md` — fachliche und technische Dokumentation dieses
  Arbeitspakets.
