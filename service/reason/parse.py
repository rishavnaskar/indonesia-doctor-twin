"""Strict parsing of a model's response into a Proposal.

A proposal that does not parse is a gate failure, not a retry. Retrying a
malformed clinical output turns a bug into a coin flip: the second attempt is
not more correct, it is just differently wrong, and the failure stops being
visible.

So this raises. The caller converts that into a refusal, the encounter ends in
ABSTAIN, and the clinician sees nothing — which is the same thing that happens
when the gate rejects a well-formed but unsafe proposal.
"""

from __future__ import annotations

import json
import re
from typing import Any

from service.contracts.proposal import (
    Assertion,
    Assessment,
    ChangeAction,
    MedicationChange,
    Proposal,
    Provenance,
    Concern,
    Recommendation,
    Target,
    Urgency,
)


class ProposalParseError(ValueError):
    pass


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise ProposalParseError("empty response")

    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProposalParseError(f"response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProposalParseError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def to_proposal(raw: dict[str, Any], provenance: Provenance) -> Proposal:
    try:
        assessment = Assessment(raw["assessment"])
    except KeyError as exc:
        # A bare KeyError repr — bad assessment/recommendation: 'assessment' —
        # tells a reader nothing about which of the two was wrong or how. Name
        # the field, say whether it was absent or unusable, and list what was
        # allowed: this text is read by someone deciding whether a model is
        # worth keeping.
        raise ProposalParseError(
            "the response has no `assessment` field. Expected one of: "
            + ", ".join(a.value for a in Assessment)
        ) from exc
    except ValueError as exc:
        raise ProposalParseError(
            f"`assessment` was {raw.get('assessment')!r}, which is not one of: "
            + ", ".join(a.value for a in Assessment)
        ) from exc

    try:
        recommendation = Recommendation(raw["recommendation"])
    except KeyError as exc:
        raise ProposalParseError(
            "the response has no `recommendation` field. Expected one of: "
            + ", ".join(r.value for r in Recommendation)
        ) from exc
    except ValueError as exc:
        raise ProposalParseError(
            f"`recommendation` was {raw.get('recommendation')!r}, which is not one of: "
            + ", ".join(r.value for r in Recommendation)
        ) from exc

    target_raw = raw.get("target_used")
    target = None
    if isinstance(target_raw, dict) and target_raw.get("citation"):
        # A model that does not know the target reports nulls here. That is not
        # malformed output, it is the model saying so — and it is gate check 2's
        # decision to make, not the parser's. Check 2 blocks a proposal with no
        # target and says why in a sentence a clinician can read; a crash here
        # would take that verdict away and replace it with a stack trace.
        #
        # A non-null value that is not a number is different: that IS malformed,
        # and it still raises.
        raw_thresholds = {
            key[:-3]: value for key, value in target_raw.items()
            if key.endswith("_lt")
        }
        if raw_thresholds and all(v is not None for v in raw_thresholds.values()):
            try:
                target = Target(
                    thresholds={k: float(v) for k, v in raw_thresholds.items()},
                    citation=str(target_raw["citation"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProposalParseError(f"bad target_used: {exc}") from exc

    changes: list[MedicationChange] = []
    for row in raw.get("medication_changes") or []:
        if not isinstance(row, dict):
            raise ProposalParseError(f"medication_changes entry is not an object: {row!r}")
        try:
            changes.append(
                MedicationChange(
                    action=ChangeAction(row["action"]),
                    molecule=str(row["molecule"]),
                    mg_per_dose=_number(row.get("mg_per_dose")),
                    doses_per_day=_integer(row.get("doses_per_day")),
                    rationale=str(row.get("rationale", "")),
                    citation=str(row.get("citation", "")),
                )
            )
        except (KeyError, ValueError) as exc:
            raise ProposalParseError(f"bad medication change {row!r}: {exc}") from exc

    concerns: list[Concern] = []
    for row in raw.get("concerns") or []:
        if isinstance(row, str):
            # A bare string is a concern at the quieter level. Promoting it
            # would let sloppy output shout.
            concerns.append(Concern(text=row, urgency=Urgency.MENTION))
            continue
        if not isinstance(row, dict) or not str(row.get("text", "")).strip():
            raise ProposalParseError(f"concern is not readable: {row!r}")
        try:
            urgency = Urgency(row.get("urgency", "mention"))
        except ValueError as exc:
            raise ProposalParseError(
                f"concern urgency {row.get('urgency')!r} is not one of: "
                + ", ".join(u.value for u in Urgency)
            ) from exc
        concerns.append(Concern(text=str(row["text"]).strip(), urgency=urgency,
                                citation=row.get("citation")))

    assertions = [
        Assertion(text=str(a.get("text", "")), citation=str(a.get("citation", "")))
        for a in raw.get("assertions") or []
        if isinstance(a, dict)
    ]

    confidence = raw.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ProposalParseError(f"confidence is not a number: {confidence!r}") from exc

    return Proposal(
        assessment=assessment,
        recommendation=recommendation,
        bp_trend_summary=str(raw.get("bp_trend_summary", "")),
        target_used=target,
        confidence=confidence,
        provenance=provenance,
        medication_changes=changes,
        investigations=[str(i) for i in raw.get("investigations") or []],
        assertions=assertions,
        patient_instructions=str(raw.get("patient_instructions", "")),
        follow_up_interval_days=_integer(raw.get("follow_up_interval_days")),
        uncertainty_notes=str(raw.get("uncertainty_notes", "")),
        concerns=concerns,
    )


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProposalParseError(f"expected a number, got {value!r}") from exc


def _integer(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProposalParseError(f"expected an integer, got {value!r}") from exc
