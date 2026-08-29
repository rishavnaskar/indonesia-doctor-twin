.PHONY: install test score checks all clean

PY := ./.venv/bin/python

install:
	python3 -m venv .venv
	./.venv/bin/pip install -q --upgrade pip
	./.venv/bin/pip install -q -r requirements.txt

test:
	$(PY) -m pytest tests/ -q

score:
	$(PY) -m eval.scorecard

checks:
	$(PY) tools/ci_checks.py

# What CI runs. A bad commit fails here.
all: checks test score

clean:
	rm -rf .pytest_cache **/__pycache__ .eval_out
