"""Plan concordance — SPEC-V1 §8.2, the twin-fidelity number.

Of the decisions a good doctor actually made on these visits, what fraction did
the system's draft match? It is the honest, measurable answer to the brief's own
phrase, and the only metric here that speaks the interviewer's language.

Three things about it are deliberate and easy to get wrong.

**It is reported, never gated.** A system tuned to maximise agreement with
historical practice would also reproduce historical mistakes, which is exactly
what the Kenya deployment existed to catch. The clinical lead sets a bar before
assist mode, and not before.

**Abstention is not disagreement.** A draft the gate refused never reached the
clinician, so it cannot be concordant or discordant with anything — it is a
third category. Folding abstentions into the denominator would let a system look
worse by being appropriately careful, or better by abstaining on everything hard.
They are counted separately.

**It can only be measured on Set C.** Real retrospective visits, blind-scored by
Indonesian physicians. Running it against decisions our own reference reasoner
produced from the same guideline the system checks against measures nothing at
all: it is a rule engine agreeing with itself. That mode exists here only to
prove the arithmetic works, and it says so loudly every time it runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from service.gate import GateContext, run_gate
from service.packs.loader import load_pack
from service.rules.eligibility import check_eligibility
from service.rules.predicates import Context


@dataclass
class Case:
    """One adjudicated visit."""

    patient: dict[str, Any]
    # What the physicians agreed the right decision was. The label, not our
    # output.
    adjudicated: str
    adjudicated_molecule: str | None = None
    note: str = ""


@dataclass
class Concordance:
    matched: int = 0
    differed: int = 0
    abstained: int = 0
    out_of_scope: int = 0
    disagreements: list[tuple[str, str]] = field(default_factory=list)
    source: str = "unknown"
    circular: bool = True

    # Split by whether the drafter's own samples agreed, when it was sampled
    # more than once. This is the only way to find out whether self-consistency
    # earns its cost: if unstable drafts are no likelier to be wrong than stable
    # ones, then abstaining on instability buys nothing and should be dropped.
    stable_matched: int = 0
    stable_differed: int = 0
    unstable_matched: int = 0
    unstable_differed: int = 0
    unstable_abstained: int = 0

    @property
    def compared(self) -> int:
        """Only visits where a draft actually reached the clinician."""
        return self.matched + self.differed

    @property
    def rate(self) -> float:
        return 100.0 * self.matched / self.compared if self.compared else 0.0

    @property
    def abstention_rate(self) -> float:
        total = self.compared + self.abstained
        return 100.0 * self.abstained / total if total else 0.0

    @property
    def measured_stability(self) -> bool:
        return bool(self.stable_matched or self.stable_differed
                    or self.unstable_matched or self.unstable_differed
                    or self.unstable_abstained)

    def _rate(self, matched: int, differed: int) -> float | None:
        total = matched + differed
        return 100.0 * matched / total if total else None


def load_cases(path: Path) -> list[Case]:
    """Read adjudicated cases from disk. The Set C loader.

    The file does not exist yet and that is the honest state of things: there is
    no client, no hospital and no lawful basis to touch a real record. The
    loader exists so that the day 300 adjudicated visits arrive, nothing has to
    be built to score them.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Case(
            patient=row["patient"],
            adjudicated=row["adjudicated"],
            adjudicated_molecule=row.get("adjudicated_molecule"),
            note=row.get("note", ""),
        )
        for row in raw
    ]


