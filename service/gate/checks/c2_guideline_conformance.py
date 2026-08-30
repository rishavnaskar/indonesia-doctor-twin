"""Check 2 — guideline conformance.

Does the proposal use the target this guideline defines for *this* patient?

The interesting failure is not a wrong number. It is a confident number for a
patient whose target we never extracted — an elderly diabetic, say. There the
correct output is silence, and this check enforces it.
"""

from __future__ import annotations

from service.gate.messages import localise
from service.gate.types import Finding, GateContext, Severity
from service.rules.predicates import Context
from service.rules.targets import resolve_target

NUMBER = 2
NAME = "guideline_conformance"

# One line a clinician can read. Lives with the check rather than in the
# surface that displays it, so the two cannot drift apart.
TITLE = 'Guideline conformance'
DESCRIPTION = (
    'Does the plan match the guideline the system is allowed to act on, and is there a target it is entitled to use for this patient?'
)

_TOLERANCE = 0.001


def _describe(thresholds: dict) -> str:
    return ", ".join(f"{code} < {value:g}" for code, value in sorted(thresholds.items()))


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []
    resolution = resolve_target(ctx.rules.guideline, Context(ctx.state))

    if not resolution.defined:
        group = resolution.blocked_group or "unclassified"
        findings.append(
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message=(
                    f"No target is defined for this patient group "
                    f"({group}). {resolution.reason} The system abstains rather "
                    "than applying the general adult target."
                ),
                message_local=localise(ctx.rules, "no_target_defined", group=group),
                rule_id="no_target_defined",
            )
        )
        return findings

    target = resolution.target
    used = ctx.proposal.target_used

    if used is None:
        findings.append(
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message="The proposal states no target, so its assessment cannot be checked.",
                rule_id="target_missing",
            )
        )
        return findings

    if set(used.thresholds) != set(target.thresholds) or any(
        abs(used.thresholds[code] - value) > _TOLERANCE
        for code, value in target.thresholds.items()
    ):
        findings.append(
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message=(
                    f"The proposal used a target of {_describe(used.thresholds)}; "
                    f"the guideline gives {_describe(target.thresholds)} for "
                    f"group '{target.group}'."
                ),
                rule_id="target_mismatch",
                citation=target.citation,
            )
        )

    return findings
