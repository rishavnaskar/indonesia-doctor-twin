"""Run the concordance metric.

    python -m tools.concordance                     # mechanism check, synthetic
    python -m tools.concordance --cases setc.json   # the real thing, when it exists

Without a case file this scores against labels our own reference reasoner
produced, which measures a rule engine agreeing with itself. That mode exists
to prove the arithmetic and says so on every run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from datagen.synthetic import make_patient
from eval.concordance import Case, load_cases, report, score
from service.packs.loader import load_pack
from service.reason import reference
from service.rules.predicates import Context
from service.rules.targets import resolve_target
from tools.demo.patients import to_wire


def _self_labelled(n: int, rules, seed0: int = 600) -> list[Case]:
    """Cases labelled by the reference reasoner. Deliberately circular."""
    site = rules.sites["SITE-A"]
    cases: list[Case] = []
    for seed in range(seed0, seed0 + n):
        state = make_patient(seed)
        state.is_synthetic = True
        try:
            label = reference.propose(state, rules, site).recommendation.value
        except Exception:  # noqa: BLE001
            continue
        cases.append(Case(patient=to_wire(state), adjudicated=label,
                          note="label from the reference reasoner"))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan concordance (SPEC-V1 §8.2).")
    parser.add_argument("--cases", help="adjudicated case file (Set C)")
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--seed", type=int, default=600,
                        help="first patient seed, so a finding can be replicated "
                             "on different cases rather than the same ones")
    parser.add_argument("--live", action="store_true", help="draft with a real model")
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
    args = parser.parse_args()

    rules = load_pack("id")

    router = None
    if args.live:
        from service.router.router import router_with_model
        from tools.live import load_env

        load_env()
        router = router_with_model(args.model, provider=args.provider,
                                   samples=args.samples, critic=args.critic, use_tools=args.tools, shadow=args.shadow)

    if args.cases:
        path = Path(args.cases)
        if not path.exists():
            print(f"\n  No such case file: {path}")
            print("  Set C is 300 real visits, blind-scored by Indonesian physicians.")
            print("  Obtaining it is a clinical and legal exercise; scoring it is this")
            print("  command. Point --cases at the file when it exists.\n")
            return 2
        cases = load_cases(path)
        circular, source = False, f"{path} ({len(cases)} adjudicated visits)"
    else:
        cases = _self_labelled(args.n, rules, args.seed)
        circular, source = True, f"self-labelled synthetic ({len(cases)} cases, seed {args.seed})"

    print(report(score(cases, rules, router=router, source=source, circular=circular)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
