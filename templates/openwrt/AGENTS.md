# Projekt: {{NAME}} (OpenWrt)
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Umgebung: Distrobox android-dev (Steuer-Container). $VIBE ist gesetzt. Nichts in ~ ablegen.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL). Shell-Befehle laufen höchstens etwa 2 Minuten; Längeres im Hintergrund mit Log starten und das Log abfragen.
- Nach jedem Arbeitspaket: Tests grün, git commit.
- Builds mit den offiziellen OpenWrt-Containern (SDK oder ImageBuilder, z. B. ghcr.io/openwrt/sdk bzw. ghcr.io/openwrt/imagebuilder, passend zu Ziel/Subtarget/Version) auf dem HOST: `distrobox-host-exec podman run ...` (nicht auf dem Host getestet).
- Ziel-Architektur, OpenWrt-Version, Feeds und Pakete stehen in SPEC.md; Build-Artefakte (bin/, build_dir/, staging_dir/) nie committen, Download-Cache (dl/) wiederverwenden.
- Tests ohne Gerät: Paket baut fehlerfrei, Paketliste/Abhängigkeiten stimmen, Skripte mit `shellcheck`, UCI-Konfiguration syntaktisch geprüft. Flashen oder Tests auf dem Router macht der Mensch.
