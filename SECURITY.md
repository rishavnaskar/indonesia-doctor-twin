# Security

## What this is

A prototype that runs on **synthetic patient data only**. There is no lawful
basis here for processing real records, and the architecture assumes there is
not one until Indonesian counsel says otherwise.

If you are considering pointing this at real data: do not, until the four
confirmations listed in `docs/DECISION.md` have actually been obtained.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository, or email the
maintainer. Please do not open a public issue for anything that would be
exploitable against a deployment.

## What the design already refuses

These are enforced in code and checked in CI, not left to review.

- **The residency guard.** A record not marked synthetic is refused before a
  request to a hosted model is built. Nothing leaves the machine. See
  `ResidencyError`, and the tests that exercise it.
- **No hosted control plane, no hosted tracing, no SaaS error tracker, no log
  drain.** `tools/ci_checks.py` fails the build if one is ever configured.
  Health data must be stored *and* processed in-country, and a stack trace from
  a clinical system carries the record that produced it.
- **Logs drop patient content and credentials by field name** before a line is
  written, and tracebacks are recorded as frames without locals, because a
  local in this codebase is frequently a patient. See `service/logging.py`.
- **The audit log cannot be rewritten.** The Postgres migration installs a
  trigger that raises on `UPDATE` and `DELETE`; the file backend is
  append-only. Clearing the clinic list writes a marker forward and deletes
  nothing.
- **A licensed doctor signs everything**, and an expired licence is refused by
  `verify_signer` rather than warned about.
- **Text the system did not author is data, never instruction.** Patient
  utterances, record free text and scanned documents are delimited before any
  model sees them, and everything a model produces faces the gate regardless.
- **The reset button is refused on a hosted deployment** unless
  `CLINICIAN_ALLOW_RESET=1` is set explicitly.

## Secrets

No key is required to run anything. `make` is offline.

Keys, when you supply them, are read from the environment or from `.env`, which
is gitignored and must stay that way. `.env.example` carries placeholders only.
`tools/ci_checks.py` scans for a committed tracing endpoint; the repository has
no committed `.env` and no hardcoded key.

CI never installs the model dependency and never has a key available, so no
test can spend money or reach a provider.

## Dependencies

Three runtime dependencies, pinned, with a lockfile. `pip-audit` runs against
the runtime lockfile on every push and fails the build on a known
vulnerability. The development lockfile is audited too, advisory only: a CVE in
a linter does not reach a patient, and blocking every merge on one would teach
people to ignore the job.

Dependabot opens update pull requests weekly for pip and monthly for GitHub
Actions and Docker.
