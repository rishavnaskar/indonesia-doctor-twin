"""The demo surface.

    python -m tools.demo                    # serve it, open a browser
    python -m tools.demo --export demo.html # one file you can send
    python -m tools.demo --live             # run it through a real model

Serving and exporting produce the same page from the same run. The export
exists because the people who most need to see this are the least likely to
clone a repository and run make.

This module is argument parsing. The routes, the background build and the
health check are in server.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from service.logging import configure, get_logger
from tools.demo.render import render
from tools.demo.run import collect
from tools.demo.server import serve
from tools.live import load_env

log = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="The clinician surface, from a real run.")
    parser.add_argument("--export", metavar="PATH", help="write a single self-contained file")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--pack", default="id")
    parser.add_argument(
        "--live",
        action="store_true",
        help="drive the scenarios with a real model instead of the deterministic reasoner",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--shadow",
        action="store_true",
        help="with --samples: measure agreement but do not apply "
        "it to the confidence, so its value can be tested",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="let the drafter request what it needs (read-only "
        "lookups) instead of being handed the whole pack",
    )
    parser.add_argument(
        "--critic",
        action="store_true",
        help="have a second model review each draft; it may only "
        "lower the confidence, never raise it",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="draft this many times and use the agreement between "
        "them as the confidence, instead of the model's own "
        "opinion of itself (costs one call per sample)",
    )
    parser.add_argument("--provider", default="openrouter", choices=["anthropic", "openrouter"])
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["debug", "info", "warning", "error"],
        help="structured logs go to stderr. CLINICIAN_LOG_LEVEL does "
        "the same thing, and CLINICIAN_LOG_FORMAT=plain makes "
        "them readable rather than machine-readable",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="interface to bind. Defaults to localhost; a public deployment sets HOST=0.0.0.0",
    )
    return parser


def export(args) -> int:
    """Write the whole run to one self-contained file."""
    router = None
    if args.live:
        load_env()
        from service.router.router import router_with_model

        router = router_with_model(
            args.model,
            provider=args.provider,
            samples=args.samples,
            critic=args.critic,
            use_tools=args.tools,
            shadow=args.shadow,
        )

    def note(done, total, title, outcome):
        log.info(
            "scenario.finished",
            extra={"done": done, "total": total, "title": title, "outcome": str(outcome)},
        )
        print(f"  [{done}/{total}] {title} -> {outcome}", flush=True)

    path = Path(args.export)
    path.write_text(render(collect(args.pack, router=router, on_progress=note)), encoding="utf-8")
    print(f"\n  Wrote {path} ({path.stat().st_size / 1024:.0f} KB, self-contained).")
    print("  Open it anywhere, or send it to someone who will not run make.\n")
    return 0


def platform_port(argv: list[str] | None = None) -> int | None:
    """The port a platform assigned, or None when there is none to obey.

    A platform tells the process which port to listen on, and it is not
    negotiable: bind the wrong one and the health check fails with the app
    running perfectly. --port still wins, so local use is unchanged.
    """
    if os.environ.get("PORT") and "--port" not in (argv if argv is not None else sys.argv):
        return int(os.environ["PORT"])
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure(args.log_level, force=True)

    port = platform_port(argv)
    if port is not None:
        args.port = port

    from service.packs.loader import PackError, load_pack

    try:
        load_pack(args.pack)
    except PackError as exc:
        log.error("pack.unreadable", extra={"pack": args.pack, "detail": str(exc)[:200]})
        print(f"\n  Could not load the rule pack {args.pack!r}: {exc}\n")
        return 2

    if args.export:
        return export(args)
    return serve(args)


if __name__ == "__main__":
    sys.exit(main())
