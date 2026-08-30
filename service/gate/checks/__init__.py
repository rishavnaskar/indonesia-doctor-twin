"""The nine checks, in order.

Order matters for readability, not for correctness — every check runs on every
proposal and the findings are collected. We do not short-circuit on the first
failure, because a clinician reviewing a rejected draft should see everything
that was wrong with it, not just the first thing.
"""

from service.gate.checks import (
    c1_red_flags,
    c2_guideline_conformance,
    c3_drug_safety,
    c4_contraindication,
    c5_formulary,
    c6_citations,
    c7_sufficiency,
    c8_uncertainty,
    c9_executable,
)

ALL_CHECKS = (
    c1_red_flags,
    c2_guideline_conformance,
    c3_drug_safety,
    c4_contraindication,
    c5_formulary,
    c6_citations,
    c7_sufficiency,
    c8_uncertainty,
    c9_executable,
)

def catalogue() -> list[dict]:
    """The nine checks, described. For any surface that has to explain itself.

    Built from the check modules so a renamed or reworded check cannot leave a
    stale description behind on a screen someone is reading.
    """
    return [
        {
            "number": check.NUMBER,
            "name": check.NAME,
            "title": check.TITLE,
            "description": check.DESCRIPTION,
        }
        for check in ALL_CHECKS
    ]


__all__ = ["ALL_CHECKS", "catalogue"]
