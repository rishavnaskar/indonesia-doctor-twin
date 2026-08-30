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


class Urgency(str, Enum):
    """How loudly a model-raised concern is carried.

    Never quieter than the rules decided. See `Concern`.
    """

    MENTION = "mention"      # worth a line the clinician can read past
    ESCALATE = "escalate"    # the clinician should look at this now


@dataclass(frozen=True)
class Concern:
    """Something the drafter thinks a clinician should see.

    The deterministic red flags are the floor and they are not negotiable: a
    rule with a defined threshold has perfect recall on the pattern it names,
    and a model doing that job at ninety-nine percent is strictly worse.

    But a rule only catches what somebody enumerated. Seven red flags is seven
    patterns, and a patient whose problem is not one of them gets no flag from
    the rules — while the model, having read the whole record, may well have
    noticed. This is the channel for that, and it exists because the alternative
    is a system that can only ever see what was anticipated.

    **A concern can only add.** It can raise what the clinician sees and can
    never lower it, suppress a rule-driven escalation, or mark anything as fine.
    That asymmetry is what makes it safe to let a model speak here at all: the
    worst a wrong concern costs is a clinician's attention, and the worst a
    missing one costs is nothing that was not already missing.
    """

    text: str
    urgency: Urgency = Urgency.MENTION
    citation: str | None = None


@dataclass(frozen=True)
class Target:
    """The target the drafter says it used. Keyed by measurement code, because
    a target is not always a blood pressure."""

    thresholds: dict[str, float]
    citation: str

    def below(self, code: str) -> float | None:
        return self.thresholds.get(code)


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

    # Which read-only tools the drafter chose to call, in order. Recorded
    # because what a model asks for is evidence: one that titrates a
    # RAAS-acting drug without ever requesting a potassium result has told us
    # something no inspection of its output would reveal.
    tools_requested: list[str] = field(default_factory=list)

    # Things the drafter wants a clinician to see that no rule asked about.
    # Additive only — see `Concern`.
    concerns: list[Concern] = field(default_factory=list)

    def citations(self) -> set[str]:
        found = {a.citation for a in self.assertions}
        found |= {c.citation for c in self.medication_changes}
        if self.target_used is not None:
            found.add(self.target_used.citation)
        return {c for c in found if c}
