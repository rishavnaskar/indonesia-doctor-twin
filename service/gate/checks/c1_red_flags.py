"""Check 1 — red-flag rules.

Re-evaluated here against the *proposal*, not only against the state. The red
flags already ran as their own node before the model was called; this is defence
in depth. If a red flag is live at gate time, something upstream failed and the
proposal must not render regardless.

Evaluated on structured state. Never on model output.
"""

from __future__ import annotations

from service.contracts.proposal import Recommendation
from service.gate.regimen import RAAS_CLASSES, resulting_regimen
from service.gate.types import Finding, GateContext, Severity
from service.rules.predicates import Context, evaluate

NUMBER = 1
NAME = "red_flags"

# One line a clinician can read. Lives with the check rather than in the
# surface that displays it, so the two cannot drift apart.
TITLE = 'Red flags'
DESCRIPTION = (
    'Does this patient show a sign that must leave this pathway immediately — an emergency, or a symptom this pathway is not designed to handle?'
)

_ESCALATING_RECOMMENDATIONS = (Recommendation.TITRATE_UP, Recommendation.ADD_AGENT)


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []
    pctx = Context(ctx.state)

    fired = []
    for rule in ctx.rules.guideline.get("red_flags", []) or []:
        if evaluate(rule["predicate"], pctx):
            fired.append(rule)
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=rule["message"],
                    message_local=rule.get("message_local", ""),
                    rule_id=rule["id"],
                    citation=rule.get("citation"),
                )
            )

    fired_ids = {r["id"] for r in fired}

    # Over-treatment must never be answered with more treatment. This is the
    # specific inversion worth naming: the patient's pressure is too low and the
    # model has proposed raising the dose.
    if "R3" in fired_ids and ctx.proposal.recommendation in _ESCALATING_RECOMMENDATIONS:
        findings.append(
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message=(
                    "Over-treatment is flagged and the proposal increases treatment. "
                    "Only a reduction may be drafted."
                ),
                rule_id="R3-consistency",
            )
        )

    # Hyperkalaemia blocks anything acting on the renin-angiotensin system.
    if "R6" in fired_ids:
        regimen = resulting_regimen(ctx.state, ctx.proposal)
        offending = [
            d.molecule
            for d in regimen.values()
            if d.changed and ctx.rules.drug_class_of(d.molecule) in RAAS_CLASSES
        ]
        if offending:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        "Potassium is above threshold and the proposal changes a "
                        f"RAAS-acting drug ({', '.join(sorted(offending))})."
                    ),
                    rule_id="R6-consistency",
                )
            )

    return findings
