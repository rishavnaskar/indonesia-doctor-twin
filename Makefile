# Four commands.
#
#   make        everything, offline: architecture rules, the test suite, the
#               scorecard, the pressure suite, the FHIR bundles against the
#               official validator, a narrated walkthrough, then the clinician
#               surface in a browser.
#
#   make live   the same, with a real model drafting instead of the reference
#               reasoner. Needs OPENROUTER_API_KEY in .env.
#
#   make check  every check CI runs, in the same order, without the browser.
#
#   make lock   regenerate the lockfiles after editing requirements*.txt or the
#               dependencies in pyproject.toml.
#
# The surface binds port 8000; `make PORT=8001` moves it.
#
# The first two bootstrap the virtualenv and start Postgres if this machine has
# Docker; neither requires either to exist. Everything optional degrades to a
# named skip rather than a failure. See tools/run.py.

.PHONY: run live check lint types test cov audit lock clean
.DEFAULT_GOAL := run

PY := ./.venv/bin/python
PIP := ./.venv/bin/pip

# Writes uv.lock. Only `make lock` uses it, inside the throwaway environment it
# resolves in, so it is pinned here rather than installed with the dev tools.
UV_VERSION := 0.11.28

# The surface binds this. Override when something already has it:
#   make PORT=8001
PORT ?= 8000

run: .venv
	@$(PY) -m tools.run --port $(PORT)

live: .venv
	@$(PY) -m tools.run --live --port $(PORT)

# ---------------------------------------------------------------- the checks
#
# Same order as .github/workflows/ci.yml, so a green `make check` means a green
# build. These need the development tools, which `make` alone does not install.

check: .venv-dev lint types test
	@$(PY) -m tools.ci_checks
	@$(PY) tools/check_lockfiles.py
	@$(PY) -m eval.scorecard
	@$(PY) -m eval.pressure
	@echo "\n  All checks passed.\n"

lint: .venv-dev
	@./.venv/bin/ruff check .
	@./.venv/bin/ruff format --check .

types: .venv-dev
	@./.venv/bin/mypy

test: .venv-dev
	@$(PY) -m pytest --cov --cov-report=term-missing

cov: test

audit: .venv-dev
	@./.venv/bin/pip-audit --strict --requirement requirements.lock

# ------------------------------------------------------------- the lockfiles
#
# Resolved in throwaway virtualenvs rather than in .venv, so whatever is
# installed here cannot leak into a lock that is meant to describe a clean
# machine.

lock:
	@echo "  Resolving requirements.txt ..."
	@rm -rf .lockenv && python3 -m venv .lockenv
	@./.lockenv/bin/pip install -q --upgrade pip
	@./.lockenv/bin/pip install -q -r requirements.txt
	@{ \
	  echo "# Runtime lockfile: the transitive closure of requirements.txt, pinned."; \
	  echo "#"; \
	  echo "#   pip install -r requirements.lock"; \
	  echo "#"; \
	  echo "# Regenerate after changing requirements.txt:"; \
	  echo "#"; \
	  echo "#   make lock"; \
	  ./.lockenv/bin/pip freeze --exclude-editable | sort -f; \
	} > requirements.lock
	@echo "  Resolving requirements-dev.txt ..."
	@rm -rf .lockenv && python3 -m venv .lockenv
	@./.lockenv/bin/pip install -q --upgrade pip
	@./.lockenv/bin/pip install -q -r requirements-dev.txt
	@{ \
	  echo "# Development lockfile: the transitive closure of requirements-dev.txt,"; \
	  echo "# which includes everything in requirements.lock."; \
	  echo "#"; \
	  echo "#   pip install -r requirements-dev.lock"; \
	  echo "#"; \
	  echo "# Regenerate after changing requirements-dev.txt:"; \
	  echo "#"; \
	  echo "#   make lock"; \
	  ./.lockenv/bin/pip freeze --exclude-editable | sort -f; \
	} > requirements-dev.lock
	@echo "  Resolving pyproject.toml into uv.lock, at requirements.lock's versions ..."
	@./.lockenv/bin/pip install -q uv==$(UV_VERSION)
	@./.lockenv/bin/uv lock --quiet $$(sed -nE \
	  's/^([A-Za-z0-9._-]+)==([^[:space:]#]+).*/--upgrade-package \1==\2/p' requirements.lock)
	@rm -rf .lockenv
	@$(PY) tools/check_lockfiles.py

clean:
	@rm -rf .venv .lockenv .pytest_cache .coverage coverage.xml
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +

# --------------------------------------------------------------- bootstrap
#
# Two stamps rather than one. A demo installs three runtime packages; a
# contributor running the checks also gets the tools. Installing the tools for
# everybody would make `make` slower for the people least likely to need them.

.venv:
	@echo "  Creating .venv and installing dependencies ..."
	@python3 -m venv .venv
	@$(PIP) install -q --upgrade pip
	@$(PIP) install -q -r requirements.lock
	@touch .venv

.venv-dev: .venv
	@echo "  Installing the development tools ..."
	@$(PIP) install -q -r requirements-dev.lock
	@touch .venv-dev
