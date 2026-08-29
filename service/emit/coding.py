"""Coding — the part that pays for the company.

The hospital is paid for the codes, not for the care. A comorbidity written in
free text and never coded is care delivered and not paid for, and that is the
leak this closes.

Two boundaries, both absolute:

  * We produce diagnosis and procedure codes and hand them to the official
    grouper. We never compute a tariff and we never assign a severity level.
  * Every suggested secondary code carries the record entry that supports it.
    A code without an evidence reference is not emitted at all.

That second rule is what separates this from upcoding, and it is enforced here
rather than promised in a policy document. We are not inventing diagnoses to
reach a higher band; we are billing for diagnoses already recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CodedDiagnosis:
    code: str
    label: str
    primary: bool
    evidence_ref: str  # what in the record supports this

    def __post_init__(self) -> None:
        if not self.evidence_ref:
            raise ValueError(f"{self.code}: a code without evidence is not emittable")


@dataclass
class ClaimDraft:
    primary: CodedDiagnosis | None = None
    secondary: list[CodedDiagnosis] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        out = [self.primary.code] if self.primary else []
        return out + [d.code for d in self.secondary]


def build_claim(state, rules) -> ClaimDraft:
    """Derive a claim draft from what is actually recorded.

    Deliberately deterministic. Coding from the structured problem list is a
    lookup, not a judgement — the model's job is to surface comorbidities
    buried in narrative, and anything it surfaces still has to land in the
    record before it can be coded.
    """
    payer = rules.payer.get("coding") or {}
    capture = payer.get("comorbidity_capture") or []
    typical_primary = payer.get("typical_primary")

    draft = ClaimDraft()
    active = [d for d in state.diagnoses if d.status == "active"]

    for diagnosis in active:
        if typical_primary and diagnosis.code.upper().startswith(typical_primary.upper()):
            draft.primary = CodedDiagnosis(
                code=diagnosis.code,
                label="primary condition managed at this encounter",
                primary=True,
                evidence_ref=f"problem-list:{diagnosis.code}",
            )
            break

    for row in capture:
        prefix = row["code_prefix"]
        for diagnosis in active:
            if not diagnosis.code.upper().startswith(prefix.upper()):
                continue
            if draft.primary and diagnosis.code == draft.primary.code:
                continue
            draft.secondary.append(
                CodedDiagnosis(
                    code=diagnosis.code,
                    label=row["label"],
                    primary=False,
                    evidence_ref=f"problem-list:{diagnosis.code}",
                )
            )
            break

    return draft
