# Handbuch

Stand: 2026-11-21
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
vibe ui password   # Anmeldekennwort anzeigen (gesetzt / nicht gesetzt)
vibe ui password set      # Kennwort unsichtbar eingeben und bestätigen
vibe ui password clear    # Kennwort entfernen
```

Das Kennwort wird unsichtbar eingegeben und nie als Befehlszeilenargument
entgegen genommen; für Skripte liest `vibe ui password set --stdin` genau eine
Zeile von der Standardeingabe. Es ist mindestens 8 Zeichen lang und liegt nur
als gesalzener Hash in `ui.json`. Ein laufendes Dashboard übernimmt die
Änderung bei der nächsten Anmeldung, ohne neu gestartet zu werden. Details:
`docs/features/AP18.md`.

Läuft das Dashboard bereits, öffnet der Starter nur den Browser. Ein fremder
Dienst auf dem Dashboard-Port wird erkannt und nicht übernommen. Details:
`docs/features/V-017.md`.

Nach dem Start zeigt die Konsole eine URL der Form
`http://127.0.0.1:8787/#t=<token>`. Das Token wird nicht in Logs geschrieben.
Ein direkter Aufruf ohne Token wird abgewiesen.

Statt mit dem Token kann die Anmeldung auch über das Anmeldekennwort
erfolgen, sobald es gesetzt ist (`vibe ui password set`, siehe oben). Beide
Wege stellen dieselbe Sitzung; das Kennwort lässt sich jederzeit ändern oder
entfernen.

## Orientierung in der Oberfläche

Die Kopfzeile hat fünf Bereiche:

| Bereich | Inhalt |
| --- | --- |
| Start | Projektliste, angeheftete Projekte, Entwicklungsordner, neues Projekt |
| Agenten | globale und projektbezogene Agenten, Modellkatalog, Profile |
| Aktivität | laufende und beendete Läufe, offene Rückfragen |
| Auswertungen | Kosten, Laufregister, Umgebung |
| Einstellungen | globale AGENTS.md, Darstellung, Zugriff, Laufverhalten, Schranken, Modelle, Profile, MCP, Harness |

Eine statische Seitenleiste gibt es nicht. Ergänzende Inhalte – etwa das
Postfach der Rückfragen, ein Bearbeitungsformular oder der Preis-Editor –
öffnen sich im situativen Panel am rechten Rand und schließen mit ×, Escape
oder einem Klick auf den Hintergrund.

Benachrichtigungen gibt es an genau einer Stelle: kurzlebige Hinweise
erscheinen oben rechts unter der Glocke und werden zusätzlich als Eintrag in
der Glocke gespeichert. Jeder Eintrag lässt sich einzeln schließen, „Alle als
gelesen“ leert die Liste, und der Zähler zeigt die ungelesenen Einträge.

Rückfragen von Agenten sind zentral sichtbar: als Banner unter der Kopfzeile,
als hervorgehobener Zähler in der Kopfzeile, als Eintrag in der Glocke und als
Postfach im situativen Panel. Antworten erfolgen per Option oder Freitext und
entfernen die Frage, ohne die Ansicht neu zu laden. Rechts oben stehen
opencode- und Dashboard-Zustand.

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

Das Detail gliedert sich in fünf Register:

| Register | Inhalt |
| --- | --- |
| Überblick | autonomer Modus, Kacheln zum Zustand, letztes Arbeitspaket, Sitzungen mit Fortsetzen |
| Arbeit | Pakete, Bugs und Feedback in einer filterbaren Liste, Priorisierung |
| Ausgabe | Live-Log, Agentenübersicht, Fokus, Fortsetzen, Stoppen |
| Assistent | fachliche Schritte für ein neues Projekt, Entwurf von SPEC und Agenten |
| Einstellungen | AGENTS.md, Basics, Sandbox, Team, GitHub, Schreibzugriff, Session-Limit |

Die Register lassen sich mit Maus und Tastatur bedienen (Pfeiltasten, Home,
Ende). Kopfaktionen und Laufzustand bleiben in jedem Register sichtbar.

## Arbeiten mit Paketen und Feedback

- **Arbeitspakete**, **Bugs** und **Feedback** stehen im Register „Arbeit“ in
  einer gemeinsamen, filterbaren Liste. Ein Badge und eine farbige Kante
  unterscheiden die Typen; die Bedienung ist für alle gleich.
- Eine Suche filtert die Liste und schließt erledigte Einträge ausdrücklich
  ein, auch wenn „Erledigte anzeigen“ ausgeschaltet ist.
- Die Priorisierung enthält alle offenen Einträge; manuell priorisierte stehen
  oben, erledigte und geschlossene nie. Beim Ziehen zeigt eine Einfügemarke die
  Zielposition, die neue Reihenfolge wird nach dem Ablegen sofort gespeichert.
- Abgeschlossene Einträge bleiben als Nachweis erhalten und lassen sich nicht
  löschen; offene bleiben löschbar.
- Ein **Entwurf** ist noch nicht zur Bearbeitung freigegeben. **Ohne Nachweis**
  bedeutet, dass ein erledigter Eintrag weder Prüfung noch Commit vorweisen
  kann. Beides erklärt ein Tooltip direkt am Eintrag.
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
- „Aktivität“ zeigt laufende und beendete Läufe mit Projekt, Zustand und
  „Öffnen“. „Auswertungen → Läufe“ bietet dasselbe Register mit Suche und
  Statusfilter sowie „Verwaiste beenden“ (prüft die tmux-Sitzung) und
  „Abgeschlossene entfernen“ (löscht nur beendete Einträge).

