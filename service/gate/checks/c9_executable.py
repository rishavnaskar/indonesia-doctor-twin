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

from datetime import date

from service.contracts.proposal import ChangeAction
from service.gate.messages import localise
from service.gate.types import Finding, GateContext, Severity

NUMBER = 9
NAME = "executable_here"

# One line a clinician can read. Lives with the check rather than in the
# surface that displays it, so the two cannot drift apart.
TITLE = 'Executable here'
DESCRIPTION = (
    'Can this hospital actually carry out this plan today: is the drug in stock and the test available on site?'
)

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
                    message_local=localise(ctx.rules, "not_stocked",
                                          molecule=change.molecule, site_id=site_id),
                    rule_id="not_stocked",
                    converts_to_referral=True,
                )
            )

    # Two different failures, deliberately not merged.
    #
    # A known test this site cannot run is a referral: the plan is right, the
    # place is wrong. An unrecognised value is neither — it means the proposal
    # put something in this field that is not an orderable investigation, and
    # reporting that as "not available at SITE-A" states something false about
    # the site. It is a malformed proposal, so it blocks without converting to a
    # referral: there is nowhere to refer to.
    # Permenkes-style operational evidence: naming a service is not the same as
    # delivering it. A capability listed but never exercised is the stale-
    # registry failure (A13, unverified) waiting to happen, and a confidently
    # wrong "yes, we run that" is worse than no check at all.
    #
    # This warns rather than blocks. The plan may well be right and the test may
    # well happen — the registry is what is doubtful, not the medicine — so the
    # clinician gets a line and keeps the draft. Blocking on a records problem
    # would deny care over paperwork.
    evidence = {row.get("service"): row for row in (site.get("evidence_ref") or [])}
    max_age = (getattr(ctx.rules, "evidence_policy", {}) or {}).get("max_age_days")
    today = ctx.state.as_of if isinstance(getattr(ctx.state, "as_of", None), date) else None

    def unevidenced(code: str) -> str | None:
        row = evidence.get(code)
        if row is None:
            return "no delivery evidence on file"
        last = row.get("last_performed")
        if not last:
            return "listed but never recorded as performed"
        if max_age and today:
            try:
                age = (today - date.fromisoformat(str(last))).days
            except ValueError:
                return f"unreadable evidence date {last!r}"
            if age > max_age:
                return f"last performed {age} days ago, beyond the {max_age}-day policy"
        return None

    catalogue = getattr(ctx.rules, "investigations", {}) or {}
    for investigation in ctx.proposal.investigations:
        if investigation not in catalogue:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{investigation!r} is not a recognised investigation code. "
                        "This field takes codes from the catalogue; monitoring "
                        "intent and intervals belong in the follow-up fields."
                    ),
                    rule_id="unrecognised_investigation",
                    converts_to_referral=False,
                )
            )
        elif investigation not in labs:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{catalogue[investigation]} ({investigation}) is not available "
                        f"at {site_id} (capability as of {as_of}). "
                        "This is a referral, not an order."
                    ),
                    message_local=localise(ctx.rules, "test_unavailable",
                                          label=catalogue[investigation], site_id=site_id),
                    rule_id="test_unavailable",
                    converts_to_referral=True,
                )
            )
        else:
            reason = unevidenced(investigation)
            if reason:
                findings.append(
                    Finding(
                        check=NUMBER,
                        check_name=NAME,
                        severity=Severity.WARN,
                        message=(
                            f"{site_id} lists {catalogue[investigation]} "
                            f"({investigation}) but {reason}. The order may not be "
                            "deliverable in practice."
                        ),
                        rule_id="capability_unevidenced",
                        citation=(getattr(ctx.rules, "evidence_policy", {}) or {}).get("citation"),
                    )
                )

    return findings
