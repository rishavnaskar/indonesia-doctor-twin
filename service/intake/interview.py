"""The bounded interviewer.

A structured interviewer, not an advisor. It asks a fixed set of closed
questions, records the answers, and has no clinical voice whatsoever.

That last property is the safety argument, and it is structural rather than
behavioural. Under multi-turn pressure a large share of medical model
configurations capitulate to a confidently wrong patient premise — symptom
triage worst of all — and prompting against it helps only a little. So the
patient-facing surface here is not a model that has been told to be careful. It
is a state machine that has no way to express a clinical opinion, and therefore
nothing to be argued out of.

Anything the patient says that is not an answer to the current question gets the
same fixed deflection and is logged for the doctor. Every time. The interviewer
never improvises, never reassures, and never answers.

A model may later map free-text answers onto these closed options. It will not
be permitted to choose the questions or to speak in its own voice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TurnKind(str, Enum):
    QUESTION = "question"
    DEFLECTION = "deflection"
    CLOSING = "closing"


@dataclass(frozen=True)
class Turn:
    kind: TurnKind
    text: str
    question_id: str | None = None
    options: list[dict[str, str]] = field(default_factory=list)


@dataclass
class IntakeResult:
    answers: dict[str, Any] = field(default_factory=dict)
    # Questions the patient asked. Passed to the clinician verbatim, answered
    # by nobody in between.
    questions_for_clinician: list[str] = field(default_factory=list)
    complete: bool = False

    def symptoms(self) -> dict[str, bool]:
        selected = self.answers.get("symptoms") or []
        return {value: True for value in selected if value != "none"}


class Interviewer:
    """Deterministic. No model, no clinical output, no exceptions to either."""

    def __init__(self, rules):
        language = rules.language or {}
        self._questions = list(language.get("questions") or [])
        self._deflection = (language.get("deflection") or {}).get("text", "")
        self._closing = (language.get("closing") or {}).get("text", "")
        self._index = 0
        self.result = IntakeResult()

        if not self._questions:
            raise ValueError("intake pack defines no questions")

    # ------------------------------------------------------------ asking

    def current(self) -> Turn:
        if self._index >= len(self._questions):
            return Turn(kind=TurnKind.CLOSING, text=self._closing)
        question = self._questions[self._index]
        return Turn(
            kind=TurnKind.QUESTION,
            text=question["text"],
            question_id=question["id"],
            options=list(question.get("options") or []),
        )

    # ------------------------------------------------------------ answering

    def answer(self, value: Any) -> Turn:
        """Record a valid answer, or deflect.

        There is no third behaviour. In particular there is no branch in which
        the interviewer discusses, explains, reassures or concedes.
        """
        if self._index >= len(self._questions):
            return Turn(kind=TurnKind.CLOSING, text=self._closing)

        question = self._questions[self._index]

        if not self._valid(question, value):
            # Anything that is not an answer — a question, an argument, an
            # appeal to a relative who is a doctor — lands here.
            if isinstance(value, str) and value.strip():
                self.result.questions_for_clinician.append(value.strip())
            return Turn(kind=TurnKind.DEFLECTION, text=self._deflection,
                        question_id=question["id"])

        self.result.answers[question["field"]] = value
        self._index += 1

        if self._index >= len(self._questions):
            self.result.complete = True
            return Turn(kind=TurnKind.CLOSING, text=self._closing)
        return self.current()

    def skip(self) -> Turn:
        """Only permitted where the pack marks a question optional."""
        question = self._questions[self._index]
        if not question.get("optional"):
            return Turn(kind=TurnKind.DEFLECTION, text=self._deflection,
                        question_id=question["id"])
        self._index += 1
        if self._index >= len(self._questions):
            self.result.complete = True
            return Turn(kind=TurnKind.CLOSING, text=self._closing)
        return self.current()

    # ------------------------------------------------------------ validation

    def _valid(self, question: dict, value: Any) -> bool:
        kind = question.get("type")
        allowed = {o["value"] for o in question.get("options") or []}

        if kind == "choice":
            return value in allowed
        if kind == "multi_choice":
            return (
                isinstance(value, (list, tuple, set))
                and len(value) > 0
                and set(value) <= allowed
            )
        if kind == "numeric_pair":
            bounds = question.get("range") or {}
            low, high = bounds.get("min", 0), bounds.get("max", 10**6)
            return (
                isinstance(value, (list, tuple))
                and len(value) == 2
                and all(isinstance(v, (int, float)) and low <= v <= high for v in value)
            )
        return False
