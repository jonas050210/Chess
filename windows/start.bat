@echo off
cd /d "%~dp0.."
set OMP_NUM_THREADS=4
echo == Lokaler Chess Bot auf http://localhost:8000 ==
python server.py
pause
