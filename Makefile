ifneq (,$(wildcard .venv/Scripts/python.exe))
PYTHON := .venv/Scripts/python.exe
else ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON := python
endif

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
	$(PYTHON) -c "import shutil, os; [shutil.rmtree(p, ignore_errors=True) for p in ('.pytest_cache', 'htmlcov', 'src/__pycache__', 'tests/__pycache__')]; [os.remove(f) for f in ('.coverage',) if os.path.exists(f)]"
