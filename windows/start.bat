@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\setup.bat first.
  exit /b 1
)
echo Chess Garden: open http://127.0.0.1:8000 in your browser
".venv\Scripts\python.exe" server.py
if errorlevel 1 pause
