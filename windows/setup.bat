@echo off
cd /d "%~dp0.."
echo == Windows / Spielen vorbereiten ==
python -m pip install -r requirements.txt
echo Fertig. checkpoint-Ordner aus Ubuntu hierher kopieren (optional).
pause
