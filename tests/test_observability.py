"""Logs, the error tally, /health, templates, and the version pin.

All of this is infrastructure rather than clinical behaviour, and every one of
them is the kind of thing that is assumed to work until the morning it does
not. A health check that answers 200 while the store is unreachable is worse
than no health check, because something downstream believes it.
"""

from __future__ import annotations

import io
import json
import logging
import tomllib
from pathlib import Path

import pytest

import service
from service.logging import ErrorTally, JSONFormatter, configure, get_logger, redact
from tools.demo import templates
from tools.demo.health import health

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------- logging


def _record(**fields) -> logging.LogRecord:
    record = logging.LogRecord("tests", logging.INFO, __file__, 1, "an.event", (), None)
    for key, value in fields.items():
        setattr(record, key, value)
    return record


def test_a_log_line_is_one_json_object():
    line = JSONFormatter().format(_record(patient_id="SYN-1", outcome="committed"))
    payload = json.loads(line)

    assert payload["event"] == "an.event"
    assert payload["level"] == "info"
    assert payload["logger"] == "tests"
    assert payload["patient_id"] == "SYN-1"
    assert payload["outcome"] == "committed"
    assert payload["ts"].endswith("Z")


# Canaries for the redaction test below. They are strings rather than the
# numbers and single letters they stand in for, because that test searches the
# whole rendered line and the line is not only the field under test: `ts` ends
# in a three-digit millisecond field, so the old canary of 180 failed roughly
# one run in a thousand on a timestamp reading ".180Z" and nothing else. A
# value that can prove a leak has to be one no other field can spell, and
# letters and hyphens are enough to put it out of a timestamp's reach.
VITAL_CANARY = "sbp-canary-9f2c"
SECRET_CANARY = "sk-live-canary-4b81"


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "authorization",
        "patient",
        "observations",
        "medications",
        "patient_instructions",
        "wire",
        "openrouter_api_key",
    ],
)
def test_patient_content_and_credentials_never_reach_a_log_line(field):
    """The one rule that makes logging this system safe at all.

    A stack trace or a log line from a clinical system is health data if it
    carries the record that produced it, and health data may not leave the
    country. The cheapest way to honour that is never to put it in the line.

    Checked twice over, because the two ways this breaks look nothing alike.
    The parsed field catches redaction returning the wrong shape; the search
    over the raw line catches the nested values surviving somewhere else in
    the record, which is the failure that would never show up in the field a
    reader thinks to look at.
    """
    line = JSONFormatter().format(
        _record(**{field: {"sbp": VITAL_CANARY, "secret": SECRET_CANARY}})
    )

    assert json.loads(line)[field] == "[redacted]"
    assert VITAL_CANARY not in line
    assert SECRET_CANARY not in line


def test_redaction_reaches_nested_fields():
    clean = redact({"site": {"id": "SITE-A", "api_key": "sk-live-1"}})

    assert clean["site"]["id"] == "SITE-A"
    assert clean["site"]["api_key"] == "[redacted]"


def test_a_traceback_is_logged_without_locals():
    """Frames, not values. A local in this codebase is frequently a patient."""
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "tests", logging.ERROR, __file__, 1, "it.failed", (), sys.exc_info()
        )
    payload = json.loads(JSONFormatter().format(record))

    assert payload["error"] == "ValueError"
    assert payload["error_message"] == "boom"
    assert "traceback" in payload


def test_errors_are_counted_by_type():
    tally = ErrorTally()
    try:
        raise KeyError("missing")
    except KeyError:
        import sys

        tally.emit(
            logging.LogRecord("tests", logging.ERROR, __file__, 1, "it.failed", (), sys.exc_info())
        )

    summary = tally.summary()
    assert summary["total"] == 1
    assert summary["by_type"] == {"KeyError": 1}
    assert summary["last"]["event"] == "it.failed"


def test_configure_writes_where_it_is_told():
    stream = io.StringIO()
    configure("info", stream=stream, force=True)
    get_logger("tests.configure").info("wrote.here", extra={"n": 1})

    assert json.loads(stream.getvalue().strip())["event"] == "wrote.here"
    configure("info", force=True)  # back to stderr for the rest of the suite


# -------------------------------------------------------------------- health


class _Build:
    def __init__(self, **status):
        self._status = {"ready": True, "error": None, "done": 9, "total": 9, **status}

    def status(self):
        return self._status


class _Args:
    pack = "id"
    live = False


def test_health_reports_the_store_backend_it_actually_reached():
    report, code = health(_Args(), _Build())

    assert code == 200
    assert report["status"] == "ok"
    assert report["version"] == service.__version__
    # The suite pins the file backend in conftest, which is exactly the claim
    # under test: /health says which of the two answered, never just "up".
    assert report["store"]["reachable"] is True
    assert report["store"]["backend"] in ("files", "postgres")
    assert "location" in report["store"]


def test_a_failed_build_is_degraded_rather_than_down():
    """The API and /clinic still serve. 503 would pull a working deployment."""
    report, code = health(_Args(), _Build(ready=False, error="PackError: nope"))

    assert code == 200
    assert report["status"] == "degraded"
    assert report["build"]["error"] == "PackError: nope"


def test_an_unreachable_store_is_unhealthy(monkeypatch):
    def explode():
        raise OSError("connection refused")

    monkeypatch.setattr("tools.demo.store_access.store", explode)
    report, code = health(_Args(), _Build())

    assert code == 503
    assert report["status"] == "unhealthy"
    assert report["store"]["reachable"] is False


def test_health_never_triggers_a_build():
    """A probe that starts work can take a deployment down by being polled."""

    class Counting(_Build):
        started = 0

        def start(self):
            Counting.started += 1

    build = Counting()
    health(_Args(), build)
    assert Counting.started == 0


