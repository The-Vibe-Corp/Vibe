# Review — GH-87 „fritzbox reconnect entfernen" (Runde 2)

Fokussierte Nachprüfung des finalen Stands nach den Korrekturen aus Runde 1. Keine Änderungen durch die Reviewerin; ausschließlich lesende Prüfung.

## Zusammenfassung

Alle Befunde aus Runde 1 sind behoben; im finalen Änderungsstand verbleibt kein blockierender Befund.

## Prüfung der Korrekturen

1. **Mittelbefund behoben.** `tests/unit/test_limits.py` enthält weder `RECONNECT_OUTPUT_MARKERS` und den zugehörigen Kommentar noch die alten Bezeichner (`assert_no_router_reconnect`, `assert_continue_without_reconnect`, `test_continue_quota_does_not_trigger_a_router_reconnect`, `test_continue_auth_does_not_trigger_a_router_reconnect`). Die neutralen Nachfolger sind vorhanden und werden verwendet: `assert_no_installation_cli_side_effect(marks)`, `assert_continue_has_no_cli_side_effect(mode)`, `test_continue_quota_has_no_installation_cli_side_effect`, `test_continue_auth_has_no_installation_cli_side_effect`. Die Sicherheitsprüfungen sind nicht geschwächt: CLI-AbwesenheitsAssertion, Wiederholungszahl, Continue-Hinweis und `install_cli_probe` (Exit 3) bleiben intakt. `docs/features/GH-87.md:20` beschreibt den Guard jetzt zutreffend ohne reconnect-spezifische Marker oder Bezeichner.
2. **Niedrige Befunde behoben.** `docs/features/README.md:234` und `docs/features/current/install-release.md:40` nennen nun 70 Dateien (vorher 71).
3. **Dokumentationsaussagen konsistent.** Dateianzahl, Manifest-Historie-Erläuterung und Diff-Zahlen in `docs/features/GH-87.md` stimmen mit den gelieferten Belegen überein.
4. **Keine neuen Referenzen.** Repo-weite Suche findet keine fritz-/reconnect-/Router-/IP-Abfrage-Reste in Code, UI, Tests oder aktiver Dokumentation über die akzeptierten historischen Aufzeichnungen hinaus; alte Bezeichner sind vollständig entfernt.
5. **Gates unverändert.** `tests/verify-baseline.json`, Prüfskripte und `min_tests` sind nicht Teil der Änderungsmenge.
6. **Gezielter Test:** vom Test-Agenten gemeldet `python3 -m unittest tests.unit.test_limits` → 16 Tests OK (eigene Ausführung in dieser Sitzung nicht möglich).

## Fazit

Sämtliche Befunde aus Runde 1 (Mittel, Niedrig, Niedrig/informativ) sind adressiert; kein verbleibender blockierender Befund.

Verdict: PASS
