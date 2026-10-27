"""The HTTP surface: routes, the background build, and one interactive run.

Split out of `__main__.py`, which is now argument parsing and nothing else.

Two things here are load-bearing rather than incidental.

**The build is a background job.** Rebuilding per request was the original
design, so that editing a pack and reloading showed the rules move. With a real
model behind the router that turned every browser request, including the one
Safari makes for a favicon, into another full set of model calls, serialised
behind a single-threaded server. Observed: twelve minutes to first paint. So:
build once, reuse, rebuild only when asked, and answer immediately with a page
that says what is happening.

**Progress is read from the workflow, not animated.** A caller that cannot say
which phase it is in can only report "working", which is also what a hung
process reports. Each patient's real step comes from the workflow's own
callback.
"""

from __future__ import annotations

import html as html_lib
import http.server
import json
import socketserver
import threading
import time
import webbrowser

from service import __version__
from service.logging import get_logger
from tools.demo import templates
from tools.demo.clinic import clinic_page
from tools.demo.health import health
from tools.demo.render import render
from tools.demo.run import collect, compare_sites, run_patients, vocabulary
from tools.live import load_env

log = get_logger(__name__)

_JOBS: dict[str, RunJob] = {}


def _router_for(args, live: bool):
    """A model-backed router, or None for the reference reasoner."""
    if not live:
        return None
    load_env()
    from service.router.router import router_with_model

    return router_with_model(
        args.model, provider=args.provider, samples=args.samples,
        critic=args.critic, use_tools=args.tools, shadow=args.shadow,
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
        log.info("clinic.run.started",
                 extra={"patients": len(self.patients), "site_id": self.site_id,
                        "live": bool(self.live)})
        try:
            router = _router_for(self.args, self.live)

            def on_step(index, name):
                with self.lock:
                    self.steps[index] = name

            def on_progress(index, total, title, outcome):
                with self.lock:
                    self.done[index] = str(outcome)
                    self.steps.pop(index, None)
                log.info("clinic.run.visit",
                         extra={"index": index, "total": total, "outcome": str(outcome)})

            result = run_patients(
                self.patients, site_id=self.site_id, pack_id=self.args.pack,
                router=router, on_progress=on_progress, on_step=on_step,
            )
            with self.lock:
                self.result = result
            log.info("clinic.run.finished",
                     extra={"patients": len(self.patients), "site_id": self.site_id,
                            "declined": result.get("declined"),
                            "elapsed_s": round(time.time() - self.started_at, 1)})
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"
            log.error("clinic.run.failed", exc_info=True,
                      extra={"site_id": self.site_id, "live": bool(self.live)})

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
        log.info("scenario.finished",
                 extra={"done": done, "total": total, "title": title,
                        "outcome": str(outcome)})

    def _run(self) -> None:
        log.info("build.started", extra={"pack": self.args.pack,
                                         "live": bool(self.args.live)})
        try:
            router = _router_for(self.args, bool(self.args.live))
            data = collect(self.args.pack, router=router, on_progress=self._note)
            page = render(data)
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"
            log.error("build.failed", exc_info=True, extra={"pack": self.args.pack})
            return
        with self.lock:
            self.html = page
        log.info("build.ready", extra={"pack": self.args.pack,
                                       "elapsed_s": round(time.time() - self.started_at, 1)})

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


def make_handler(args, build: Build):
    """The request handler, closed over this process's arguments and build."""

    class Handler(http.server.BaseHTTPRequestHandler):
        # HEAD sets this, so the routing below runs unchanged and only the body
        # is withheld. See do_HEAD.
        head_only = False

        def _send(self, body: bytes, content_type: str, code: int = 200) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if not self.head_only:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser hung up; nothing to report

        def _json(self, payload: dict, code: int = 200) -> None:
            self._send(json.dumps(payload).encode("utf-8"), "application/json", code)

        def _router(self, live: bool):
            return _router_for(args, live)

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": f"could not read the request: {exc}"}, 400)
                return

            try:
                if path == "/api/generate":
                    from tools.demo.patients import generate

                    self._json({"patients": generate(
                        int(body.get("n", 3)),
                        seed=int(body.get("seed", 0)),
                        profile=str(body.get("profile", "clean")),
                    )})
                    return

                if path == "/api/compare":
                    patients = body.get("patients") or []
                    if not patients:
                        self._json({"error": "no patients to compare"}, 400)
                        return
                    self._json(compare_sites(
                        patients, pack_id=args.pack,
                        router=self._router(bool(body.get("live"))),
                    ))
                    return

                if path == "/api/reset":
                    # Destroys the audit trail. Distinct from /api/history/clear,
                    # which deletes nothing and only moves the page's start
                    # marker forward. Guarded rather than hidden: a button the
                    # server refuses is better than a button that is not there,
                    # because the refusal says why.
                    from tools.demo.run import reset_allowed, reset_everything

                    if not reset_allowed():
                        self._json({"error": "Reset is switched off on this "
                                             "deployment. Set CLINICIAN_ALLOW_RESET=1 "
                                             "to enable it."}, 403)
                        return
                    if body.get("confirm") != "DELETE":
                        self._json({"error": "confirmation missing"}, 400)
                        return
                    counts = reset_everything()
                    log.warning("store.reset", extra={"destroyed": counts})
                    build.start()  # the scripted page was built from what just went
                    self._json({"destroyed": counts})
                    return

                if path == "/api/history/clear":
                    from tools.demo.run import clear_clinic_history

                    self._json({"cleared_at": clear_clinic_history()})
                    return

                if path == "/api/run":
                    patients = body.get("patients") or []
                    if not patients:
                        self._json({"error": "no patients to run"}, 400)
                        return
                    job_id = f"j{len(_JOBS) + 1}-{int(time.time() * 1000) % 100000}"
                    _JOBS[job_id] = RunJob(
                        patients, str(body.get("site_id", "SITE-A")),
                        bool(body.get("live")), args,
                    )
                    self._json({"job_id": job_id})
                    return
            except Exception as exc:  # noqa: BLE001
                # Including ResidencyError, which is the guard doing its job and
                # therefore belongs on screen with its own words rather than as
                # a 500 the browser renders as "something went wrong".
                log.warning("request.refused",
                            extra={"path": path, "error": type(exc).__name__,
                                   "detail": str(exc)[:200]})
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)
                return

            self._json({"error": "not found"}, 404)

        def do_HEAD(self):
            """Same status and headers as GET, no body.

            Without this, BaseHTTPRequestHandler answers every HEAD with 501.
            That is not a cosmetic gap: health checks, uptime monitors and
            proxies routinely probe with HEAD, and a 501 reads as unhealthy,
            which is a restart, and then another, with the application working
            perfectly the entire time.

            Routing is not duplicated. The GET handler runs exactly as it would
            otherwise and `_send` withholds the body, so the two can never
            disagree about what a path returns.
            """
            self.head_only = True
            try:
                self.do_GET()
            finally:
                self.head_only = False

        def do_GET(self):
            path = self.path.split("?", 1)[0]

            # Anything that is not the page must never trigger a rebuild. A
            # favicon request used to cost a full set of model calls.
            if path == "/favicon.ico":
                self._send(b"", "image/x-icon", 204)
                return
            if path in ("/health", "/healthz"):
                # Cheap, side-effect free, and the only route a load balancer
                # or an uptime monitor is expected to call. It never triggers a
                # build: a probe that starts work is a probe that can bring a
                # deployment down by being polled.
                report, code = health(args, build)
                self._json(report, code)
                return
            if path == "/clinic":
                self._send(clinic_page().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/sites":
                # Built per request rather than cached with the scripted page:
                # it reads the pack and nothing else, so it costs a file read
                # and can never be stale against an edited guideline.
                from tools.demo.run import sites_view
                from tools.demo.sites import render_sites

                self._send(render_sites(sites_view(args.pack)).encode("utf-8"),
                           "text/html; charset=utf-8")
                return
            if path == "/api/sites":
                from tools.demo.run import sites_view

                self._json(sites_view(args.pack))
                return
            if path.startswith("/api/job"):
                job_id = ""
                if "?" in self.path:
                    from urllib.parse import parse_qs

                    job_id = (parse_qs(self.path.split("?", 1)[1]).get("id") or [""])[0]
                job = _JOBS.get(job_id)
                if job is None:
                    self._json({"error": "unknown job"}, 404)
                else:
                    self._json(job.status())
                return
            if path == "/api/vocabulary":
                self._json(vocabulary(args.pack))
                return
            if path == "/api/history":
                from tools.demo.run import clinic_history, store

                self._json({
                    "visits": clinic_history(),
                    "backend": store().backend,
                    "location": store().summary()["location"],
                })
                return
            if path == "/status":
                self._send(json.dumps(build.status()).encode(), "application/json")
                return
            if path == "/rerun":
                build.start()
                self._send(templates.load("building.html").encode(),
                           "text/html; charset=utf-8")
                return
            if path != "/":
                self._send(b"not found", "text/plain", 404)
                return

            status = build.status()
            if status["error"]:
                self._send(
                    f"<pre>{html_lib.escape(status['error'])}</pre>".encode(),
                    "text/html; charset=utf-8", 500,
                )
            elif status["ready"]:
                self._send(build.html.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(templates.load("building.html").encode(),
                           "text/html; charset=utf-8")

        def log_message(self, fmt, *a):
            # The stdlib writes an unstructured line straight to stderr, which
            # would interleave with the JSON. Demoted to debug and given the
            # same shape as everything else.
            log.debug("http.request", extra={"client": self.address_string(),
                                             "line": fmt % a})

    return Handler


class _Server(socketserver.ThreadingTCPServer):
    """Threaded, so polling /status is not queued behind anything."""

    allow_reuse_address = True
    daemon_threads = True


def serve(args) -> int:
    """Bind, announce, and serve until interrupted."""
    build = Build(args)
    build.start()

    try:
        server = _Server((args.host, args.port), make_handler(args, build))
    except OSError as exc:
        # Almost always a previous run still serving, or a second checkout. A
        # stack trace ending in "Address already in use" underneath a `make`
        # that has just spent two minutes passing every gate reads as though
        # something broke, which is the opposite of what happened.
        print(f"\n  Port {args.port} is already in use.\n")
        print("  Something is already serving there, usually a previous run of")
        print("  this. Stop it, or pick another port:\n")
        print(f"      make PORT={args.port + 1}\n")
        print(f"  ({type(exc).__name__}: {exc})\n")
        log.error("server.bind_failed", extra={"port": args.port,
                                               "error": type(exc).__name__})
        return 1

    with server as httpd:
        url = f"http://{args.host}:{args.port}/"
        log.info("server.listening", extra={"host": args.host, "port": args.port,
                                            "pack": args.pack, "live": bool(args.live),
                                            "version": __version__})
        print(f"\n  Serving the clinician surface at {url}")
        if args.host in ("127.0.0.1", "localhost"):
            print("  Bound to localhost only. The page answers straight away and shows")
            print("  progress while the scenarios run.")
        else:
            print(f"  Bound to {args.host}, reachable from outside this machine.")
            print("  Synthetic records only: the residency guard refuses to send")
            print("  anything else to a hosted model.")
        if args.live:
            print("  Live mode: one model call per scenario, built once and reused.")
        print(f"  Build your own patients at {url}clinic")
        print(f"  Health and store status at  {url}health")
        print("  Visit /rerun to run the scripted scenarios again.  Ctrl-C to stop.\n")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("server.stopped")
            print("\n  stopped.\n")
    return 0
