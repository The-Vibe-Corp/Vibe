# Entwicklung

Vibe wird inkrementell weiterentwickelt. Der bestehende Quellcode ist Ausgangspunkt; ein vollständiger Rewrite erfordert ein explizit genehmigtes Migration Ticket. [cite:1]

## Repository klonen

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
```

## Zielstruktur

Die angestrebte Struktur trennt Anwendung, Web-Oberfläche, Daten, Templates, Skripte, Tests und Dokumentation. [cite:1]

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

## Architekturprinzipien

- CLI und Web-API bleiben schlank.
- Domänen-Services werden für Projekte, Agenten, Profile und MCP geteilt.
- Dateizugriff liegt hinter testbaren Repository- und Storage-Funktionen.
- Business Logic liefert strukturierte Ergebnisse statt stdout zu capturen.
- Statische Frontend-Dateien sind vom Python-Code getrennt.
- Das Importieren von Modulen darf keine Server, Container oder Programme starten. [cite:1]

## Tests

Vibe verwendet drei Testebenen:

| Testart | Zweck |
|---|---|
| **Unit tests** | Domänenlogik und Validierung |
| **Integration tests** | API, Storage und Prozess-Adapter |
| **Browser tests** | Zentrale Workflows |

Mocks ersetzen keine Browser- oder System-Akzeptanztests. Tests verwenden temporäre Verzeichnisse und dedizierte Ports, nicht persönliche Projekte oder Produktionskonfiguration. [cite:1]

## Qualitätskriterien

Jedes Ticket benötigt funktionale und technische Nachweise sowie ein unabhängiges Review. Geändertes testbares Verhalten muss durch geeignete Tests demonstriert werden. [cite:1]

Bestehende Tests genügen, wenn sie ausgeführt wurden und das Kriterium belegen. Für Änderungen ohne relevantes Laufzeitverhalten wird ein angemessener alternativer Check dokumentiert. [cite:1]

Verifikationsrecords dokumentieren Command, Ergebnis und Grenzen des Nachweises. [cite:1]

## Locked Decisions

- Bestehenden Quellcode importieren, nicht regenerieren.
- Funktionalität nicht als complete markieren, bevor sie verifiziert wurde.
- Lokale Web-Anwendung und CLI beibehalten.
- Features inkrementell entkoppeln.
- Runtime-Daten und Secrets aus dem Repository halten.
- Unverifizierte Modellinformationen als unknown markieren.
- Security- und Data-Integrity-Defekte vor Convenience-Features addressieren. [cite:1]

## Beitragen

Beiträge folgen den Richtlinien in [`CONTRIBUTING.md`](../CONTRIBUTING.md). Bitte halte Pull Requests fokussiert, beschreibe das gelöste Problem und liefere geeignete Tests beziehungsweise Nachweise. [cite:1]
