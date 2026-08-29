"""Eligibility — the ELIGIBLE node of the state machine.

Runs before any model call, on structured data only. An excluded encounter
costs zero tokens, which is a nice property but not the point. The point is
that deciding "this patient is not ours" is a rules decision, and asking a
model to notice it should not be involved is strictly worse than checking.

An exclusion is not a failure. HANDOFF is a terminal state that counts as a
success: the clinician gets the encounter untouched, with a stated reason, and
no clinical content from us.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from service.rules.predicates import Context, evaluate


@dataclass(frozen=True)
class Exclusion:
    exclusion_id: str
    label: str
    reason: str


@dataclass
class EligibilityResult:
    eligible: bool
    exclusions: list[Exclusion] = field(default_factory=list)

    def handoff_message(self) -> str:
        """What the panel shows. No clinical content, ever."""
        if self.eligible:
            return ""
        reasons = "; ".join(e.label for e in self.exclusions)
        return f"Not handled by the assistant — {reasons}."


def check_eligibility(guideline: dict[str, Any], ctx: Context) -> EligibilityResult:
    hits = [
        Exclusion(
            exclusion_id=row["id"],
            label=row.get("label", row["id"]),
            reason=row.get("reason", ""),
        )
        for row in (guideline.get("exclusions") or [])
        if evaluate(row["predicate"], ctx)
    ]
    return EligibilityResult(eligible=not hits, exclusions=hits)
