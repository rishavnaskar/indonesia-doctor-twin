"""The demo surface.

    python -m tools.demo                    # serve it, open a browser
    python -m tools.demo --export demo.html # one file you can send
    python -m tools.demo --live             # run it through a real model

Serving and exporting produce the same page from the same run. The export
exists because the people who most need to see this are the least likely to
clone a repository and run make.

The server answers immediately and builds in the background. A live run makes
one model call per scenario and, on a rate-limited free tier, that can take
minutes — during which a server that simply does not respond is
indistinguishable from one that has hung. It says what it is doing instead.
"""

from __future__ import annotations

import argparse
import html as html_lib
import http.server
import json
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

from tools.demo.clinic import CLINIC_HTML
from tools.demo.render import render
from tools.demo.run import collect, compare_sites, run_patients, vocabulary
from tools.live import load_env


class RunJob:
    """One interactive run, watched while it happens.

    The model call is the slow phase, so a caller that cannot say which phase
    it is in can only report "working" — which is what a hung process reports
    too. This records the real step each patient is on, from the workflow's own
    callback, so the page shows what is actually happening rather than an
    animation of what usually happens.
    """

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
        try:
            router = None
            if self.live:
                load_env()
                from service.router.router import router_with_model

                router = router_with_model(self.args.model, provider=self.args.provider,
                                           samples=self.args.samples, critic=self.args.critic, use_tools=self.args.tools, shadow=self.args.shadow)

            def on_step(index, name):
                with self.lock:
                    self.steps[index] = name

            def on_progress(index, total, title, outcome):
                with self.lock:
                    self.done[index] = str(outcome)
                    self.steps.pop(index, None)

            result = run_patients(
                self.patients, site_id=self.site_id, pack_id=self.args.pack,
                router=router, on_progress=on_progress, on_step=on_step,
            )
            with self.lock:
                self.result = result
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"

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


_JOBS: dict[str, RunJob] = {}


class Build:
    """One run of the scenarios, built once and reused.

    Rebuilding per request was the original design, so that editing a pack and
    reloading showed the rules move. With a real model behind the router that
    turned every browser request — including the one Safari makes for a
    favicon — into another full set of model calls, serialised behind the
    single-threaded server. Observed: twelve minutes to first paint.

    So: build once, reuse, and rebuild only when explicitly asked.
    """

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
        print(f"  [{done}/{total}] {title} -> {outcome}", flush=True)

    def _run(self) -> None:
        try:
            router = None
            if self.args.live:
                load_env()
                from service.router.router import router_with_model

                router = router_with_model(self.args.model, provider=self.args.provider,
                                           samples=self.args.samples, critic=self.args.critic, use_tools=self.args.tools, shadow=self.args.shadow)
            data = collect(self.args.pack, router=router, on_progress=self._note)
            page = render(data)
        except Exception as exc:  # noqa: BLE001 - a broken pack must be visible
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"
            print(f"  build failed: {self.error}", flush=True)
            return
        with self.lock:
            self.html = page
        print(f"  ready in {time.time() - self.started_at:.0f}s", flush=True)

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


