"""Check 7 — is there enough information to say anything at all?

The check most systems omit, and the one that matters most in a setting where
labs are weeks old and the patient's last visit was at a different hospital.

A system that cannot decline to answer will confabulate under exactly the
conditions where confabulation is most dangerous. When this fires the output is
a *request* — "potassium and eGFR are seven months old, needed before any change
to an ACE inhibitor" — never a recommendation.
"""

from __future__ import annotations

from service.gate.regimen import resulting_regimen, touches_raas
from service.gate.types import Finding, GateContext, Severity

NUMBER = 7
NAME = "sufficiency"

# One line a clinician can read. Lives with the check rather than in the
# surface that displays it, so the two cannot drift apart.
TITLE = 'Sufficiency'
DESCRIPTION = (
    'Is there enough information to advise at all, or is a required measurement missing or too old?'
)


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []
    sufficiency = ctx.rules.guideline.get("sufficiency") or {}
    state = ctx.state

    requirements = list(sufficiency.get("always_required") or [])

    regimen = resulting_regimen(state, ctx.proposal)
    if touches_raas(regimen, ctx.rules):
        requirements += list(sufficiency.get("required_for_raas_action") or [])

    missing: list[str] = []
    for requirement in requirements:
        code = requirement["code"]
        max_age = int(requirement.get("max_age_days", 0))
        label = requirement.get("label", code)
        age = state.observation_age_days(code)
        if age is None:
            missing.append(f"{label} (absent)")
        elif age > max_age:
            missing.append(f"{label} — currently {age} days old")

    if missing:
        findings.append(
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message="Insufficient information to advise. Needed: " + "; ".join(missing),
                rule_id="insufficient_data",
            )
        )

    return findings
