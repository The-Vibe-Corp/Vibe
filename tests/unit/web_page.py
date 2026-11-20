"""Hilfe für Tests der ausgelieferten Weboberfläche (V-019).

Seit V-019 besteht die Oberfläche aus getrennten statischen Dateien
(``bin/web/index.html``, ``styles.css``, ``app.js``). Tests, die Inhalte der
Oberfläche prüfen, laden deshalb HTML und statische Dateien zusammen. Sie
prüfen damit weiterhin genau das, was der Browser beim Aufruf erhält, statt
sich auf eine einzelne eingebettete Seite zu verlassen. Seit AP22 liegt die
alte Oberfläche unter ``/classic`` (Datei ``bin/web/classic.html``); dieser
Helfer liefert deshalb die klassische Seite.
"""

ASSETS = ("/static/styles.css", "/static/app.js")


def served_page(request):
    """Liefert HTML, Stylesheet und Skript der ausgelieferten Seite zusammen.

    ``request`` ist die Anfragehilfe des jeweiligen Tests und liefert
    ``(status, text)``. Jede der drei Antworten muss mit 200 ausgeliefert
    werden; fehlt eine Datei, schlägt der Test an dieser Stelle fehl.
    """
    status, html = request("/classic", token=False)
    if status != 200:
        raise AssertionError("Klassische Seite nicht ausgeliefert: HTTP %s" % status)
    parts = [html]
    for path in ASSETS:
        status, body = request(path, token=False)
        if status != 200:
            raise AssertionError("%s nicht ausgeliefert: HTTP %s" % (path, status))
        parts.append(body)
    return "\n".join(parts)
