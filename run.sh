#!/usr/bin/env bash
set -euo pipefail

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
else
  PY="python3"
fi

echo "[1/4] Running flake8 style and complexity check..."
"$PY" -m flake8 --max-line-length=79 --max-complexity=10 src tests

echo "[2/4] Running Stage 1, Stage 2, and Stage 3 demonstrations..."
"$PY" -m src.demo_stage1
"$PY" -m src.demo_stage2
"$PY" -m src.demo_stage3

echo "[3/4] Running Hypothesis model-based tests with branch coverage..."
"$PY" -m coverage run --branch --source=src -m pytest tests/test_mbt.py -v

echo "[4/4] Printing branch coverage report..."
"$PY" -m coverage report -m

echo "All checks completed successfully."
