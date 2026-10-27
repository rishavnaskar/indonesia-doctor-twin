"""What this process can and cannot currently do.

A health check that only proves the socket is open proves the one thing nobody
was worried about. This one asks the store whether it is reachable and which
backend answered, reads the in-process error tally, and reports the build.

In its own module so that it can be called without starting a server, which is
how the test suite exercises it.
"""

from __future__ import annotations

import time
from typing import Any

from service import __version__
from service.logging import errors as error_tally
from service.logging import get_logger

log = get_logger(__name__)

STARTED_AT = time.time()


def health(args, build) -> tuple[dict[str, Any], int]:
    """The report, and the HTTP status that should carry it.

    `build` is anything with a `.status()` dict: the live Build in the
    server, or a stand-in in a test.

    Degraded rather than down when the scripted page failed to build: the
    interactive surface and the API are still serving, and returning 503 for
    the whole process would take a working deployment out of a load balancer
    over a broken demo page.
    """
    from tools.demo.store_access import store

    report: dict[str, Any] = {
        "status": "ok",
        "version": __version__,
        "uptime_s": round(time.time() - STARTED_AT),
        "pack": args.pack,
        "live": bool(args.live),
        "build": {k: build.status()[k] for k in ("ready", "error", "done", "total")},
        "errors": error_tally(),
    }

    try:
        summary = store().summary()
        report["store"] = {
            "reachable": True,
            "backend": summary["backend"],
            "location": summary["location"],
            "encounters_checkpointed": summary["encounters_checkpointed"],
            "signatures": summary["signatures"],
            "queued": summary["queued"],
            "damaged_lines": summary["damaged_lines"],
        }
        if summary["damaged_lines"]:
            report["status"] = "degraded"
    except Exception as exc:
        log.error("health.store_unreachable", exc_info=True)
        report["store"] = {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}
        report["status"] = "unhealthy"

    if build.status()["error"] and report["status"] == "ok":
        report["status"] = "degraded"

    return report, (503 if report["status"] == "unhealthy" else 200)
