"""The lockfile check, which until now was a CI step nothing tested.

Each test copies this repository's real dependency files into a temporary
directory and makes one of the mistakes the check exists to catch. Copying
the real files rather than writing small fake ones means a change to how
uv.lock is laid out shows up here, instead of in a check that passes on a
fixture and fails to read the file it is actually given.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tools import check_lockfiles

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "pyproject.toml",
    "requirements.txt",
    "requirements.lock",
    "requirements-dev.txt",
    "requirements-dev.lock",
    "uv.lock",
)


@pytest.fixture
def tree(tmp_path) -> Path:
    for name in FILES:
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def _edit(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    edited, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    assert count == 1, f"{pattern!r} matched nothing in {path.name}"
    path.write_text(edited, encoding="utf-8")


def test_the_lockfiles_in_this_repository_agree():
    assert check_lockfiles.check() == []


def test_the_copied_tree_agrees_before_anything_is_changed(tree):
    """Without this, every test below could pass on a copy that was never valid."""
    assert check_lockfiles.check(tree) == []


def test_a_dependency_added_without_relocking_fails(tree):
    _edit(
        tree / "pyproject.toml",
        r'^    "psycopg\[binary\]>=3\.1",$',
        '    "psycopg[binary]>=3.1",\n    "rich>=13",',
    )

    problems = check_lockfiles.check(tree)

    assert problems == [
        "pyproject.toml declares rich>=13, but uv.lock was not resolved from it. Run `make lock`."
    ]


def test_a_dependency_removed_without_relocking_fails(tree):
    _edit(tree / "pyproject.toml", r'^model = \["anthropic>=1\.0"\]$', "")

    problems = check_lockfiles.check(tree)

    assert len(problems) == 1
    assert problems[0].startswith("uv.lock was resolved from anthropic>=1.0 (the 'model' extra)")


def test_uv_lock_at_another_version_than_requirements_lock_fails(tree):
    _edit(
        tree / "uv.lock",
        r'^name = "pyyaml"\nversion = "6\.0\.3"$',
        'name = "pyyaml"\nversion = "6.0.2"',
    )

    assert check_lockfiles.check(tree) == [
        "pyyaml: requirements.lock pins 6.0.3, uv.lock has 6.0.2. Run `make lock`."
    ]


def test_a_version_bump_without_relocking_fails(tree):
    _edit(tree / "pyproject.toml", r'^version = "[^"]+"$', 'version = "9.9.9"')

    problems = check_lockfiles.check(tree)

    assert len(problems) == 1
    assert problems[0].startswith("pyproject.toml says version 9.9.9, uv.lock was resolved for ")


def test_a_missing_uv_lock_fails(tree):
    (tree / "uv.lock").unlink()

    assert check_lockfiles.check(tree) == ["uv.lock is missing. Run `make lock`."]
