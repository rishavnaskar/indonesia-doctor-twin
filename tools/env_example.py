"""Every environment variable the system reads has a line in .env.example.

The README has said so since the file was written, and until now that was true
by diligence: whoever added a variable remembered to add its line. This makes
it true by construction, in both directions, because a stale line misleads a
reader as much as a missing one does:

  * a variable read under service/, tools/, eval/ or datagen/ with no line in
    .env.example is a failure
  * a line in .env.example that nothing reads is a failure too

A commented line counts. Two variables are commented on purpose, because no
value means the same as leaving them out; .env.example says which and why, and
tests/test_env_example.py holds every other line to the claim in its header.

Reads are found in the syntax tree, not by searching text: `os.environ.get`,
`os.environ[...]`, `os.getenv`, and `setdefault` or `pop`, each with a literal
name. A name computed at runtime cannot be checked statically and is not
attempted. The one such call is load_env's own setdefault, which is what reads
.env rather than a setting anything depends on.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("service", "tools", "eval", "datagen")

# `NAME=value` or `# NAME=value`, and nothing else. Prose in a comment that
# mentions a variable ("Set CLINICIAN_ALLOW_RESET=1 to ...") starts with a
# word, so it is not mistaken for that variable's line.
LINE = re.compile(r"^\s*(?P<comment>#\s*)?(?P<name>[A-Z][A-Z0-9_]*)=")

_METHODS = {"get", "setdefault", "pop"}


def _is_environ(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "environ"


def _literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _name_read(node: ast.AST) -> str | None:
    if isinstance(node, ast.Subscript) and _is_environ(node.value):
        return _literal(node.slice)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        first = node.args[0] if node.args else None
        if node.func.attr in _METHODS and _is_environ(node.func.value):
            return _literal(first)
        if node.func.attr == "getenv":
            return _literal(first)
    return None


def reads(root: Path = ROOT) -> dict[str, list[str]]:
    """Each variable the code reads, with every place it reads it."""
    found: dict[str, list[str]] = {}
    for top in SOURCES:
        for path in sorted((root / top).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                name = _name_read(node)
                if name:
                    found.setdefault(name, []).append(f"{path.relative_to(root)}:{node.lineno}")
    return found


def documented(path: Path) -> dict[str, bool]:
    """Each variable .env.example has a line for, and whether it is commented."""
    names: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LINE.match(line)
        if match:
            names[match["name"]] = bool(match["comment"])
    return names


def check(root: Path = ROOT) -> list[str]:
    example = root / ".env.example"
    if not example.exists():
        return [".env.example is missing, and the README sends every reader to it."]
    read, named = reads(root), documented(example)
    failures = [
        f"{name} is read at {', '.join(read[name])} but has no line in .env.example."
        for name in sorted(set(read) - set(named))
    ]
    failures += [
        f".env.example has a line for {name}, which nothing reads. A line for a "
        "setting that does nothing is a wrong instruction, so delete it."
        for name in sorted(set(named) - set(read))
    ]
    return failures
