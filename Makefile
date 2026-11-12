PYTHON := .venv/Scripts/python.exe

.PHONY: all lint demo test clean

all: lint demo test

lint:
	$(PYTHON) -m flake8 --max-line-length=79 --max-complexity=10 src tests

demo:
	$(PYTHON) -m src.demo_stage1
	$(PYTHON) -m src.demo_stage2
	$(PYTHON) -m src.demo_stage3

test:
	$(PYTHON) -m coverage run --branch --source=src -m pytest tests/test_mbt.py -v
	$(PYTHON) -m coverage report -m

clean:
	rm -rf .coverage htmlcov .pytest_cache src/__pycache__ tests/__pycache__
