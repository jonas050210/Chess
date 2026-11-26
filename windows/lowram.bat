@echo off
REM 2-GB-RAM-Laptop: kleine MCTS, keine Daueranalyse, langsameres Polling.
cd /d "%~dp0.."
set CHESS_LOW_RAM=1
set PORT=8000
set CHESS_PORT=8000
set OMP_NUM_THREADS=1
py main.py --low %*