_LOADING = """<!doctype html><html><head><meta charset="utf-8">
<title>AI clinician — building</title><style>
:root{--bg:#f5f6f8;--panel:#fff;--ink:#14171a;--muted:#5f6871;--line:#dfe3e8;--accent:#1c4fd8;--code:#eef1f4}
@media (prefers-color-scheme:dark){:root{--bg:#131619;--panel:#1b1f23;--ink:#e8eaed;--muted:#9aa4ae;--line:#2b3137;--accent:#7da2ff;--code:#22272c}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:26px 30px;max-width:620px;width:92%}
h1{margin:0 0 6px;font-size:17px}
p{color:var(--muted);font-size:13.5px;margin:0 0 18px}
.bar{height:6px;background:var(--code);border-radius:4px;overflow:hidden;margin-bottom:14px}
.fill{height:100%;background:var(--accent);width:0;transition:width .4s}
li{font-size:13px;margin-bottom:5px;list-style:none}
ul{padding:0;margin:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--muted)}
.err{color:#b3261e}
</style></head><body><div class="box">
<h1>Running the scenarios</h1>
<p id="sub">Each visit is one call to a real model. On a free tier this can take a couple of
minutes, and a rate-limited model is retried before the next one is tried.</p>
<div class="bar"><div class="fill" id="fill"></div></div>
<ul id="log"></ul>
<div class="mono" id="t"></div>
</div><script>
async function tick(){
  const s = await (await fetch("/status")).json();
  if (s.ready) { location.reload(); return; }
  if (s.error) { document.getElementById("log").innerHTML =
    `<li class="err">Build failed: ${s.error}</li>`; return; }
  document.getElementById("fill").style.width = s.total ? (100*s.done/s.total)+"%" : "6%";
  document.getElementById("log").innerHTML =
    s.progress.map(p=>`<li>&#10003; ${p.title} <span class="mono">&rarr; ${p.outcome}</span></li>`).join("");
  document.getElementById("t").textContent =
    `${s.done} of ${s.total||"?"} done &middot; ${s.elapsed}s elapsed`.replace("&middot;","·");
  if (!s.live) document.getElementById("sub").textContent =
    "Running the scenarios through the rule-following reasoner. This should be quick.";
  setTimeout(tick, 700);
}
tick();
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="The clinician surface, from a real run.")
    parser.add_argument("--export", metavar="PATH", help="write a single self-contained file")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--pack", default="id")
    parser.add_argument("--live", action="store_true",
                        help="drive the scenarios with a real model instead of the "
                             "deterministic reasoner")
    parser.add_argument("--model", default=None)
    parser.add_argument("--shadow", action="store_true",
                        help="with --samples: measure agreement but do not apply "
                             "it to the confidence, so its value can be tested")
    parser.add_argument("--tools", action="store_true",
                        help="let the drafter request what it needs (read-only "
                             "lookups) instead of being handed the whole pack")
    parser.add_argument("--critic", action="store_true",
                        help="have a second model review each draft; it may only "
                             "lower the confidence, never raise it")
    parser.add_argument("--samples", type=int, default=1,
                        help="draft this many times and use the agreement between "
                             "them as the confidence, instead of the model's own "
                             "opinion of itself (costs one call per sample)")
    parser.add_argument("--provider", default="openrouter", choices=["anthropic", "openrouter"])
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    if args.export:
        router = None
        if args.live:
            load_env()
            from service.router.router import router_with_model

            router = router_with_model(args.model, provider=args.provider,
                                       samples=args.samples, critic=args.critic, use_tools=args.tools, shadow=args.shadow)

        def note(done, total, title, outcome):
            print(f"  [{done}/{total}] {title} -> {outcome}", flush=True)

        path = Path(args.export)
        path.write_text(render(collect(args.pack, router=router, on_progress=note)),
                        encoding="utf-8")
        print(f"\n  Wrote {path} ({path.stat().st_size / 1024:.0f} KB, self-contained).")
        print("  Open it anywhere, or send it to someone who will not run make.\n")
        return 0

    build = Build(args)
    build.start()

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, body: bytes, content_type: str, code: int = 200) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser hung up; nothing to report

        def _json(self, payload: dict, code: int = 200) -> None:
            self._send(json.dumps(payload).encode("utf-8"), "application/json", code)

        def _router(self, live: bool):
            if not live:
                return None
            load_env()
            from service.router.router import router_with_model

            return router_with_model(args.model, provider=args.provider,
                                     samples=args.samples, critic=args.critic, use_tools=args.tools, shadow=args.shadow)

        def do_POST(self):  # noqa: N802 - stdlib naming
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
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)
                return

            self._json({"error": "not found"}, 404)

        def do_GET(self):  # noqa: N802 - stdlib naming
            path = self.path.split("?", 1)[0]

            # Anything that is not the page must never trigger a rebuild. A
            # favicon request used to cost a full set of model calls.
            if path == "/favicon.ico":
                self._send(b"", "image/x-icon", 204)
                return
            if path == "/clinic":
                self._send(CLINIC_HTML.encode("utf-8"), "text/html; charset=utf-8")
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
            if path == "/status":
                self._send(json.dumps(build.status()).encode(), "application/json")
                return
            if path == "/rerun":
                build.start()
                self._send(_LOADING.encode(), "text/html; charset=utf-8")
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
                self._send(_LOADING.encode(), "text/html; charset=utf-8")

        def log_message(self, *a):  # quiet
            pass

    # Threaded, so polling /status is not queued behind anything.
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", args.port), Handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"\n  Serving the clinician surface at {url}")
        print("  Bound to localhost only. The page answers straight away and shows")
        print("  progress while the scenarios run.")
        if args.live:
            print("  Live mode: one model call per scenario, built once and reused.")
        print(f"  Build your own patients at {url}clinic")
        print("  Visit /rerun to run the scripted scenarios again.  Ctrl-C to stop.\n")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
