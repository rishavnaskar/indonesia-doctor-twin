.PHONY: install test score checks pressure demo live free prompt all e2e clean

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

# What CI runs. A bad commit fails here. Never calls a model: a test suite that
# costs money per run and varies between runs is neither a test suite nor a
# suite.
all: checks test score pressure

# Everything, including a real model. This is the full end-to-end run: the four
# offline gates first, then the narrated walkthrough, then real encounters
# through a live model. Needs OPENROUTER_API_KEY in .env; free by default.
e2e: checks test score pressure demo live
	@echo
	@echo "  End to end complete: architecture rules, tests, scorecard,"
	@echo "  pressure suite, walkthrough, and live encounters through a"
	@echo "  real model — all green."
	@echo

clean:
	rm -rf .pytest_cache **/__pycache__ .eval_out

demo:
	$(PY) -m tools.walkthrough

live:
	$(PY) -m tools.live --n 5

free:
	$(PY) -m tools.live --list-free

prompt:
	$(PY) -m tools.live --show-prompt
