#!/usr/bin/env bash
# Terminal-Training v6. Alle Parameter werden an ai/train_cli.py durchgereicht.
# Keine GUI, keine direkten Überschreibungen von model.npz / model_torch.pt.
set -e
cd "$(dirname "$0")/.."

echo "== Chess-Training v6 · Terminal only =="
echo "Hilfe: python3 ai/train_cli.py --help"
echo "Plan:  bash ubuntu/train.sh --dry-run"
exec python3 ai/train_cli.py "$@"
