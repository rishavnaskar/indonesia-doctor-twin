"""One command.

    make          everything, offline
    make live     everything, with a real model drafting

There used to be fourteen make targets, which is fourteen ways to run a subset
and one way to think you ran all of it. This runs the whole thing in order and
stops at the first thing that fails, so "it passed" means the same thing every
time.

The order is deliberate: the cheap checks that need nothing come first, and the
clinician surface comes last because it blocks. By the time a browser opens,
the architecture rules, the test suite, the scorecard, the pressure suite and
the FHIR bundles have all been proven — which is the claim the surface is
demonstrating.

Nothing here is required to be present. No Docker, no validator jar and no API
key each degrade to a named skip rather than a failure, because the machine
this has to run on during a demo is not the machine it was built on.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

BOLD, DIM, GREEN, RED, YELLOW, OFF = (
    "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"
)


def _say(text: str = "") -> None:
    print(text, flush=True)


def _heading(step: int, total: int, title: str, detail: str) -> None:
    _say()
    _say(f"{BOLD}[{step}/{total}] {title}{OFF}  {DIM}{detail}{OFF}")


def _stage(argv: list[str], *, quiet: bool = False) -> bool:
    """Run one stage. Returns whether it passed."""
    started = time.monotonic()
    result = subprocess.run(
        argv, cwd=ROOT,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
        text=True,
    )
    took = time.monotonic() - started
    if result.returncode != 0:
        if quiet and result.stdout:
            _say(result.stdout.rstrip())
        _say(f"{RED}  failed after {took:.0f}s{OFF}")
        return False
    if quiet:
        # A quiet stage prints one line: its verdict. Taking the *last* line of
        # output looked right and was not — these tools end on a caveat about
        # how their numbers should be read, so the run reported "and UCUM
        # annotations — not conformance failures" as a result. Match the
        # verdict instead, and print nothing if there is no clear one.
        for line in reversed((result.stdout or "").splitlines()):
            if any(word in line for word in ("passed", "failed", "violation")):
                _say(f"  {line.strip()}")
                break
    _say(f"{GREEN}  ok{OFF} {DIM}({took:.0f}s){OFF}")
    return True


# ------------------------------------------------------------------- database


def _database_up() -> str:
    """Start Postgres if this machine can. Returns a one-line status.

    Best effort on purpose. The store falls back to append-only files, so a
    machine with no Docker runs the whole system — it just keeps its state
    somewhere a text editor can reach.
    """
    if os.environ.get("CLINICIAN_STORE_BACKEND", "").lower() == "files":
        return "files (pinned by CLINICIAN_STORE_BACKEND)"
    if shutil.which("docker") is None:
        return "files (no docker on this machine)"
    probe = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if probe.returncode != 0:
        return "files (docker installed, daemon not running)"

    started = subprocess.run(
        ["docker", "compose", "up", "-d", "--wait"],
        cwd=ROOT, capture_output=True, text=True,
    )

    from service.store import Store

    if started.returncode != 0:
        # Compose failing does not mean there is no database. A second checkout
        # of this project on one machine brings up a container binding the same
        # port, and the first one to get there wins — which is fine, because it
        # is the same schema. Ask before assuming.
        store = Store()
        if store.backend == "postgres":
            return (f"postgres at {store.summary()['location']}"
                    " (already running, not started by this run)")
        return f"files ({_compose_failure(started.stderr or started.stdout)})"

    store = Store()
    return f"{store.backend} at {store.summary()['location']}"


def _compose_failure(output: str) -> str:
    """The one line of compose's output worth putting on screen.

    "docker compose could not start postgres" is true and useless. The actual
    cause is usually a port already bound, and saying so is the difference
    between a reader fixing it in ten seconds and shrugging at the fallback.
    """
    for line in (output or "").splitlines():
        lowered = line.lower()
        if "bind" in lowered or "address already in use" in lowered:
            return "port 5544 is already in use. Set CLINICIAN_DATABASE_URL"
        if "permission denied" in lowered:
            return "docker refused the request. Check its permissions"
    return "docker compose could not start postgres"


# ----------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run everything. --live adds a real model.",
    )
    parser.add_argument("--live", action="store_true",
                        help="draft with a real model instead of the reference reasoner")
    parser.add_argument("--ci", action="store_true",
                        help="the gates only: no walkthrough, no browser, no model")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))

    stages: list[tuple[str, str, list[str], bool]] = [
        ("Architecture rules",
         "no country, payer, drug or guideline named in the engine",
         [PY, "tools/ci_checks.py"], True),
        ("Test suite",
         "every safety property, three storage backends",
         # No -q here: pytest.ini already sets it in addopts, and a second one
         # is -qq, which suppresses the "N passed" line this stage reports.
         [PY, "-m", "pytest", "tests/"], True),
        ("Scorecard",
         "the seven gates that decide whether this is allowed to run",
         [PY, "-m", "eval.scorecard"], False),
        ("Pressure suite",
         "hostile input against the deterministic gate",
         [PY, "-m", "eval.pressure"], False),
        ("FHIR conformance",
         "official HL7 validator, if it has been downloaded",
         [PY, "-m", "tools.validate_fhir"], False),
    ]
    if not args.ci:
        stages.append(
            ("Walkthrough", "one narrated encounter per outcome",
             [PY, "-m", "tools.walkthrough"], False))
    if args.live and not args.ci:
        stages.append(
            ("Live encounters",
             "real model, real refusals, real provenance, replayed once stored",
             [PY, "-m", "tools.live", "--n", "5"], False))

    total = len(stages) + (0 if args.ci else 1)

    _say()
    _say(f"{BOLD}  A digital twin of a doctor's work, not a doctor.{OFF}")
    _say(f"  {DIM}Drafting is a model's job. Deciding whether a draft is allowed"
         f" to exist is not.{OFF}")
    _say()
    _say(f"  storage    {_database_up()}")
    _say(f"  drafting   {'a real model over the network' if args.live else 'the reference reasoner (no network, no cost)'}")

    for index, (title, detail, argv, quiet) in enumerate(stages, start=1):
        _heading(index, total, title, detail)
        if not _stage(argv, quiet=quiet):
            _say()
            _say(f"{RED}  Stopped at: {title}.{OFF} Nothing after it was run.")
            return 1

    if args.ci:
        _say()
        _say(f"{GREEN}{BOLD}  All gates green.{OFF}")
        return 0

    _heading(total, total, "Clinician surface",
             f"http://localhost:{args.port} (ctrl-c to stop)")
    _say()
    surface = [PY, "-m", "tools.demo", "--port", str(args.port)]
    if args.live:
        surface.append("--live")
    try:
        return subprocess.call(surface, cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
