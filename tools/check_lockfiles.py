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
  * uv.lock was resolved from pyproject.toml as it now reads, and pins every
    package in requirements.lock at the same version

Why there is a uv.lock at all. requirements.lock is what this repository
installs, but it is a pip requirements file under a name that tooling built
around pyproject.toml does not look for. A code scanner read this repository,
found pyproject.toml, and reported no lockfile, which is the mistake anything
else of that kind would make for the same reason. uv.lock is the lock that
belongs to a pyproject.toml. It is not a second source of truth: `make lock`
writes it at requirements.lock's versions, and this fails the build the moment
the two disagree. It also locks the optional `model` extra, which nothing else
did.

What it does not do is re-resolve. That needs the network and a matching
interpreter, and this has to be able to run in a sandbox. Regenerating is
`make lock`.

    python tools/check_lockfiles.py
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAIRS = (
    ("requirements.txt", "requirements.lock"),
    ("requirements-dev.txt", "requirements-dev.lock"),
)

UV_LOCK = "uv.lock"

# `name[extra1,extra2] == 1.2.3`, with the extras and whitespace optional.
PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)\s*(?:\[(?P<extras>[^\]]*)\])?\s*==\s*(?P<version>[^\s;#]+)"
)


# `psycopg[binary] >= 3.1`, the shape pyproject.toml declares a dependency in.
REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)\s*(?:\[(?P<extras>[^\]]*)\])?\s*(?P<specifier>[^;]*)"
)
EXTRA_MARKER = re.compile(r"extra\s*==\s*['\"](?P<extra>[^'\"]+)['\"]")


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


Dependency = tuple[str, tuple[str, ...], str, str | None]


def _dependency(name: str, extras, specifier: str, extra: str | None) -> Dependency:
    """One comparable shape for a pyproject.toml line and a uv.lock entry."""
    return (
        normalise(name),
        tuple(sorted(normalise(e) for e in extras if e.strip())),
        re.sub(r"\s+", "", specifier),
        extra,
    )


def _show(dep: Dependency) -> str:
    name, extras, specifier, extra = dep
    shown = f"{name}[{','.join(extras)}]{specifier}" if extras else f"{name}{specifier}"
    return f"{shown} (the {extra!r} extra)" if extra else shown


def check_uv_lock(root: Path = ROOT, runtime: dict[str, str] | None = None) -> list[str]:
    """uv.lock was resolved from pyproject.toml as it is, at requirements.lock's versions."""
    path = root / UV_LOCK
    if not path.exists():
        return [f"{UV_LOCK} is missing. Run `make lock`."]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads(path.read_text(encoding="utf-8"))
    packages = lock.get("package", [])

    wanted: set[Dependency] = set()
    declared = {None: project.get("dependencies", []), **project.get("optional-dependencies", {})}
    for extra, lines in declared.items():
        for line in lines:
            match = REQUIREMENT.match(line.strip())
            if match:
                extras = (match["extras"] or "").split(",")
                wanted.add(_dependency(match["name"], extras, match["specifier"], extra))

    me = next((p for p in packages if normalise(p["name"]) == normalise(project["name"])), {})
    recorded: set[Dependency] = set()
    for dep in me.get("metadata", {}).get("requires-dist", []):
        marker = EXTRA_MARKER.search(dep.get("marker", ""))
        recorded.add(
            _dependency(
                dep["name"],
                dep.get("extras", []),
                dep.get("specifier", ""),
                marker["extra"] if marker else None,
            )
        )

    stale = "Run `make lock`."
    problems = [
        f"pyproject.toml declares {_show(dep)}, but {UV_LOCK} was not resolved from it. {stale}"
        for dep in sorted(wanted - recorded, key=str)
    ]
    problems += [
        f"{UV_LOCK} was resolved from {_show(dep)}, which pyproject.toml no longer declares. "
        f"{stale}"
        for dep in sorted(recorded - wanted, key=str)
    ]
    for field, ours, theirs in (
        ("version", project.get("version"), me.get("version")),
        ("requires-python", project.get("requires-python"), lock.get("requires-python")),
    ):
        if ours != theirs:
            problems.append(
                f"pyproject.toml says {field} {ours}, {UV_LOCK} was resolved for {theirs}. {stale}"
            )

    # The point of keeping both: they must never disagree about what a
    # deployment installs. One version per package, too, since a lock that
    # forks by platform would install something different somewhere.
    versions: dict[str, set[str]] = {}
    for package in packages:
        versions.setdefault(normalise(package["name"]), set()).add(package.get("version", ""))
    for name, version in sorted((runtime or {}).items()):
        found = versions.get(name, set())
        if found != {version}:
            problems.append(
                f"{name}: requirements.lock pins {version}, {UV_LOCK} has "
                f"{', '.join(sorted(found)) or 'nothing'}. {stale}"
            )
    return problems


def check(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    locks: dict[str, dict[str, str]] = {}

    for source_name, lock_name in PAIRS:
        source_path, lock_path = root / source_name, root / lock_name
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
    return problems + check_uv_lock(root, runtime)


def main() -> int:
    print("\nLockfiles")
    print("=" * 64)
    problems = check()
    for source_name, lock_name in (*PAIRS, ("pyproject.toml", UV_LOCK)):
        if lock_name == UV_LOCK:
            related = [p for p in problems if UV_LOCK in p]
        else:
            related = [
                p for p in problems if UV_LOCK not in p and (source_name in p or lock_name in p)
            ]
        print(f"  [{'PASS' if not related else 'FAIL'}] {source_name} -> {lock_name}")
        for problem in related:
            print(f"         {problem}")
    print("=" * 64)
    print(f"  {len(problems)} problem(s)\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
