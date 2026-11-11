# Sicherheitsrichtlinie

## Unterstützte Versionen

Der Support erfolgt für den aktuellen Stand des Haupt-Branchs. Ältere
Versionen oder Release-Archive werden nicht gepflegt; bitte vor einer Meldung
auf den neuesten Stand aktualisieren.

## Melden

Bitte melde Sicherheitsprobleme nicht in einem öffentlichen Issue.

- Bevorzugter Weg: GitHub-Funktion „Private vulnerability reporting“ im
  Repository (Tab „Security“).
- Alternativ: privater Kontakt zum Repository-Eigner (M0P) über GitHub.

Nenne in der Meldung nach Möglichkeit: betroffene Komponente, betroffene
Version/Commit, Schritte zur Reproduktion, erwartetes statt beobachtetes
Verhalten und eine Einschätzung des Risikos. Geheimnisse (Tokens, Passwörter)
gehören in keine Meldung — maskiere sie.

## Umgang

Der Eigner prüft die Meldung, hält den Melder auf dem Laufenden und
veröffentlicht eine Korrektur mit Danksagung, sobald ein Fix bereitsteht.

## Umfang und Hinweise

vibe läuft als lokale Anwendung (Dashboard nur auf Loopback) und verwaltet
keine eigenen Nutzerkonten. Bekannte Sicherheitszusammenhänge sind in
`SPEC.md` (Qualität und Abnahme) und `docs/betrieb.md` beschrieben. Das
Repository enthält nach Projektregel keine Laufzeitdaten, Geheimnisse oder
persönlichen Konfigurationen; Entdeckst du dennoch Zugangsdaten im
Quellbestand, zählt das als Sicherheitsmeldung.
