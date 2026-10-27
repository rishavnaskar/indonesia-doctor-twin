"""Does each lockfile still match the file it was generated from?

A lockfile that has drifted from its input is worse than having none: it looks
reproducible and is not. Adding a package to requirements.txt and forgetting to
regenerate the lock is the easy mistake, and it stays invisible until a
deployment installs the lock and the import fails.

What this checks, and deliberately not more:

  * every package named in requirements.txt appears in requirements.lock, at a
    version the requirement permits
  * requirements-dev.txt likewise against requirements-dev.lock
  * every pin is an exact `==`, in both inputs and both locks
  * the dev lock is a superset of the runtime lock, since it installs both

What it does not do is re-resolve. That needs the network and a matching
interpreter, and this has to be able to run in a sandbox. Regenerating is
`make lock`.

    python tools/check_lockfiles.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAIRS = (
    ("requirements.txt", "requirements.lock"),
    ("requirements-dev.txt", "requirements-dev.lock"),
)

# `name[extra1,extra2] == 1.2.3`, with the extras and whitespace optional.
PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)\s*(?:\[(?P<extras>[^\]]*)\])?\s*==\s*(?P<version>[^\s;#]+)"
)


def normalise(name: str) -> str:
    """PEP 503: `psycopg_binary`, `Psycopg-Binary` and `psycopg.binary` are one."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read(path: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """Pins, extras requested, and any requirement that is not an exact pin."""
    pins: dict[str, str] = {}
    extras: list[str] = []
    loose: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-r") or line.startswith("--"):
            continue
        match = PIN.match(line)
        if not match:
            loose.append(line)
            continue
        pins[normalise(match["name"])] = match["version"]
        if match["extras"]:
            extras += [normalise(e) for e in match["extras"].split(",") if e.strip()]
    return pins, extras, loose


def check() -> list[str]:
    problems: list[str] = []
    locks: dict[str, dict[str, str]] = {}

    for source_name, lock_name in PAIRS:
        source_path, lock_path = ROOT / source_name, ROOT / lock_name
        if not lock_path.exists():
            problems.append(f"{lock_name} is missing. Run `make lock`.")
            continue

        source, extras, loose = read(source_path)
        lock, _, lock_loose = read(lock_path)
        locks[lock_name] = lock

        for line in loose:
            problems.append(f"{source_name}: {line!r} is not an exact pin (use ==)")
        for line in lock_loose:
            problems.append(f"{lock_name}: {line!r} is not an exact pin")

        for name, version in source.items():
            if name not in lock:
                problems.append(
                    f"{source_name} requires {name}=={version}, which is not in "
                    f"{lock_name}. Run `make lock`."
                )
            elif lock[name] != version:
                problems.append(
                    f"{name}: {source_name} pins {version}, {lock_name} has "
                    f"{lock[name]}. Run `make lock`."
                )

        # An extra is a package: `psycopg[binary]` must put psycopg-binary in
        # the lock, and a lock without it installs a psycopg that cannot
        # connect.
        for extra in extras:
            if not any(extra in name for name in lock):
                problems.append(
                    f"{source_name} asks for the {extra!r} extra, but nothing in "
                    f"{lock_name} provides it. Run `make lock`."
                )

    runtime, dev = locks.get("requirements.lock"), locks.get("requirements-dev.lock")
    if runtime and dev:
        for name, version in runtime.items():
            if dev.get(name) != version:
                problems.append(
                    f"{name}=={version} is in requirements.lock but "
                    f"requirements-dev.lock has {dev.get(name) or 'nothing'}. The "
                    "development lock installs both. Run `make lock`."
                )
    return problems


def main() -> int:
    print("\nLockfiles")
    print("=" * 64)
    problems = check()
    for source_name, lock_name in PAIRS:
        related = [p for p in problems if source_name in p or lock_name in p]
        print(f"  [{'PASS' if not related else 'FAIL'}] {source_name} -> {lock_name}")
        for problem in related:
            print(f"         {problem}")
    print("=" * 64)
    print(f"  {len(problems)} problem(s)\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
