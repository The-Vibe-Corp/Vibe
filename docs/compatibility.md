# opencode-Kompatibilität

Stand: 2026-10-30
Geprüfte Version: **opencode 2.1.4**
Adapter: `bin/vibe_opencode.py`
Bezug: `SPEC.md` (Abschnitte „Modelle und Anbieter“, „MCP-Verwaltung“,
„Diagnose“), `TICKETS.md` V-007

## Zweck

vibe behandelt opencode als austauschbare externe Schnittstelle. Alle Annahmen
über Unterbefehle, Ausgabeformate, Konfigurationsschema und Agentenregeln
liegen deshalb in einem Adapter. Ändert sich opencode, wird zuerst der Adapter
und diese Datei geprüft und angepasst — nicht verstreuter Code in CLI, Web-API
oder MCP-Verwaltung.

## Geprüfte Version und Verfahren

Die tatsächlich installierte Version wurde in dieser Umgebung mit dem
mitgelieferten Programm geprüft:

```
$ opencode --version
opencode v2.1.4
```

Der Adapter liest dieselbe Ausgabe, erkennt die Version mit einem festen
Muster und vergleicht sie mit dem geprüften Profil. Geprüft ist ausschließlich
die exakte Version `2.1.4`. Andere Versionen gelten als **ungeprüft**, auch
wenn sie nur eine Patch-Version abweichen.

Verfahren für eine neue Version:

1. `opencode --version` ausführen und die Version notieren.
2. `opencode models --standalone` ausführen und prüfen, dass Zeilen im Format
   `anbieter/modell` erscheinen.
3. `opencode serve --help` prüfen: Unterbefehl sowie `--hostname` und `--port`.
4. In einem temporären Projekt `opencode mcp add probe -- echo hi` ausführen
   und die geschriebene Konfiguration prüfen (Schema `mcp.servers` oder
   `mcp.<name>`).
5. Agentenregeln prüfen: Pflichtfeld `description`, erlaubte `mode`-Werte,
   Verzeichnisse `~/.config/opencode/agents` und `<projekt>/.opencode/agents`.
6. Erst danach ein neues Profil in `PROFILES` ergänzen, Tests mit einer
   Fixture dieser Version laufen lassen und diese Datei aktualisieren.

## Was der Adapter kapselt

| Bereich | Umsetzung | Geprüft |
| --- | --- | --- |
| Version | `opencode --version`, Muster `v?X.Y.Z`, exakter Profilvergleich | 2.1.4 |
| Modelllisting | `opencode models --standalone`, Zeilen `anbieter/modell` | Ausgabe in dieser Umgebung geprüft; Parser mit Fixtures getestet |
| Agenten | Verzeichnisregel und Frontmatter-Prüfung (`description`, `mode`, nichtleerer Prompt) aus dem Profil | Regeln aus vorhandenen Agentendateien abgeleitet |
| MCP-Schema | Erkennung aus der vorhandenen Konfiguration; Profil nur für leere Dateien der geprüften Version | 2.1.4 schreibt `mcp.servers` |
| Serverstart | `opencode serve --hostname <host> --port <port>` als Argumentliste | `opencode serve --help` |

### Modelllisting

Der Adapter verwendet für die geprüfte Version
`opencode models --standalone`. Der eigene Server verhindert eine Kollision mit
einem bereits laufenden verwalteten opencode-Dienst. In dieser Sitzung lieferte
der Aufruf Modell-IDs aus den verbundenen Anbietern, ohne eine Modellanfrage
auszulösen.

Unerwartete Ausgabe (Exit 0, aber keine erkennbare Modell-ID) gilt als Fehler,
nicht als leere Erfolgsliste. Ein leerer Katalog ohne Ausgabe bleibt eine
gültige leere Liste. Fehlendes Programm, Fehlercode und Zeitüberschreitung
werden getrennt gemeldet.

### MCP-Schema

`vibe_mcp` rät das Schema nicht mehr aus der Hauptversionsnummer. Die
Reihenfolge ist:

