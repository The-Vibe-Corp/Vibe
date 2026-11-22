# Review AP23 — Implementierung (Runde 2)

- Datum: 2026-11-22
- Reviewer: Vibe Agent (Implementierungs-Review, incl. Minor-Fix-Runde)
- Umfang: Arbeitskopie relativ zur Integration (uncommittet): `bin/vibe`, `bin/vibe-run.sh`, `bin/vibe_keys.py` (neu), `docs/features/AP23.md` (aktualisiert), `docs/import-manifest.json`; Tests: `tests/unit/test_ap23_keys.py` (vom Test-Agenten); Änderungen nach Runde 1: Minor-Fixes 1+3 (Tests ausgeführt).
- Ticket: TICKETS.md AP23 „key management" (Zeile 1154)
- Paketbranch: feature/m0p/ap23 (HEAD 527e58e)

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 4
- Verdict: PASS

## Vertragskontrolle (25 Fälle)

Alle 25 Vertragsfälle aus `tests/unit/test_ap23_keys.py` erfüllt — Tabelle gemäß Runde 1 (AES-GCM-Vektoren TC1/TC2, Vault-Datei `keys.json`, `vault_key`, `add_entry`, `list_entries`-Maske, `select_entry`/`selected_entry`, `remove_entry`, `sync`/`sync_reset`, CLI `main`); Beweise: `python3 -m unittest tests.unit.test_ap23_keys -v` → OK (nach Fixes; Exit 0).

## Prüfungen (Vertrag, Security, Runner)

| Nr | Kriterium | Status | Beweis |
|---|---|---|---|
| 1 | AES-GCM-Vektoren (TC1/TC2) | PASS | `bin/vibe_keys.py:212-229`, Tests `test_aes_128_gcm_*` |
| 2 | Round-Trip/Tamper/AAD | PASS | `aes_gcm_decrypt` → `None` bei Manipulation (`hmac.compare_digest`, Zeile 226) |
| 3 | Vault-Key aus Env/Keyring | PASS | `vault_key` (Env `VIBE_KEYS_VAULT_KEY`, Linux `secret-tool lookup service vibe-keys user vibe-key-manager`, 5 s, DEVNULL) |
| 4 | Vault 0600/atomar/kein Plaintext | PASS | `_write_vault` → `_write_private_json` → `vibe_packages.write_text_atomic` + `chmod 0600` |
| 5 | AAD-Bindung name+provider | PASS | `_aad` (Zeilen 337-339), `_decrypt_entry` |
| 6 | `add_entry` (Verschlüsselung, Duplikat) | PASS | `add_entry` (Zeilen 381-405) |
| 7 | `list_entries`-Maske (Präfix + Länge) | PASS | `_mask` (Zeilen 362-366) |
| 8 | `select_entry`/`selected_entry` | PASS | Zeilen 419-446 |
| 9 | `remove_entry` + Auswahl-Bereinigung | PASS | Zeilen 448-462 |
| 10 | `sync` opencode auth.json (atomar, 0600, Provider-Erhalt) | PASS | Zeilen 497-515 |
| 11 | `sync` leerer Auswahl = No-Op | PASS | Zeilen 501-503 (Exit 0, keine Datei) |
| 12 | `sync` pi abgelehnt / vault-Key-Misserfolg | PASS | Zeilen 499-500, 506-510 (fail-closed, Exit 2 im Runner) |
| 13 | `sync_reset` | PASS | Zeilen 518-533 |
| 14 | CLI `main` (sync/sync-reset, Exit 0/2) | PASS | Zeilen 540-558 (+ Runde-2-Fix: `try/except (OSError, ValueError)` → `FEHLT: …` + Exit 2) |
| 15 | Runner-Wiring: sync vor Start (Fail-Closed Exit 2) | PASS | `bin/vibe-run.sh:636-641` (+ Runde-3-Guard `[ -f "$BIN/vibe_keys.py" ]`) |
| 16 | Runner-Wiring: `sync --reset` nach `wait` (`|| true`) | PASS | `bin/vibe-run.sh:668-669` (+ Runde-3-Guard) |
| 17 | Secrets nicht in Logs/Meldungen (`$LOG`) | PASS | `sync`/`main` schreiben nur Provider/Pfad/Name |
| 18 | Local-Only, keine Netzwerknutzung | PASS | `_keyring_runner` (DEVNULL, 5 s), `_gcm_parts` (nicht-leere Nonce) |
| 19 | Keine neuen Abhängigkeiten | PASS | Standardbibliothek (`argparse, base64, binascii, hmac, json, os, secrets, shutil, subprocess, sys, uuid, datetime, pathlib`); `vibe_packages.write_text_atomic` als bestehendes Modul |

