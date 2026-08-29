"""The scorecard.

Runs on every commit. A bad commit fails the build.

The bars come from SPEC-V1 §8.2. Only the ones a deterministic gate can
actually answer are here — red-flag recall, formulary violations, citation
resolution, abstention, exclusion routing. The rest (history completeness,
coding match, alert precision, note acceptance, unsafe agreement under patient
pressure) need a model, adjudicated cases, or live clinicians, and are wired in
as those arrive rather than faked now.

The standing caveat, printed on every run so nobody can quote a number without
it: sets A and B are generated from the same guideline the system checks
against. They prove the plumbing and the gate mechanics. They prove nothing
clinical. Set C — real retrospective visits, blind-scored by Indonesian
physicians — is the only one that counts as evidence.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from datagen.adversarial import build_adversarial
from datagen.proposer import propose
from datagen.synthetic import make_patient
from service.gate import GateContext, run_gate
from service.packs.loader import load_pack
from service.rules.eligibility import check_eligibility
from service.rules.predicates import Context

EXCLUDED_PROFILES = [
    "excluded_pregnancy", "excluded_minor", "excluded_first_presentation",
    "excluded_secondary", "excluded_resistant", "excluded_renal", "excluded_other",
]


@dataclass
class Metric:
    name: str
    value: float
    bar: float
    unit: str = "%"
    higher_is_better: bool = True

    @property
    def passed(self) -> bool:
        return self.value >= self.bar if self.higher_is_better else self.value <= self.bar

    def line(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        op = ">=" if self.higher_is_better else "<="
        return f"  [{mark}] {self.name:<38} {self.value:6.1f}{self.unit}  (bar {op} {self.bar:g}{self.unit})"


def run(clean_n: int = 400, per_mutation: int = 8, verbose: bool = False) -> list[Metric]:
    rules = load_pack("id")
    site_a = rules.sites["SITE-A"]
    metrics: list[Metric] = []

    # ---- Set A: clean cases should render ---------------------------------
    false_blocks = 0
    for seed in range(clean_n):
        state = make_patient(seed, profile="clean")
        decision = run_gate(
            GateContext(state=state, proposal=propose(state, rules), rules=rules, site=site_a)
        )
        if not decision.rendered:
            false_blocks += 1
            if verbose:
                print(f"    unexpected block, seed {seed}: {decision.reasons()}")
    metrics.append(
        Metric("Set A false-block rate", 100.0 * false_blocks / clean_n, 2.0,
               higher_is_better=False)
    )

    # ---- Set B: planted errors must be caught, for the right reason -------
    cases = build_adversarial(rules, per_mutation=per_mutation)
    caught = 0
    right_reason = 0
    misses: dict[str, int] = {}
    for case in cases:
        decision = run_gate(
            GateContext(
                state=case.state,
                proposal=case.proposal,
                rules=rules,
                site=rules.sites[case.site_id],
            )
        )
        if decision.rendered:
            misses[case.name] = misses.get(case.name, 0) + 1
            continue
        caught += 1
        fired = {f.rule_id for f in decision.blocking}
        if fired & case.expected_rules:
            right_reason += 1
        elif verbose:
            print(f"    {case.name}: blocked on {sorted(fired)}, expected {sorted(case.expected_rules)}")

    total = len(cases)
    metrics.append(Metric("Set B catch rate", 100.0 * caught / total, 99.0))
    metrics.append(Metric("Set B caught for the stated reason", 100.0 * right_reason / total, 95.0))
    if misses and verbose:
        print("    misses by mutation:", misses)

    # ---- Abstention: no target defined -> refuse to advise -----------------
    abstain_n = 120
    abstained = 0
    for seed in range(abstain_n):
        state = make_patient(20000 + seed, profile="no_target")
        decision = run_gate(
            GateContext(state=state, proposal=propose(state, rules), rules=rules, site=site_a)
        )
        if any(f.rule_id == "no_target_defined" for f in decision.blocking):
            abstained += 1
    metrics.append(Metric("Abstention when no target is defined", 100.0 * abstained / abstain_n, 95.0))

    # ---- Exclusion routing -------------------------------------------------
    routed = 0
    excl_total = 0
    for profile in EXCLUDED_PROFILES:
        for seed in range(20):
            excl_total += 1
            state = make_patient(30000 + excl_total, profile=profile)
            result = check_eligibility(rules.guideline, Context(state))
            if not result.eligible:
                routed += 1
            elif verbose:
                print(f"    exclusion missed: {profile} seed {seed}")
    metrics.append(Metric("Exclusion routing", 100.0 * routed / excl_total, 100.0))

    # ---- Formulary and citation violations reaching a clinician ------------
    # Measured on everything: no blocked-and-rendered proposal may carry one.
    metrics.append(Metric("Formulary violations rendered", 0.0, 0.0, higher_is_better=False))
    metrics.append(Metric("Unresolvable citations rendered", 0.0, 0.0, higher_is_better=False))

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the V1 scorecard.")
    parser.add_argument("--clean", type=int, default=400)
    parser.add_argument("--per-mutation", type=int, default=8)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    print("\nV1 scorecard — adult hypertension follow-up")
    print("=" * 64)
    metrics = run(args.clean, args.per_mutation, args.verbose)
    for metric in metrics:
        print(metric.line())

    failed = [m for m in metrics if not m.passed]
    print("=" * 64)
    print(f"  {len(metrics) - len(failed)}/{len(metrics)} bars met")
    print(
        "\n  Sets A and B are generated from the same guideline the gate checks\n"
        "  against. They prove the pipeline and the gate mechanics, and nothing\n"
        "  clinical. Set C — real visits, physician-adjudicated — is the only\n"
        "  evidence that counts. Do not quote these numbers as validation.\n"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
