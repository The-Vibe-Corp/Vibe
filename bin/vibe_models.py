"""Versionierter Modellkatalog für vibe (V-011, nur Standardbibliothek).

Der Katalog ``models.json`` trennt belegte Fakten von Einschätzungen. Jede
nicht triviale Angabe trägt Quelle und Datum; unbekannte Werte sind erlaubt und
werden ausdrücklich als ``unbekannt`` geführt. Preise nennen Währung, Einheit,
Gültigkeitsdatum, Quelle und getrennte Tarife. Unbestätigte Modell-IDs und
veraltete Preise werden gemeldet, nicht stillschweigend übernommen.

Der alte Katalog (Schema 1, ``{"models": [...]}``) bleibt lesbar. Er wird als
Altbestand markiert: alle Angaben erhalten Quelle und Datum des Altkatalogs,
Altpreise ohne Gültigkeitsdatum werden zu ``unbekannt``.

Der Import dieses Moduls liest keine Dateien und startet keine Prozesse.
"""
import json
import re
from datetime import date

SCHEMA_VERSION = 2
MAX_PREIS_ALTER_TAGE = 90

PREIS_STATUS = ("kostenlos", "bekannt", "unbekannt")
ID_STATUS = ("bestaetigt", "entfernt")
FAKTEN_ARTEN = ("fakt", "messung", "altbestand")
EINSCHAETZUNG_ARTEN = ("einschaetzung", "nutzerbericht", "messung", "altbestand")
ALLE_ARTEN = tuple(sorted(set(FAKTEN_ARTEN) | set(EINSCHAETZUNG_ARTEN)))

_UNBEKANNT = {
    "", "unbekannt", "unklar", "keine daten", "keine angabe", "keine angaben",
    "kein wert", "n/a", "unbekannt (altbestand)",
}
_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WAEHRUNG_RE = re.compile(r"^[A-Z]{3}$")


def _text(value):
    return "" if value is None else str(value).strip()


def is_unknown(value):
    """Unbekannt ist ein zulässiger Wert, keine fehlende Angabe."""
    if value is None:
        return True
    return _text(value).lower() in _UNBEKANNT


def parse_date(value):
    """Liest ein ISO-Datum (JJJJ-MM-TT) oder lässt unbekannt (None) stehen."""
    text = _text(value)
    if not _DATUM_RE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def assertion_text(node):
    """Sichtbarer Wert einer Angabe; ``unbekannt`` bleibt ``unbekannt``."""
    if not isinstance(node, dict):
        return "unbekannt"
    value = node.get("wert", node.get("text"))
    return "unbekannt" if is_unknown(value) else _text(value)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "?"
    return f"{value:.2f}".replace(".", ",")


def price_text(price):
    """Preisangabe mit Währung, Einheit und getrennten Tarifen.

    ``unbekannt`` wird nicht durch ``0`` ersetzt. Eine andere Währung wird
    unverändert genannt, damit keine falsche Euro-Angabe entsteht.
    """
    if not isinstance(price, dict):
        return "unbekannt"
    status = _text(price.get("status"))
    if status == "unbekannt":
        return "unbekannt"
    waehrung = _text(price.get("waehrung")) or "?"
    einheit = _text(price.get("einheit")) or "?"
    tarife = price.get("tarife") if isinstance(price.get("tarife"), dict) else {}
    eingabe = _number(tarife.get("eingabe"))
    ausgabe = _number(tarife.get("ausgabe"))
    if status == "kostenlos":
        return f"kostenlos (Eingabe {eingabe} / Ausgabe {ausgabe} {waehrung} je {einheit})"
    return f"{eingabe} / {ausgabe} {waehrung} je {einheit}"


def is_free(entry):
    """Kostenloses Modell laut Katalog; alles andere ist nicht automatisch frei."""
    price = entry.get("preis") if isinstance(entry, dict) else None
    return isinstance(price, dict) and _text(price.get("status")) == "kostenlos"


def _add(findings, code, pfad, text):
    findings.append({"code": code, "pfad": pfad, "text": text})


