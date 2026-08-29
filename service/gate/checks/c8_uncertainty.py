"""Check 8 — the uncertainty floor.

Below a calibrated confidence the system abstains and escalates rather than
producing a low-confidence plan. The floor is a clinical risk decision, not a
modelling one, so it lives in the pack where changing it is a reviewed data
change.

Worth stating plainly: a model's self-reported confidence is weak evidence. This
check is a backstop on top of the deterministic ones, never a substitute for
them. If the only thing standing between a patient and a bad plan is the model's
own opinion of itself, the gate has already failed.
"""

from __future__ import annotations

from service.gate.types import Finding, GateContext, Severity

NUMBER = 8
NAME = "uncertainty"


def run(ctx: GateContext) -> list[Finding]:
    abstention = ctx.rules.guideline.get("abstention") or {}
    floor = abstention.get("confidence_floor")
    if floor is None:
        return [
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message="No abstention floor is configured, so confidence cannot be judged.",
                rule_id="floor_missing",
            )
        ]

    confidence = ctx.proposal.confidence
    if confidence is None or not (0.0 <= float(confidence) <= 1.0):
        return [
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message=f"Proposal confidence is missing or out of range: {confidence!r}.",
                rule_id="confidence_invalid",
            )
        ]

    if float(confidence) < float(floor):
        return [
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message=(
                    f"Confidence {float(confidence):.2f} is below the abstention floor "
                    f"of {float(floor):.2f}. Escalating rather than drafting."
                ),
                rule_id="below_floor",
            )
        ]

    return []
