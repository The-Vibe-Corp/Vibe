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
       bash scripts/verify.sh package
       bash scripts/verify.sh full

   `quick` ist die statische Prüfung, `package` die Paketprüfung mit
   Testnachweis (aus `VERIFY_PACKAGE`), `full` die vollständige Abnahme aus
   `VERIFY_FULL`. Prüfe in Stufen: während der Bearbeitung nur die
   betroffenen Testmodule (z. B. `python3 -m unittest
   tests.unit.test_verify_script`) und `package`; die vollständige Suite
   (`full`) läuft einmal vor der Abnahme. Für vollständige Läufe über
   mehrere Kerne steht der parallele Läufer bereit (Ergebnisse sind mit
   `unittest discover` vergleichbar; `--jobs` begrenzt die Parallelität):

       python3 scripts/run-tests-parallel.py --dir tests/unit
       python3 scripts/run-tests-parallel.py --dir tests/unit --dir tests/browser --jobs 2

   Mit `--timeout SEK` (Default 900, 0 ohne Limit) wird ein hängendes
   Modul beendet und als fehlgeschlagen gemeldet.

5. Stelle einen Pull Request; benutze die Vorlage
   `.github/PULL_REQUEST_TEMPLATE.md` und nenne Ticket, Tests, Prüfergebnisse
   und Dokumentation.

## Verhaltensregeln

Bitte beachte `CODE_OF_CONDUCT.md`. Sicherheitsmeldungen gehören nicht in
öffentliche Issues — siehe `SECURITY.md`.
