"""The gate engine.

Runs the nine checks and decides one thing: does the clinician see this
proposal at all?

Two properties worth stating, because both are deliberate and both look like
bugs to someone who has not read the spec:

  1. **It fails toward silence.** On any blocking finding the proposal does not
     render. The clinician sees the encounter exactly as if the assistant had
     said nothing, plus a quiet log entry. A wrong draft costs more than no
     draft, in a setting where the reviewing doctor may have nobody to ask.

  2. **A crash is a block, not an exception.** If a rule is malformed, or a
     check itself raises, the encounter is blocked and the error is recorded.
     A gate that can be disabled by a bad YAML key is not a gate.
"""

from __future__ import annotations

from service.gate.checks import ALL_CHECKS
from service.gate.types import Finding, GateContext, GateDecision, Severity


def run_gate(ctx: GateContext) -> GateDecision:
    findings: list[Finding] = []

    for check in ALL_CHECKS:
        try:
            findings.extend(check.run(ctx))
        except Exception as exc:  # noqa: BLE001 - deliberate: fail closed, never open
            findings.append(
                Finding(
                    check=check.NUMBER,
                    check_name=check.NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"Check {check.NUMBER} ({check.NAME}) could not be evaluated: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    rule_id="check_error",
                )
            )

    return GateDecision(findings=findings)
