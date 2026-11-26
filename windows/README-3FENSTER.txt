Drei-Fenster-Start (Windows)
============================
1. Python von python.org installieren; "py launcher" und "tcl/tk and IDLE" anhaken.
2. Einmalig im Projektordner:  setup.bat
3. Start im Projektordner:  py main.py
   Alternativ: Doppelklick auf windows\launch3.bat oder windows\lowram.bat.

Es öffnen sich 3 kleine native Fenster:
  - Chess · Spiel              Brett, Drag & Drop, Uhren, Züge, FEN, Eval-Bar,
                                Schach-Markierung, Rechtsklick-Markierungen
  - Chess · Bot & Rewards      Engine, Reaktion, Reward, W/D/L, MCTS/Cache,
                                Live-Analyse, Taktiken, PV, Regel-Status
  - Chess · Match & Settings   Zeit/Inkrement, Level, Denkzeit, Premove,
                                Auto-Dame, Koordinaten, 6 Themes, Neue Partie,
                                Zurück, Tipp, Drehen, Aufgabe, Remis-Anspruch,
                                Remis-Einigung

Alle Fenster bleiben live am selben lokalen Server (127.0.0.1:8000).
Es wird keine echte .exe kompiliert; `py main.py` ist der plattformgleiche Start.
Ubuntu: `python3 main.py` oder `bash ubuntu/lowram.sh`
        falls nötig: `sudo apt install python3-tk`
Vorschau: `../assets/preview/all-preview.png`

v6.2 · Storybook
==============
Default ist jetzt das helle Storybook-Theme (Grün #58cc02, Storybook #d7ffb8,
Blau #1cb0f6, Night Ink #000437). Alte Themes bleiben im Match-Fenster wählbar.
Shortcuts: N neu · U zurück · H Tipp · F drehen · O Remis anbieten ·
A Abbruch · C Markierungen löschen · Esc Premove abbrechen.
Rechtsklick: Feld markieren; Rechtsklick-Drag: Pfeil zeichnen.
Figuren: neu gezeichnet, aus ../assets/pieces.zip geladen (keine losen PNGs).
Drag: Figur wird angehoben; Zuege werden animiert (auch Rochade).
Fenster verschieben: am "⋮⋮ ZIEHEN"-Header im jeweiligen Fenster ziehen.
2 GB RAM: lowram.bat starten (kleine MCTS, Analyse aus, kein Browser nötig).
Alle Karten/Checks/Selects/Buttons sind jetzt wirklich abgerundet;
Brett: weiss + #a5ed6e statt komplett gruen.
Vorschau: ..\assets\preview\all-preview.png
