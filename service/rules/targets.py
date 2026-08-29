"""Blood-pressure target resolution.

The target is a *function* of patient attributes, not a constant. The important
behaviour here is the one that looks like a bug and is not: when a patient
belongs to a group whose target we have not extracted from the primary source,
this returns no target and the system abstains. It does **not** fall back to the
general adult value.

That is SPEC-V1 §2.2, and it is the difference between a system that says "I
don't know" and one that quietly applies the wrong threshold to a diabetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from service.rules.predicates import Context, evaluate


@dataclass(frozen=True)
class ResolvedTarget:
    group: str
    sbp_lt: float
    dbp_lt: float
    citation: str


@dataclass(frozen=True)
class TargetResolution:
    target: ResolvedTarget | None
    blocked_group: str | None = None
    reason: str | None = None

    @property
    def defined(self) -> bool:
        return self.target is not None


def resolve_target(guideline: dict[str, Any], ctx: Context) -> TargetResolution:
    # Blocking groups win first, and they win over any matching target.
    for row in guideline.get("no_target_groups", []) or []:
        if evaluate(row["predicate"], ctx):
            return TargetResolution(
                target=None,
                blocked_group=row.get("group"),
                reason=row.get("reason", "No target defined for this patient group."),
            )

    for row in guideline.get("targets", []) or []:
        if evaluate(row["predicate"], ctx):
            return TargetResolution(
                target=ResolvedTarget(
                    group=row["group"],
                    sbp_lt=float(row["sbp_lt"]),
                    dbp_lt=float(row["dbp_lt"]),
                    citation=row["citation"],
                )
            )

    return TargetResolution(
        target=None,
        blocked_group=None,
        reason="No target rule matched this patient.",
    )
