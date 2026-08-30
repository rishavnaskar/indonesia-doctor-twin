.PHONY: install test score checks pressure demo live prompt all clean

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

pressure:
	$(PY) -m eval.pressure

# What CI runs. A bad commit fails here.
all: checks test score pressure

clean:
	rm -rf .pytest_cache **/__pycache__ .eval_out

demo:
	$(PY) -m tools.walkthrough

live:
	$(PY) -m tools.live --n 5

prompt:
	$(PY) -m tools.live --show-prompt
