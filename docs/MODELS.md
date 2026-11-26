# Modelle und Modellprofile

Vibe verwaltet Modelle verschiedener Provider und ermöglicht deren rollenbasierte Zuordnung über Modellprofile. Ein **Model Profile** ordnet Modelle Rollen zu, beispielsweise Coder und Reviewer. [cite:1]

## Modellübersicht

Die Modell-Tabelle bietet eine Übersicht und Bewertung verfügbarer Modelle. Sie enthält unter anderem:

- Modell-ID
- Provider
- Verfügbarkeit
- Kontextgröße
- Bildunterstützung
- Stärken und Schwächen
- Geschwindigkeit
- Aufwand
- Datenbedingungen
- Preis [cite:1]

Unbekannte Werte werden ausdrücklich als unbekannt gekennzeichnet. Vibe erfindet keine Modell-IDs oder Fähigkeiten. [cite:1]

## Fakten, Messungen und Bewertungen

Vibe unterscheidet zwischen Fakten, Messungen, Nutzerberichten und Bewertungen. Wo möglich, werden Quelle, Datum und Testmethode angegeben. [cite:1]

Veraltete Informationen werden markiert. Alte Bewertungen oder Preise werden nicht ungeprüft übernommen. [cite:1]

## Preise

Preise geben Währung, Einheit, Input- und Output-Rate sowieEffective Date an. Cache-Preise, Tiers und Zuschläge werden separat dargestellt. [cite:1]

## Modellprofile

Modellprofile können erstellt, bearbeitet, kopiert, gelöscht und angewendet werden. Sie unterstützen konfigurierbare Rollen, mindestens Coder und Reviewer, die globalen oder projektbezogenen Agenten zugeordnet werden. [cite:1]

Beim Anwenden eines Profils gilt:

- Die exakten Änderungen werden vor dem Schreiben als Vorschau angezeigt.
- Alle Ziel-Agenten und Modelle werden vor dem ersten Schreiben validiert.
- Die Anwendung ist transaktional oder nach einem partiellen Fehler vollständig reversibel.
- Ein leeres Profil darf keinen erfolgreichen Abschluss melden. [cite:1]

## Abweichungen erkennen

Wenn spätere manuelle Änderungen dazu führen, dass Agenten vom Profil abweichen, macht Vibe das sichtbar. [cite:1]

## Kosten und Paid Models

Paid Profiles werden klar gekennzeichnet. Vibe schaltet niemals automatisch von einem kostenlosen Modell auf ein kostenpflichtiges Modell um. [cite:1]

Credentials gehören weder in Agent-Dateien noch in dieses Repository. Vibe unterscheidet zwischen einem gelisteten Modell und einem Modell, für das der Nutzer autorisiert ist. [cite:1]
