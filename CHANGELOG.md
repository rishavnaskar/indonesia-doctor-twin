# Changelog

Notable changes to this prototype. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html), with the caveat
that nothing here is a published package: the version pins what the scorecard
and the FHIR bundles were produced by.

The version lives in two places, `pyproject.toml` and `service/__init__.py`,
and a test fails if they disagree. `uv.lock` records it as well, and the
lockfile check fails if that copy is stale.

0.3.0 is the first version cut as a release and tagged. 0.1.0 and 0.2.0 were
written up afterwards, together, in 857dd20, and never tagged, so their
headings link to nothing rather than to a commit picked after the fact.

## [Unreleased]

## [0.3.0] - 2026-10-29

Nothing clinical changed. The dependency files and `.env.example` can now be
read by tools as well as by people, and CI holds them to it. Every file is
under 400 lines, the container reports its own health, and the defects found
on the way are fixed, each with a test that fails without the fix.

### Added

- **`uv.lock`**, the lock that belongs to `pyproject.toml`. The existing
  `requirements.lock` is a pip requirements file under a name tooling built
  around `pyproject.toml` does not look for, and a code scanner that read this
  repository reported no lockfile at all. `make lock` now also writes
  `uv.lock`, at `requirements.lock`'s exact versions, with uv installed into
  the throwaway environment at a version pinned in the Makefile.
  `tools/check_lockfiles.py` fails the build if `uv.lock` was resolved from a
  `pyproject.toml` other than the current one (a dependency, the version or
  `requires-python` changed without relocking), or if it and
  `requirements.lock` disagree about any version. It also locks the optional
  `model` extra, which nothing did before.
- **Tests for the lockfile check** (`tests/test_lockfiles.py`), which had only
  ever run as a CI step. They copy the real files and make each mistake the
  check exists to catch.
- **`.env.example` is checked in CI** (`tools/env_example.py`, run by
  `tools/ci_checks.py`). Every environment variable read under `service/`,
  `tools/`, `eval/` or `datagen/` must have a line, found from the syntax tree
  rather than by searching text, and every line must be read by something. The
  README has always said every variable is in the file; that was true by
  diligence, and is now true by construction.
- **A container health check.** The Dockerfile has a `HEALTHCHECK` that polls
  `/health` with the standard library, since the image has no curl. Until now
  only compose's Postgres had one, so a platform could tell the application
  container was running but not whether it was working.
- **The store says why it chose its backend.** `store.opened` names the
  backend, where it is, and whether `CLINICIAN_STORE_BACKEND` pinned it;
  `db.unreachable` and `db.driver_missing` say why Postgres was not used,
  without the password; `store.reset` records what it destroyed. The page and
  `/health` already said which backend answered, never why the other did not.
- **`LICENSE`** (MIT). `pyproject.toml` declared MIT with no file behind it,
  and now points at the file.
- **Reference sections in the README**: install, commands, tests,
  configuration, HTTP endpoints and layout, each a section of its own beside
  the argument rather than inside it.

### Changed

- **`.env.example` sets each line to its default** instead of commenting it
  out, so copying it to `.env` changes nothing until a line is edited, and
  each default is a value rather than a sentence. That is the code's own
  default where it has one and empty where empty and absent read the same,
  which is not the same thing: `CLINICIAN_STORE=` would put the store in the
  repository root and `HOST=` would bind every interface.
  `tests/test_env_example.py` asks each deciding function what the system
  would do with the file loaded and without it, and fails on any difference.
  Two lines stay commented because no value means the same as leaving them
  out: `CLINICIAN_ALLOW_RESET`, where even an empty value is a decision, and
  `ANTHROPIC_AUTH_TOKEN`, which the SDK reads directly.
- **No Python file over 400 lines**, down from 500, enforced in
  `tools/ci_checks.py`. Five files were split along seams their authors had
  already marked: `tests/test_resume.py` keeps the thread-id rules while the
  clinic and live surfaces that apply them have files of their own, reply
  parsing has moved from `service/router/backends/hosted.py` to `replies.py`,
  the two `tools.live` modes that make no model call are in
  `tools/live_inspect.py`, the diabetic cohort is in `datagen/diabetic.py`,
  and the helpers `datagen/adversarial.py` writes its cases with are in
  `datagen/mutation_kit.py`.
- **The coverage floor is 66, up from 60**, a couple of points under the 68.2
  measured over `/service`: the margin a branch skipped on one interpreter
  costs.
- A reply that cannot be parsed now names the model that answered, not the one
  that was asked. In a fallback chain they differ.
- `platform_port()` is out of `tools/demo/__main__.py`'s `main()`, so the
  decision about `PORT` can be tested without starting a server. Behaviour is
  unchanged.
- GitHub Actions, bumped by Dependabot: `actions/checkout` 5 to 7,
  `actions/setup-python` 6 to 7, `actions/upload-artifact` 4 to 7.

### Fixed

- **`tools.live` and `tools.store` never installed a log handler.** `/service`
  leaves that to the application by design, and these two are applications.
  Their warnings came out through logging's last-resort handler as a bare
  event name with every field stripped, which looks like logging working.
  Covered by a test that runs the entry point as a subprocess, because
  `configure()` is idempotent and an in-process test would pass on a handler
  some earlier test installed.
- **A redaction test failed one run in a thousand.** It planted the integer
  180 and searched the whole log line, whose timestamp ends in a three-digit
  millisecond field. The canaries are now strings no timestamp can spell, and
  the nested secret, which was `"x"` and could not be searched for, has an
  assertion of its own.
- **The README said an unset `CLINICIAN_DATABASE_URL` meant files.** It does
  not: unset, the store still tries `localhost:5544`, where `docker compose up`
  puts Postgres, and only falls back to files when nothing answers.
- The README said `make clean` removes the store. It removes the virtualenv and
  the caches, and leaves the store alone.
- `tools/ci_checks.py` described five checks and a 500-line limit. It runs
  eight, and the limit is 400.

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

[Unreleased]: https://github.com/rishavnaskar/indonesia-doctor-twin/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/rishavnaskar/indonesia-doctor-twin/releases/tag/v0.3.0