### Rückfragen und autonomer Modus

Ein Agent kann mit `vibe ask "Frage" --option "A" --option "B"` eine Rückfrage
stellen. Sie ist im Dashboard zentral sichtbar – Banner unter der Kopfzeile,
Zähler in der Kopfzeile, Eintrag in der Glocke und Postfach im situativen
Panel – und lässt sich dort mit Option oder Freitext beantworten. Im autonomen
Modus entscheidet der Agent selbst und dokumentiert die Entscheidung:

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

## Einstellungen

Die Einstellungen nutzen den verfügbaren Platz über eine eigene Navigation und
gliedern sich in zehn Bereiche:

| Bereich | Inhalt |
| --- | --- |
| Globale AGENTS.md | Regeln für alle Projekte, einklappbar, mit Vorlage und Sicherung |
| Darstellung | Akzentfarbe (Farbmuster mit Vorschau), Sprache, Währung und Kurs |
| Zugriffssicherheit | Anmeldung, Token und Kennwort |
| Funktionen | optionale Funktionsschalter |
| Laufverhalten | was ein neuer Lauf tut: fortsetzen oder stoppen |
| Schranken | Werte global oder je Projekt, mit Herkunft und Abweichung |
| Modelle | Katalog, Preise und Quellen, aufklappbar |
| Profile | Rollen je Profil, anwenden mit Vorschau |
| MCP-Server | Karten mit Status, Umschalter, Test, Bearbeiten im Panel |
| Harness | Auswahl opencode oder Pi |

„Schranken“ speichert alle Werte einer Ansicht gemeinsam und atomar; ein
ungültiger Wert ändert nichts. Kosten, Laufregister und Umgebung liegen nicht
mehr in den Einstellungen, sondern unter „Auswertungen“.

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
`templates/generic`). Darin stehen ausschließlich projektspezifische Hinweise.

Die verbindlichen Regeln für laufzeitgesteuerte Agentenarbeit (Arbeitskopie,
Prüfungen, Nachweise, Review, Ticketabschluss und Git-Operationen des Läufers)
liefert vibe getrennt: Der Läufer schreibt sie bei jedem opencode-Lauf als
versteckte Datei `platform_instructions.md` in den Zustandsordner und übergibt
sie opencode als zusätzliche `instructions`-Quelle. Sie liegen außerhalb jedes
Projekts und der persönlichen opencode-Konfiguration und haben höhere Priorität
als eine `AGENTS.md`. `vibe init`, `vibe new` und `vibe clone` ergänzen in
`AGENTS.md` keinen Regelblock; vorhandene Dateien bleiben unverändert.

Im Projektdetail unter „Einstellungen“ steht die Karte „AGENTS.md“ als erster
Bereich und zeigt den Inhalt:

- Die beiden Textfelder enthalten die freien Teile vor und nach einem noch
  vorhandenen Legacy-Block. Beide Teile sind immer bearbeitbar; „Speichern“
  schreibt die Datei.
- Ein Legacy-Block (`<!-- vibe:general-rules -->` bis
  `<!-- /vibe:general-rules -->`) aus älteren Projekten bleibt beim Speichern
  byte-identisch erhalten und wird nicht über die Oberfläche geändert. Neue
  Dateien enthalten keinen solchen Block.
- Fehlt die Datei, legt „Aus Vorlage anlegen“ sie aus der Typvorlage an.

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

„Auswertungen → Kosten“ zeigt Tokens und Kosten je Projekt und Arbeitspaket,
aufgeschlüsselt nach Eingabe, Cache und Ausgabe, mit Monatssummen und dem
Anteil am Gesamtbetrag. Fehlt ein Preis, markiert die Zeile „Preis fehlt“ und
verlinkt in den Preis-Editor. Die Währung (EUR/USD samt Umrechnungskurs) wird
unter „Einstellungen → Darstellung“ gewählt. Unbekannte Preise bleiben
unbekannt; eingegebene Preise überschreiben sie nachvollziehbar. Der Katalog
enthält keine erfundenen Preise.

## Umgebung und Release

„Auswertungen → Umgebung“ zeigt:

- die Releasebasis: Version, Commit und Herkunft der Kennung (Installation oder
  Quelle),
- die Umgebungsprüfung (`vibe doctor`): Container, Schreibbarkeit, Werkzeuge,
  opencode-Version, KVM, Android-Umgebung, Prüfdateien, Katalog, freier Platz,
- den optionalen Fritzbox-Reconnect (standardmäßig aus).

`/api/health` liefert dieselbe Releasekennung ohne Geheimnisse und dient dem
Starter zur Erkennung einer echten vibe-Instanz.

### Harness auswählen (opencode/Pi)

Neben opencode (Standard und Initialwert) ist Pi verfügbar, wenn das Programm
im PATH liegt: `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`.
Nicht installierte Harnesses erscheinen deaktiviert mit der Anzeige
„(nicht installiert)“; die Statuszeilen der Harnesses werden „Installiert“
oder „Nicht installiert“ nennbar. Für nicht installierte Harnesses ist ein
Installieren-Knopf sichtbar: Er führt den Registry-Befehl aus, prüft danach
erneut (npm läuft, Version wird geprüft) und meldet Rückmeldung im
Feedback-Bereich — bei Erfolg ist die Option aktiviert und der Status
„Installiert“. Das Speichern eines nicht installierten Harness als Auswahl
wird abgelehnt („Auswahl nicht gespeichert.“); die Ansicht zeigt immer den
tatsächlich persistierten Zustand (`harness.json`), nicht den lokalen
Wunschzustand. Das CLI `vibe harness use` bleibt unverändert.

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