1. Vorhandene Konfiguration mit `mcp.servers` → Schema `servers`.
2. Vorhandene Konfiguration mit Serverobjekten direkt unter `mcp` → Schema
   `classic`.
3. Nicht zuordenbare Einträge unter `mcp` → Schema unbekannt; es wird nichts
   geschrieben. Das gilt auch für gemischte Blöcke mit Serverobjekten und
   weiteren Objekten, damit kein unbekannter Eintrag verloren geht.
4. Leere Konfiguration und geprüfte Version → geprüftes Schema aus dem Profil.
5. Leere Konfiguration und ungeprüfte Version → Schema unbekannt; es wird
   nichts geschrieben.

Für 2.1.4 wurde das Schema mit einer isolierten Probe bestätigt:

```
$ opencode mcp add probe -- echo hi
MCP server "probe" added to <temporäres Projekt>/opencode.json
```

Die geschriebene Datei enthielt:

```json
{"mcp": {"servers": {"probe": {"type": "local", "command": ["echo", "hi"]}}}}
```

Damit ist `mcp.servers` für 2.1.4 belegt und keine ungeprüfte Annahme.

Die tatsächlich unterstützten Felder der beiden Servertypen sind im Profil
hinterlegt (`mcp_fields`/`mcp_oauth_fields`) und werden von der
MCP-Verwaltung geprüft:

| Typ | Felder |
| --- | --- |
| `local` | `type`, `command`, `cwd`, `environment`, `enabled`, `timeout` |
| `remote` | `type`, `url`, `enabled`, `headers`, `oauth`, `timeout` |
| `oauth` | `clientId`, `clientSecret`, `scope`, `callbackPort`, `redirectUri` |

Nicht unterstützte Felder werden nicht geschrieben; bei bestehenden Einträgen
bleiben unbekannte Felder unverändert erhalten, neue unbekannte Felder und
Änderungen an vorhandenen unbekannten Feldern werden abgelehnt.

Die Listen wurden am 2026-10-30 gegen das im installierten opencode 2.1.4
(`opencode --version` → `2.1.4`) eingebettete Zod-Schema geprüft. Das Binary
enthält die Schema-Bezeichner `McpLocalConfig`, `McpRemoteConfig` und
`McpOAuthConfig`; die Definitionen nennen genau die oben gelisteten Felder.
`McpOAuthConfig.callbackPort` ist auf 1–65535 begrenzt, `McpRemoteConfig.oauth`
erlaubt ein Objekt oder `false`, und `McpLocalConfig.cwd` löst relative Pfade
vom Workspace-Verzeichnis auf. Für `timeout` nennt das Schema einen Standard
von 5000 ms; vibe schreibt das Feld nur, wenn ein Wert eingetragen ist.

### MCP-Konfigurationsdateien

`opencode mcp add` sucht die Konfiguration in dieser Reihenfolge und verwendet
die erste vorhandene Datei:

1. `<basis>/opencode.json`
2. `<basis>/opencode.jsonc`
3. `<basis>/.opencode/opencode.json`
4. `<basis>/.opencode/opencode.jsonc`

Ohne Treffer wird `<basis>/opencode.json` angelegt. Für globale Server ist
`<basis>` das opencode-Konfigurationsverzeichnis (`~/.config/opencode`), für
projektbezogene Server das Projektverzeichnis. `vibe_mcp.cfg_path()` bildet
genau diese Reihenfolge ab, damit vibe nicht eine andere Datei bearbeitet als
opencode zuerst liest.

Die Reihenfolge wurde mit dem installierten opencode 2.1.4 in einem isolierten
Projekt erneut geprüft (`HOME` und `XDG_CONFIG_HOME` in einem temporären
Verzeichnis): bei vorhandener `opencode.json` und `opencode.jsonc` schrieb
`opencode mcp add` nach `opencode.json`; ohne diese Datei nach
`opencode.jsonc`; ohne beide nach `.opencode/opencode.json`. Die Datei
`opencode.jsonc` blieb dabei jeweils unverändert.

