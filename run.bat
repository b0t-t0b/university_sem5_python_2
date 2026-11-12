@echo off
setlocal
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo [1/4] Running flake8 style and complexity check...
"%PY%" -m flake8 --max-line-length=79 --max-complexity=10 src tests || exit /b 1

echo [2/4] Running Stage 1, Stage 2, and Stage 3 demonstrations...
"%PY%" -m src.demo_stage1 || exit /b 1
"%PY%" -m src.demo_stage2 || exit /b 1
"%PY%" -m src.demo_stage3 || exit /b 1

echo [3/4] Running Hypothesis model-based tests with branch coverage...
"%PY%" -m coverage run --branch --source=src -m pytest tests/test_mbt.py -v || exit /b 1

echo [4/4] Printing branch coverage report...
"%PY%" -m coverage report -m || exit /b 1

echo All checks completed successfully.
endlocal
