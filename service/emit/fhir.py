"""Outbound bundle construction.

The exchange format is a boundary. We map outward here, at the edge, and the
internal clinical model owes it nothing — which is why adding a national profile
is a pack change rather than a refactor of patient state.

Every system URL, code system and endpoint comes from the interop pack, so this
module names no country and no payer. It also performs no network I/O: it builds
a bundle and hands it to the queue. Separating "what to send" from "when it
actually leaves" is what makes offline operation tractable rather than bolted on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Bundle:
    payload: dict[str, Any]
    idempotency_key: str

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.payload, indent=indent, sort_keys=True)

    @property
    def entry_count(self) -> int:
        return len(self.payload.get("entry", []))


def build_bundle(state, claim, proposal, site, signer_id: str, rules, *, encounter_id: str) -> Bundle:
    interop = rules.interop
    systems = interop.get("systems") or {}
    codes = interop.get("observation_codes") or {}
    encounter_cfg = interop.get("encounter") or {}

    patient_ref = f"Patient/{state.patient_id}"
    practitioner_ref = f"Practitioner/{signer_id}"
    org_ref = f"Organization/{site['site_id']}"
    entries: list[dict[str, Any]] = []

    # Encounter
    entries.append(
        _entry(
            "Encounter",
            {
                "resourceType": "Encounter",
                "id": encounter_id,
                "status": encounter_cfg.get("status", "finished"),
                "class": {
                    "code": encounter_cfg.get("class_code", "AMB"),
                    "display": encounter_cfg.get("class_display", "ambulatory"),
                },
                "subject": {"reference": patient_ref},
                "participant": [{"individual": {"reference": practitioner_ref}}],
                "serviceProvider": {"reference": org_ref},
                "period": {"start": state.as_of.isoformat()},
            },
        )
    )

    # Conditions — only what was actually coded, and only with its evidence.
    coded = ([claim.primary] if claim and claim.primary else []) + (
        claim.secondary if claim else []
    )
    for index, diagnosis in enumerate(coded):
        entries.append(
            _entry(
                "Condition",
                {
                    "resourceType": "Condition",
                    "id": f"{encounter_id}-cond-{index}",
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {
                        "coding": [
                            {
                                "system": systems.get("icd10"),
                                "code": diagnosis.code,
                                "display": diagnosis.label,
                            }
                        ]
                    },
                    "subject": {"reference": patient_ref},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    # The evidence reference travels with the code. A claim that
                    # cannot point at what supports it should not be defensible,
                    # and here it is not even representable.
                    "note": [{"text": f"evidence: {diagnosis.evidence_ref}"}],
                },
            )
        )

    # Observations
    for index, code in enumerate(("sbp", "dbp", "k", "egfr")):
        observation = state.latest(code)
        spec = codes.get(code)
        if observation is None or spec is None:
            continue
        entries.append(
            _entry(
                "Observation",
                {
                    "resourceType": "Observation",
                    "id": f"{encounter_id}-obs-{index}",
                    "status": "final",
                    "code": {
                        "coding": [
                            {
                                "system": systems.get("loinc"),
                                "code": spec["loinc"],
                                "display": spec["display"],
                            }
                        ]
                    },
                    "subject": {"reference": patient_ref},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    "effectiveDateTime": observation.taken_at.isoformat(),
                    "valueQuantity": {
                        "value": observation.value,
                        "unit": spec["unit"],
                        "system": "http://unitsofmeasure.org",
                    },
                    # Provenance survives the trip. A patient-reported reading
                    # must not arrive downstream looking like a lab result.
                    "note": [{"text": f"source: {observation.source.value}"}],
                },
            )
        )

    # Medication requests — signed prescriptions only.
    for index, change in enumerate(proposal.medication_changes if proposal else []):
        entries.append(
            _entry(
                "MedicationRequest",
                {
                    "resourceType": "MedicationRequest",
                    "id": f"{encounter_id}-rx-{index}",
                    "status": "active",
                    "intent": "order",
                    "medicationCodeableConcept": {"text": change.molecule},
                    "subject": {"reference": patient_ref},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    "requester": {"reference": practitioner_ref},
                    "dosageInstruction": [
                        {
                            "text": (
                                f"{change.mg_per_dose:g} mg, "
                                f"{change.doses_per_day} times daily"
                            ),
                            "timing": {
                                "repeat": {
                                    "frequency": change.doses_per_day,
                                    "period": 1,
                                    "periodUnit": "d",
                                }
                            },
                        }
                    ],
                },
            )
        )

    payload = {
        "resourceType": "Bundle",
        "type": (interop.get("exchange") or {}).get("bundle_type", "transaction"),
        "entry": entries,
    }
    return Bundle(payload=payload, idempotency_key=_key(encounter_id, payload))


def _entry(resource_type: str, resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "fullUrl": f"urn:uuid:{resource['id']}",
        "resource": resource,
        "request": {"method": "PUT", "url": f"{resource_type}/{resource['id']}"},
    }


def _key(encounter_id: str, payload: dict[str, Any]) -> str:
    """Stable across retries, distinct across content.

    Retrying after a dropped connection must not create a second encounter, and
    a genuine correction must not be swallowed as a duplicate. Hashing the
    content alongside the encounter id gives both.
    """
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"{encounter_id}:{digest}"