def _check_assertion(node, pfad, allowed_arts, findings):
    """Prüft eine einzelne Angabe; unbekannte Werte brauchen keine Quelle."""
    if not isinstance(node, dict):
        _add(findings, "angabe_ungueltig", pfad, "Angabe ist kein Objekt.")
        return
    value = node.get("wert", node.get("text"))
    if is_unknown(value):
        return
    art = _text(node.get("art"))
    if not art:
        _add(findings, "art_fehlt", pfad, "Art der Angabe fehlt (fakt, messung, nutzerbericht, einschaetzung, altbestand).")
    elif art not in ALLE_ARTEN:
        _add(findings, "art_ungueltig", pfad, f"Unbekannte Art '{art}'.")
    elif art not in allowed_arts:
        _add(findings, "art_falsch", pfad, f"Art '{art}' gehört nicht in diesen Abschnitt.")
    if not _text(node.get("quelle")):
        _add(findings, "quelle_fehlt", pfad, "Quelle fehlt.")
    datum = _text(node.get("datum"))
    if not datum:
        _add(findings, "datum_fehlt", pfad, "Datum fehlt.")
    elif parse_date(datum) is None:
        _add(findings, "datum_ungueltig", pfad, f"Datum '{datum}' ist kein ISO-Datum (JJJJ-MM-TT).")


def _check_tarif(tarif, pfad, findings):
    if not isinstance(tarif, dict):
        _add(findings, "tarif_ungueltig", pfad, "Tarif ist kein Objekt.")
        return
    for key in ("eingabe", "ausgabe"):
        value = tarif.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            _add(findings, "tarif_ungueltig", pfad + "." + key,
                 f"Tarif '{key}' muss eine nichtnegative Zahl sein.")
    for key in ("cache_lesen", "cache_schreiben"):
        cache = tarif.get(key)
        if cache is not None and (isinstance(cache, bool) or not isinstance(cache, (int, float)) or cache < 0):
            _add(findings, "tarif_ungueltig", pfad + "." + key,
                 f"Cachetarif '{key}' muss eine nichtnegative Zahl sein.")


def _check_price(price, pfad, heute, findings):
    if not isinstance(price, dict):
        _add(findings, "preis_ungueltig", pfad, "Preis ist kein Objekt.")
        return
    status = _text(price.get("status"))
    if status not in PREIS_STATUS:
        _add(findings, "preis_status_ungueltig", pfad,
             "Preisstatus muss kostenlos, bekannt oder unbekannt sein.")
        return
    if status == "unbekannt":
        if not _text(price.get("grund")):
            _add(findings, "preis_grund_fehlt", pfad,
                 "Unbekannter Preis braucht einen Grund.")
        return
    if not _WAEHRUNG_RE.match(_text(price.get("waehrung"))):
        _add(findings, "waehrung_fehlt", pfad,
             "Währung fehlt oder ist kein ISO-4217-Kürzel (z. B. USD, EUR).")
    if not _text(price.get("einheit")):
        _add(findings, "einheit_fehlt", pfad, "Tarifeinheit fehlt (z. B. 1 Mio. Tokens).")
    quelle = _text(price.get("quelle"))
    stand = _text(price.get("stand"))
    if not quelle or not stand:
        _add(findings, "preis_beleg_fehlt", pfad,
             "Preis braucht Quelle und Gültigkeitsdatum.")
    else:
        datum = parse_date(stand)
        if datum is None:
            _add(findings, "preis_datum_ungueltig", pfad,
                 f"Gültigkeitsdatum '{stand}' ist kein ISO-Datum.")
        elif (heute - datum).days > MAX_PREIS_ALTER_TAGE:
            _add(findings, "preis_veraltet", pfad,
                 f"Preis vom {stand} ist älter als {MAX_PREIS_ALTER_TAGE} Tage.")
    tarife = price.get("tarife")
    if not isinstance(tarife, dict):
        tarife = {}
    if status in ("bekannt", "kostenlos"):
        _check_tarif(tarife, pfad + ".tarife", findings)
    for index, staffel in enumerate(tarife.get("staffeln") or []):
        staffel_pfad = f"{pfad}.tarife.staffeln[{index}]"
        if not isinstance(staffel, dict):
            _add(findings, "tarif_ungueltig", staffel_pfad, "Staffel ist kein Objekt.")
            continue
        ab = staffel.get("ab_kontext")
        if isinstance(ab, bool) or not isinstance(ab, int) or ab <= 0:
            _add(findings, "tarif_ungueltig", staffel_pfad,
                 "Staffel braucht eine positive Kontextgröße 'ab_kontext'.")
        _check_tarif(staffel, staffel_pfad, findings)