### Verlustarme Bearbeitung

`vibe_mcp` ersetzt beim Speichern nicht den gesamten `mcp`-Block. Es ändert nur
den betroffenen Servereintrag und dessen geänderte Felder. Dadurch bleiben
JSONC-Kommentare, Trailing Commas, Formatierung und unbekannte Einstellungen
außerhalb des geänderten Feldes erhalten. Unveränderte Servereinträge werden
nicht neu geschrieben; maskierte Geheimnisse werden vor dem Schreiben aus dem
bisherigen Eintrag wiederhergestellt. Lässt sich ein maskiertes Geheimnis
nicht zuordnen (fehlender bisheriger Schlüssel oder URL-Parameter), bricht der
Schreibvorgang ab, statt `***` oder einen leeren Wert zu speichern.

### Agenten

Der Adapter liefert das Projektverzeichnis `.opencode/agents` und prüft
Frontmatter und Prompt gegen die Regeln der geprüften Version. Die globalen
Agenten liegen weiterhin unter `~/.config/opencode/agents` (über das Pfadmodell
konfigurierbar).

`opencode debug agents` konnte in dieser Sitzung nicht als Quelle verwendet
werden: Der Unterbefehl benötigt den verwalteten opencode-Dienst, dessen Port
im laufenden opencode-Kontext bereits belegt war. Die Agenten werden deshalb
weiterhin aus den opencode-Markdown-Dateien gelesen; die Regeln dafür sind
zentral im Adapter hinterlegt.

### Serverstart

Für 2.1.4 ist der Unterbefehl `serve` geprüft (`opencode serve --help` nennt
`--hostname` und `--port`). Der Adapter baut eine Argumentliste; der
tmux-Aufruf quotet sie mit `shlex.join`. Der frühere, ungeprüfte Aufruf
`opencode web` entfällt.

## Unbekannte Versionen

Unbekannt bedeutet in diesem Adapter:

- Ausgabe nicht lesbar (kein `X.Y.Z`),
- Version nicht im geprüften Profil,
- opencode fehlt, endet mit Fehlercode oder antwortet nicht rechtzeitig.

Verhalten:

- `vibe doctor` zeigt die erkannte Version und den Status als Prüfung an.
- Modelllisting wird bei einer lesbaren, aber ungeprüften Version weiterhin
  versucht; das Ergebnis trägt eine Warnung.
- Serverstart und versionabhängige MCP-Schreibvorgänge werden mit einer
  verständlichen Meldung abgelehnt, die die geprüfte Version nennt.
- Vorhandene MCP-Konfigurationen werden weiterhin gelesen, wenn ihr Schema
  eindeutig erkennbar ist.

## Grenzen

- Die Prüfung bezieht sich auf die CLI von opencode, nicht auf jede
  Weboberfläche oder API-Version.
- `opencode models` kann je nach Anbieter-Anmeldung unvollständig sein; die
  Liste ist keine Nutzungsberechtigung.
- Neue opencode-Versionen werden nicht automatisch als kompatibel behandelt.
- Agentenregeln und das Projektverzeichnis `.opencode/agents` gelten derzeit
  unabhängig von der erkannten Version. Eine unbekannte Version wird dort
  nicht geprüft; diese Versionsprüfung gehört zu V-010.
- `vibe models` zeigt nur die Liste. Fehler- und Warnmeldungen des Adapters
  (fehlendes Programm, ungeprüfte Version) erscheinen über `vibe doctor`;
  die Modellansicht bleibt bei einem Fehler leer.
- Zwei ältere Aufrufe umgehen den Adapter weiterhin: `opencode session list`
  im Projektmenü und `opencode run --standalone` beim Agentenstart. Beide
  gehören nicht zu den in V-007 genannten Bereichen und werden in einem
  Folgepaket übernommen.
- Die Tests des Adapters verwenden Fixtures und Attrappen; sie ersetzen keine
  manuelle Prüfung einer neu installierten Version nach dem oben genannten
  Verfahren.
