# Review F30 „Sub Agent view" (Bugfix)

**Paket:** FEEDBACK.md F30 „Sub Agent view" — **Ausgangscommit:** `5f6c8fe` (AP16)
**Branch:** `vibe/vibe-F30-1794597769845746436-3112012-26243` (Arbeitskopie `…/worktrees/vibe-F30-TooFxO`, ungecommitted)
**Geprüft:** `bin/vibe-web.py` (Handler `/api/subagent-output`, `live_subagent_output`, `opencode_request`), `bin/web/app.js` (`outputView`/`makeChild`/`sync`/`loadChild`, 2-s-Polling), `bin/web/styles.css` (`.bv-root/.bv-subs/.bv-sub/.bv-sub.enlarged`), `tests/unit/test_f30_subagent_view.py`, `tests/browser/test_f30_subagent_view_ui.py`, `docs/features/F30.md`, `docs/reviews/F30-test-agent-report.md`, `docs/import-manifest.json` (F30-Eintrag), `FEEDBACK.md` (Tickettext), `SPEC.md`, `AGENTS.md`, `.vibe/project.env`
**Datum:** 2026-11-13
**Reviewer-Einschränkung:** Dem Review-Agent sind Shell-/Git-Befehle nicht freigegeben (Aufruf `git status`/`git diff` → Permission denied). Geprüft wurde daher per vollständiger Lektüre aller als geändert gemeldeten Dateien im Arbeitsbaum; der Diff gegen `5f6c8fe` und die Vollständigkeit der Änderungsliste konnten nicht independent aus Git verifiziert werden (siehe „Nicht verifiziert").

## Akzeptanzkriterien

| Kriterium | Status | Implementierung | Test / Nachweis |
|---|---|---|---|
| AK1 Live-Ausgabe statt eingefrorenem erfasstem Text | PASS | `bin/vibe-web.py:903-912` (live zuerst, Fallback, Tail) | Unit-Tests 1/2/8 (Rotphase belegt, grün gemeldet); Browser-Test 3 (Ende-zu-Ende) |
| AK2 Erfasste Ausgabe bleibt Fallback (kein Kennwort, Serverstörung, nur Nutzernachricht) | PASS | `bin/vibe-web.py:908-910`; `opencode_request` liefert `None` bei fehlendem Kennwort/HTTP≥300/Fehler (`bin/vibe-web.py:207-234`) | Unit-Tests 3/4/5 (inkl. „keine /message-Anfrage ohne Kennwort") |
| AK3 Klare Leer-Meldung unverändert | PASS | `bin/vibe-web.py:913-919` (ok:false, status, Meldungstext) | Unit-Test 6 |
| AK4 Unbekannte Session ohne Serverabfrage abgelehnt; Abruf mit `order=asc` | PASS | `bin/vibe-web.py:892-902`; `live_subagent_output` `bin/vibe-web.py:336-337` | Unit-Tests 7/8 (Anfrageprotokoll der Attrappe prüft `order=asc` bzw. keine Anfrage) |
| AK5 Karten ≥ 300 px, kein 160-px-Deckel | PASS | `bin/web/styles.css:56-58` (300 px, kein max-height), `.bv-root` scrollt (`styles.css:41`) | Browser-Test 1 (Bounding-Box, ≥ 30 % Hauptansicht, `.bv-subs`-Höhe); Rotphase 150 px belegt |
| AK6 Vergrößern/Verkleinern per Maus und Tastatur, aria-Vertrag | PASS | `bin/web/app.js:476-490` (button, aria-label mit „vergrö/verkleinern", aria-expanded, Zustand am Kartenelement), `styles.css:60-62` (fixed inset:8px) | Browser-Tests 2/4 (Fokus+Enter, ≥ 70 % Höhe / ≥ 60 % Breite, Wiederherstellung, keine JS-Fehler) |
| AK7 Ausgabe folgt dem 2-s-Polling | PASS | Backend AK1 + `app.js:493-500,521-523` (`loadChild`, `node.loading`, `setText`) | Unit-Test 2, Browser-Tests 3/4 (Textwechsel LIVE-A→B ohne Neuladen) |
| „Doppelt" — bewusster Nicht-Fix, dokumentiert | PASS (Doku) | `docs/features/F30.md:21-41,148-150` | Belege (`_logs/Website.log` Z. 12715/12724, state.json) Koordinator-geliefert, nicht unabhängig prüfbar; Begründung (Deduplizierung würde reale Parallelarbeit verbergen) ist fachlich nachvollziehbar und SPEC-konform (Lauf „beobachten" = Realitätsanzeige) |

## Befunde

- **[Low] `bin/web/app.js:515`** — Fokusverlust, wenn eine vergrößerte Karte verschwindet
  - Beleg: `sync()` entfernt beendete Subagenten per `node.view.remove()`. War die Karte vergrößert und der Fokus lag auf dem Verkleinern-Knopf (einziger fokussierbarer Anker der Overlay-Ansicht), fällt der Fokus auf `<body>`; der Bediener verliert den Tastaturkontext ohne Hinweis. Reines Randverhalten (Subagent endet genau während Vergrößerung), keine Funktionsstörung.
  - Empfehlung: Beim Entfernen des fokussierten (ggf. vergrößerten) Knotens den Fokus bewusst auf ein stabiles Element der Ansicht zurücksetzen; als Testkontakt beim Test-Agenten anregen.
- **[Low] `bin/vibe-web.py:336-337`** — 500-Nachrichten-Limit kann bei sehr langen Kind-Sessions die Live-Ausgabe am alten Ende einfrieren
  - Beleg: `live_subagent_output` fragt `/message?limit=500&order=asc`. Falls opencode `limit` auf die chronologisch **ersten** 500 Nachrichten anwendet, erhalten sehr lange Läufe nie neuere Nachrichten — derselbe Symptomtyp („statisch"), den F30 behebt, nur für lange Sessions. Der 64-KiB-Tail hilft hier nicht, weil die Kürzung serverseitig vor dem Join passiert. Das ist bestehender AP14-Code; F30 macht ihn jedoch zur primären Quelle, wodurch der Randfall relevanter wird. Die opencode-Limit-Semantik ist in diesem Repo nicht belegt (AGENTS.md: frühere opencode-Annahmen nicht ungeprüft übernehmen).
  - Empfehlung: Nicht selbst „reparieren" — Grenze in `docs/features/F30.md` unter „Grenzen" benennen und die Limit-Semantik beim nächsten erlaubten echten opencode-Kontakt verifizieren; falls earliest-N bestätigt, beim Test-Agenten einen Grenzfall anstoßen.
- **[Low] `tests/browser/test_f30_subagent_view_ui.py:514-524`** — doppelter Knopf-Suchcode
  - Beleg: Die Vergrößern-Knopf-Suche (Schleife über `aria-label` mit „vergrö") steht wörtlich doppelt (EnlargeTest und PollingRefreshTest). Kleiner Wartungshinweis, kein Defekt.
  - Empfehlung: Beim nächsten Testkontakt durch den Test-Agenten in eine gemeinsame Helper-Methode ziehen. (Nicht vom Coding-Agent selbst ändern — Testhoheit liegt beim Test-Agenten.)

Keine Critical-, High- oder Medium-Befunde. Insbesondere: keine abgeschwächten oder leeren Assertions in den neuen Tests (alle 12 Fälle tragen reale, fehlschlagfähige Assertions und dokumentierte Vorbedingung/Aktion/Erwartung); keine Skip-Marker; Backend-Änderung ist minimal und lokal (nur `/api/subagent-output`), B12-Downgrade-/Sandbox-Semantik (`subagents_of`, `live_subagents`) und die F25/B11-Pfade wurden nicht angetastet; Manifest-F30-Eintrag vorhanden (`docs/import-manifest.json:824-833`); keine Geheimnisse in den neuen Dateien; `FEEDBACK.md` F30 korrekt weiterhin offen (Abschluss erst nach Review/Commit).

## Nicht verifiziert / Grenzen des Nachweises

- **Diff-Basis:** `git status`/`git diff 5f6c8fe` konnte ich wegen fehlender Shell-Berechtigung nicht ausführen. Die Änderungsorte und -inhalte der drei Produktdateien, der zwei neuen Testdateien und der Doku habe ich vollständig gelesen; ob **außerdem** weitere Dateien geändert wurden und ob bestehende Tests unangetastet blieben, konnte ich nicht unabhängig aus Git bestätigen und stütze mich hier auf die Änderungsliste des Koordinators.
- **Hashes:** Die aktualisierten SHA-256-Einträge im Manifest für `bin/vibe-web.py`, `bin/web/app.js`, `bin/web/styles.css` habe ich nicht neu berechnet (keine Befehle); `verify.sh quick` wurde mit Exit 0 gemeldet.
- **Testausführungen:** Alle Laufzeitergebnisse (Rotphase 3+4 Fehlfälle, 30 Unit-/12 Browser-Tests OK, `verify.sh quick` Exit 0, Vollauf 1735 Tests mit 2 vorbestehenden Fehlern inkl. Baseline-Reproduktion an `5f6c8fe`) sind dem Coding-/Test-Agenten-Bericht entnommen und von mir nicht erneut ausgeführt. Die zwei Vollauf-Fehler sind konsistent in `FEEDBACK.md:569` (B12, Stand 6959136) als vorbestehend dokumentiert; die F30-Dokumente enthalten keine `/home`-Pfade, die den Release-Geheimnis-/Pfadtest verschärfen könnten.
- **Test-Agent-Herkunft:** `TESTER=test-agent` ist in `.vibe/project.env:21` konfiguriert; der Bericht `docs/reviews/F30-test-agent-report.md` dokumentiert Herleitung ohne Implementierungsdiff und Rotphasen-Wortlaut. Die Urheberschaft selbst ist ein Berichts-Merkmal, keine von Git prüfbare Tatsache.
- **„Doppelt"-Belege:** `_logs/Website.log` (Z. 12715/12724) und `_logs/Website.log.state.json` liegen außerhalb des Repositories und waren mir nicht zugänglich; die Entscheidung „kein Fix, nur Doku" ist damit Koordinator-belegt, nicht reviewer-unabhängig.

## Restrisiken

- Unsicherheit über das opencode-`limit`-Verhalten (Low-Fund 2) und die angenommene Änderungsliste (Diff nicht aus Git gegenprüft). Beide sind dokumentiert und blockieren das Paket nicht.

Verdict: PASS
