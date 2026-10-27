"""The surface's HTML, kept as HTML.

These pages used to be raw strings inside the Python modules that served them,
which made three files the largest in the repository and none of them readable
as what they are. An editor highlights a .html file; nothing highlights a
1,100-line r-string.

Substitution is deliberately the dumbest thing that works: `__NAME__` markers
replaced by `fill()`. No template engine, because a template engine is a
dependency, and this system is not allowed a hosted anything and should not
grow a rendering library to print four values either.

`tools/ci_checks.py` reads these files for the em-dash rule, exactly as it
reads the string literals they replaced, so moving them out of Python cost the
check nothing.
"""

from __future__ import annotations

import functools
from pathlib import Path

HERE = Path(__file__).resolve().parent


@functools.cache
def load(name: str) -> str:
    """One template, by file name. Cached: the files never change at runtime.

    Reads from this package's directory rather than importlib.resources,
    because the repository is run from a checkout and the simpler of two
    equivalent things wins.
    """
    path = HERE / name
    if not path.is_file():
        known = ", ".join(sorted(p.name for p in HERE.glob("*.html")))
        raise FileNotFoundError(f"no template {name!r} in {HERE}. Known: {known}")
    return path.read_text(encoding="utf-8")


def fill(name: str, **values: str) -> str:
    """Load a template and substitute its `__NAME__` markers.

    Every marker the caller names must be present, and every marker in the
    template must be named. A silently unfilled `__DATA__` renders a page that
    looks fine and contains nothing, which is the kind of failure that reaches
    a browser before it reaches a test.
    """
    text = load(name)
    for key, value in values.items():
        marker = f"__{key.upper()}__"
        if marker not in text:
            raise KeyError(f"{name} has no marker {marker}")
        text = text.replace(marker, value)
    return text
