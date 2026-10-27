"""Structured logs: one JSON object per line, on stderr.

Everything long-running in this system used to print. A print is fine for a
narrated walkthrough and useless for a service: it cannot be filtered by level,
it carries no timestamp, it cannot be shipped anywhere, and a field inside it
is only recoverable by regex. The surface is meant to run durably against
Postgres, so it gets a log.

JSON rather than a human format, because the destination is a log aggregator
and the fields are the point:

    {"ts": "...", "level": "info", "event": "encounter.finished",
     "logger": "tools.demo.run", "patient": "SYN-0007", "outcome": "committed"}

Three rules this module exists to enforce.

**No hosted backend.** No SaaS error tracker, no hosted tracing endpoint, no
log drain to somebody else's cloud. Health data must be stored and processed
in-country, and a stack trace from a clinical system is health data: it carries
the record that produced it. Logs go to stderr and the deployment decides where
stderr goes. `tools/ci_checks.py` fails the build if a hosted tracing endpoint
is ever configured.

**No patient content.** Identifiers and outcomes, never values. `SYN-0007`
belongs in a log line; a blood pressure, a drug, a symptom or a free-text note
does not. `redact()` is applied to every field, and the field names it drops
are listed in `_NEVER_LOG`.

**Errors are counted, not just printed.** An exception that has been logged and
forgotten is an exception nobody is going to fix, so `ErrorTally` keeps a
running count per exception type and `/health` reports it. That is the whole
error-tracking story: in-process, in-country, and visible from outside.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import traceback
from collections import Counter
from typing import Any

LEVELS = ("debug", "info", "warning", "error", "critical")

DEFAULT_LEVEL = "info"

# Field names whose values never reach a log line, whatever a caller passes.
# Patient content, credentials and anything that could carry either.
_NEVER_LOG = frozenset({
    "api_key", "authorization", "token", "password", "secret", "dsn",
    "patient", "patient_state", "record", "note", "notes", "utterance",
    "free_text", "instructions", "patient_instructions", "observations",
    "medications", "diagnoses", "symptoms", "allergies", "wire", "proposal",
})

REDACTED = "[redacted]"

# Set by configure(). Guarded because the surface configures from the main
# thread while background build threads are already logging.
_LOCK = threading.Lock()
_CONFIGURED = False


def redact(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop anything that could carry patient content or a credential.

    Name-based rather than value-based on purpose: a value-based scrubber has
    to recognise what it is looking at, and the one thing certain about free
    text in a clinical record is that it does not look like anything.
    """
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        lowered = key.lower()
        if lowered in _NEVER_LOG or any(marker in lowered for marker in ("key", "secret", "token")):
            clean[key] = REDACTED
        elif isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        elif isinstance(value, (list, tuple, set)):
            clean[key] = [str(v) for v in value][:20]
        elif isinstance(value, dict):
            clean[key] = redact(value)
        else:
            clean[key] = str(value)
    return clean


class JSONFormatter(logging.Formatter):
    """One JSON object per record, with the caller's extra fields merged in."""

    # Everything LogRecord sets by itself. Anything else on the record came
    # from a caller's `extra=` and belongs in the output.
    _BUILTIN = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        extra = {
            k: v for k, v in vars(record).items()
            if k not in self._BUILTIN and k not in ("message", "asctime")
        }
        payload.update(redact(extra))
        if record.exc_info:
            kind, value, tb = record.exc_info
            payload["error"] = getattr(kind, "__name__", str(kind))
            payload["error_message"] = str(value)[:500]
            # Frames only, no locals: a local in this codebase is frequently a
            # patient.
            payload["traceback"] = "".join(traceback.format_tb(tb))[-2000:]
        return json.dumps(payload, ensure_ascii=False, default=str)


class ErrorTally(logging.Handler):
    """Counts errors by exception type, so /health can report them.

    This is the error tracking. It is deliberately not a hosted service: a
    stack trace from this system names a patient, and shipping it to a vendor
    would put health data outside the country in the one place nobody thinks
    to look for it.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._lock = threading.Lock()
        self.counts: Counter[str] = Counter()
        self.last: dict[str, Any] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        kind = "error"
        if record.exc_info and record.exc_info[0] is not None:
            kind = record.exc_info[0].__name__
        with self._lock:
            self.counts[kind] += 1
            self.last = {
                "event": record.getMessage(),
                "type": kind,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            }

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": sum(self.counts.values()),
                "by_type": dict(self.counts),
                "last": self.last,
            }


TALLY = ErrorTally()


def configure(level: str | None = None, *, stream=None, force: bool = False) -> None:
    """Install the JSON handler on the root logger. Safe to call repeatedly.

    `CLINICIAN_LOG_LEVEL` overrides the argument, so an operator can raise the
    level on a running deployment without a code change. `CLINICIAN_LOG_FORMAT`
    accepts `plain` for local work, where a human is reading the terminal
    rather than a machine reading a file.
    """
    global _CONFIGURED
    with _LOCK:
        if _CONFIGURED and not force:
            return
        chosen = (os.environ.get("CLINICIAN_LOG_LEVEL") or level or DEFAULT_LEVEL).lower()
        if chosen not in LEVELS:
            chosen = DEFAULT_LEVEL

        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

        handler = logging.StreamHandler(stream or sys.stderr)
        if os.environ.get("CLINICIAN_LOG_FORMAT", "").lower() == "plain":
            handler.setFormatter(logging.Formatter("  %(levelname)-7s %(name)s %(message)s"))
        else:
            handler.setFormatter(JSONFormatter())
        root.addHandler(handler)
        root.addHandler(TALLY)
        root.setLevel(getattr(logging, chosen.upper()))
        _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """A logger that writes structured lines, configuring on first use.

    Configuring here rather than only at a main() means a library caller gets
    structured output too, instead of logging into the void because nobody
    installed a handler.
    """
    configure()
    return logging.getLogger(name)


def errors() -> dict[str, Any]:
    """What has gone wrong in this process, for /health."""
    return TALLY.summary()
