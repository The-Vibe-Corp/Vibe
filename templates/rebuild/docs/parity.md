# Paritätsmatrix — {{NAME}}

Diese Datei ist der Nachweis für die fachliche Gleichwertigkeit. Eine Zeile gilt
nur dann als erfüllt, wenn der genannte Nachweis tatsächlich ausgeführt wurde.
Die fachliche Funktionsweise wird **1:1** übernommen; technische Abweichungen
sind erlaubt, müssen aber begründet und hier sichtbar sein.

## Statuswerte

- `offen` — noch nicht geprüft.
- `teilweise` — einige Fälle geprüft, andere offen.
- `paritätisch` — Verhalten und sichtbare Ergebnisse stimmen überein.
- `bewusst abweichend` — technisch oder fachlich begründet, mit Entscheidung.

## Funktionen

| Funktion / Fall | Originalverhalten | Neuversion | Nachweis (Test, Screenshot, Datei) | Status |
| --- | --- | --- | --- | --- |
| Beispiel: Start ohne Speicherstand | ... | ... | `tests/...` | offen |
| Beispiel: ungültige Eingabe | ... | ... | `tests/...` | offen |

## Speicherstände

| Format / Version | Lesen | Schreiben | Unbekannte Felder | Roundtrip-Nachweis | Status |
| --- | --- | --- | --- | --- | --- |
| Beispielformat v1 | offen | offen | offen | `tests/...` | offen |

Regeln:

- Originaldateien werden nie überschrieben, ohne vorher eine Sicherung anzulegen.
- Nach dem Speichern muss die Datei erneut gelesen werden können; die Neuversion
  und das Original müssen sie gegenseitig öffnen können.
- Unbekannte Felder und Reihenfolgen bleiben erhalten, soweit das Format es
  zulässt. Geht das nicht, ist es eine dokumentierte Abweichung.
- Migrationen brauchen eine Sicherung, einen Rückweg und Tests mit echten
  Beispieldateien.
- Fixtures enthalten keine personenbezogenen Daten und keine Geheimnisse.

## Offene Punkte

- ...
