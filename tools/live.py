"""Run real encounters through a real model.

    python -m tools.live --n 5
    python -m tools.live --n 5 --model anthropic/claude-sonnet-5

Every run costs money, so the default is small and the count is explicit.
Synthetic patients only — the residency guard refuses anything else, and it
refuses before the request is built rather than after.

What this is actually testing is not the model's medical knowledge. It is
whether the contract holds when something non-deterministic is placed behind
it: does the output parse, does the gate still catch bad drafts, does anything
reach a clinician that should not have. A model that scores badly here is a
finding. A model that scores well here has proved the plumbing, not its
medicine.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from datagen.synthetic import make_patient
from service.emit.queue import OutboundQueue
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.reason.parse import ProposalParseError
from service.router.router import router_with_model
from service.signing import AuditLog, Signer

RULE = "─" * 74


def load_env(path: Path = Path(".env")) -> None:
    """Minimal .env reader. No dependency, no export to the shell."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run encounters through a real model.")
    parser.add_argument("--n", type=int, default=5, help="encounters (each one API call)")
    parser.add_argument("--model", default=None, help="model slug")
    parser.add_argument("--site", default="SITE-A")
    parser.add_argument("--show-prompt", action="store_true")
    args = parser.parse_args()

    load_env()

    rules = load_pack("id")
    site = rules.sites[args.site]
    router = router_with_model(args.model)
    backend = router.get("model").backend
    queue = OutboundQueue()
    now = datetime(2026, 8, 29, 10, 0)

    print(f"\n{RULE}\n  Live run — {backend.version()} — {args.n} encounters at {args.site}")
    print(f"  Synthetic patients only. The residency guard enforces it.\n{RULE}")

    if args.show_prompt:
        # Inspecting the prompt costs nothing and needs no credentials.
        from service.reason import prompt as prompt_module
        from service.rules.predicates import Context
        from service.rules.targets import resolve_target

        state = make_patient(900, controlled=False)
        target = resolve_target(rules.guideline, Context(state)).target
        print("\n--- system ---\n" + prompt_module.system_prompt())
        print("\n--- user (truncated) ---")
        print(prompt_module.build_user_prompt(state, rules, site, target)[:1500] + "\n...")
        return 0

    if not os.environ.get("OPENROUTER_API_KEY"):
        print(
            "\n  OPENROUTER_API_KEY is not set.\n"
            "  Put it in .env (already gitignored):\n\n"
            "      OPENROUTER_API_KEY=sk-or-...\n"
        )
        return 2

    tally: dict[str, int] = {}
    parse_failures = 0

    for index in range(args.n):
        state = make_patient(900 + index, controlled=(index % 2 == 0))
        label = "controlled" if index % 2 == 0 else "uncontrolled"
        try:
            result = run_encounter(
                state, rules, site, router, InMemoryRuntime(),
                thread_id=f"LIVE-{index}",
                signer=Signer(site["practitioners"][0]["practitioner_id"], True),
                audit=AuditLog(), now=now, queue=queue,
            )
        except ProposalParseError as exc:
            parse_failures += 1
            tally["parse_failure"] = tally.get("parse_failure", 0) + 1
            print(f"\n  [{index}] {label:12s} -> PARSE FAILURE (correctly not retried)")
            print(f"      {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"\n  [{index}] {label:12s} -> ERROR {type(exc).__name__}: {exc}")
            tally["error"] = tally.get("error", 0) + 1
            continue

        tally[result.outcome.value] = tally.get(result.outcome.value, 0) + 1
        print(f"\n  [{index}] {label:12s} -> {result.outcome.value.upper()}")

        if result.proposal is not None:
            proposal = result.proposal
            print(f"      draft: {proposal.recommendation.value}, "
                  f"confidence {proposal.confidence:.2f}")
            for change in proposal.medication_changes:
                print(f"             {change.action.value} {change.molecule} "
                      f"{change.mg_per_dose:g} mg x{change.doses_per_day}")
        if result.decision and result.decision.blocking:
            for reason in result.decision.reasons():
                print(f"      gate:  {reason}")
        if result.outcome is Outcome.COMMITTED and result.claim:
            print(f"      coded: {', '.join(result.claim.codes)}")

    print(f"\n{RULE}")
    print("  " + " · ".join(f"{k}: {v}" for k, v in sorted(tally.items())))
    print(f"  queued for submission: {len(queue)}")
    if parse_failures:
        print(f"  {parse_failures} response(s) did not parse. That is a gate failure by")
        print("  design, not a retry — a malformed clinical output is not made correct")
        print("  by asking again.")
    print(f"{RULE}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
