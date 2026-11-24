# B1 — Ticketlogik aufräumen: ein Typfeld, Editor ohne Zustandswechsel, GitHub-Anlage, Läufer-Status

Status: umgesetzt und abgenommen; Reviews
`docs/reviews/B1-review-4.md` und `docs/reviews/B1-review-5.md`
beide **Verdict: PASS** (Runde 4 wegen
Kennungskollision, siehe unten).
Ticket: `TICKET-B1.json` — „Clean up inconsistent category and ticket type
logic for tickets" (Typ: bug).
Branch: `feature/korbat/b1`
Ausgangsstand: `821982c`

Hinweis zur Kennung: Der alte, bereits geschlossene B1 (Kostentabelle,
`docs/features/B1.md`, FEEDBACK.md-Ära) bleibt unberührt; diese Dokumentation
beschreibt das aktuelle Ticket B1 aus dem maschinenlesbaren Ticketspeicher.
Der Dateiname folgt dem Projektpräzedenzfall B3/B4/B6/B7 (beschreibender
Zusatz bei Kennungskollision). Zusätzlich enthält `docs/features/B1.md`
einen abgegrenzten Abschnitt für dieses Ticket (Präzedenz B1/2026-11-20),
damit die Abschlussschranke (`gate_errors`) und die Historie beide erfüllt
sind; die Review-Dateien starten bei Runde 4, weil die Runden 1–3 zum
älteren Kostentabelle-B1 gehören.

## Ziel

Vier Anforderungen aus dem Ticket und zwei Dashboard-Entscheidungen:

1. **Ein Typfeld statt doppelter Logik.** Beim Anlegen gab es zwei
   überlappende Felder: „Kategorie" (Feature/Bug/Feedback, GitHub-Label) und
   „Tickettyp" (Paket/Bug/Feature/Feedback, Speichertyp). B1 führt EIN Feld
   (`select[data-nv-field='ticket-type']`, Optionen feature/bug/feedback)
   ein; „Paket" (interner Typ `task`) wird nicht mehr angeboten, bleibt aber
   als Speicher-/API-Typ gültig (Bestandstickets wie GH-70).
2. **Editor ändert nie den Zustand** (Nutzer-Entscheidung „Option A",
   Dashboard-Frage `q6cb12b771c28`). Öffnen, Speichern und Abbrechen des
   Text-Editors lassen den Zustand unverändert; das ersetzt die
   GH-67-Nachforderung „Bearbeiten startet Umsetzung". Manuelle Wechsel
   bleiben vollständig: Detail-Zustandsauswahl (Entwurf/Bereit/In Progress),
   Board-Buttons „Freigeben"/„Zurück in Planung", Drag&drop.
3. **Anlage erreicht GitHub.** Bug-/Feedback-Anlagen liefen über
   `/api/feedback` (rein lokal, `B<n>`) — so entstand das Ticket B1 selbst
   ohne GitHub-Bezug. Jetzt läuft jede Anlage über `/api/ticket action=add`
   mit `type`; verbundene Projekte legen das Issue zuerst an
   (Label = Typ, Ready-Label nur bei open) und danach das lokale
   `GH-<n>`-Ticket mit `github=<n>`.
4. **Läufer markiert den Bearbeitungsbeginn** (Nutzer-Entscheidung per
   Dashboard): `mark_start`/CLI `mark-start` setzt `open → in-progress`
   idempotent; `bin/vibe-run.sh` ruft es nach der Worktree-Registrierung und
   vor dem Tickettransport auf (auch bei RECONNECT), nicht blockierend.
   Verbundene Tickets erhalten zusätzlich das In-Progress-Label
   (GH-47-Semantik), damit der nächste Sync den Zustand nicht zurücksetzt.
   Zustandswechsel im Ticketspeicher sind damit Läufer- oder
   Nutzeraktion — nie Agenten- oder Editor-Nebenwirkung.

## Umsetzung je Anforderung

### 1. Ein Typfeld

- `bin/web/nova-project.js` (`nvpOpenTicketForm`): Kategorie-Auswahl entfernt;
  das Typfeld bietet genau feature/bug/feedback (Anzeige Feature/Bug/Feedback,
  `aria-label` „Ticket Type", Feldlabel „Tickettyp"). Vorauswahl je
  Anlage-Button: Paket anlegen → feature, Bug melden → bug, Feedback geben →
  feedback; bis zum Speichern änderbar. Der Paket-Button übergibt
  `type: 'feature'` (vorher `task`).
