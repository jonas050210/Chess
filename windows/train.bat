@echo off
REM Terminal-Training v6 (CPU). Auf Ubuntu/GPU: ..\ubuntu\train.sh
cd /d "%~dp0.."
echo == Chess-Training v6 ^| Terminal only ==
echo Hilfe: py ai\train_cli.py --help
py ai\train_cli.py %*
