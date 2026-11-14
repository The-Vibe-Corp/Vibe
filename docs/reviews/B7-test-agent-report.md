# B7 — Test-Agenten-Report: GitHub-Authentifizierung über die UI (Bug zu AP6)

Autor: unabhängiger Test-Agent (TESTER=test-agent, .vibe/project.env)
Datum: 2026-11-10 · Arbeitskopie: Worktree vibe-B7-y4ZwXo, Branch
`vibe/vibe-B7-1794295794403437735-1660139-21935`
Quellen: TICKETS/FEEDBACK.md (Eintrag B7), SPEC.md „Sicherheit und
Datenintegrität“, verbindlicher Schnittstellenvertrag aus der Testanforderung.
Die Testfälle wurden unabhängig vom Implementierungsdiff abgeleitet.
(Ablage: vom Coding-Agenten unverändert übernommen; Berichtsinhalt des
Test-Agenten.)

## 1. Erzeugte Testdateien (Ausschließlichkeit)

| Datei | Testfälle | Befehl (verbindlich) | Exit |
|---|---|---|---|
| tests/unit/test_b7_github_auth.py | 31 | `python3 -m unittest discover -s tests/unit -p test_b7_github_auth.py -v` | grün 0 |
| tests/browser/test_b7_github_auth_ui.py | 6 | `python3 -m unittest discover -s tests/browser -p test_b7_github_auth_ui.py -v` | grün 0 |

Kein bestehender Test wurde geändert, abgeschwächt oder gelöscht; Produkt-
und Build-Dateien wurden vom Test-Agenten nicht angerührt. Die Implementierung
ist nicht Bestandteil dieses Reports (Prüfung obliegt dem Reviewer).

## 2. Testisolation (Vorbereitungen, für Nachvollziehbarkeit)

- Kein echtes Netz, keine Modellkosten, keine produktive Instanz. github.com
  wird in keinem Test berührt.
- Unit: temporäres `VIBE_STATE`, gelöschte Token-Umgebung (GITHUB_TOKEN/GH_TOKEN),
  `GIT_CONFIG_GLOBAL/SYSTEM=devnull`, `GIT_TERMINAL_PROMPT=0`, `NO_PROXY=127.0.0.1`.
  Git läuft nur mit deaktivierter Systemkonfiguration und fester Test-Identität.
- Credential-Tests prüfen über einen `subprocess.run`-Stub (Protokollierung von
  argv, cwd und der übergebenen Prozessumgebung — keine echten Git-Prozesse).
- Ein realer Leck-Probe fährt echtes Git gegen einen 401-HTTP-Server auf
  127.0.0.1 („fremder Host“) und zeichnet jede Authentifizierung auf.
- Browser: Dashboard als echter Prozess (freier Port, temp-VIBE/VIBE_STATE/
  HOME, Fake-opencode/pi), Fake-GitHub-REST nur auf 127.0.0.1; Projekte
  `gh-b7-demo` (file://-Origin, Fake-API), `gh-b7-official` (offizielle API,
  Merge-Request scheitert offline verständlich am fehlenden Token),
  `gh-b7-broken` (einziges Remote `http://127.0.0.1:1/x.git` scheitert sofort).
- Token-Aktionen der Tests: Token speichern/entfernen ausschließlich
  über die UI bzw. `/api/github`; Testtoken „b7-unit-fake-token-123“ /
  „b7-unit-env-token-456“ / „b7-browser-token-9999xyz“ (Fake-Werte, keine
  Geheimnisse; das Dashboard bekommt Token nie über die Umgebung).

## 3. Testfallverzeichnis Unit (31)

### TokenStoreTest — AC1 (Token-Speicher im Zustandsordner)
1. test_token_state_path_lies_inside_vibe_state_and_moves_with_it — Pfad liegt
   absolut im temp-VIBE_STATE und folgt einem ENV-Wechsel (keine Kopplung an
   die Modul-Importzeit).