- `bin/web/i18n.js`: die dadurch ungenutzten Schlüssel „Kategorie" (en/de)
  entfernt; „Paket" bleibt für die Karten-Badges erhalten.
- Offline-Auto-ID: `bin/vibe_tickets.py` ergänzt
  `TYPE_PREFIXES["feature"] = "AP"` — feature teilt den AP-Zähler mit task
  (AP1→AP2, AP10→AP11); bug→`B<n>`, feedback→`F<n>` unverändert.

### 2. Editor ohne Zustandswechsel

- `nvpStartTicketProgress` (State-POST beim Öffnen des Editors) und die
  Steuervariable `editState` sind vollständig entfernt. Das Formular schickt
  beim Bearbeiten nur `action=update` (Titel/Beschreibung); kein
  `action=state`-Aufruf entsteht aus Öffnen, Abbrechen oder Speichern.
- Die Detail-Zustandsauswahl, Board-Buttons und Drag&drop sind unverändert
  und bleiben die bewussten Wege für Zustandswechsel.

### 3. Einheitliche Anlage über `/api/ticket`

- `bin/vibe-web.py` (`/api/ticket action=add`): Body-Feld `type`, validiert
  gegen `vibe_tickets.TYPES`; fehlt es, gilt der Default `feature`;
  unbekannte Werte werden mit Klartext abgelehnt (kein Issue-POST, Speicher
  unverändert). `category`/`kind` haben keinen Einfluss mehr.
- `bin/vibe_issues.py` (`add_ticket_connected`): EIN Typ-Parameter bestimmt
  GitHub-Label (nur bug/feature/feedback; `task` ohne Typ-Label) und
  Speichertyp; `draft` lässt das Ready-Label weg und legt `state=draft` an.
  Schlägt die Issue-Anlage fehl, bleibt der Ticketspeicher unverändert
  (bestehende Invariante).
- `bin/web/nova-project.js` (Save-Handler): Anlagen gehen immer an
  `/api/ticket` mit `{action:'add', type, id, state:'draft'}` — kein
  `/api/feedback`-Redirect, kein `kind`, kein `category`. Neue Tickets
  bleiben Entwürfe (GH-56). Das Bearbeiten bestehender Tickets behält das
  bisherige Routing (bug/feedback → `/api/feedback update`, gleiche
  Speicheroperation).
- `/api/feedback action=add` (klassische Oberfläche `/classic`) bleibt
  bewusst unverändert und rein lokal; die Nova-Oberfläche nutzt ihn für
  Anlagen nicht mehr. Bekannte Grenze, siehe unten.

### 4. Läufer markiert den Bearbeitungsbeginn

