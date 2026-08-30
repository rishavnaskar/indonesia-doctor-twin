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
    Recommendation,
    Target,
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
        recommendation = Recommendation(raw["recommendation"])
    except (KeyError, ValueError) as exc:
        raise ProposalParseError(f"bad assessment/recommendation: {exc}") from exc

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
        sbp_raw, dbp_raw = target_raw.get("sbp_lt"), target_raw.get("dbp_lt")
        if sbp_raw is not None and dbp_raw is not None:
            try:
                target = Target(
                    sbp_lt=float(sbp_raw),
                    dbp_lt=float(dbp_raw),
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
