"""Check 6 — citation resolution, and provenance completeness.

No source, no answer. Every clinical assertion has to resolve to a versioned
section of the corpus, or it is dropped before a human sees it.

Provenance lives here too, because an unpinned proposal is unauditable in the
same way an uncited one is unverifiable. Three pins: model, prompt template,
corpus. A regression in any of them has to be traceable to the exact output it
produced.
"""

from __future__ import annotations

from service.gate.types import Finding, GateContext, Severity

NUMBER = 6
NAME = "citations"


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []

    provenance = ctx.proposal.provenance
    if provenance is None or not provenance.complete():
        findings.append(
            Finding(
                check=NUMBER,
                check_name=NAME,
                severity=Severity.BLOCK,
                message=(
                    "Proposal provenance is incomplete. Model, prompt template and "
                    "corpus must each be pinned to a version."
                ),
                rule_id="provenance_incomplete",
            )
        )

    known = ctx.rules.citations
    for citation in sorted(ctx.proposal.citations()):
        if citation not in known:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=f"Citation {citation!r} does not resolve in the corpus.",
                    rule_id="unresolvable_citation",
                    citation=citation,
                )
            )

    # An assertion with no citation at all is the same failure wearing a
    # different hat, and it is the more common one.
    for assertion in ctx.proposal.assertions:
        if not assertion.citation:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=f"Clinical assertion carries no citation: {assertion.text!r}",
                    rule_id="uncited_assertion",
                )
            )

    return findings