def _check_model(model, index, heute, findings, seen):
    pfad = f"modelle[{index}]"
    if not isinstance(model, dict):
        _add(findings, "modell_ungueltig", pfad, "Modelleintrag ist kein Objekt.")
        return
    model_id = _text(model.get("id"))
    if not model_id:
        _add(findings, "id_fehlt", pfad, "Modell-ID fehlt.")
    elif model_id in seen:
        _add(findings, "doppelte_id", pfad, f"Modell-ID '{model_id}' kommt mehrfach vor.")
    seen.add(model_id)

    status = _text(model.get("id_status"))
    if status not in ID_STATUS:
        _add(findings, "unbestaetigte_id", pfad,
             f"Modell-ID '{model_id}' ist nicht bestätigt (id_status={status or 'leer'}).")
    if status == "entfernt":
        if not _text(model.get("entfernt_quelle")) or parse_date(model.get("entfernt_am")) is None:
            _add(findings, "entfernt_beleg_fehlt", pfad,
                 "Entferntes Modell braucht 'entfernt_quelle' und 'entfernt_am'.")
    else:
        beleg = model.get("id_beleg")
        if (not isinstance(beleg, dict) or not _text(beleg.get("quelle"))
                or parse_date(beleg.get("datum")) is None):
            _add(findings, "id_beleg_fehlt", pfad,
                 "Modell-ID braucht Quelle und Datum (id_beleg).")

    fakten = model.get("fakten")
    if not isinstance(fakten, dict):
        _add(findings, "fakten_fehlt", pfad, "Abschnitt 'fakten' fehlt.")
    else:
        for key, node in fakten.items():
            _check_assertion(node, f"{pfad}.fakten.{key}", FAKTEN_ARTEN, findings)

    einschaetzungen = model.get("einschaetzungen")
    if not isinstance(einschaetzungen, dict):
        _add(findings, "einschaetzungen_fehlen", pfad,
             "Abschnitt 'einschaetzungen' fehlt.")
        einschaetzungen = {}
    for key, node in einschaetzungen.items():
        if key in ("staerken", "schwaechen"):
            if not isinstance(node, list):
                _add(findings, "angabe_ungueltig", f"{pfad}.einschaetzungen.{key}",
                     "Stärken und Schwächen müssen Listen sein.")
                continue
            for item_index, item in enumerate(node):
                _check_assertion(item, f"{pfad}.einschaetzungen.{key}[{item_index}]",
                                 EINSCHAETZUNG_ARTEN, findings)
        else:
            _check_assertion(node, f"{pfad}.einschaetzungen.{key}",
                             EINSCHAETZUNG_ARTEN, findings)

    _check_price(model.get("preis"), f"{pfad}.preis", heute, findings)


def validate(catalog, heute=None, aktuell=None):
    """Prüft einen Katalog und liefert eine Liste von Befunden (leer = gültig).

    ``aktuell`` ist die Modellliste aus ``opencode models``. Ist sie gesetzt,
    werden entfernte und unbekannte Modelle zusätzlich gemeldet.
    """
    heute = heute or date.today()
    findings = []
    if not isinstance(catalog, dict):
        _add(findings, "schema_ungueltig", "", "Katalog ist kein Objekt.")
        return findings
    if catalog.get("schema") == 1 or ("models" in catalog and "modelle" not in catalog):
        _add(findings, "altkatalog", "",
             "Altkatalog (Schema 1): Angaben sind nicht erneut geprüft und nur als Altbestand lesbar.")
        return findings
    if catalog.get("schema") != SCHEMA_VERSION:
        _add(findings, "schema_ungueltig", "schema",
             f"Erwartet wird Schema {SCHEMA_VERSION}, gefunden: {catalog.get('schema')!r}.")
    if parse_date(catalog.get("stand")) is None:
        _add(findings, "katalog_stand_fehlt", "stand",
             "Katalog braucht ein Stand-Datum (JJJJ-MM-TT).")
    models = catalog.get("modelle")
    if not isinstance(models, list) or not models:
        _add(findings, "keine_modelle", "modelle", "Katalog enthält keine Modelle.")
        models = []
    seen = set()
    for index, model in enumerate(models):
        _check_model(model, index, heute, findings, seen)

    uebernommen = catalog.get("nicht_uebernommen")
    if uebernommen is not None:
        if not isinstance(uebernommen, list):
            _add(findings, "nicht_uebernommen_ungueltig", "nicht_uebernommen",
                 "'nicht_uebernommen' muss eine Liste sein.")
        else:
            for index, item in enumerate(uebernommen):
                pfad = f"nicht_uebernommen[{index}]"
                if not isinstance(item, dict) or not _text(item.get("id")):
                    _add(findings, "nicht_uebernommen_ungueltig", pfad,
                         "Eintrag braucht eine Modell-ID.")
                    continue
                if not _text(item.get("grund")):
                    _add(findings, "nicht_uebernommen_beleg_fehlt", pfad,
                         "Eintrag braucht einen Grund.")
                if not _text(item.get("quelle")) or parse_date(item.get("datum")) is None:
                    _add(findings, "nicht_uebernommen_beleg_fehlt", pfad,
                         "Eintrag braucht Quelle und Datum.")

    if aktuell is not None:
        current = {_text(item) for item in aktuell}
        catalog_ids = {_text(model.get("id")) for model in models if isinstance(model, dict)}
        for index, model in enumerate(models):
            if not isinstance(model, dict):
                continue
            model_id = _text(model.get("id"))
            if model_id and model_id not in current and _text(model.get("id_status")) != "entfernt":
                _add(findings, "modell_entfernt", f"modelle[{index}]",
                     f"'{model_id}' steht nicht in 'opencode models' (entfernt oder Anbieter nicht verbunden).")
        for model_id in sorted(current - catalog_ids):
            _add(findings, "modell_unbekannt", "opencode models",
                 f"'{model_id}' ist verbunden, hat aber keinen Katalogeintrag (keine Einschätzung).")
    return findings