def score(cases: list[Case], rules=None, router=None, source: str = "unknown",
          circular: bool = True) -> Concordance:
    from service.reason import reference
    from tools.demo.patients import from_wire

    rules = rules or load_pack("id")
    propose = router.propose if router is not None else (
        lambda state, rs, site=None: reference.propose(state, rs, site)
    )
    site = rules.sites["SITE-A"]
    result = Concordance(source=source, circular=circular)

    for case in cases:
        state = from_wire(case.patient)

        if not check_eligibility(rules.guideline, Context(state)).eligible:
            # Never in this pathway, so there was never a draft to compare.
            result.out_of_scope += 1
            continue

        try:
            proposal = propose(state, rules, site)
        except Exception:  # noqa: BLE001 - a drafter that fails produced no draft
            result.abstained += 1
            continue

        decision = run_gate(
            GateContext(state=state, proposal=proposal, rules=rules, site=site)
        )
        stable = proposal.agreement is None or proposal.agreement >= 1.0

        if not decision.rendered:
            result.abstained += 1
            if not stable:
                result.unstable_abstained += 1
            continue

        ours = proposal.recommendation.value
        matched = ours == case.adjudicated
        if matched:
            result.matched += 1
        else:
            result.differed += 1
            result.disagreements.append((case.adjudicated, ours))

        if proposal.agreement is not None:
            if stable and matched:
                result.stable_matched += 1
            elif stable:
                result.stable_differed += 1
            elif matched:
                result.unstable_matched += 1
            else:
                result.unstable_differed += 1

    return result


def report(result: Concordance) -> str:
    lines = [
        "",
        "Plan concordance — SPEC-V1 §8.2",
        "=" * 64,
        f"  Source                       {result.source}",
        f"  Drafts that reached a doctor {result.compared}",
        f"  Matched the adjudication     {result.matched}",
        f"  Differed                     {result.differed}",
        f"  Concordance                  {result.rate:.1f}%   (reported, not gated)",
        "",
        f"  Abstained (no draft shown)   {result.abstained}  "
        f"({result.abstention_rate:.1f}% of in-scope visits)",
        f"  Out of this pathway          {result.out_of_scope}",
    ]

    if result.measured_stability:
        stable = result._rate(result.stable_matched, result.stable_differed)
        unstable = result._rate(result.unstable_matched, result.unstable_differed)
        lines.append("")
        lines.append("  Does instability predict error? (self-consistency's whole case)")
        lines.append(
            f"    samples agreed      {result.stable_matched + result.stable_differed:>3} drafts"
            + (f"   {stable:.1f}% concordant" if stable is not None else "   —")
        )
        lines.append(
            f"    samples disagreed   {result.unstable_matched + result.unstable_differed:>3} drafts"
            + (f"   {unstable:.1f}% concordant" if unstable is not None else "   —")
        )
        lines.append(
            f"    disagreed, abstained {result.unstable_abstained:>2} drafts   "
            "(never reached a doctor)"
        )
        if stable is not None and unstable is not None and unstable >= stable:
            lines.append("")
            lines.append("    On this run instability did NOT predict error. Self-consistency")
            lines.append("    is costing abstentions and buying nothing measurable. That is a")
            lines.append("    reason to drop it, not to keep it because it sounds rigorous.")

    if result.disagreements:
        tally: dict[tuple[str, str], int] = {}
        for pair in result.disagreements:
            tally[pair] = tally.get(pair, 0) + 1
        lines.append("")
        lines.append("  Where it differed — doctor said / we drafted:")
        for (theirs, ours), count in sorted(tally.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {theirs:<14} -> {ours:<14} x{count}")

    lines.append("")
    if result.circular:
        lines.append("  THIS NUMBER IS NOT EVIDENCE. The labels were produced by the same")
        lines.append("  rule engine, from the same guideline the gate checks against, so")
        lines.append("  the run measures a rule engine agreeing with itself. It is here to")
        lines.append("  prove the arithmetic, and for no other reason.")
    lines.append("  Abstentions are excluded from the denominator on purpose: a draft the")
    lines.append("  gate refused never reached a clinician, so it can be neither")
    lines.append("  concordant nor discordant. Folding them in would let a system look")
    lines.append("  better by abstaining on everything difficult.")
    lines.append("")
    lines.append("  Real concordance needs Set C: 300 retrospective visits, blind-scored")
    lines.append("  by Indonesian physicians. Until then the bar stays unset, by design —")
    lines.append("  a system tuned to agree with historical practice reproduces historical")
    lines.append("  mistakes.")
    lines.append("=" * 64)
    return "\n".join(lines)
