.PHONY: install test score checks pressure demo live free prompt surface surface-live page page-live concordance all e2e clean

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

# SPEC-V1 §8.2 twin fidelity. Reported, never gated, and not evidence until
# Set C exists — the run says so itself.
concordance:
	$(PY) -m tools.concordance

# Download the official HL7 validator once. ~190 MB, into .tools/ (gitignored).
fhir-setup:
	@mkdir -p .tools
	@echo "  Downloading the HL7 FHIR validator (~190 MB) into .tools/ ..."
	@curl -L --progress-bar -o .tools/validator_cli.jar \
	  https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar
	@echo "  Done. Now run: make fhir"

# The official HL7 validator, over the bundles this system emits.
# Run `make fhir-setup` first; this says so rather than failing if it is absent.
fhir:
	$(PY) -m tools.validate_fhir

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

# The clinician surface. Localhost only, rebuilt on every reload — so editing a
# pack file and refreshing shows the rules moving, which is the fastest way to
# demonstrate that they are data rather than code.
surface:
	$(PY) -m tools.demo

# The same surface, with a real model drafting instead of the reference
# reasoner. Needs OPENROUTER_API_KEY in .env; free by default.
surface-live:
	$(PY) -m tools.demo --live

# One self-contained file, for the people who will not clone a repository.
page:
	$(PY) -m tools.demo --export demo.html

page-live:
	$(PY) -m tools.demo --live --export demo.html

live:
	$(PY) -m tools.live --n 5

free:
	$(PY) -m tools.live --list-free

prompt:
	$(PY) -m tools.live --show-prompt
