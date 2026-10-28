"""What the lines in .env.example say, held to the claim in its header.

tools/env_example.py checks that every variable the code reads has a line.
This checks the lines themselves: that copying the file to .env changes
nothing until one is edited. The header says so, and it is the kind of claim
that is true the day it is written and false the first time someone adds a
variable whose default is not empty, then writes the obvious line for it.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from unittest import mock

from tools import env_example
from tools.live import load_env

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"

# Placeholders to replace rather than settings to keep, as the header says. A
# key that is present but wrong is supposed to behave differently from none.
KEYS = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")


def _effective() -> dict:
    """What the system would do, asked of the code that decides it.

    Not a re-reading of the variables, which would test this file against
    itself. Each entry is the answer from the function the system calls.
    """
    from service import db, store
    from service.logging import configure
    from tools.demo.__main__ import build_parser, platform_port
    from tools.demo.store_access import reset_allowed
    from tools.validate_fhir import _find_jar

    args = build_parser().parse_args([])
    # Not the default level, so a CLINICIAN_LOG_LEVEL line that overrode the
    # flag would show up as a difference rather than agreeing by coincidence.
    configure("warning", stream=io.StringIO(), force=True)
    root = logging.getLogger()
    return {
        "store directory": store.default_dir(),
        "re-run stored work": store.forced_fresh(),
        "pinned to files": store._forced_to_files(),
        "database tried": db.dsn(),
        "reset allowed": reset_allowed(),
        "validator jar": _find_jar(None),
        "bind host": args.host,
        "platform port": platform_port([]),
        "log level": root.level,
        "log format": type(root.handlers[0].formatter).__name__,
    }


def test_copying_env_example_changes_nothing(tmp_path):
    settings = tmp_path / ".env"
    settings.write_text(
        "\n".join(
            line
            for line in EXAMPLE.read_text(encoding="utf-8").splitlines()
            if not line.startswith(tuple(f"{key}=" for key in KEYS))
        ),
        encoding="utf-8",
    )
    try:
        # patch.dict restores the environment exactly, removing what load_env
        # adds as well, so a failure here cannot leak into the next test.
        with mock.patch.dict(os.environ):
            for name in env_example.documented(EXAMPLE):
                os.environ.pop(name, None)
            absent = _effective()
            load_env(settings)
            copied = _effective()
    finally:
        from service.logging import configure

        configure("info", force=True)  # put the suite's own logging back

    assert copied == absent


def test_the_check_finds_a_missing_line_and_a_stale_one(tmp_path):
    (tmp_path / "service").mkdir()
    (tmp_path / "service" / "settings.py").write_text(
        "import os\n"
        'a = os.environ.get("ACTIVE")\n'
        'b = os.environ["COMMENTED"]\n'
        'c = os.getenv("ONLY_IN_PROSE")\n'
        "d = os.environ.get(computed_at_runtime)\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text(
        "ACTIVE=\n"
        "# COMMENTED=1\n"
        "# Set ONLY_IN_PROSE=1 to switch it on. A mention is not a line.\n"
        "NOTHING_READS_THIS=1\n",
        encoding="utf-8",
    )

    failures = env_example.check(tmp_path)

    assert len(failures) == 2, failures
    assert failures[0].startswith("ONLY_IN_PROSE is read at service/settings.py:4")
    assert "NOTHING_READS_THIS" in failures[1]


def test_every_variable_the_system_reads_has_a_line():
    assert env_example.check() == []
