# Mitwirken

Danke für dein Interesse an vibe. Dieses Dokument beschreibt, wie Beiträge
ablaufen.

## Rahmen

- `SPEC.md` ist die fachliche Wahrheit für den Produktumfang.
- `TICKETS.md` und `FEEDBACK.md` sammeln Arbeitspakete und Befunde; beide
  Dateien sind lokale Werk-Notizen und gehören nicht in Beiträge.
- `AGENTS.md` beschreibt die verbindlichen Regeln für Implementierung, Tests,
  Git und Review. Sie gelten für Menschen und Agenten gleichermaßen.

## Ablauf für einen Beitrag

1. Suche nach einem bestehenden Issue oder lege einen an; beachte die
   Vorlagen unter `.github/ISSUE_TEMPLATE/`.
2. Arbeite an einem eigenen Feature-Branch, niemals direkt auf dem
   Haupt-Branch.
3. Die Tests werden unabhängig vom Implementierungscode entwickelt und
   zuerst geschrieben (Rotphase vor Grünphase). Attrappen allein gelten
   nicht als Abnahme.
4. Prüfe deinen Stand mit:

       bash scripts/verify.sh quick
       bash scripts/verify.sh full

5. Stelle einen Pull Request; benutze die Vorlage
   `.github/PULL_REQUEST_TEMPLATE.md` und nenne Ticket, Tests, Prüfergebnisse
   und Dokumentation.

## Verhaltensregeln

Bitte beachte `CODE_OF_CONDUCT.md`. Sicherheitsmeldungen gehören nicht in
öffentliche Issues — siehe `SECURITY.md`.
