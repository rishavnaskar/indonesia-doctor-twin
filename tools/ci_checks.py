"""Architectural checks that run in CI.

These are cheap now and impossible to retrofit later, which is the entire
argument for having them on day one.

  1. Nothing under /service names a country, payer, drug or guideline.
     The banned vocabulary is read from the packs themselves, so adding a drug
     to the formulary automatically forbids hard-coding it in the engine.
  2. /service/gate imports nothing from /service/reason, no orchestration
     library, and no YAML.
  3. Only /service/graph may import the orchestration library.
  4. No hosted tracing endpoint is configured anywhere.

Check 1 inspects identifiers and non-docstring string literals — not comments
and not docstrings. A comment explaining *why* a rule is national is exactly
the kind of thing we want people to write; a string literal `"fornas"` buried
in the reasoning layer is what we are trying to prevent.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "service"

ORCHESTRATION = ("langgraph", "langchain", "langsmith")

STATIC_BANNED = {
    "indonesia", "indonesian", "bahasa", "jakarta", "papua",
    "bpjs", "jkn", "inacbg", "ina-cbg", "eklaim", "e-klaim", "idrg",
    "satusehat", "fornas", "efornas", "khanza", "simrs",
    "kemenkes", "permenkes", "kepmenkes", "perki", "inash", "persi", "arssi",
    "puskesmas", "dukcapil", "bpom", "prolanis",
}

TRACING_MARKERS = (
    "langchain_tracing", "langsmith_endpoint", "langsmith_api_key",
    "langchain_api_key", "smith.langchain.com",
)


def _banned_vocabulary() -> set[str]:
    words = set(STATIC_BANNED)
    try:
        sys.path.insert(0, str(ROOT))
        from service.packs.loader import load_pack

        for pack_id in [p.name for p in (ROOT / "packs").iterdir() if p.is_dir()]:
            rules = load_pack(pack_id)
            words.add(rules.pack_id.lower())
            words |= {m.lower() for m in rules.molecules}
            words |= {m.lower() for m in rules.recognised}
    except Exception as exc:  # pragma: no cover
        print(f"  ! could not read packs for vocabulary: {exc}")
    # 'id' as a pack id is far too short to grep for without drowning in noise.
    return {w for w in words if len(w) > 3}


def _tokens(path: Path) -> list[tuple[int, str]]:
    """Identifiers and non-docstring string literals, with line numbers."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute):
            found.append((node.lineno, node.attr))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.lineno, node.name))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                found.append((node.lineno, node.value))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            found.append((node.lineno, module))
            for alias in node.names:
                found.append((node.lineno, alias.name))
    return found


def check_no_national_names() -> list[str]:
    banned = _banned_vocabulary()
    failures = []
    for path in sorted(SERVICE.rglob("*.py")):
        for lineno, token in _tokens(path):
            lowered = token.lower()
            for word in banned:
                if word in lowered:
                    failures.append(
                        f"{path.relative_to(ROOT)}:{lineno}: /service names {word!r} "
                        f"(in {token!r}). It belongs in a pack."
                    )
    return failures


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append((node.lineno, node.module or ""))
    return out


def check_gate_purity() -> list[str]:
    failures = []
    for path in sorted((SERVICE / "gate").rglob("*.py")):
        for lineno, module in _imports(path):
            low = module.lower()
            if any(low.startswith(o) for o in ORCHESTRATION):
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: gate imports {module!r}")
            if low == "yaml" or low.startswith("yaml."):
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: gate imports YAML")
            if low.startswith("service.reason"):
                failures.append(
                    f"{path.relative_to(ROOT)}:{lineno}: gate imports from /reason ({module!r})"
                )
    return failures


