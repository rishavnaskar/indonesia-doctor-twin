"""The demo surface.

    python -m tools.demo                    # serve it, open a browser
    python -m tools.demo --export demo.html # one file you can send
    python -m tools.demo --live             # run it through a real model

Serving and exporting produce the same page from the same run. The export
exists because the people who most need to see this are the least likely to
clone a repository and run make.
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

from tools.demo.render import render
from tools.demo.run import collect
from tools.live import load_env


def _build(args) -> str:
    router = None
    if args.live:
        load_env()
        from service.router.router import router_with_model

        router = router_with_model(args.model, provider=args.provider)
    return render(collect(args.pack, router=router))


def main() -> int:
    parser = argparse.ArgumentParser(description="The clinician surface, from a real run.")
    parser.add_argument("--export", metavar="PATH", help="write a single self-contained file")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--pack", default="id")
    parser.add_argument("--live", action="store_true",
                        help="drive the scenarios with a real model instead of the "
                             "deterministic reasoner")
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default="openrouter", choices=["anthropic", "openrouter"])
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    if args.export:
        path = Path(args.export)
        path.write_text(_build(args), encoding="utf-8")
        size = path.stat().st_size / 1024
        print(f"\n  Wrote {path} ({size:.0f} KB, self-contained — no network, no CDN).")
        print("  Open it anywhere, or send it to someone who will not run make.\n")
        return 0

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib naming
            # Rebuilt per request, so editing a pack and refreshing shows the
            # change. That is also the fastest way to demonstrate that the rules
            # are data: edit the YAML, reload, watch the verdict move.
            try:
                body = _build(args).encode("utf-8")
            except Exception as exc:  # noqa: BLE001 - a broken pack should be visible
                body = f"<pre>{type(exc).__name__}: {exc}</pre>".encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The browser gave up while we were building the page — likely
                # a reload during a slow live run. Nothing to report.
                pass

        def log_message(self, *a):  # quiet
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"\n  Serving the clinician surface at {url}")
        print("  Bound to localhost only. Rebuilt on every reload, so editing a")
        print("  pack file and refreshing shows the rules moving.  Ctrl-C to stop.\n")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
