"""Check 5 — formulary membership and its restrictions.

A hard set test, plus the restrictions that make this pack worth having. The
restriction that earns its keep is the ARB one: an ARB is not prescribable until
at least a month of documented ACE-inhibitor intolerance exists in this
patient's own record. No amount of model quality substitutes for that, and it is
checkable deterministically.
"""

from __future__ import annotations

from datetime import timedelta

from service.contracts.proposal import ChangeAction
from service.gate.types import Finding, GateContext, Severity

NUMBER = 5
NAME = "formulary"

_PRESCRIBING_ACTIONS = (
    ChangeAction.START,
    ChangeAction.INCREASE,
    ChangeAction.DECREASE,
    ChangeAction.CONTINUE,
)


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []
    rules, state = ctx.rules, ctx.state

    for change in ctx.proposal.medication_changes:
        if change.action not in _PRESCRIBING_ACTIONS:
            continue

        molecule = rules.molecules.get(change.molecule)
        if molecule is None:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{change.molecule} is not on the formulary for this pathway "
                        "and cannot be prescribed to a scheme patient."
                    ),
                    rule_id="not_on_formulary",
                )
            )
            continue

        for restriction in molecule.restrictions:
            finding = _check_restriction(ctx, change.molecule, restriction)
            if finding is not None:
                findings.append(finding)

    return findings


def _check_restriction(ctx: GateContext, molecule: str, restriction: dict) -> Finding | None:
    rtype = restriction.get("type")
    state = ctx.state
    message = (restriction.get("message") or "").strip()

    if rtype == "requires_documented_intolerance":
        target_class = restriction["to_drug_class"]
        min_days = int(restriction.get("min_duration_days", 0))
        cutoff = state.as_of - timedelta(days=min_days)

        qualifying = [
            i
            for i in state.intolerances
            if i.drug_class == target_class and i.documented_at <= cutoff
        ]
        if qualifying:
            return None

        recent = [i for i in state.intolerances if i.drug_class == target_class]
        if recent:
            newest = max(i.documented_at for i in recent)
            days = (state.as_of - newest).days
            detail = (
                f"the recorded intolerance is {days} days old and {min_days} are required"
            )
        else:
            detail = f"no {target_class} intolerance is documented for this patient"

        return Finding(
            check=NUMBER,
            check_name=NAME,
            severity=Severity.BLOCK,
            message=f"{molecule}: {message} Blocked because {detail}.",
            rule_id="requires_documented_intolerance",
        )

    if rtype == "requires_diagnosis":
        codes = restriction.get("any_of_codes", [])
        if any(state.has_diagnosis_prefix(c) for c in codes):
            return None
        return Finding(
            check=NUMBER,
            check_name=NAME,
            severity=Severity.BLOCK,
            message=(
                f"{molecule}: {message} Blocked because none of "
                f"{', '.join(codes)} is recorded for this patient."
            ),
            rule_id="requires_diagnosis",
        )

    if rtype == "requires_recent_labs":
        within = int(restriction.get("within_days", 90))
        missing = []
        for code in restriction.get("codes", []):
            age = state.observation_age_days(code)
            if age is None:
                missing.append(f"{code} (absent)")
            elif age > within:
                missing.append(f"{code} ({age} days old)")
        if not missing:
            return None
        return Finding(
            check=NUMBER,
            check_name=NAME,
            severity=Severity.BLOCK,
            message=f"{molecule}: {message} Missing or stale: {', '.join(missing)}.",
            rule_id="requires_recent_labs",
        )

    # An unrecognised restriction is a pack bug. Fail closed, loudly — the
    # loader validates types, so reaching here means the two drifted apart.
    raise ValueError(f"unknown restriction type {rtype!r} on {molecule}")