def check_orchestration_confined() -> list[str]:
    failures = []
    for path in sorted(SERVICE.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative.parts[:2] == ("service", "graph"):
            continue
        for lineno, module in _imports(path):
            if any(module.lower().startswith(o) for o in ORCHESTRATION):
                failures.append(
                    f"{relative}:{lineno}: imports {module!r}. Only /service/graph may."
                )
    return failures


def check_no_hosted_tracing() -> list[str]:
    failures = []
    patterns = ("*.py", "*.yaml", "*.yml", "*.toml", "*.ini", "*.cfg", "*.env", "*.json")
    skip = {".venv", ".git", "__pycache__", "tools"}
    for pattern in patterns:
        for path in ROOT.rglob(pattern):
            if any(part in skip for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for marker in TRACING_MARKERS:
                if marker in text:
                    failures.append(
                        f"{path.relative_to(ROOT)}: configures {marker!r}. "
                        "Health data must not leave the country."
                    )
    return failures


# Docs and rendered text carry an em-dash convention. It is a writing rule, not
# an architectural one, and it is here because the alternative is checking by
# eye: the first pass over the markdown missed every string literal, every YAML
# value the surface renders, and every `&mdash;` entity, because a grep for the
# character finds none of the last of those. A check that reads what actually
# ships is the only version of this that stays true.
#
# Table cells use a lone em-dash to mean "no value", which is ordinary
# typography rather than prose, so a string that is only an em-dash passes.
EM_DASH = "\u2014"
ENTITY_DASHES = ("&mdash;", "&#8212;", "&#x2014;")


# `"\u2014"` as a whole quoted token is a table cell meaning "no value". Strip
# those before looking, so a template that renders one is not mistaken for prose.
PLACEHOLDER = f'"{EM_DASH}"'


def _prose_dash(text: str) -> bool:
    return EM_DASH in text.replace(PLACEHOLDER, "").strip(EM_DASH)


def check_no_em_dashes_in_docs() -> list[str]:
    failures = []
    for path in sorted(ROOT.glob("docs/*.md")) + [ROOT / "README.md"]:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if EM_DASH in line or any(e in line for e in ENTITY_DASHES):
                failures.append(f"{path.relative_to(ROOT)}:{n}")
    return failures


def check_no_em_dashes_in_rendered_text() -> list[str]:
    """Every string the user reads: pack values, and Python string literals.

    Docstrings and comments are exempt. They are notes to whoever maintains
    this, not text the surface renders.
    """
    failures = []

    for path in sorted((ROOT / "packs").rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except Exception:
            continue

        def walk(node, trail=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield from walk(v, f"{trail}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    yield from walk(v, f"{trail}[{i}]")
            elif isinstance(node, str) and _prose_dash(node):
                yield trail

        for trail in walk(data):
            failures.append(f"{path.relative_to(ROOT)} value {trail}")

    for path in sorted(ROOT.rglob("*.py")):
        if any(part in path.parts for part in (".venv", "__pycache__", "tests")):
            continue
        if path.name == "ci_checks.py":
            continue  # this file names the characters it is looking for
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        exempt = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) and node.body:
                if ast.get_docstring(node, clean=False) is not None:
                    exempt.add(node.body[0].lineno)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if node.lineno in exempt:
                continue
            if _prose_dash(node.value) or any(e in node.value for e in ENTITY_DASHES):
                failures.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return failures


CHECKS = [
    ("no country/payer/drug/guideline names under /service", check_no_national_names),
    ("gate imports no orchestration library, no YAML, nothing from /reason", check_gate_purity),
    ("orchestration library confined to /service/graph", check_orchestration_confined),
    ("no hosted tracing endpoint configured", check_no_hosted_tracing),
    ("no em-dashes in the docs", check_no_em_dashes_in_docs),
    ("no em-dashes in rendered text: pack values, printed and HTML strings",
     check_no_em_dashes_in_rendered_text),
]


def main() -> int:
    print("\nArchitectural checks")
    print("=" * 64)
    total = 0
    for label, check in CHECKS:
        failures = check()
        total += len(failures)
        print(f"  [{'PASS' if not failures else 'FAIL'}] {label}")
        for failure in failures:
            print(f"         {failure}")
    print("=" * 64)
    print(f"  {total} violation(s)\n")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
