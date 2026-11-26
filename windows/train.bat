@echo off
REM Candidate training and Arena evaluation run here, not in the web UI.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\setup.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" ai\train_cli.py %*
