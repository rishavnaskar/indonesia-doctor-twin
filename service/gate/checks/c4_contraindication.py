"""Check 4 — contraindication against this patient's own recorded conditions.

Not against a generic profile. The difference matters: a drug that is fine for
the population and wrong for this person is precisely the error a busy clinician
is most likely to wave through.
"""

from __future__ import annotations

from service.gate.regimen import resulting_regimen
from service.gate.types import Finding, GateContext, Severity

NUMBER = 4
NAME = "contraindication"

# One line a clinician can read. Lives with the check rather than in the
# surface that displays it, so the two cannot drift apart.
TITLE = 'Contraindications'
DESCRIPTION = (
    'Is any proposed drug one this specific patient must not receive, given their allergies, intolerances and conditions?'
)


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []
    rules, state = ctx.rules, ctx.state
    regimen = resulting_regimen(state, ctx.proposal)

    for rule in rules.interactions:
        if rule.get("type") != "forbidden_in_state":
            continue

        flag = rule.get("state_flag")
        if not state.flags.get(flag, False):
            continue

        applies = set(rule.get("applies_to_classes", []))
        offending = sorted(
            d.molecule for d in regimen.values() if rules.drug_class_of(d.molecule) in applies
        )
        if offending:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK
                    if rule.get("severity") == "block"
                    else Severity.WARN,
                    message=f"{rule['message'].strip()} Present: {', '.join(offending)}.",
                    rule_id=rule.get("id"),
                    citation=rule.get("citation"),
                )
            )

    return findings
