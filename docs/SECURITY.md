# Sicherheit und Datenintegrität

Vibe ist lokal ausgerichtet. Nutzer behalten Kontrolle über lokale Daten, Zugangsdaten und Projektquellen. Sicherheitsrelevante Aktionen sind sichtbar, begrenzt und in auditierbaren Logs nachvollziehbar. [cite:1]

## Netzwerk und Zugriff

- Der Webserver bindet sich standardmäßig an Loopback.
- Ein explizit konfigurierter Netzwerk-Bind muss eine IP-Adresse sein; DNS-Hostnamen werden abgelehnt, um DNS Rebinding zu verhindern.
- Eine IP/CIDR-Allowlist kann Clients einschränken; Loopback bleibt dadurch erlaubt. [cite:1]

## Authentifizierung

Die Authentifizierung verwendet einen Token oder ein Passwort mit Session Cookie, statt einen permanenten Token im Browser zu hinterlassen. Mutierende API-Anfragen erfordern gültige Authentifizierung. [cite:1]

Zusätzlich werden Host- und Origin-Checks sowie CSRF-Schutz durchgesetzt. [cite:1]

## Secrets

- Tokens erscheinen niemals in Access-Logs oder Fehlermeldungen.
- Credentials gehören nicht in Agent-Dateien oder dieses Repository.
- Secret-Werte bleiben beim Speichern erhalten, werden aber maskiert.
- Secrets werden weder in Antworten, Fehlermeldungen, Command-Anzeigen noch Logs offengelegt. [cite:1]

## Eingaben und Dateizugriff

- Input- und Request-Größen werden begrenzt.
- Path Traversal und unautorisierte Symlink-Ziele werden verhindert.
- Externe Commands werden mit Argumentlisten statt Shell-Concatenation aufgerufen, sofern keine explizit konfigurierte Shell-Ausführung erforderlich ist. [cite:1]

## Trusted Code

Projekt-Check-Commands und MCP-Programme werden als **trusted-code execution** behandelt, nicht als passive Konfiguration. [cite:1]

## Dateien und Backups

- Dateien werden atomar geschrieben.
- Gleichzeitige Änderungen werden erkannt.
- Backups kollidieren nicht und können sensible Daten enthalten.
- Sensible Laufzeitdaten werden auf einem angemessen geschützten Dateisystem gespeichert.
- Unix-Berechtigungen werden auf FUSE oder NTFS nicht ohne Nachweis als wirksam behandelt. [cite:1]

## Git und Repository

API-Keys, Tokens, globale Konfigurationen oder persönliche Agenten werden niemals automatisch zu Git hinzugefügt. [cite:1]

## Sandbox

Agenten können optional in einer Sandbox laufen, um den Zugriff auf den Host zu begrenzen. [cite:1]

## Sicherheitsmeldungen

Sicherheitsprobleme bitte nicht öffentlich als Issue melden. Verwende die Richtlinien in [`SECURITY.md`](../SECURITY.md). [cite:1]