2. test_save_and_read_roundtrip_stores_exact_token_without_newline — Datei-
   inhalt exakt der Token, read_stored_token()==Token, kein angehängter
   Zeilenumbruch.
3. test_save_token_rejects_empty_and_control_characters_without_side_effects —
   ValueError für "" / "   " / "\0" / "\n" / "\r" innerhalb des Texts; keine
   Restdatei nach allein fehlgeschlagener Speicherung; bereits gespeicherter
   Token bleibt unverändert.
4. test_file_mode_is_0600_best_effort — asserts 0o600 (nur, wenn chmod im FS
   wirksam ist; auf FUSE/NTFS fällt die Modus-Assertion weg, Existenz+Inhalt
   bleiben Pflicht — SPEC „Bei FUSE/NTFS nicht fälschlich wirksame Rechte“).
5. test_read_without_stored_token_returns_empty_string — "" ohne Ausnahme;
   auch nach Save+Delete.
6. test_delete_token_removes_file_and_is_tolerant — Datei weg, zweiter
   Aufruf ohne Ausnahme.
7. test_token_status_precedence_and_clear_state — {"set","source"}:
   umgebung > gespeichert; nach delete {set:False,source:""}.
8. test_status_view_reports_auth_without_token_content — status(project)
   enthält `auth {set, source}` (gespeichert/leer); serialisierter Status
   ohne Tokeninhalt.

### GitCredentialTest — AC2/AC3 (Git-Credential-Mechanik, subprocess-Stub)
9.  test_fetch_with_stored_token_gets_url_scoped_credentials_without_token_in_argv —
    gespeichertes Token: Fernaufruf trägt `credential.https://github.com.helper`
    + `x-access-token` (in argv oder ENV); Tokeninhalt nur in der übergebenen
    Prozessumgebung (Injektionsnachweis, da Start-ENV sauber ist); niemals im
    argv; GIT_TERMINAL_PROMPT=0 bleibt.
10. test_push_with_stored_token_gets_credentials_the_same_way — analog für push.
11. test_pull_with_env_token_gets_credentials_without_token_in_argv — analog
    für pull mit GITHUB_TOKEN; bestehende Regeln unverändert.
12. test_without_token_git_behaviour_is_unchanged — ohne Token: keine
    github.com-Helper-Konfiguration, kein x-access-token, Prompt-Schutz bleibt.
13. test_non_github_remote_never_receives_stored_token_mechanism —
    Remote git.example.com: jede `credential.`-Konfiguration muss exakt auf
    `https://github.com` gescort sein (kein Fremd-Host, kein ungeordneter
    Helper); Tokeninhalt nie argv; kein GIT_ASKPASS/SSH_ASKPASS im ENV des
    Netz-Aufrufs.

### GitHostLeakProbeTest — AC3/AC5 (echtes Git, roher 401-Host auf 127.0.0.1)
14. test_real_git_to_non_github_http_host_never_uploads_stored_token —
    Protokoll des Probe-Servers enthält nie den gespeicherten Token (kein
    Authorization, keine URLs); fetch scheitert mit geführter, token-freier
    Meldung (AC5-Bonus: „terminal prompts disabled“ wird klassifiziert).

### RestAuthTest — AC3/AC4 (REST-Token-Auflösung)
15. test_list_issues_resolves_env_token_by_default — recorder-Stub: Token ==
    ENV-Token.
16. test_list_issues_resolves_stored_token_for_official_api — Token ==
    gespeicherter Token.
17. test_env_token_wins_over_stored_token — Umgebung gewinnt.
18. test_stored_token_is_never_sent_to_non_official_api — echter Fake-REST auf
    127.0.0.1: keine Authorization mit dem gespeicherten Token in Logs des
    Servers.
19. test_env_token_keeps_rest_delivery_to_configured_api — Authorization
    "Bearer <ENV-Token>" an die konfigurierbare API (bisheriges Lieferverhalten).
20. test_create_pull_request_without_any_token_fails_comprehensibly —
    „Kein GitHub-Zugangstoken …“, kein Aufruf (Recorder leer).
