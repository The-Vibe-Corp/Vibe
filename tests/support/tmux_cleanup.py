"""Aufräumumgebung für einen eigenen, isolierten tmux-Server.

Ein geerbtes ``TMUX`` hat in tmux Vorrang vor ``TMUX_TMPDIR``: es nennt den
Socket der Sitzung, aus der ein Prozess gestartet wurde. Wird beim Aufräumen
nur ``TMUX_TMPDIR`` gesetzt, richtet sich ``tmux kill-server`` gegen den
Server des Aufrufers und beendet dort alle Sitzungen – Dashboard, opencode
und laufende Agentenläufe eingeschlossen.

``cleanup_env`` entfernt deshalb die Client-Variablen und setzt ``TMUX_TMPDIR``
auf das eigene Verzeichnis. Die übergebene Umgebung bleibt unverändert.
"""

CLIENT_VARIABLES = ("TMUX", "TMUX_PANE")


def cleanup_env(environ, tmux_dir):
    """Umgebung für ``tmux kill-server`` auf dem eigenen Server."""
    environment = {
        key: value
        for key, value in environ.items()
        if key not in CLIENT_VARIABLES
    }
    environment["TMUX_TMPDIR"] = str(tmux_dir)
    return environment