def compare(catalog_view, aktuell):
    """Abgleich einer Sicht mit der tatsächlich verfügbaren Modellliste.

    Liefert nur ergänzende Befunde; die Katalogprüfung selbst bleibt in
    :func:`validate`.
    """
    current = {_text(item) for item in (aktuell or [])}
    models = catalog_view.get("models") or []
    known = {_text(model.get("id")) for model in models}
    findings = []
    for index, model in enumerate(models):
        model_id = _text(model.get("id"))
        if model_id and model_id not in current and _text(model.get("id_status")) != "entfernt":
            _add(findings, "modell_entfernt", f"modelle[{index}]",
                 f"'{model_id}' steht nicht in 'opencode models' (entfernt oder Anbieter nicht verbunden).")
    for model_id in sorted(current - known):
        _add(findings, "modell_unbekannt", "opencode models",
             f"'{model_id}' ist verbunden, hat aber keinen Katalogeintrag (keine Einschätzung).")
    return findings


def _normalized_price(price):
    if not isinstance(price, dict):
        return {"status": "unbekannt", "text": "unbekannt",
                "grund": "kein Preis im Katalog"}
    result = dict(price)
    result["status"] = _text(result.get("status")) or "unbekannt"
    result["text"] = price_text(result)
    return result


def _legacy_assertion(value, stand, art="altbestand"):
    if is_unknown(value):
        return {"wert": "unbekannt"}
    return {"wert": _text(value), "art": art,
            "quelle": "Altkatalog (Schema 1)", "datum": stand}


def _legacy_entry(model, stand):
    if not isinstance(model, dict):
        return {"id": "", "name": "", "anbieter": "", "id_status": "unbestaetigt",
                "preis": _normalized_price({"status": "unbekannt",
                                            "grund": "Modelleintrag unlesbar"}),
                "fakten": {}, "einschaetzungen": {}, "staerken": [], "schwaechen": []}
    rohpreis = _text(model.get("preis"))
    if rohpreis.lower() == "kostenlos":
        price = {"status": "kostenlos", "text": "kostenlos",
                 "quelle": "Altkatalog (Schema 1)", "stand": stand,
                 "grund": ""}
    else:
        price = {"status": "unbekannt", "text": "unbekannt",
                 "grund": "Altpreis ohne Gültigkeitsdatum nicht übernommen"}
    fakten = {
        "kontext": _legacy_assertion(model.get("ctx"), stand),
        "bild": _legacy_assertion(model.get("vision"), stand),
        "daten": _legacy_assertion(model.get("daten_text") or model.get("daten"), stand),
    }
    einschaetzungen = {
        "tempo": _legacy_assertion(model.get("tempo"), stand),
        "aufwand": _legacy_assertion(model.get("aufwand"), stand),
        "coder": _legacy_assertion(model.get("coder"), stand),
        "reviewer": _legacy_assertion(model.get("reviewer"), stand),
    }
    staerken = [{"text": _text(item), "art": "altbestand",
                 "quelle": "Altkatalog (Schema 1)", "datum": stand}
                for item in (model.get("staerken") or []) if not is_unknown(item)]
    schwaechen = [{"text": _text(item), "art": "altbestand",
                   "quelle": "Altkatalog (Schema 1)", "datum": stand}
                  for item in (model.get("schwaechen") or []) if not is_unknown(item)]
    return {
        "id": _text(model.get("id")),
        "name": _text(model.get("name")) or _text(model.get("id")),
        "anbieter": _text(model.get("lab")),
        "id_status": "unbestaetigt",
        "id_beleg": {},
        "preis": _normalized_price(price),
        "fakten": fakten,
        "einschaetzungen": einschaetzungen,
        "staerken": staerken,
        "schwaechen": schwaechen,
    }


