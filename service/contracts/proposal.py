"""The Proposal — the only thing the reasoning step is allowed to emit.

SPEC-V1 §5.6. Structured output, schema-enforced. A proposal that does not parse
is a gate failure, not a retry: retrying a malformed clinical output is how you
turn a bug into a coin flip.

Why this lives in /service/contracts and not in /service/reason: the gate has to
read a Proposal, and the gate may never import from /reason. Rather than bend
that rule for "just a dataclass", the shared vocabulary sits in a neutral module
that both sides depend on and neither owns. /reason produces one, /gate consumes
one, and there is no import path between them for a model to sneak along.

Nothing in this module reasons. It defines the shape of the thing that gets
handed to the gate, and the gate does not trust it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Assessment(str, Enum):
    CONTROLLED = "controlled"
    UNCONTROLLED = "uncontrolled"
    OVER_TREATED = "over_treated"


class Recommendation(str, Enum):
    CONTINUE = "continue"
    TITRATE_UP = "titrate_up"
    TITRATE_DOWN = "titrate_down"
    ADD_AGENT = "add_agent"
    SWITCH_AGENT = "switch_agent"
    REFER = "refer"


class ChangeAction(str, Enum):
    START = "start"
    STOP = "stop"
    INCREASE = "increase"
    DECREASE = "decrease"
    CONTINUE = "continue"


@dataclass(frozen=True)
class Provenance:
    """Three pins, not one.

    The corpus version alone is not enough. Model and prompt template change far
    more often than a guideline does, and a regression in either has to be
    traceable to the exact proposal it produced. A proposal missing any pin is
    malformed and the gate rejects it.
    """

    model: str  # name@version
    prompt_template: str  # name@version
    corpus: str  # name@version

    def complete(self) -> bool:
        return all(
            isinstance(v, str) and "@" in v and not v.startswith("@")
            for v in (self.model, self.prompt_template, self.corpus)
        )


@dataclass(frozen=True)
class MedicationChange:
    action: ChangeAction
    molecule: str
    mg_per_dose: float | None
    doses_per_day: int | None
    rationale: str
    citation: str

    @property
    def mg_daily(self) -> float | None:
        if self.mg_per_dose is None or self.doses_per_day is None:
            return None
        return self.mg_per_dose * self.doses_per_day


@dataclass(frozen=True)
class Assertion:
    """Any clinical claim the proposal makes, with the source it rests on."""

    text: str
    citation: str


@dataclass(frozen=True)
class Target:
    sbp_lt: float
    dbp_lt: float
    citation: str


@dataclass
class Proposal:
    assessment: Assessment
    recommendation: Recommendation
    bp_trend_summary: str
    target_used: Target | None
    confidence: float
    provenance: Provenance

    medication_changes: list[MedicationChange] = field(default_factory=list)
    investigations: list[str] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    patient_instructions: str = ""
    follow_up_interval_days: int | None = None
    uncertainty_notes: str = ""

    # Fraction of independent samples that produced this exact plan, when the
    # drafter was sampled more than once. None means it was drafted once and
    # the question was never asked — which is different from "they disagreed",
    # and the two must not be conflated by anything reading this.
    agreement: float | None = None

    def citations(self) -> set[str]:
        found = {a.citation for a in self.assertions}
        found |= {c.citation for c in self.medication_changes}
        if self.target_used is not None:
            found.add(self.target_used.citation)
        return {c for c in found if c}
