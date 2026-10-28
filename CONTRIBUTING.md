# Contributing

This is a prototype built to answer a question, not a library looking for
users. It is still worth being able to clone it and get to a green suite in one
command, which is what this file is for.

## Set up

```bash
git clone https://github.com/rishavnaskar/indonesia-doctor-twin.git
cd indonesia-doctor-twin
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.lock
```

Python 3.11 or newer. CI runs 3.11 and 3.13, the floor and the ceiling of what
`pyproject.toml` claims.

Nothing else is required. No Docker, no API key, no database: each one that is
missing turns into a named skip rather than a failure.

```bash
cp .env.example .env    # only if you want a real model or a real database
```

## The checks, in the order CI runs them

```bash
ruff check .                 # lint
ruff format --check .        # formatting
mypy                         # types, over /service
python -m tools.ci_checks    # the architectural rules
python tools/check_lockfiles.py
pytest --cov                 # the suite, with the coverage floor
python -m eval.scorecard     # the measurement
python -m eval.pressure
```

Or all of them at once:

```bash
make check
```

`make` on its own is the demo: it runs everything above and then serves the
clinician surface. `make check` is the same set without the browser.

## What the rules are, and why

The architectural checks are not style. They encode the four constraints that
are cheap now and impossible to retrofit, and `tools/ci_checks.py` explains
each one at the top of the file.

1. **Nothing under `/service` names a country, a payer, a drug or a
   guideline.** The banned vocabulary is read from the packs themselves, so
   adding a drug to the formulary automatically forbids hard-coding it in the
   engine. If you need a clinical fact, it goes in `/packs`.
2. **`/service/gate` imports nothing**: no orchestration library, no YAML,
   nothing from `/service/reason`. The gate is the part that has to be right,
   a doctor has to be able to read it, and it has to be testable with nothing
   else running.
3. **Only `/service/graph` may import the orchestration library.**
4. **No hosted tracing endpoint, anywhere.** Health data must be stored and
   processed in-country. This is also why there is no SaaS error tracker and no
   log drain: a stack trace here can carry the record that produced it.

There is a fifth, which is a writing rule rather than an architectural one: no
em-dashes in the docs or in any text the surface renders. The check reads pack
values, Python string literals and the HTML templates, because a check that
only reads what you remember writing stays true for about a week.

## Conventions

- **No file over 500 lines.** Three were, and splitting them is what
  `tools/demo/` looks like now.
- **Comments say why, not what.** The code says what.
- **A test asserts behaviour.** `assert gate_refused_because_potassium_is_high`
  is a test; `assert len(findings) == 3` is a tripwire.
- **A new clinical rule is a pack change plus a test.** If it needs engine
  code, that is worth saying out loud in the pull request, because the second
  pathway going in as two YAML files with no engine code is one of this
  project's two architectural claims.
- The safety gate is plain code and never a model. That is not negotiable.

## Dependencies

`requirements.txt` is what a deployment installs. `requirements-dev.txt` is the
tools. Both are exactly pinned, and both have a lockfile pinning their
transitive closure, which is what CI installs. `pyproject.toml` declares the
same runtime dependencies as ranges, and `uv.lock` locks them at
`requirements.lock`'s versions, for tooling that reads `pyproject.toml` rather
than requirements files.

After changing any of them:

```bash
make lock
```

That resolves them in clean virtualenvs and rewrites all three locks. The
step that writes `uv.lock` installs uv into the same throwaway environment, at
the version pinned in the Makefile, so there is nothing to install first.
`tools/check_lockfiles.py` fails the build if you forget, including when
`uv.lock` and `requirements.lock` disagree about a single version.

## Pull requests

- One change, with its test, and a note on what it is for.
- CI must be green. It runs on every push, so there is no path that skips it.
- Say what you could not verify. A pull request that reports a skipped step
  honestly is more useful than one that implies it ran.