def view(catalog, heute=None, aktuell=None):
    """Normalisierte Sicht für CLI und Dashboard.

    Die Sicht enthält zusätzlich ``findings``; sie ersetzt keine Prüfung und
    keine Quelle. ``legacy`` markiert den alten, ungeprüften Altbestand.
    ``aktuell`` ist optional die Modellliste aus ``opencode models``.
    """
    findings = validate(catalog, heute=heute, aktuell=aktuell)
    legacy = isinstance(catalog, dict) and (
        catalog.get("schema") == 1
        or ("models" in catalog and "modelle" not in catalog))
    base = {
        "schema": 1 if legacy else (catalog.get("schema") if isinstance(catalog, dict) else 0),
        "version": _text(catalog.get("version")) if isinstance(catalog, dict) else "",
        "stand": _text(catalog.get("stand")) if isinstance(catalog, dict) else "",
        "waehrung": _text(catalog.get("waehrung")) if isinstance(catalog, dict) else "",
        "einheit": _text(catalog.get("einheit")) if isinstance(catalog, dict) else "",
        "hinweis": _text(catalog.get("hinweis")) if isinstance(catalog, dict) else "",
        "findings": findings,
        "legacy": legacy,
        "quellen": list(catalog.get("quellen") or []) if isinstance(catalog, dict) else [],
        "nicht_uebernommen": [],
        "models": [],
    }
    if not isinstance(catalog, dict):
        return base
    if legacy:
        base["models"] = [_legacy_entry(model, base["stand"])
                          for model in (catalog.get("models") or [])]
        return base

    for model in catalog.get("modelle") or []:
        if not isinstance(model, dict):
            continue
        einschaetzungen = model.get("einschaetzungen")
        if not isinstance(einschaetzungen, dict):
            einschaetzungen = {}
        base["models"].append({
            "id": _text(model.get("id")),
            "name": _text(model.get("name")) or _text(model.get("id")),
            "anbieter": _text(model.get("anbieter")),
            "id_status": _text(model.get("id_status")),
            "id_beleg": model.get("id_beleg") if isinstance(model.get("id_beleg"), dict) else {},
            "entfernt_am": _text(model.get("entfernt_am")),
            "entfernt_quelle": _text(model.get("entfernt_quelle")),
            "preis": _normalized_price(model.get("preis")),
            "fakten": dict(model.get("fakten") if isinstance(model.get("fakten"), dict) else {}),
            "einschaetzungen": {key: value for key, value in einschaetzungen.items()
                                if key not in ("staerken", "schwaechen")},
            "staerken": list(einschaetzungen.get("staerken") or []),
            "schwaechen": list(einschaetzungen.get("schwaechen") or []),
        })
    uebernommen = catalog.get("nicht_uebernommen")
    base["nicht_uebernommen"] = list(uebernommen) if isinstance(uebernommen, list) else []
    return base


def enrich(models, live_ids, heute=None):
    """Reichert die Details tatsächlich verfügbarer Modelle an.

    ``models`` ist die normalisierte Katalogliste aus :func:`view`.
    ``live_ids`` ist die Modellliste des aktiven Harness. Für jede Live-ID
    entsteht ein Eintrag mit den sichtbaren Feldern der Modellliste. Fehlende,
    unvollständige oder veraltete Angaben werden nicht ersetzt, sondern über
    ``hinweis`` erklärt und in ``info_unvollstaendig`` geführt.
    """
    heute = heute or date.today()
    catalogue = {}
    for model in models or []:
        if isinstance(model, dict) and _text(model.get("id")):
            catalogue[_text(model.get("id"))] = model
    info = {}
    incomplete = []
    for model_id in [str(item) for item in (live_ids or [])]:
        detail = _enriched_entry(model_id, catalogue.get(model_id), heute)
        info[model_id] = detail["info"]
        if detail["unvollstaendig"]:
            incomplete.append(model_id)
    return {"info": info, "info_unvollstaendig": incomplete}