21. test_create_pull_request_uses_stored_token_for_official_api — Recorder
    erhielt den gespeicherten Token; PR-Ergebnis ({number}) unverändert.
22. test_errors_and_status_never_disclose_token — alle Fehlerpfade und
    token_status-Ausgaben ohne Tokeninhalt.

### ErrorClassificationTest — AC5 (klare Klassifizierung + Handlungshinweis)
23. test_could_not_read_username_is_classified_with_token_guidance
24. test_terminal_prompts_only_is_classified_with_token_guidance
25. test_broken_askpass_is_classified_with_token_guidance (ksshaskpass)
26. test_german_askpass_variant_is_classified_with_token_guidance
    („Zusammenführen nicht möglich … ksshaskpass … could not read Username")
27. test_authentication_failed_is_classified_with_token_guidance
    je × fetch/pull/push (subTests): ok=False; Meldung enthält Handlungshinweis
    (Regex token|zugangsdaten|authentifiz|anmelden|hinterlegen); nie
    Tokeninhalt; gilt auch trotz bereits hinterlegtem Token.

### TokenRoutesWebTest — AC6 (Web-API /api/github, echtes Dashboard)
28. test_token_save_persists_state_and_hides_secret — POST token.save → 200,
    Datei im VIBE_STATE mit exaktem Inhalt; Antwort/Body ohne Tokeninhalt;
    auth {set:true, source:"gespeichert"}.
29. test_token_clear_removes_the_stored_token — Datei weg; auth
    {set:False,source:""}; wiederholtes clear bleibt tolerant (200).
30. test_unauthorized_github_calls_are_rejected — falsches/kein X-Token ≥400,
    strukturiert, ohne Geheimnis, keine Dateianlage (V-004-Absicherung bleibt).
31. test_detail_view_reports_auth_state_without_secret — GET /api/project
    zeigt `github.auth` gespeichert/leer, ohne Tokeninhalt.

## 4. Testfallverzeichnis Browser (6)

32. test_auth_block_is_visible_with_password_input_and_both_actions (AC7) —
    Token-Block sichtbar (Text „…Token…“), genau ein `input[type=’password’]`,
    Buttons „Token speichern“/„Token entfernen“ (Regex
    token…*(speichern|hinterlegen) / token…*(entfernen|löschen)).
33. test_save_then_clear_token_via_ui_persists_without_leaking_secrets
    (AC6/7/8) — Save: Datei erscheint an token_state_path() mit exaktem
    Inhalt; Karte zeigt Status (Regex gespeichert|hinterlegt|umgebung);
    Clear: Datei weg. Alle gefangenen HTTP-Responses und der Seitentext
    ohne Tokeninhalt.
34. test_failed_git_actions_leave_persistent_message_in_card_error_box (AC7) —
    fetch/pull/push auf dem sofort scheiternden Fernabruf (127.0.0.1:1): Meldung in der
    Karten-Fehlerbox (`.bad` innerhalb der Karte, nicht nur Toast); bleibt
    sichtbar + nicht leer nach ≥2,2 s.
35. test_merge_request_failure_shows_token_guidance_and_clears_after_success
    (AC5/7) — Bestätigungsfluss pr ohne Token: Fehlerbox enthält Token-Hinweis,
    steht bleibt; die nächste erfolgreiche Aktion (Speichern) leert sie.
36. test_no_token_content_in_any_api_response (AC8) — Save+Clear über die UI;
    Protokolle jeder Response ohne Tokeninhalt; ≥2 /api/github-Aufrufe
    (Beleg, dass die UI-Aktionen über die Web-API laufen).
37. test_fetch_failure_message_never_contains_a_stored_token (AC8) — Manuell
    hinterlegter Token taucht in fetch-Fehlerbox/Seitentext nicht auf.

## 5. Rotphase (vor der Implementierung, tatsächlich ausgeführt)

- Unit: `python3 -m unittest discover -s tests/unit -p test_b7_github_auth.py -v`
  → `Ran 31 tests in 2.146s — FAILED (failures=3, errors=32)`, Exit 1.
- Browser: `python3 -m unittest discover -s tests/browser -p test_b7_github_auth_ui.py -v`
  → `Ran 6 tests in 80.410s — FAILED (failures=3, errors=4)`, Exit 1.

Fehlschlagmuster (alle intendiert, keine Rotphase durch Broken Fixture,
Syntax oder Umgebungsprobleme):
- AttributeError auf fehlende Schnittstellen `token_state_path`,
  `save_token`, `read_stored_token`, `delete_token`, `token_status` in
  bin/vibe_github.py (Token-Speicher, Status v. a. in setUp).
- FAIL: Credential-Helper `credential.https://github.com.helper` fehlt bei
  fetch/pull/push (Stub-Protokolle: keine git-Credential-Mechanik).
- FAIL: list_issues reicht einen Umgebungstoken NICHT automatisch weiter
  (`Bearer <env>` fehlt am Fake-REST; recorder token=None).
- Browser FAIL: kein Auth-Block/Passwortfeld/keine Token-Buttons in der Karte;
  ERROR: token.save via UI endet ohne Persistenz (Schnittstelle fehlt);
  ERROR: `.bad`-Fehlerbox erscheint bei fetch/pull/push-Fehlern nicht
  (Timeout 15 s) — genau die gemeldete B7-Lücke.
- Grün stehende Baseline-Aussagen zu Beginn der Rotphase (beide
  Regressionwächter, müssen grün bleiben):
  create_pull_request ohne Token meldet verständlich „Kein GitHub-
  Zugangstoken …“ und ruft nichts auf; pr-Fehlschlag füllt die
  Karten-Fehlerbox dauerhaft (existierendes AP6-Niveau).

Fixture-Hinweis: Die ersten beiden Rotphasenläufe des Browsers brachen
innerhalb `setUpClass` an der fehlenden `token_state_path`-Schnittstelle;
danach wurde die Test-Fixture rotphasen-tolerant (keine Änderung der
Assertionen): Seitdem laufen alle 6 Testfälle und scheitern am fachlichen
Verhalten. Der endgültige Browser-Rotphaselauf (80,410 s) entspricht dem
finalen Testdateiinhalt bis auf eine rein ordnungswidrige Verschiebung
eines `assertIsNotNone` (Position, nicht Aussage).

Logdateien (temporär, außerhalb des Repos):
/tmp/opencode/vibe-sandbox/vibe-B7-y4ZwXo-6921a82ae4/tmp/b7logs/
  red_unit.log · red_browser4.log · green_unit.log · green_browser.log ·
  monitor_ap06_unit.log

## 6. Grünphase (nach der Implementierung, vom Test-Agenten persönlich ausgeführt)

- Unit: `python3 -m unittest discover -s tests/unit -p test_b7_github_auth.py -v`
  → `Ran 31 tests in 2.209s OK`, Exit 0.
- Browser: `python3 -m unittest discover -s tests/browser -p test_b7_github_auth_ui.py -v`
  → `Ran 6 tests in 14.884s OK`, Exit 0.
- Baseline: `unittest discover -s tests/unit -p test_ap06_github.py -v`
  → `Ran 54 tests in 10.942s OK`, Exit 0 (bestehende AP6-Tests laufen grün).

Die Testdateien blieben zwischen Rot- und Grünphase inhaltlich unverändert
(31/6 `def test_`, Dateizeitstempel identisch mit denen der Rotphase; keine
Assertionsabschwächungen, keine gelöschten Tests).

## 7. Zuordnung der Akzeptanzkriterien

| AC | Unit-Tests | Browser-Tests |
|---|---|---|
| 1 Token-Speicher/Status | 1–8, 22 | — (indirekt 33) |
| 2 Git-Credential-Mechanik | 9–12 | — |
| 3 Host-Scoping/Umgebungs-Token | 13, 14, 16, 18, 19 | — |
| 4 REST-Token-Auflösung | 15–17, 20, 21 | — |
| 5 Fehlerklassifizierung | 14, 23–27 | 35 |
| 6 Web-API token.save/clear | 28–31 | 33, 36 |
| 7 UI-AuthBlock + errBox | 8 | 32–35 |
| 8 Kein Tokeninhalt in Meldungen/Logs/Ausgaben | 8, 22, 30, 31 | 33, 36, 37 |

## 8. Grenzen und verbleibende Lücken

- chmod-Assertion in Unit-Test Nr. 4 ist umgebungsbedingt nur wirksam, wenn
  chmod real wirkt (Probe im Test); auf FUSE/NTFS ist die Prüfung laut SPEC
  abgeschwächt (best effort ohne Rechteanspruch).
- Der Credential-AC beweist die Vertraulichkeit des GitHub-Aufrufs strukturell
  (Scoping-Regel, argv/ENV-Audit + echter Leck-Probe gegen 127.0.0.1);
  ein echter https://github.com-Aufruf wurde wie vorgesehen nie ausgeführt.
- Die Akzeptanz „Benutzername x-access-token“ und die
  exakten UI-Bezeichnungen (Buttons/Statuswörter) sind mit dem ggf. leicht
  abweichenden Meldungstext (Regex statt exakter Gleichheit) toleriert;
  die Assertions prüfen Akzeptanzinhalte, keine Formulierungen.
- Nicht vom Test-Agenten geprüft: Weitlauf-Suiten (verify.sh full),
  Doku-Abgleich (docs/features/B7.md), Trilium-Sync, Review —
  verbleiben in der Verantwortung des Coding-/Review-Agenten.

---

# Nachtrag 1 — Fall test_auth_line_follows_the_server_source_after_save_and_clear (Review-Befund „statische Auth-Quelle")

Datum: 2026-11-10 · Branch: vibe/vibe-B7-1794295794403437735-1660139-21935 (worktree vibe-B7-y4ZwXo)
Autor: unabhängiger Test-Agent (TESTER=test-agent)

## Neuer Browser-Testfall (Fallzahl 6 → 7)

**Datei:** `tests/browser/test_b7_github_auth_ui.py`
**Testfall:** `test_auth_line_follows_the_server_source_after_save_and_clear`

- **Vorbedingung:** Zweites, im Testfall selbst gestartetes Dashboard
  (eigener Port, eigenes VIBE_STATE `_state-envtoken`, eigener
  Runtime-Ordner, gleiche VIBE-Wurzel), dessen Prozessumgebung
  `GITHUB_TOKEN="b7-fake-env"` trägt (Fake-Wert, kein echtes Secret, keine
  produktiven Konfigurationen); kein gespeicherter Token. Werkzeuge/Fakes
  wie im Basismodul (fakebin, Fake-GitHub-API ausschließlich 127.0.0.1,
  kein echtes Netz).
- **Aktion:** Projekt „gh-b7-demo" → Einstellungen → Karte „Git & GitHub"
  aufklappen; initialen Auth-Zustand der Zeile `div[data-auth]` lesen;
  Passwortfeld füllen, „Token hinterlegen" klicken; Server-Erfolg wird vor
  der Zeilenbeobachtung über den Zustandsnachweis belegt (Token-Datei
  erscheint im `_state-envtoken`); Zeile 2,5 s vollständig beobachten;
  danach „Token entfernen" klicken, Erfolg erneut über Datei-Nachweis
  belegen (verschwindet), Zeile wieder 2,5 s beobachten.
- **Erwartung:** Die Zeile zeigt — nach belegtem Server-Erfolg beider
  Aktionen — ausschließlich die Serverquelle `extra["auth"].source`
  (hier stets „umgebung"; Vertragsformel
  `setAuth(r.auth && r.auth.set ? r.auth.source : '')`; Ref:
  `bin/vibe-web.py`, `/api/github` token.save/token.clear,
  `extra["auth"]`). Die hartkodierten Texte „GitHub-Token gespeichert …"
  bzw. „Kein Token hinterlegt …" dürfen in keiner Beobachtung auftreten.
- **Fehlerfall (Rotphase):** Hartkodierte Anzeige nach token.save
  („gespeichert") bzw. nach token.clear ('' → „Kein Token hinterlegt").

## Rotphase (vor der Implementierung, tatsächlich ausgeführt)

Befehl:

    TMPDIR=/tmp/opencode/b7x python3 -m unittest discover -s tests/browser -p test_b7_github_auth_ui.py -v

- Erster Rotlauf: `Ran 7 tests in 27.499s — FAILED (failures=1)`, Exit 1;
  Log: `/tmp/opencode/vibe-sandbox/vibe-B7-y4ZwXo-6921a82ae4/tmp/b7logs/red_authsource_browser.log`
  (Clear-Zweig scheiterte; der Save-Check lief zufällig durch, weil die
  erste Zeilenablesung der Server-Response zuvorkam — Race).
- Endgültiger gehärteter Rotlauf (Server-Erfolg vor der Beobachtung
  über Zustandsnachweis belegt; alle 2,5-s-Fenstertexte je Aktion
  geprüft): `Ran 7 tests in 17.787s — FAILED (failures=1)`, Exit 1;
  Log: `…/b7logs/red_authsource_browser2.log`.
  FAIL: `test_auth_line_follows_the_server_source_after_save_and_clear`
  → AssertionError: 'gespeichert' unexpectedly found in 'GitHub-Zugang:
  GitHub-Token gespeichert (im Zustandsordner, außerhalb jedes
  Projektordners).' — token.save-Zweig hartkodiert statt Serverquelle
  'umgebung'. Clear-Zweig (Diagnose-Einzelrun mit voller
  Beobachtungsliste): „Kein Token hinterlegt" bleibt nach belegtem
  token.clear dauerhaft stehen statt 'umgebung'.
- 6 Basisfälle blieben in beiden Rotläufen unverändert ok.

## Grünphase (nach Implementierung durch den Coding-Agenten, vom Test-Agenten ausgeführt)

Befehl:

    TMPDIR=/tmp/opencode/b7x python3 -m unittest discover -s tests/browser -p test_b7_github_auth_ui.py -v

- **Ran 7 tests in 20.188s — OK**, Exit 0.
  Log: `…/b7logs/green_authsource_browser.log` (7/7 `test_`-Zeilen,
  0 FAIL/ERROR).
- Regression AP06-Unit: `TMPDIR=/tmp/opencode/b7x python3 -m unittest
  tests.unit.test_ap06_github -v` → `Ran 54 tests in 10.972s / OK`, Exit 0.
  Log: `…/b7logs/green_authsource_ap06.log`.
- Unit-B7 (Datei unverändert): … `test_b7_github_auth.py -v` →
  `Ran 31 tests in 2.203s / OK`, Exit 0.
  Log: `…/b7logs/green_authsource_unit.log`.

## Implementierungsprüfung (Befundbestätigung)

In `bin/web/app.js` tragen nach token.save und token.clear beide
`setAuth`-Aufrufe die Serverquelle:

    if(r.ok){tokenIn.value='';setAuth(r.auth&&r.auth.set?r.auth.source:'')}

Damit grün ohne Assertionsabschwächung und ohne gelöschte Tests; der
neue Fall fehlte in der Rotphase wie belegt und ist nach der Änderung
grün.

## Bestandsnachweis

- `tests/browser/test_b7_github_auth_ui.py`: 7 Testfälle,
  MD5 `7a0320655b121e96db526e5e3b656eb2` (ersetzt
  `8dffa481806e4f417a2150557d7c0d49`; Änderung ausschließlich der neuen
  Testmethode, `cls.fakebin`-Attribut und Helfer `start_token_dashboard`).
- `tests/unit/test_b7_github_auth.py`: unverändert, 31 Fälle,
  MD5 `5e2d560f680bb922237c2dad6cdd1a72`.
- Vom Test-Agenten wurden keine Produktdateien geändert, nichts gestaged
  und nichts committed.
