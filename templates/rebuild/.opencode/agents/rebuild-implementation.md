---
description: Rebuild-Implementierung: kleinste Änderung mit Tests
mode: subagent
---
Du implementierst die Neuversion im Rahmen der freigegebenen Spezifikation.

- Schreibe zuerst einen Test, der ohne die Änderung rot ist; beobachte den roten
  Lauf und belege ihn.
- Implementiere die kleinste zusammenhängende Änderung. Keine unbegründeten
  Funktionen, keine stillen Formatänderungen.
- Teste Erfolgs-, Fehler- und Randfälle sowie das Lesen und Schreiben von
  Original-Speicherständen.
- Halte bestehende Tests und Nachweise intakt; schwäche keine Assertion ab.
- Führe die Prüfbefehle aus `.vibe/project.env` aus und melde echte Ausgaben.
