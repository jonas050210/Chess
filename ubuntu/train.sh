#!/usr/bin/env bash
# Training is terminal-only. Candidates must pass the paired Arena gate.
set -e
cd "$(dirname "$0")/.."
exec python3 ai/train_cli.py "$@"
