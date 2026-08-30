# Two commands.
#
#   make        everything, offline: architecture rules, the test suite, the
#               scorecard, the pressure suite, the FHIR bundles against the
#               official validator, a narrated walkthrough, then the clinician
#               surface in a browser.
#
#   make live   the same, with a real model drafting instead of the reference
#               reasoner. Needs OPENROUTER_API_KEY in .env.
#
# The surface binds port 8000; `make PORT=8001` moves it.
#
# Both bootstrap the virtualenv and start Postgres if this machine has Docker;
# neither requires either to exist. Everything optional degrades to a named
# skip rather than a failure — see tools/run.py.

.PHONY: run live
.DEFAULT_GOAL := run

PY := ./.venv/bin/python

# The surface binds this. Override when something already has it:
#   make PORT=8001
PORT ?= 8000

run: .venv
	@$(PY) -m tools.run --port $(PORT)

live: .venv
	@$(PY) -m tools.run --live --port $(PORT)

.venv:
	@echo "  Creating .venv and installing dependencies ..."
	@python3 -m venv .venv
	@./.venv/bin/pip install -q --upgrade pip
	@./.venv/bin/pip install -q -r requirements.txt
