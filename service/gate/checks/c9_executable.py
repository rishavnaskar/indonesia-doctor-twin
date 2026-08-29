"""Check 9 — is this plan deliverable at this site, today?

The one axis on which the best published diagnostic model lost to human doctors
was the practicality of its management plans, and the reason is structural
rather than a model weakness: a doctor knows what their hospital can actually
do. A plan that prescribes a drug the pharmacy does not stock, or orders a test
that has to travel to another island, is worse than no plan — it burns the
clinician's trust, and that is how a tool quietly dies.

A failure here does not mean the plan is wrong. It means the output is a
referral rather than a recommendation, which is why these findings carry
`converts_to_referral`.

The honest caveat, carried in the panel and not buried here: the registry can go
stale (assumption A13, unverified). A confidently wrong "yes, it's in stock" is
worse than no check at all, so the registry is capped at slow-moving facts, the
`as_of` date is always shown, and a clinician override path exists.
"""

from __future__ import annotations

from service.contracts.proposal import ChangeAction
from service.gate.types import Finding, GateContext, Severity

NUMBER = 9
NAME = "executable_here"

_DISPENSING_ACTIONS = (
    ChangeAction.START,
    ChangeAction.INCREASE,
    ChangeAction.DECREASE,
    ChangeAction.CONTINUE,
)


def run(ctx: GateContext) -> list[Finding]:
    site = ctx.site
    if site is None:
        # No site record is not "everything is available". It is an unknown, and
        # an unknown must not be presented as an executable plan.
        return [
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message="No site capability record is available, so executability is unknown.",
                rule_id="site_unknown",
                converts_to_referral=True,
            )
        ]

    findings: list[Finding] = []
    stocked = set(site.get("stocked_molecules") or [])
    labs = set(site.get("labs_available") or [])
    as_of = site.get("as_of", "unknown")
    site_id = site.get("site_id", "this site")

    for change in ctx.proposal.medication_changes:
        if change.action in _DISPENSING_ACTIONS and change.molecule not in stocked:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{change.molecule} is not stocked at {site_id} "
                        f"(stock list as of {as_of}). This is a referral, not a prescription."
                    ),
                    rule_id="not_stocked",
                    converts_to_referral=True,
                )
            )

    for investigation in ctx.proposal.investigations:
        if investigation not in labs:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{investigation} is not available at {site_id} "
                        f"(capability as of {as_of}). This is a referral, not an order."
                    ),
                    rule_id="test_unavailable",
                    converts_to_referral=True,
                )
            )

    return findings
