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
    """What this patient's numbers must be below, whatever those numbers are.

    Was two floats named sbp_lt and dbp_lt. That shape survived exactly as long
    as there was one pathway: adding a second, whose target is a single HbA1c,
    made it obvious that the engine had a blood pressure baked into its idea of
    a target. Thresholds are now read from any `<code>_lt` key in the pack, so a
    pathway declares what it measures and the engine does not need to know.
    """

    group: str
    thresholds: dict[str, float]
    citation: str

    def below(self, code: str) -> float | None:
        return self.thresholds.get(code)

    def describe(self, units: dict[str, str] | None = None) -> str:
        units = units or {}
        return ", ".join(
            f"{code} below {value:g}{(' ' + units[code]) if code in units else ''}"
            for code, value in sorted(self.thresholds.items())
        )


@dataclass(frozen=True)
class TargetResolution:
    target: ResolvedTarget | None
    blocked_group: str | None = None
    reason: str | None = None

    @property
    def defined(self) -> bool:
        return self.target is not None


def thresholds(row: dict[str, Any]) -> dict[str, float]:
    """Every `<code>_lt` key in a target row, as {code: value}.

    A naming convention rather than a schema, deliberately: a pathway adds a
    measurement by naming it, with no change here.
    """
    found = {
        key[:-3]: float(value)
        for key, value in row.items()
        if key.endswith("_lt") and isinstance(value, (int, float))
    }
    if not found:
        raise ValueError(f"target {row.get('group')!r} declares no <code>_lt threshold")
    return found


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
                    thresholds=thresholds(row),
                    citation=row["citation"],
                )
            )

    return TargetResolution(
        target=None,
        blocked_group=None,
        reason="No target rule matched this patient.",
    )
