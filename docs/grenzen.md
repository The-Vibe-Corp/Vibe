# Bekannte Grenzen

Stand: 2026-11-03
Gilt für: vibe 0.18.0 (Repositorystand, siehe `VERSION`)

Diese Datei veröffentlicht Grenzen, die für den Betrieb wichtig sind. Sie
ersetzt keine Tickets: offene Arbeitspakete bleiben in `TICKETS.md` sichtbar.
Alles hier Genannte ist bewusst nicht zugesagt, bis ein Ticket es ändert.

## Offene Funktionen

- **Modellprofile sind nicht transaktional (V-012).** `vibe profile use`
  validiert alle zugeordneten Modelle vor dem ersten Schreibvorgang und
  verweigert nicht verfügbare Modelle. Es gibt aber keine vollständige
  Änderungsvorschau und keinen Rollback, wenn ein späterer Schreibvorgang
  fehlschlägt. Ein Profil ohne gesetzte Modelle wird mit übersprungenen
  Agenten gemeldet, nicht als Fehler. Abweichungen durch spätere manuelle
  Agentenänderungen werden nicht angezeigt. V-012 ist in `TICKETS.md` offen.
- Die Oberfläche ist deutschsprachig; weitere Sprachen sind nicht umgesetzt.
- Ein öffentlicher oder entfernter Zugriff auf das Dashboard ist nicht
  vorgesehen. Es gibt keinen Mehrbenutzerbetrieb und keine Cloud-Synchronisation.

## opencode-Abhängigkeit

- Geprüft ist ausschließlich **opencode 2.1.4** (`docs/compatibility.md`). Die
  Entwicklungsumgebung dieses Pakets hatte 2.2.5 installiert; `vibe doctor`
  meldet sie ausdrücklich als ungeprüft. Versionsabhängige Schreibvorgänge
  (z. B. das MCP-Schema unbekannter Versionen) werden nicht erzwungen.
- Seit F26 gilt für lesbare, nicht exakt geprüfte Versionen (z. B. 2.2.6 nach
  einem Update): vibe behandelt sie als vermutlich kompatibel, verwendet das
  am besten passende geprüfte Profil und meldet die ungeprüfte Version in
  Doctor, Agentenverwaltung, Modelllisting, MCP-Speicherung und Serverstart.
  Ohne lesbare Version bleiben Schreib- und Startvorgänge gesperrt.
- Agentenregeln, Modelllisting und MCP-Schema werden über einen Adapter
  gekapselt. Änderungen an opencode können den Adapter dennoch brechen; dann
  ist zuerst `docs/compatibility.md` zu befolgen.
- Fehlende Anbieteranmeldung und fehlende Modellberechtigung sind getrennte
  Zustände. vibe prüft keine OAuth-Anmeldung und führt keine
  kostenpflichtigen Testanfragen aus.

## Browserabnahme

- Die automatisierten Browsertests laufen mit **Chromium 153 über Playwright
  1.63**. Firefox, WebKit, Safari und mobile Browser sind nicht automatisiert
  geprüft.
- Die Tests decken die zentralen Abläufe und viele Einzelfunktionen ab, aber
  nicht jeden Bedienpfad. Ein grüner Browsertest beweist keine vollständige
  visuelle oder barrierefreie Konformität.
- Screenshots in `docs/features/` sind Nachweise einzelner Läufe, keine
  fortlaufend aktualisierte Bilddokumentation.
- Die manuelle Bazzite-Abnahme (Starter, Container aus/an, Fremddienst,
  Doppelklick, Tokenwechsel) ist in `docs/abnahme-bazzite.md` dokumentiert.
  Sie verwendet Attrappen für Browser und Notifier; ein echter Klick im
  GNOME-Menü wurde nicht ausgeführt.

## Plattformen und Dateisysteme

- Agentenläufe benötigen `tmux` und `flock`. Unter Windows ist dafür WSL2
  oder Docker nötig; der Setup weist darauf hin. Windows ist kein getesteter
  Laufzeitstand für Agentenläufe.
- Auf FUSE/NTFS sind Unix-Dateirechte, Atomarität und `fsync` nicht
  zusicherbar. vibe behauptet dort keine wirksamen Rechte. Laufzeitdaten und
  Sicherungen gehören auf ein geeignet geschütztes Dateisystem.
- Die Shell-Sandbox benötigt `bubblewrap`. Ist sie nicht verfügbar oder nicht
  wirksam, meldet die Sandbox das; ein sandboxed Lauf ist kein vollständiger
  Schutz gegen einen kompromittierten Agenten.
- Der Bazzite-Starter prüft den Port als Momentaufnahme. Zwischen
  Health-Prüfung und Browseröffnung kann ein anderer Prozess den Port belegen.

## MCP

- Der Verbindungstest prüft `initialize` und `tools/list`. Er beweist nicht,
  dass ein Agent alle Werkzeuge nutzen darf, und ruft keine fachlichen
  Werkzeuge auf.
- OAuth-Anmeldungen führt vibe nicht durch. Server mit Schlüssel im Header
  können ohne OAuth konfiguriert werden.
- Nicht unterstützte Transporte werden als solche gemeldet, nicht als
  defekter Server.
- Geheimnisse werden maskiert; auf FUSE/NTFS ist der Schutz der
  Konfigurationsdateien nicht zusicherbar.

## Modelle und Kosten

- Der mitgelieferte Modellkatalog ist ein belegter Stand (Quellen und Datum je
  Angabe), keine Live-Abfrage. Preise und Fähigkeiten können veralten.
- Unbekannte Preise bleiben unbekannt und werden nicht geschätzt. Eingegebene
  Preise sind Nutzerangaben.
- Die Kostenermittlung liest die opencode-Datenbank nur lesend. Sie ist keine
  Abrechnung und kein Geldbudget.

## Release und Reproduzierbarkeit

- Eine Release wird aus einem Git-Stand gebaut. Nicht committete Änderungen
  sind nicht enthalten; das ist beabsichtigt und keine Grenze der Prüfung.
- Die Byte-Gleichheit gilt für denselben Commit und dieselbe Python-/gzip-
  Implementierung. Andere Kompressionsbibliotheken können abweichende, aber
  inhaltlich gleiche Archive erzeugen.
- Die Releaseprüfung ist eine Heuristik für offensichtliche Geheimnisse und
  absolute Home-Pfade. Sie ersetzt kein vollständiges Secret-Scanning und keine
  juristische Prüfung.
- Symbolische Links und Untermodule im Git-Stand werden nicht in eine Release
  übernommen; der Bau bricht mit einer Meldung ab, statt den Inhalt still zu
  verfälschen.
- Push, Merge und Veröffentlichung erfolgen nie automatisch.

## Trilium

Die fachliche Dokumentation liegt zusätzlich in Trilium. Ist der MCP-Zugang
nicht verfügbar, wird das als Blockierung gemeldet und nicht durch eine lokale
Datei ersetzt.
