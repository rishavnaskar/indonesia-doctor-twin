"""The proposal's wire schema, for backends that can enforce one.

Built from the enums rather than written out beside them. A hand-maintained
copy drifts the moment someone adds a recommendation, and the failure is
silent: the model is simply never told the new value exists.

Enforcement at the API level is worth having because the alternative has a
measurable cost. A free model in a live run emitted `titraate_up` — a typo the
strict parser correctly rejected, at the price of a wasted call and a visit with
no draft. Constrained decoding makes that class of failure impossible rather
than merely caught.

It does not replace the parser, and this is not a theoretical caution.
Asked for a strict `json_schema`, one free model accepted the request without
error and returned a fenced markdown block containing a structure of its own
invention — fields that appear nowhere in the schema it had just agreed to.
Enforcement is a claim by the provider, not a property of the output. The
parser stays strict and trusts nothing.

The investigation codes come from the pack, because /service may not name a
test any more than it may name a drug.
"""

from __future__ import annotations

from typing import Any

from service.contracts.proposal import Assessment, ChangeAction, Recommendation


def _values(enum_class) -> list[str]:
    return [member.value for member in enum_class]


def proposal_schema(rules=None) -> dict[str, Any]:
    investigations: dict[str, Any] = {"type": "string"}
    codes = sorted(getattr(rules, "investigations", None) or {}) if rules else []
    if codes:
        investigations = {"type": "string", "enum": codes}

    return {
        "type": "object",
        "properties": {
            "assessment": {"type": "string", "enum": _values(Assessment)},
            "recommendation": {"type": "string", "enum": _values(Recommendation)},
            "bp_trend_summary": {"type": "string"},
            # Threshold keys are `<code>_lt` and depend on the pathway, so this
            # object stays open where the rest of the schema is closed. The
            # parser reads whatever `_lt` keys arrive and gate check 2 compares
            # them against the target the pack actually resolved, so an invented
            # threshold is caught there rather than admitted here.
            "target_used": {
                "type": "object",
                "properties": {"citation": {"type": "string"}},
                "required": ["citation"],
            },
            "medication_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": _values(ChangeAction)},
                        "molecule": {"type": "string"},
                        "mg_per_dose": {"type": "number"},
                        "doses_per_day": {"type": "integer"},
                        "rationale": {"type": "string"},
                        "citation": {"type": "string"},
                    },
                    "required": ["action", "molecule", "rationale", "citation"],
                    "additionalProperties": False,
                },
            },
            "investigations": {"type": "array", "items": investigations},
            "assertions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "citation": {"type": "string"},
                    },
                    "required": ["text", "citation"],
                    "additionalProperties": False,
                },
            },
            "patient_instructions": {"type": "string"},
            "patient_instructions_en": {"type": "string"},
            "follow_up_interval_days": {"type": "integer"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "uncertainty_notes": {"type": "string"},
            # The channel for something a rule did not ask about. Additive
            # only: it can raise what a clinician sees and never lower it.
            "concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "urgency": {"type": "string", "enum": ["mention", "escalate"]},
                    },
                    "required": ["text", "urgency"],
                    "additionalProperties": False,
                },
            },
        },
        # Deliberately short. Over-constraining `required` pushes a model into
        # inventing a value rather than omitting one, which is exactly the
        # failure this system exists to avoid.
        "required": ["assessment", "recommendation", "confidence"],
        "additionalProperties": False,
    }
