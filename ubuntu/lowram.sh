#!/usr/bin/env bash
# Browser-only server for a small laptop: no continuous analysis, fewer MCTS sims.
set -e
cd "$(dirname "$0")/.."
export CHESS_LOW_RAM=1 OMP_NUM_THREADS=1
exec python3 main.py "$@"
