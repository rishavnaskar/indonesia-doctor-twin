# Changelog

Notable changes to this prototype. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html), with the caveat
that nothing here is a published package: the version pins what the scorecard
and the FHIR bundles were produced by.

The version lives in two places, `pyproject.toml` and `service/__init__.py`,
and a test fails if they disagree.

## [Unreleased]

## [0.2.0] - 2026-10-28

The build is now reproducible and enforced. Nothing clinical changed except
one fixed bug, which is listed under Fixed with the test that now covers it.

### Added

- **CI on every push and pull request** (`.github/workflows/ci.yml`): lint,
  type-check, the architectural checks, the full test suite on Python 3.11 and
  3.13 with a coverage floor, the scorecard, the pressure suite, a dependency
  audit, and a fresh-clone job that installs only what the README says to
  install and then drives the running server.
- **Lockfiles.** `requirements.lock` and `requirements-dev.lock` pin the
  transitive closure of `requirements.txt` and `requirements-dev.txt`.
  `tools/check_lockfiles.py` fails the build when a lock has drifted from its
  input, because a lockfile that no longer matches is worse than none: it looks
  reproducible and is not.
- **Runtime and development dependencies are separate.** A deployment installs
  neither a test runner nor a linter.
- **Structured logging** (`service/logging.py`): one JSON object per line on
  stderr, with patient content and credentials dropped by field name before a
  line is written. No hosted log drain and no SaaS error tracker, by design: a
  stack trace from this system can carry the record that produced it, and
  health data must be processed in-country. Errors are counted in-process by
  exception type and reported at `/health`.
- **`/health` and `/healthz`**: store reachability and which backend answered,
  the build state, the error tally, version and uptime. 503 only when the store
  is unreachable; a failed scripted-page build is degraded, not down, because
  the API and `/clinic` are still serving.
- **Lint and type-check configuration** in `pyproject.toml`: ruff for both
  linting and formatting, mypy over `/service` with the gate, the contracts and
  the rules checked hardest.
- **`.env.example`**, listing every environment variable the system reads, with
  placeholder values and a note on what each one changes.
- **Dependabot** for pip, GitHub Actions and Docker.
- **CONTRIBUTING.md** and **SECURITY.md**.
- Tests for the new surface area: structured logging and redaction, the error
  tally, `/health` across its three states, the HTML template loader, the
  version pin, the hosted backend's response_format degradation, and the HTTP
  routes over a real socket.

### Changed

- **No file over 500 lines.** `tools/demo/run.py` (1,116) is now orchestration
  only, with the store, the thread id, the JSON shapes, the clinic history and
  the pack read-outs in modules of their own. `tools/demo/__main__.py` is
  argument parsing; the routes, the background build and the health check are
  in `tools/demo/server.py`. The three HTML pages moved out of Python string
  literals into `tools/demo/templates/*.html`.
- `tools/ci_checks.py` now reads those HTML files for the em-dash rule, so
  moving 1,200 lines of rendered text out of Python cost the check nothing.
- `TargetResolution.defined` is no longer used at call sites; they narrow on
  `resolution.target` directly, which a type checker can follow.
- `sign()` with no site now refuses by name instead of raising AttributeError
  three frames down. Both block the signature; only one says why.

### Fixed

- **The hosted backend's response_format degradation never ran.** `_post` read
  a `json_mode` name the method has never had, so a provider that rejects
  `response_format` with a 400 produced a `NameError` on the line meant to
  recover from it. It now steps the enforcement down one notch at a time,
  schema to object to off, and `tests/test_hosted_backend.py` covers each step.
  Nothing caught this because reaching the line needs a provider that rejects
  the field, which the suite had no reason to simulate.
- Dead and unreachable code removed: an unused `state` binding in the formulary
  check, unused blood-pressure lookups in the reference reasoner, a conditional
  in the pressure suite whose branches were identical.

## [0.1.0] - 2026-10-26

First complete prototype: two pathways, nine gate checks, the Indonesian rule
packs, eligibility routing, the signature line, the durable store with Postgres
and file backends, FHIR R4 emission validated against the official HL7
validator, the scorecard and the pressure suite, and both demo surfaces.

[Unreleased]: https://github.com/rishavnaskar/indonesia-doctor-twin/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/rishavnaskar/indonesia-doctor-twin/releases/tag/v0.2.0
[0.1.0]: https://github.com/rishavnaskar/indonesia-doctor-twin/releases/tag/v0.1.0