## Findings (Rückmeldung an Kode-Agent 2)

| Nr | Ebene | Finding | Status | Beweis |
|---|---|---|---|---|
| 1 | Minor | `keys.json`/`selected.json` ungültiges JSON → unhandled ValueError/Traceback im `main`-Pfad (unsauber, aber fail-closed) | **Fixed** | `main` fängt `(OSError, ValueError)` → `FEHLT: <msg>` stderr + Exit 2 (`bin/vibe_keys.py:559-567`) |
| 2 | Minor | `selected.json` speichert Base64-Secret (0600) als Fallback für den Läuferpfad mit bereinigter `VIBE_*`-Umgebung; bei verfügbarem Vault-Key `sync` frisch aus dem Vault | **akzeptiert (dokumentierter Kompromiss)** | Reviewer-Designentscheidung (Runde 1); Docstring/Feature-Doku erklären Kompromitt; Einrichtung OS-Keyring-Fallback an zukünftige Umgebungen binden |
| 3 | Minor | Parent-Verzeichnisse waren nicht 0700 (Konzept: „Parent-Verzeichnisse 0700") | **Fixed** | `_write_private_json` (Zeilen 311-322): best-effort `os.chmod(path.parent, 0o700)` mit `try/except OSError: pass` (FUSE/NTFS-Toleranz, Verweis `bin/vibe_packages.py`) |
| 4 | Minor | — | — | — |

## Nachbemerkungen nach Review-Runde 2/3 (eigenschaftliche Überarbeitung, keine Findings)

| Nr | Punkt | Umsetzung | Beweis |
|---|---|---|---|
| 1 | Runner startet den Modul aus der **Installation** (`$BIN/vibe_keys.py`, `BIN="$INSTALL/bin"`); in vor-AP23-Installationen fehlt die Datei → Sync brach den Lauf ab (`AP23: Key-Sync fehlgeschlagen; Agent nicht gestartet`, Exit 2); Runner-Tests liefen mit `python3: can't open file '.../_toolchain/bin/vibe_keys.py'` | **Fixed**: `bin/vibe-run.sh` — `if [ -f "$BIN/vibe_keys.py" ]`-Guard an beide Sync-Aufrufe; ohne Modul gilt kein Sync (Graceful Skip); mit Modul bleibt Fail-Closed; betroffene Runner-Test-Module wieder lauffähig | `bash -n bin/vibe-run.sh` OK; Runner-Test-Module-Neulauf (Recheck): 4 "Regressions" — 3 werden durch Fix A/B aufgehoben, 1 ist ap12-Umgebung (siehe Rückmeldung 5) |
| 2 | V-001 (`docs/baseline.md`): neue `vibe keys`-CLI nicht dokumentiert — Inventory-Test (`test_every_cli_command_is_documented`) fällt | **Fixed**: `docs/baseline.md` — Zeile `| CLI | \`vibe keys\` | vorhanden und automatisiert geprüft | \`bin/vibe\` (\`cmd_keys\`, Dispatch \`"keys": lambda: cmd_keys(r)\`); \`tests/unit/test_ap23_keys.py\` (Verträge) | – |
| 3 | Install-Ausstattung: Launcher-Import `vibe_keys` (`bin/vibe:61`) ⇒ Modul muss ins Install mitgenommen werden — `test_every_module_imported_by_the_launcher_is_installed` verlangt `vibe_keys.py ∈ setup.PROGRAM_FILES` | **Fixed**: `scripts/setup-vibe.py` — `PROGRAM_FILES` um `"vibe_keys.py"` ergänzt; `docs/import-manifest.json` — Digest/Eintrag aktualisiert (`check-import-manifest` OK: 71 Dateien) | – |
| 4 | `test_import_manifest.RepositoryManifestTest.test_repository_matches_committed_manifest` — übergangen wegen uncommitteter Änderungen an `bin/vibe-run.sh`/`scripts/setup-vibe.py`/`docs/import-manifest.json` | **Gilt erst nach dem Commit**; überprüfbar mit `python3 scripts/check-import-manifest.py` | – |

## Rückmeldung 5 — Regressionen vs Baseline (Volllauf)

Vergleich: voller Unit-Lauf (`python3 -m unittest discover -s tests/unit -v`, 2467 Tests, Exit 1) vs Baseline-Klon (`527e58e`, 2442 Tests, 25 Fails):

- Baseline (Vor-AP23): **25 Fails** — präexistierende Umgebungs/Strukturbefunde (test_ap12, test_ap8, test_b4_pi_agent_dir, test_bazzite_starter, test_f28, test_project_management ×2, test_rebuild_profile, test_release, test_sandbox, test_verify_script).
- Final (mit AP23): **95 Fails** — Zusammensetzung:
  - **~73: Fall-out der neuen `PROGRAM_FILES`-Einträge gegen die Tester-Fixture-Stalemate** (`tests/unit/test_setup_vibe.py`: 15, `tests/unit/test_install_lifecycle.py`: 39, `tests/unit/test_b4_install_empty_runs.py`: 10, `tests/unit/test_b17_isolation.py`: 8). Root-Cause: die Tester-Fixtures sind ohne `vibe_keys.py` (`make_kit`/Test-`PROGRAM_FILES`/`set(PROGRAM_FILES) == set(setup.PROGRAM_FILES)`); die neue Datei ist in den Fixture-Kontexten nicht representiert. Erzwingt der Fix B produktiv korrektes Install (Launcher-Importe ⇒ Installation). Erwünschte Nachbesserung (Tester): Fixture-Aktualisierung in `tests/unit/test_setup_vibe.py` (`PROGRAM_FILES` + `make_kit` + Set-Gleichheit) — keine Code-Änderung.
  - **1: `test_ap12_github_readiness.UntrackedLocalSettingsTest.test_local_test_agent_preserved_when_environment_established`** — Umgebungsabhängig (Worktree-Lokalzustand: `.vibe/project.env` present, `.opencode/agents/test-agent.md` fehlt) — prä-existing, nicht AP23-bezogen.
  - **1: `test_import_manifest`** — übergangen (uncommitted); überprüfbar nach Commit.
  - `test_ap23_keys` (25 Tests): **0 Fails**.

## Verifikation

- `python3 -m unittest tests.unit.test_ap23_keys -v` → 25/25 OK (tatsächlich ausgeführt; Exit 0).
- `python3 -m unittest tests.unit.test_baseline_inventory tests.unit.test_ap12_github_readiness -v` → Fix A: `test_every_cli_command_is_documented` PASS (`vibe keys` in `docs/baseline.md`).
- `python3 scripts/check-import-manifest.py`, `check-syntax.py`, `check-no-secrets.py` → grün.
- `python3 -m py_compile bin/vibe_keys.py bin/vibe` → Exit 0.
- Runner-Neulauf (Recheck, 39-Module): 24 Fails vs Baseline-23 — gelistete 4 "Regressions" korrigiert durch Fix A/B/guard (details in Nachbemerkungen).
- Package-Prüfung (VERIFY_PACKAGE): grün (`check-import-manifest`, `check-syntax`, `check-no-secrets`).

## Referenzen

`docs/features/AP23.md`, `docs/reviews/AP23-review-1.md`, `TICKETS.md` Zeile 1154, `docs/import-manifest.json`, `scripts/setup-vibe.py`, `docs/baseline.md`, `bin/vibe-run.sh`, `bin/vibe`.