- `bin/vibe_packages.py`: `mark_start(project, pid)` → `(changed, message)`
  nach dem Muster `mark_blocked`/`mark_waiting_merge`. Nur `open` wechselt
  auf `in-progress`; bereits in-progress ist idempotent (Hinweis
  „bereits in Bearbeitung"); draft/done/blocked/waiting-merge und fehlende
  Tickets werden abgelehnt, ohne den Speicher zu verändern. Bei aktivem
  Issues-Sync mit GitHub-Bezug folgt das Label über
  `vibe_issues.set_issue_state` (Ready-Label bleibt erhalten); ein
  REST-Fehlschlag setzt den lokalen Zustand trotzdem (Best-effort-Meldung,
  der Sync gleicht später ab). CLI-Subcommand `mark-start --project --id`
  (Exit 0/OK bei Änderung, Exit 1/HINWEIS sonst).
- `bin/vibe-run.sh`: nicht blockierender Aufruf
  (`python3 "$PACKAGES_PY" mark-start --project "$P" --id "$ID" >>"$LOG" 2>&1 || true`)
  nach `worktree-register`, vor dem Tickettransport (`copy-notes`) — die
  transportierte `TICKET-<ID>.json` zeigt den Zustand damit bereits beim
  Start, auch bei RECONNECT.

## Ursachen der behobenen Fehler

- **Doppelte Felder (GH-67-Rest):** Kategorie (Label) und Tickettyp waren
  getrennte Felder mit getrennten Speicherwegen; „Paket" als Typwahl war
  überflüssig, weil Arbeitspakete ohnehin über den Anlage-Button entstehen
  und das Board task/feature einheitlich als „Paket" darstellt.
- **Cancel-Sprung draft→in-progress:** `nvpOpenTicketForm` rief beim
  **Öffnen** des Editors `nvpStartTicketProgress` auf — der Zustand stand
  damit fest, bevor Speichern/Abbrechen überhaupt gewählt wurde.
- **Bug ohne GitHub-Upload:** Der Save-Handler leitete bug/feedback-Anlagen
  an `/api/feedback` weiter (`vibe.add_bug`, lokale `B<n>`-Kennung),
  während nur `/api/ticket` den verbundenen Anlageweg
  (`add_ticket_connected`, Issue zuerst) kannte.

## Testherkunft und -korrekturen

Der unabhängige Test-Agent hat die Fälle aus `TICKET-B1.json`, `SPEC.md` und
den Dashboard-Entscheidungen abgeleitet, vor der Implementierung rot
ausgeführt und nach der Umsetzung grün bestätigt:

- Neu: `tests/browser/test_b1_work_ui.py` (7 Fälle: ein Typfeld,
  Button-Vorauswahl, Editor ohne Zustandswechsel inkl. Abbruch,
  Anlage-Routing, Offline-Präfixe, manueller Wechsel draft→open, keine
  JS-Fehler).
- Neu: `MarkStartedTest` in `tests/unit/test_gh48_runner_tickets.py`
  (11 Fälle: Übergänge, Idempotenz, CLI-Exitcodes, Label-PATCH mit
  Ready-Erhalt, REST-Fehlschlag → lokal, Transport-Reihenfolge, Aufruf in
  `vibe-run.sh`).
- Angepasst (nur B1-Vertrag): `test_gh67_work_ui.py` (Typfeld statt
  Kategorie, Editor ohne automatischen Wechsel, i18n), `test_gh56_work_ui.py`
  (Close-Fall), `test_gh48_web_api.py` (type-basierte verbundene Anlage,
  Labels, Default, Offline-Präfix), `test_ap3_korbat_issues_backend.py`
  (Ein-Parameter-Signatur, Label-/Typ-Matrix), `test_gh48_ticket_store.py`
  (feature→AP-Zähler), `test_ap3_korbat_surfaces.py` (ein Typfeld).
  Board-Button-, DnD- und Zustandsauswahl-Fälle blieben unangetastet grün.
- Korrektur mit Begründung: die Alt-Assertions auf einen
  `issuesEnabled`-Board-Marker („F33 WP3") waren am Branchpunkt bereits rot
  — der Marker existierte im Codebestand nie. Die funktionslosen Assertions
  sind entfernt; die zur „Erfüllung" zwischenzeitlich ergänzte, ungenutzte
  Variable im Board-Aufbau wurde zurückgebaut (KISS).

## Prüfergebnisse

Die folgende Tabelle nennt ausschließlich tatsächlich ausgeführte Prüfungen.

| Befehl | Ergebnis |
|--------|----------|
| `python3 -m unittest tests.unit.test_gh48_ticket_store tests.unit.test_gh48_web_api tests.unit.test_ap3_korbat_issues_backend tests.unit.test_gh48_runner_tickets` | Ran 115, OK |
| `python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v` | Ran 25, FAILED (failures=5) — exakt die vorbestehenden, nicht B1-betroffenen (siehe unten) |
| `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_b1_work_ui tests.browser.test_gh67_work_ui tests.browser.test_gh56_work_ui -v` | Ran 69 (7+41+21), OK |
| `node --check bin/web/nova-project.js` | OK |
| `python3 scripts/check-syntax.py` | OK: 266 Python-, 8 Bash-, 5 JSON-Dateien |
| `python3 scripts/check-no-secrets.py` | OK: keine Geheimnisse erkannt |
| `python3 scripts/check-import-manifest.py` | OK: 71 Dateien stimmen überein (7 Hashes + B1-Eintrag aktualisiert) |
| `bash scripts/verify.sh quick` | Exit 0 |
| `bash scripts/verify.sh package` | Exit 0 |
| `bash scripts/verify.sh full` (Abnahmelauf, einmalig, ohne Flags) | Erster Lauf: Exit 7 — 2736 Tests, 17 fehlgeschlagene Module, davon 5 als „Neue Regression" gemeldet. Auflösung evidenzbasiert (siehe unten): eine Vertragsanpassung (ap9), vier Baseline-Progressionen. Wiederholungslauf nach den echten Test-/Baseline-Änderungen: **Exit 0 — BASELINE-OK** (2736 Tests, 138/154 Module, `baseline_ok=1`, `test_ap9_runner_wiring` grün; alle verbleibenden 16 Module bekannt rot) |

### Abnahmelauf: Auflösung der fünf gemeldeten Regressionen

Der erste Abnahmelauf meldete fünf Module als „Neue Regression". Für jedes
Modul wurde am Branchpunkt `821982c` (frischer Klon im temporären Verzeichnis,
dieselbe Maschine) derselbe Modullauf wiederholt und die Failure-Inhalte
verglichen:

| Modul | Befund am Branchpunkt | Bewertung | Behandlung |
|---|---|---|---|
| `tests.unit.test_ap9_runner_wiring` | Modul grün (3/3) | Durch B1-Anforderung 4 verursacht: Der Läufer markiert den Start (`open` → `in-progress`); der End-to-End-Fall erwartete noch den alten Startzustand `open` nach blockiertem Abschluss | Test-Agent passt den Fall an den B1-Vertrag an (erwartet `in-progress`; die geschützte Intention — nicht geschlossen, nicht gemergt, neu wählbar — bleibt unverändert) |
| `tests.unit.test_ap12_github_readiness` | Identische 2 Failures (B7-Homepfad-Inhaltsprüfung; Umgebungsfall `.opencode/agents/test-agent.md` greift nur mit transportiertem `.vibe/project.env`, im Frischklon übersprungen) | Vorbestehend/umgebungsabhängig, nicht B1 | Baseline-Progression: Eintrag `sha256:70d607fd…` |
| `tests.unit.test_ap5_korbat_waiting_state` | Identische 3 Failures (alte `WARTET AUF MERGE`-Labels und Stale-List-Marker aus der FEEDBACK.md-Ära) | Vorbestehend, nicht B1 | Baseline-Progression: Eintrag `sha256:09ee2c84…` |
| `tests.unit.test_ap3_korbat_surfaces` | Identische 5 Failures | Vorbestehend, nicht B1 | Baseline-Progression: Eintrag `sha256:da1655baf…` |
| `tests.unit.test_release` | Byte-identische Problemliste (u. a. `docs/features/B7-subagent-permissions.md:109`, Homepfad; keine B1-Datei betroffen — die eigenen B1-Dokumente sind sauber) | Vorbestehend, nicht B1 | Baseline-Progression: Eintrag `sha256:ae67d8a0…` |

Die vier vorbestehenden Einträge sind unter dem Umgebunglabel
`VERIFY_ENV=pi-aarch64-py3.14-namespaces` in `tests/verify-baseline.json`
ergänzt worden (nur Anfügen, keine Bestandseinträge verändert) und reisen mit
dem normalen Paket-Merge-Request durch die Review; kein lokales
`--write-baseline`-Proposal wurde erzeugt. Nach der ap9-Vertragsanpassung
wurde der Abnahmelauf einmal wiederholt (echte Teständerung seit dem letzten
Lauf); das Ergebnis steht in der Tabelle oben.

Rot-Phase vor der Implementierung (Test-Agent): 75 Tests mit 7 Failures +
2 Errors an den B1-Vertragspunkten (feature-Auto-ID fehlte, Default war
`task`, verbundene Anlage setzte keine Typ-Labels), Browser-Suite rot an
Kategorie/task/State-POST/`/api/feedback`-Routing; Läufer-Fälle rot an
fehlendem `mark_start`/`mark-start`.

### Vorbestehende Failures (nicht B1)

Am Branchpunkt `821982c` (frischer Klon, dieselbe Maschine) nachgewiesen und
per Baseline-Progression getragen:

- `tests/unit/test_ap3_korbat_surfaces` — fünf Failures
  (`test_ticket_form_has_draft_checkbox`,
  `test_cards_show_draft_state_with_gray_pill_and_explanation`,
  `test_in_progress_pill_uses_warn_class_and_draft_stays_muted`,
  `test_state_helpers_know_in_progress`,
  `test_work_list_and_tiles_include_progress_without_board`); betreffen alte
  Board-/Checkbox-/Pillen-Hooks aus der FEEDBACK.md-Ära.
- `tests/unit/test_ap5_korbat_waiting_state` — drei Failures
  (integrierte Arbeitsliste, `WARTET AUF MERGE`-Labels,
  Waiting-Pillen-Farben); Altverträge, die der Codebestand nicht mehr erfüllt.
- `tests/unit/test_ap12_github_readiness` — zwei Failures: die
  Inhaltsprüfung meldet u. a. den Homepfad in
  `docs/features/B7-subagent-permissions.md` (nicht B1), und der
  Umgebungsfall `.opencode/agents/test-agent.md` greift nur, wenn ein
  transportiertes `.vibe/project.env` vorliegt (Paket-Worktree), und schlägt
  dann fehl; im Frischklon wird er übersprungen. Am Branchpunkt mit dem
  Umgebungstrigger identisch reproduziert.
- `tests/unit/test_release` — die Inhaltsprüfung meldet dieselbe
  Problemliste wie am Branchpunkt (byte-identisch; keine B1-Datei darin).

`tests/unit/test_ap9_runner_wiring` ist dagegen am Branchpunkt grün; seine
eine Failure entsteht durch B1s beabsichtigten Läufer-Start und ist über die
Test-Vertragsanpassung (erwarteter Zustand nach blockiertem Abschluss:
`in-progress`) gelöst, nicht über die Baseline.

## Abhängigkeiten

- **GH-48** — maschinenlesbarer Ticketspeicher, Zustands-/Typkonstanten,
  Done-Invariante; B1 ergänzt nur das feature-Präfix.
- **GH-47** — Label-basierte Zustandssynchronisation; `set_issue_state`
  wird für den Läufer-Start wiederverwendet.
- **GH-56/GH-57** — Kanban, Editor-Shell; nur der Anlage-Dialog und die
  automatische Statuslogik ändern sich.
- **GH-67** — Kategorie/Tickettyp-Trennung wird zugunsten eines Felds
  zurückgenommen; die Nachforderung „Bearbeiten startet Umsetzung" wird per
  Nutzentscheid (Option A) zurückgebaut.

## Einschränkungen und Grenzen

- `/api/feedback action=add` (klassische Oberfläche) bleibt rein lokal und
  ohne GitHub-Anlage — bewusstes Legacy-Verhalten, aus B1 ausdrücklich
  ausgeklammert; die Nova-Oberfläche verwendet ihn für Anlagen nicht mehr.
- `mark_start` setzt in Teilinstallationen ohne `vibe_github.py`/`vibe_issues.py`
  den Zustand nicht (kontrollierter Abbruch, im Läufer über `|| true`
  protokolliert, Lauf läuft weiter); der lokale Fallback gilt für
  vollständig installierte Umgebungen.
- Die produktive Instanz nutzt die `_toolchain`-Installation; die
  Läufer-Änderung (`mark-start`) wird erst mit dem nächsten
  Installations-Update des Produktionsstands aktiv. Für das laufende B1-Paket
  greift sie deshalb nicht rückwirkend — das Ticket geht beim Abschluss wie
  bisher direkt auf `done`.
- Browserabnahme mit Headless-Chromium (1500×1100, 600×800-Mobilfälle der
  bestehenden Suiten); keine Touch-/Screenreader-Prüfung.

## Beteiligte

- **Test-Agent** (unabhängig): neue Browser- und Läufer-Fälle, Anpassung der
  bestehenden Suiten an den B1-Vertrag, Rot-Phase vor der Umsetzung.
- **Coding-Agent**: Implementierung aller vier Anforderungen in `bin/`,
  Grün-Phase.
- **Koordinator**: Ursachenanalyse, Vertragsdefinition, Dashboard-Entscheidungen,
  Korrektur der toten Variable/Stale-Assertions, Manifest, Doku, Prüfungen,
  Commit.
- **Reviewer** (unabhängig): `docs/reviews/B1-review-4.md` (Haupt-Review,
  Verdict: PASS) und `docs/reviews/B1-review-5.md` (Delta-Nachprüfung nach
  der Abnahmeprüfung, Verdict: PASS).
