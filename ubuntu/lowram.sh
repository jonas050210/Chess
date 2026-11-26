#!/usr/bin/env bash
# 2-GB-RAM-Modus: kleine MCTS, keine Daueranalyse, langsameres Polling.
set -e
cd "$(dirname "$0")/.."
export CHESS_LOW_RAM=1 PORT=8000 CHESS_PORT=8000 OMP_NUM_THREADS=1
exec python3 main.py --low "$@"
