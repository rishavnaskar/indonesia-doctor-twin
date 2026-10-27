"""The two pieces of background work the surface runs.

Both exist for the same reason: a model call is slow, and a server that cannot
say which phase it is in can only report "working", which is also what a hung
process reports.

`Build` produces the scripted page once and reuses it. Rebuilding per request
was the original design, so that editing a pack and reloading showed the rules
move. With a real model behind the router that turned every browser request,
including the one Safari makes for a favicon, into another full set of model
calls, serialised behind a single-threaded server. Observed: twelve minutes to
first paint.

`RunJob` is one interactive run, watched while it happens. Each patient's real
step comes from the workflow's own callback rather than from an animation of
what usually happens.
"""

from __future__ import annotations

import threading
import time

from service.logging import get_logger
from tools.demo.render import render
from tools.demo.run import run_patients
from tools.demo.scripted import collect
from tools.live import load_env

log = get_logger(__name__)


def router_for(args, live: bool):
    """A model-backed router, or None for the reference reasoner."""
    if not live:
        return None
    load_env()
    from service.router.router import router_with_model

    return router_with_model(
        args.model,
        provider=args.provider,
        samples=args.samples,
        critic=args.critic,
        use_tools=args.tools,
        shadow=args.shadow,
    )


class RunJob:
    """One interactive run, watched while it happens."""

    def __init__(self, patients, site_id, live, args):
        self.patients = patients
        self.site_id = site_id
        self.live = live
        self.args = args
        self.lock = threading.Lock()
        self.steps: dict[int, str] = {}
        self.done: dict[int, str] = {}
        self.result: dict | None = None
        self.error: str | None = None
        self.started_at = time.time()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        log.info(
            "clinic.run.started",
            extra={
                "patients": len(self.patients),
                "site_id": self.site_id,
                "live": bool(self.live),
            },
        )
        try:
            router = router_for(self.args, self.live)

            def on_step(index, name):
                with self.lock:
                    self.steps[index] = name

            def on_progress(index, total, title, outcome):
                with self.lock:
                    self.done[index] = str(outcome)
                    self.steps.pop(index, None)
                log.info(
                    "clinic.run.visit",
                    extra={"index": index, "total": total, "outcome": str(outcome)},
                )

            result = run_patients(
                self.patients,
                site_id=self.site_id,
                pack_id=self.args.pack,
                router=router,
                on_progress=on_progress,
                on_step=on_step,
            )
            with self.lock:
                self.result = result
            log.info(
                "clinic.run.finished",
                extra={
                    "patients": len(self.patients),
                    "site_id": self.site_id,
                    "declined": result.get("declined"),
                    "elapsed_s": round(time.time() - self.started_at, 1),
                },
            )
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"
            log.error(
                "clinic.run.failed",
                exc_info=True,
                extra={"site_id": self.site_id, "live": bool(self.live)},
            )

    def status(self) -> dict:
        with self.lock:
            return {
                "ready": self.result is not None,
                "error": self.error,
                "total": len(self.patients),
                "steps": {str(k): v for k, v in self.steps.items()},
                "finished": {str(k): v for k, v in self.done.items()},
                "elapsed": round(time.time() - self.started_at),
                "result": self.result,
            }


class Build:
    """One run of the scenarios, built once and reused."""

    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self.html: str | None = None
        self.error: str | None = None
        self.progress: list[dict] = []
        self.done = 0
        self.total = 0
        self.started_at = 0.0
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.html = None
            self.error = None
            self.progress = []
            self.done = 0
            self.total = 0
            self.started_at = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _note(self, done, total, title, outcome) -> None:
        with self.lock:
            self.done, self.total = done, total
            self.progress.append({"title": title, "outcome": str(outcome)})
        log.info(
            "scenario.finished",
            extra={"done": done, "total": total, "title": title, "outcome": str(outcome)},
        )

    def _run(self) -> None:
        log.info("build.started", extra={"pack": self.args.pack, "live": bool(self.args.live)})
        try:
            router = router_for(self.args, bool(self.args.live))
            data = collect(self.args.pack, router=router, on_progress=self._note)
            page = render(data)
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"
            log.error("build.failed", exc_info=True, extra={"pack": self.args.pack})
            return
        with self.lock:
            self.html = page
        log.info(
            "build.ready",
            extra={"pack": self.args.pack, "elapsed_s": round(time.time() - self.started_at, 1)},
        )

    def status(self) -> dict:
        with self.lock:
            return {
                "ready": self.html is not None,
                "error": self.error,
                "done": self.done,
                "total": self.total,
                "elapsed": round(time.time() - self.started_at),
                "progress": list(self.progress),
                "live": bool(self.args.live),
            }