def _enriched_entry(model_id, model, heute):
    """Detailansicht eines Modells samt erklärendem Hinweis."""
    if not isinstance(model, dict):
        return {
            "info": {
                "id": model_id,
                "anbieter": "",
                "preis": {"status": "unbekannt", "text": "unbekannt",
                          "quelle": "", "grund": "kein Katalogeintrag"},
                "status": "unbekannt",
                "fakten": {},
                "einschaetzungen": {},
                "hinweis": ("Kein Katalogeintrag für '" + model_id
                            + "'; Anbieter, Preis und Details sind unbekannt."),
            },
            "unvollstaendig": True,
        }

    anbieter = _text(model.get("anbieter"))
    if is_unknown(anbieter):
        anbieter = ""
    price = dict(model.get("preis") if isinstance(model.get("preis"), dict) else {})
    price_status = _text(price.get("status")) or "unbekannt"
    price_value = _text(price.get("text")) or price_text(price)
    price_quelle = _text(price.get("quelle"))
    fakten = model.get("fakten") if isinstance(model.get("fakten"), dict) else {}
    einschaetzungen = (model.get("einschaetzungen")
                       if isinstance(model.get("einschaetzungen"), dict) else {})
    status = _text(model.get("id_status")) or "unbekannt"

    reasons = []
    if not anbieter:
        reasons.append("Anbieter ist unbekannt")
    if price_status == "unbekannt" or is_unknown(price_value):
        grund = _text(price.get("grund"))
        reasons.append("Preis unbekannt" + (": " + grund if grund else ""))
    else:
        stand = _text(price.get("stand"))
        datum = parse_date(stand)
        if datum is None:
            reasons.append("Preisstand fehlt oder ist kein ISO-Datum")
        elif (heute - datum).days > MAX_PREIS_ALTER_TAGE:
            reasons.append("Preis vom " + stand + " ist veraltet (älter als "
                           + str(MAX_PREIS_ALTER_TAGE) + " Tage)")
    if not fakten:
        reasons.append("keine Fakten im Katalogeintrag")

    price["status"] = price_status
    price["text"] = price_value if price_value else "unbekannt"
    price["quelle"] = price_quelle
    return {
        "info": {
            # Die klassische Oberfläche liest weiterhin Katalogfelder wie
            # Name, id_status und id_beleg aus dieser Ansicht.
            "id": model_id,
            "name": _text(model.get("name")) or model_id,
            "anbieter": anbieter,
            "id_status": status,
            "id_beleg": (dict(model.get("id_beleg"))
                         if isinstance(model.get("id_beleg"), dict) else {}),
            "entfernt_am": _text(model.get("entfernt_am")),
            "entfernt_quelle": _text(model.get("entfernt_quelle")),
            "preis": price,
            "status": status,
            "fakten": dict(fakten),
            "einschaetzungen": dict(einschaetzungen),
            "staerken": list(model.get("staerken") or []),
            "schwaechen": list(model.get("schwaechen") or []),
            "hinweis": "; ".join(reasons),
        },
        "unvollstaendig": bool(reasons),
    }


def _empty(hinweis, code=None):
    findings = []
    if code:
        _add(findings, code, "", hinweis)
    return {"schema": 0, "version": "", "stand": "", "waehrung": "", "einheit": "",
            "hinweis": hinweis, "findings": findings, "legacy": False,
            "quellen": [], "nicht_uebernommen": [], "models": []}


def load(path, aktuell=None):
    """Liest einen Katalog; ein fehlender oder defekter Katalog ist kein Absturz."""
    try:
        with open(path, encoding="utf-8") as handle:
            catalog = json.load(handle)
    except FileNotFoundError:
        return _empty("Kein Modellkatalog gefunden: " + str(path))
    except OSError as error:
        return _empty("Modellkatalog nicht lesbar: " + str(error), "katalog_ungueltig")
    except ValueError as error:
        return _empty("Modellkatalog ist kein gültiges JSON: " + str(error), "katalog_ungueltig")
    return view(catalog, aktuell=aktuell)
