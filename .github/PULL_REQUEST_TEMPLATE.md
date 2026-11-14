# Pull-Request-Checkliste

## Was wird geändert?

Kurzbeschreibung des Arbeitspakets/Issues (Ticket- oder Issue-ID nennen).

## Grundlage

- [ ] Basis: Haupt-Branch, eigene Feature-Branch-Umsetzung.
- [ ] Keine Änderungen an fremden, paketfernen Dateien.
- [ ] `SPEC.md`-Regeln beachtet (keine Geheimnisse, keine Laufzeitdaten,
  keine persönlichen Konfigurationen im Bestand).

## Tests und Prüfung

- [ ] Tests existieren vor/nach der Änderung und sind unabhängig entwickelt
  (Rotphase dokumentiert, keine abgeschwächten Assertions).
- [ ] `bash scripts/verify.sh quick` — Ergebnis: <!-- Exit-Code, Testzahl -->
- [ ] `bash scripts/verify.sh full` — Ergebnis: <!-- Exit-Code, Testzahl,
  vorbestehende Fehlschläge separat benennen -->

## Nachweise

- [ ] Feature-Dokumentation (`docs/features/<ticket>.md`) aktualisiert.
- [ ] Unabhängiger Review vorhanden (`docs/reviews/…`, Verdict).
- [ ] Commit-Meldungen verständlich und auf das Wesentliche reduziert.
