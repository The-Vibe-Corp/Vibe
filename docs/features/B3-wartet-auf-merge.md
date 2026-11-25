# B3 — Gemergtes Arbeitspaket bleibt als „wartet auf Merge“ markiert

Stand: 2026-11-22
Ausgangscommit: `d53efa4` (Branch `feature/korbat/ap3-korbat`, Basis `dev`)
Arbeitspaket: FEEDBACK.md-Eintrag B3 „Completed and merged work
package still marked as waiting for merge" (Art: Bug)

Hinweis zur Kennung: Der alte, bereits geschlossene B3 (Kennwortdatei zum
Laufstart, `docs/features/B3.md`) ist ein anderes Thema; die Kennung wurde
im Projektordner neu vergeben. Dieser Bericht gehört zum NEUEN B3; Review:
`docs/reviews/B3-review-2.md` (Runde 2 der Kennung — Runde 1 gehörte zum
alten B3).

## 1. Fehlerbild (laut Eintrag, drei Teile)

1. Ein vollständig abgeschlossenes, automatisch gemergtes Paket
   (AP5-Korbat, Merge-Request #29, squash-gemergt, Branch gelöscht,
   Ticket abgehakt, Abschlussbericht „Wartet auf Merge: keine") wurde in
   der Oberfläche weiterhin als „wartet auf Merge" angezeigt.
2. In der klassischen Oberfläche fehlte der Knopf, ein wartendes Paket
   nach manuell erfolgtem Merge abzuschließen (der Knopf existierte nur
   in Nova).
3. Prozessfrage: Ein Parallel-Paket zog `dev` einen Commit weiter, während
   ein anderes Paket seinen Merge versuchte; der Merge scheiterte. Wie
   soll der Prozess damit umgehen?

## 2. Ursachenanalyse (Teil 1)

Der AP5-Korbat-Block in TICKETS.md zitiert als Beschreibungstext wörtlich
die Läufer-Ausgabe eines FRÜHEREN PR-only-Laufs (pi-infra, Merge-Request
#6) — inklusive der Zeile

```
  WARTET AUF MERGE: AP5 — Merge-Request https://github.com/Korbat8/pi-infra/pull/6; danach: vibe package close pi-infra AP5
```

Die Zustandserkennung wertete die Marken `BLOCKIERT:`/`WARTET AUF MERGE:`
als Substring über den GESAMTEN Block aus — und zwar VOR der
Abhaken-Prüfung:

- `bin/vibe`, `_parse_entry`: Marke vor `checked`/Nachweis.
- `bin/vibe`, `open_items`: gleiche Reihenfolge.
- `bin/vibe_packages.py`, `status_report`: `is_blocked`/`is_waiting_merge`
  vor `is_done`+`proof_ok`.

Folge: Das abgehakte, nachweisbelegte, bereits gemergte AP5-Korbat wurde
dauerhaft als „WARTET AUF MERGE" klassifiziert — Oberfläche und CLI
zeigten ein wartendes Paket, obwohl keines mehr wartete. Live am
Ausgangsstand reproduziert:

```
status_report('.') → {'open': ['AP3-Korbat'], 'waiting': ['AP5-Korbat'],
                      'blocked': [], 'done': ['AP1', 'AP2-Korbat',
                      'AP4-Korbat', 'B1', 'B2']}
```

Der Abschlussbericht des Läufers meldete korrekt „Wartet auf Merge:
keine", weil er dafür das Bash-Array `WAITING_MERGE` auswertet (nur
`pr_only_fallback` füllt es) und nicht `status_report`. Richtig war die
Reihenfolge bereits in `priority_view` und im `standard`-Block
(`bin/vibe_packages.py`): dort gewinnt „erledigt mit Nachweis" vor den
Marken. Genau diese Reihenfolge wird jetzt überall benutzt.

### Entscheidung (Teil 1)

Erledigt-Vorrang: Ein abgehaktes Paket mit gültigem Nachweis (für
FEEDBACK zusätzlich `proof_ok`, für TICKETS genügt die Checkbox) ist
„erledigt" — auch wenn sein Blocktext zitierte Markenzeilen enthält.
Nicht vollständig erledigte Einträge behalten ihre Markenzustände
unverändert (BLOCKIERT gewinnt weiterhin über WARTET AUF MERGE).
Begründung: Marken werden von Läufer und Nutzern ausschließlich in
OFFENE Einträge geschrieben; in abgehakten Blöcken sind verbleibende
Marken zitiertertext Reste. Eine textliche Unterscheidung echter und
zitierter Marken ist nicht zuverlässig möglich (die zitierte Zeile ist
einer echten Marke im Format gleich), daher ist der semantische
Vorrang der richtige Hebel — kein Parser-Sonderrweg, keine Migration
von Bestandsblöcken.

## 3. Ursachenanalyse (Teil 2)

Der Knopf „Paket abschließen" existierte nur in Nova
(`bin/web/nova-project.js`, Spalten „Blockiert" und „Wartet auf Merge",
nur Pakete, Aufruf `POST /api/package` mit `action:'close'`). Die
klassische Oberfläche (`bin/web/app.js`) bot auf Ticketkarten nur
„Bearbeiten"/„Löschen". Der Knopf wird jetzt in `ticketCard` für offene
Pakete mit Zustand `BLOCKIERT` oder `WARTET AUF MERGE` nachgereicht —
gleiches Backend, gleiche Wirkung wie `vibe package close <projekt>
<id>` bzw. der Nova-Knopf: ohne registrierten Arbeitskopie-Zweig oder
ohne per REST verifizierten, gemergten Merge-Request verweigert das
Backend gefahrlos mit einer verständlichen Meldung. Feedback-Karten
bekommen bewusst keinen Abschlussknopf (`/api/package` schließt nur
Pakete). Der Knopftext erhielt zusätzlich sein englischsprachiges
Wörterbuchpaar („Close work package"), damit die englische Oberfläche
nicht auf den deutschen Text zurückfällt.

## 4. Prozess (Teil 3) — dokumentierter bestehender Ablauf

Entscheidung per Nutzerrückfrage `qc35c59a5c341` (Dashboard, beantwortet
2026-11-21/22, wörtlich):

> „Wenn jetzt schon ein fetch, dann ein ein origin/dec -> feature branch
> gibt, bleiben wir bei C. Was passiert wenn dieser merge schon
> fehlschlägt, ist das berücksichtigt? Wenn ja, einfach fortfahren, dann
> hatte mein Kollege vielleicht eine veraltete Version installiert."

Damit gilt Variante C: Der bestehende Prozess bleibt unverändert und wird
hier klar dokumentiert. Die im Eintrag beschriebene Sorge ist bereits
durch die bestehende Kette abgedeckt:

1. **Vor jedem Abschluss** zieht der Läufer die Basis in den
   Paketbranch: `ensure-mergeable` (T-G7, AP4) führt in der Arbeitskopie
   `git fetch origin` und `git merge origin/<base>` aus — ein während
   der Bearbeitung weitergezogener `dev` wird also VOR Push und
   Merge-Request eingearbeitet. (AP5 4c stellt dafür die
   Zugangsdatenauflösung über den Projektkonfigurationspfad bereit.)
2. **Schlägt dieser Merge mit Konflikt fehl** (Exit 2): genau eine
   begrenzte Agenten-Reparaturrunde in der Arbeitskopie (Konflikte
   lösen, `git add`, `git merge --continue`; niemals rebase/force-push);
   bleibt der Konflikt bestehen, wird der Merge abgebrochen und das
   Paket BLOCKIERT markiert — stiller Fehlschluss gibt es nicht.
3. **Schlägt fetch/Basis-Bestimmung ohne Konflikt fehl** (Exit 1): an
   dieser Stelle wird bewusst nicht gesperrt; die Ursache meldet sich
   an der nächsten echten Schranke (`github-complete`: Push und
   Merge-Request) und blockiert das Paket dort mit der konkreten
   Ursache.
4. **Rennen im letzten Moment** (Parallel-Merge landet zwischen Schranke
   und Squash-Merge): der REST-Squash-Merge meldet Konflikt (Exit 2) →
   ein begrenzter automatischer Reparaturversuch (Basis neu mergen,
   pushen, erneut mergen); bleibt er erfolglos, Rückfall auf PR-only —
   der Merge-Request steht offen, der Eigentümer merged manuell und
   schließt danach (`vibe package close` bzw. Knopf).
5. Agenten müssen selbst NICHT verfolgen, wann `dev` weitergezogen
   wurde: die Integration passiert einmalig an der Abschlusskette, wo
   auch die Konfliktlösungswerkzeuge (Reparaturrunde, Reattach) liegen.
   Ein „no merge conflict"-Fall kostet dadurch keinen zusätzlichen
   Aufwand — genau das im Eintrag beschriebene „does not matter"-
   Verhalten.

Antwort auf die Rückfrage: Ja, das Scheitern des vorab ausgeführten
Merge ist berücksichtigt (Punkte 2 und 3). Die beobachtete Kollegen-
Störung erklärt sich am plausibelsten durch eine Installation VOR
AP4/AP5 (die T-G7-Schranke, die Reparaturrunde und die
Zugangsdatenweiterreichung stammen aus AP4/AP5).

## 5. Umsetzung

| Datei | Änderung |
| --- | --- |
| `bin/vibe` | `_parse_entry`: Erledigt-Vorrang vor den Marken (Bestandssemantik `not root` bleibt erhalten); `open_items`: vollständig erledigte Einträge werden übersprungen statt als BLOCKIERT/WARTET/offen aufgeführt. |
| `bin/vibe_packages.py` | `status_report`: `is_done`+`proof_ok` zuerst → `done`, danach unverändert `blocked`/`waiting`/`open` (Reihenfolge wie `priority_view`). `priority_view`/`standard` unangetastet. |
| `bin/web/app.js` | `ticketCard`: Knopf „Paket abschließen" für offene Pakete mit Zustand BLOCKIERT/WARTET AUF MERGE; Aufruf `api('/api/package', {name, id, action:'close'})`, Meldung per `toast`, Neuladen per `detail(name)`. Kein Knopf in `feedbackCard`. |
| `bin/web/i18n.js` | EN „Paket abschließen“ → „Close work package“; DE-Identitätspaar ergänzt. |
| `docs/import-manifest.json` | Bytes + SHA-256 der vier geänderten `bin/**`-Dateien aktualisiert. |

Nicht geändert: `bin/vibe-run.sh` (Prozess unverändert, Variante C),
`priority_view`/`standard`, `is_blocked`/`is_waiting_merge`,
`mark_blocked`/`mark_waiting_merge`, `select_package`, `_apply_proof`,
`sync_proof`, Vorlagen.

## 6. Tests (unabhängiger Test-Agent, Rotphase zuerst)

Datei: `tests/unit/test_b3_merged_waiting.py` (26 Fälle, 6 Klassen);
Bericht: `docs/reviews/B3-test-agent-report.md`. Die Fälle wurden aus
dem Arbeitspaket und SPEC.md abgeleitet, vor der Implementierung
geschrieben und am unveränderten Bestand ausgeführt:

```
python3 -m unittest tests.unit.test_work_packages -v
Ran 26 tests … FAILED (failures=15)   # Rotphase am Bestand
```

Abdeckung: AK1/AK2 abgehakte Pakete/Feedback mit Nachweis und
zitierter Marke → erledigt (in `_parse_entry`, `open_items`,
`status_report`); AK3 echte Marken bei offenen Einträgen bleiben
erhalten (BLOCKIERT gewinnt, abgehaktes Feedback ohne Nachweis bleibt
Markenzustand); AK5 klassische Oberfläche: Knopf vorhanden, korrekter
Endpunkt, Zustandsbindung BLOCKIERT/WARTET, Meldung + Neuladen, kein
Knopf auf Feedback-Karten; AK6 i18n EN/DE; AK7 `priority_view`/`standard`
unverändert (Schutzwachen). AK4: `test_ap5_korbat_waiting_state.py`
unverändert (Bestandsschutz).

## 7. Verifikation (tatsächlich ausgeführt)

Grünläufe nach Implementierung (vom Koordinator unabhängig
nachgerechnet):

| Befehl | Ergebnis |
| --- | --- |
| `python3 -m unittest tests.unit.test_b3_merged_waiting` | Ran 26, OK |
| `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state` | Ran 23, OK |
| `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_b16_runner_wiring` | Ran 6, OK |
| `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap4_korbat_gui tests.unit.test_ap4_korbat_github` | Ran 35, OK |
| `python3 -m unittest tests.unit.test_project_management` | Ran 36, FAILED (failures=6, errors=1) — exakt die dokumentierte F22-Vorbaseline (Test-Agent-Feature, in 35233ff entfernt); keine neuen Fehler |
| `python3 scripts/check-import-manifest.py` | Exit 0 (67 Dateien) |
| `python3 scripts/check-syntax.py` | Exit 0 |
| `python3 scripts/check-no-secrets.py` | Exit 0 |
| `bash scripts/verify.sh quick` | Exit 0 |
| Sanity am echten Bestand: `status_report('.')` | `waiting` leer; AP5-Korbat unter `done` — gemeldetes Fehlerbild behoben |

Paket- und Gesamtprüfung (`VERIFY_PACKAGE`, `VERIFY_FULL`) führt der
Läufer mit den autoritativen Befehlen des Integrationsstands aus
(runner-owned).

**Grünphase-Bestätigung des unabhängigen Test-Agenten:** erneuter Lauf
von `python3 -m unittest tests.unit.test_b3_merged_waiting -v` durch den
Test-Agenten selbst → `Ran 26 tests`, OK, alle 15 ehemals Roten grün,
keine Assertion verändert.

**Review:** Runde 2 der Kennung (`docs/reviews/B3-review-2.md`; Runde 1
gehörte zum alten B3): `Verdict: PASS` — 0 Critical, 0 High, 0 Medium,
0 Minor. Der Reviewer hat Zustandssemantik, GUI-/Backend-Vertrag,
Test-Integrität (keine Bestandstests verändert), Doku-Fakten gegen den
Quelltext, Manifest, Umfang und Geheimnisschutz sowie die
Baseline-Zuordnung geprüft; Grenze: kein Browser in der Umgebung
(Quelltext-/Strukturassertionen, Bestandsmuster AP4/AP5).

## 8. Grenzen (ehrlich benannt)

- Kein Browser/Playwright in der Umgebung: AK5/AK6 sind Quelltext-/
  Strukturassertionen (Bestandsmuster aus AP4/AP5); echtes Klicken und
  Layout sind nicht nachgewiesen.
- `test_project_management` trägt die vorbestehende F22-Altschuld
  (erwartet das in 35233ff entfernte Test-Agent-Feature; identische
  Fehlermenge am Ausgangsstand — kein B3-Fall).
- Der PR-only-Bestandstest benötigt eine ungesetzte `GITHUB_AUTO_MERGE`-
  Umgebung (`env -u GITHUB_AUTO_MERGE`, dokumentiertes AP5-Verhalten);
  unter gesetzter Variable meldet er einen Umgebungstreffer.
- `tests/unit/test_b3_password_auto_setup.py` (ALTER B3, Kennwortdatei)
  bleibt vorbestehend rot: Er mockt das in 35233ff entfernte
  `ensure_test_agent`. Vorbefund am Ausgangsstand, dokumentiert im
  AP5-Baseline-Umfeld; von diesem Paket bewusst nicht berührt.
- Trilium-MCP: nicht konfiguriert/verfügbar — keine Synchronisation
  (Ticketregel: meldet, blockiert nicht).

## 9. Nutzerhandlungen (nicht vom Paket erledigt)

- Keine Migration, keine neuen Konfigurationseinträge.
- Abschlussknopf klassisch: Projekt öffnen → „Arbeit" → Ticketkarte mit
  Status BLOCKIERT oder WARTET AUF MERGE → „Paket abschließen" (Nova:
  unverändert in den Spalten „Blockiert"/„Wartet auf Merge").
- Das B3-Häkchen liegt in der Arbeitskopie dieser Paketarbeitskopie
  (FEEDBACK.md ist gitignorerter Laufzeitstand). Der Läufer schreibt
  beim Abschluss nur den Nachweis des Laufpakets (AP3-Korbat) zurück;
  der Eigentümer übernimmt das B3-Häkchen im Projektordner (Zeile im
  Abschlussbericht) oder mit
  `python3 bin/vibe_packages.py sync-proof --project <Projektordner> --worktree <Arbeitskopie> --id B3`.
- AGENTS.md: keine Anpassung nötig (Variante C — der dokumentierte
  Ablauf beschreibt bereits das bestehende Verhalten).
