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


@pytest.mark.parametrize(
    "field",
    ["api_key", "authorization", "patient", "observations", "medications",
     "patient_instructions", "wire", "openrouter_api_key"],
)
def test_patient_content_and_credentials_never_reach_a_log_line(field):
    """The one rule that makes logging this system safe at all.

    A stack trace or a log line from a clinical system is health data if it
    carries the record that produced it, and health data may not leave the
    country. The cheapest way to honour that is never to put it in the line.
    """
    line = JSONFormatter().format(_record(**{field: {"sbp": 180, "secret": "x"}}))

    assert json.loads(line)[field] == "[redacted]"
    assert "180" not in line


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

        record = logging.LogRecord("tests", logging.ERROR, __file__, 1,
                                   "it.failed", (), sys.exc_info())
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

        tally.emit(logging.LogRecord("tests", logging.ERROR, __file__, 1,
                                     "it.failed", (), sys.exc_info()))

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
        self._status = {"ready": True, "error": None, "done": 9, "total": 9,
                        **status}

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