# ----------------------------------------------------------------- templates


def test_every_template_loads():
    names = sorted(p.name for p in (ROOT / "tools" / "demo" / "templates").glob("*.html"))

    assert names, "the surface has no pages"
    for name in names:
        assert templates.load(name).strip()


def test_a_missing_template_names_the_ones_that_exist():
    with pytest.raises(FileNotFoundError, match=r"clinic\.html"):
        templates.load("nope.html")


def test_an_unfilled_marker_is_an_error_not_a_blank_page():
    """A silently unfilled __DATA__ renders a page that contains nothing."""
    with pytest.raises(KeyError, match=r"__NOPE__"):
        templates.fill("report.html", title="t", data="{}", nope="x")


def test_the_report_page_carries_its_data():
    page = templates.fill("report.html", title="A title", data='{"encounters":[]}')

    assert "__DATA__" not in page and "__TITLE__" not in page
    assert '{"encounters":[]}' in page
    assert "A title" in page


# ------------------------------------------------------------------- version


def test_the_version_is_the_same_in_both_places():
    """Two files carrying one number is two files that will disagree."""
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

    assert declared == service.__version__


# ------------------------------------------------------- the engine's logging
#
# /service is a library. It takes loggers and emits; it never installs a
# handler. The demo surface is the application and does that once in main().


def test_importing_the_engine_does_not_hijack_root_logging():
    """A library that reconfigures logging on import is rude in a demo and
    unacceptable in a deployment that already has its own setup."""
    import importlib
    import logging as stdlib_logging

    import service.logging as engine_logging

    root = stdlib_logging.getLogger()
    saved = list(root.handlers)
    for handler in saved:
        root.removeHandler(handler)
    # Without this the test passes for the wrong reason: configure() is
    # idempotent, an earlier test has already run it, and a module that calls
    # get_logger() on import would therefore install nothing here. Checked by
    # pointing service.store at get_logger and confirming this test goes red.
    engine_logging._CONFIGURED = False

    try:
        for name in ("service.store", "service.db"):
            importlib.reload(importlib.import_module(name))
        assert root.handlers == [], "importing the engine installed a handler"
    finally:
        configure("info", force=True)  # put the suite's own logging back


def test_the_store_says_which_backend_it_chose(caplog):
    """The decision is on the page and at /health, which answers "what is it
    on now" and not "what did it pick at startup"."""
    from service.store import Store

    with caplog.at_level(logging.INFO, logger="service.store"):
        Store()

    opened = [r for r in caplog.records if r.getMessage() == "store.opened"]
    assert opened, "opening a store logged nothing"
    assert opened[-1].backend in ("files", "postgres")
    assert opened[-1].pinned_to_files is True  # conftest pins the suite to files


def test_an_unreachable_database_logs_why_without_the_password(caplog):
    """A refused connection and an uninstalled driver look identical from
    outside and need different fixes, so both are named."""
    from service import db

    secret = "hunter2"
    url = f"postgresql://clinician:{secret}@127.0.0.1:1/nothing"

    with caplog.at_level(logging.WARNING, logger="service.db"):
        assert db.connect(url) is None

    events = {r.getMessage() for r in caplog.records}
    assert events & {"db.unreachable", "db.driver_missing"}, events
    assert secret not in caplog.text, "the connection string's password reached a log line"


def test_safe_location_strips_the_credentials():
    from service.db import safe_location

    assert safe_location("postgresql://user:pw@db.example:5432/clinic") == "db.example:5432/clinic"
    assert (
        safe_location("postgresql://db.example:5432/clinic")
        == "postgresql://db.example:5432/clinic"
    )


def test_destroying_the_store_is_logged(tmp_path, caplog):
    """The one event here worth finding in a log a week later."""
    from service.store import Store

    store = Store(tmp_path / "store")
    store.checkpoints.parent.mkdir(parents=True, exist_ok=True)
    store.checkpoints.write_text('{"a": 1}\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="service.store"):
        counts = store.reset()

    reset_records = [r for r in caplog.records if r.getMessage() == "store.reset"]
    assert reset_records, "a wipe logged nothing"
    assert reset_records[-1].destroyed == counts
    assert counts["checkpoints"] == 1


def test_a_cli_entry_point_installs_the_handler(tmp_path):
    """A library that logs into the void is a library nobody can debug.

    `/service` deliberately never calls `configure()`, which leaves it on each
    application to do so. `tools.live` did not, so the store's own warning -
    the one that says which host refused the connection and why - came out
    through logging's last-resort handler as the bare string "db.unreachable"
    with every field stripped off. That is worse than silence: it looks like
    logging is working.

    A subprocess rather than a monkeypatched import, because the thing under
    test is what the handler does to a real process's stderr, and because
    `configure()` is idempotent - an in-process check passes on a handler some
    earlier test installed. That mistake was made once here already.
    """
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "CLINICIAN_DATABASE_URL": "postgresql://clinician:hunter2@127.0.0.1:1/nothing",
        "CLINICIAN_STORE": str(tmp_path / "store"),
        "CLINICIAN_STORE_BACKEND": "",
        "CLINICIAN_LOG_FORMAT": "",
    }
    done = subprocess.run(
        [sys.executable, "-m", "tools.store"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    events = {}
    for line in done.stderr.splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
            events[payload["event"]] = payload

    assert "store.opened" in events, f"no structured line on stderr: {done.stderr!r}"
    opened = events["store.opened"]
    assert opened["level"] == "info"
    assert opened["logger"] == "service.store"
    assert opened["backend"] == "files"
    # The whole point of the line: it fell back, and the reason is on stderr
    # next to it rather than nowhere.
    assert "db.unreachable" in events or "db.driver_missing" in events
    assert "hunter2" not in done.stderr, "the connection string's password reached stderr"
