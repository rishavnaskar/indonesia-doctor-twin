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
    parser.add_argument("--provider", default="openrouter",
                        choices=["anthropic", "openrouter"],
                        help="which backend (default: openrouter, which has free models)")
    parser.add_argument("--list-free", action="store_true",
                        help="list models that cost nothing right now, then exit")
    parser.add_argument("--no-thinking", action="store_true",
                        help="disable adaptive thinking (cheaper, faster)")
    parser.add_argument("--no-fallback", action="store_true",
                        help="do not fall back to another free model when one is "
                             "rate-limited; fail loudly instead")
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
    parser.add_argument("--site", default="SITE-A")
    parser.add_argument("--show-prompt", action="store_true")
    args = parser.parse_args()

    load_env()

    if args.list_free:
        from service.router.backends.hosted import list_free_models

        print("\n  Free models available right now (queried live, not hard-coded):\n")
        for model in list_free_models():
            mark = "json" if model["structured"] else "  — "
            print(f"    [{mark}] {model['id']:<52} ctx {model['context']:,}")
        print("\n  [json] = advertises structured output. Prefer those; the others")
        print("  still work, because the strict parser does not trust either.\n")
        print("  Use with: python -m tools.live --n 5 --model <id>\n")
        return 0

    rules = load_pack("id")
    site = rules.sites[args.site]
    kwargs = {}
    if args.provider == "anthropic" and args.no_thinking:
        kwargs["thinking"] = False
    if args.provider in ("openrouter", "hosted"):
        # An explicitly named model is a deliberate choice — usually an
        # experiment about that model. Silently substituting another one would
        # corrupt the experiment, so naming a model turns fallback off unless
        # nothing was named.
        if args.no_fallback or args.model:
            kwargs["fallbacks"] = ()
    router = router_with_model(args.model, provider=args.provider,
                               samples=args.samples, critic=args.critic, use_tools=args.tools, shadow=args.shadow, **kwargs)
    backend = router.get("model").backend
    queue = OutboundQueue()
    now = datetime(2026, 8, 29, 10, 0)

    print(f"\n{RULE}\n  Live run — {backend.version()} — {args.n} encounters at {args.site}")
    chain = getattr(backend, "fallbacks", ())
    if chain:
        print(f"  Falling back through: {', '.join(chain)}")
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

    # Credential handling differs by provider, and the difference matters.
    #
    # The Anthropic SDK resolves credentials itself, in order: ANTHROPIC_API_KEY,
    # then ANTHROPIC_AUTH_TOKEN, then an `ant auth login` profile on disk. So a
    # missing environment variable is NOT proof there are no credentials, and
    # hard-failing here would block a perfectly good CLI login. Warn, then let
    # the SDK speak for itself.
    #
    # The OpenAI-compatible backend reads the variable directly, so there the
    # check is real.
    if args.provider == "anthropic":
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            print("  No ANTHROPIC_API_KEY in the environment — trying the SDK's own")
            print("  credential chain (an `ant auth login` profile also works).\n")
    elif not os.environ.get("OPENROUTER_API_KEY"):
        print(
            "\n  OPENROUTER_API_KEY is not set.\n"
            "  Put it in .env (already gitignored):\n\n"
            "      OPENROUTER_API_KEY=sk-or-...\n"
        )
        return 2

    tally: dict[str, int] = {}
    parse_failures = 0
    requested = backend.version()

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
            name = type(exc).__name__
            if name == "TruncatedResponse":
                # Ours, not the model's. Counted separately so a config bug can
                # never be read off the scoreboard as poor model quality.
                tally["truncated"] = tally.get("truncated", 0) + 1
                print(f"\n  [{index}] {label:12s} -> TRUNCATED (our token budget)")
                print(f"      {exc}")
                continue
            if name == "RateLimited":
                tally["rate_limited"] = tally.get("rate_limited", 0) + 1
                print(f"\n  [{index}] {label:12s} -> RATE LIMITED")
                print(f"      {exc}")
                continue
            if name == "ModelRefusal":
                # Not a crash. The model declined, which routes exactly where
                # our own refusals route: the clinician sees nothing.
                tally["model_refusal"] = tally.get("model_refusal", 0) + 1
                print(f"\n  [{index}] {label:12s} -> MODEL REFUSAL (treated as abstain)")
                print(f"      {exc}")
                continue
            print(f"\n  [{index}] {label:12s} -> ERROR {name}: {exc}")
            tally["error"] = tally.get("error", 0) + 1
            continue

        tally[result.outcome.value] = tally.get(result.outcome.value, 0) + 1
        answered_by = backend.version()
        served = "" if answered_by == requested else f"  [served by {answered_by}]"
        print(f"\n  [{index}] {label:12s} -> {result.outcome.value.upper()}{served}")

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
