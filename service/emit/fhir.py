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
import uuid
from dataclasses import dataclass
from typing import Any

# A fixed namespace so the same resource id always yields the same urn. The
# bundle is replayed after a connectivity gap, and a fullUrl that changed
# between attempts would make two submissions of one encounter look like two
# encounters.
_URN_NAMESPACE = uuid.UUID("6f2a5d3e-9c41-4b7a-8e2d-1f0c5a7b9d34")


def _urn(resource_id: str) -> str:
    """`urn:uuid:` requires an actual UUID after the prefix.

    Every entry used to read `urn:uuid:ENC-1`, which is not one — a server
    validating the bundle rejects the whole transaction, and the failure is at
    submission time rather than anywhere we would have seen it. Derived rather
    than random so replay stays idempotent.
    """
    return f"urn:uuid:{uuid.uuid5(_URN_NAMESPACE, resource_id)}"


@dataclass(frozen=True)
class Bundle:
    payload: dict[str, Any]
    idempotency_key: str

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.payload, indent=indent, sort_keys=True)

    @property
    def entry_count(self) -> int:
        return len(self.payload.get("entry", []))


def _vital_signs_category() -> dict[str, Any]:
    return {"coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "vital-signs",
    }]}


def _component(systems: dict, spec: dict, observation) -> dict[str, Any]:
    return {
        "code": {"coding": [{"system": systems.get("loinc"), "code": spec["loinc"]}]},
        "valueQuantity": {
            "value": observation.value,
            "unit": spec["unit"],
            "system": "http://unitsofmeasure.org",
            "code": spec["unit"],
        },
    }


def _pathway_codes(rules) -> list[str]:
    """Measurements the pathway in force actually reads."""
    found: list[str] = []
    guideline = getattr(rules, "guideline", {}) or {}
    for row in guideline.get("targets") or []:
        for key in row:
            if key.endswith("_lt"):
                found.append(key[:-3])
    for requirement_set in (guideline.get("sufficiency") or {}).values():
        for row in requirement_set or []:
            if isinstance(row, dict) and row.get("code"):
                found.append(row["code"])
    return found


def build_bundle(state, claim, proposal, site, signer_id: str, rules, *, encounter_id: str) -> Bundle:
    interop = rules.interop
    systems = interop.get("systems") or {}
    codes = interop.get("observation_codes") or {}
    encounter_cfg = interop.get("encounter") or {}

    # When an entry's fullUrl is a urn, references to it inside the bundle must
    # use that urn. My own uuid5 fix broke this: the validator matched the
    # entries by type and id and then warned that "Encounter/ENC-1" does not
    # resolve to "urn:uuid:e0886315-...". Fixing one complaint created another,
    # which is the argument for running the real validator rather than a
    # hand-written approximation of it.
    encounter_ref = _urn(encounter_id)

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
                # Encounter.class is a Coding bound to ActEncounterCode, and
                # Condition.clinicalStatus to condition-clinical. Both bindings
                # are *required* in R4, so a code without its system is not a
                # code — a validating server rejects it.
                "class": {
                    "system": encounter_cfg.get(
                        "class_system", "http://terminology.hl7.org/CodeSystem/v3-ActCode"),
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
                    "clinicalStatus": {"coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                    }]},
                    "code": {
                        "coding": [
                            {
                                "system": systems.get("icd10"),
                                "code": diagnosis.code,
                            }
                        ]
                    },
                    "subject": {"reference": patient_ref},
                    "encounter": {"reference": encounter_ref},
                    # The evidence reference travels with the code. A claim that
                    # cannot point at what supports it should not be defensible,
                    # and here it is not even representable.
                    "note": [{"text": f"evidence: {diagnosis.evidence_ref}"}],
                },
            )
        )

    # Observations.
    #
    # The codes come from the pathway's own sufficiency rules and target rather
    # than a literal tuple — the emitter had ("sbp","dbp","k","egfr") baked in,
    # so a diabetes encounter shipped without its HbA1c.
    wanted: list[str] = []
    for code in _pathway_codes(rules):
        if code in codes and code not in wanted:
            wanted.append(code)

    panel = interop.get("blood_pressure_panel") or {}
    systolic, diastolic = panel.get("systolic"), panel.get("diastolic")
    index = 0

    if panel and systolic in wanted and diastolic in wanted:
        sys_obs, dia_obs = state.latest(systolic), state.latest(diastolic)
        if sys_obs is not None and dia_obs is not None:
            entries.append(
                _entry(
                    "Observation",
                    {
                        "resourceType": "Observation",
                        "id": f"{encounter_id}-obs-{index}",
                        "status": "final",
                        "category": [_vital_signs_category()],
                        "code": {"coding": [{"system": systems.get("loinc"),
                                             "code": panel["loinc"]}]},
                        "subject": {"reference": patient_ref},
                        "encounter": {"reference": encounter_ref},
                        "effectiveDateTime": sys_obs.taken_at.isoformat(),
                        "component": [
                            _component(systems, codes[systolic], sys_obs),
                            _component(systems, codes[diastolic], dia_obs),
                        ],
                        "performer": [{"reference": practitioner_ref}],
                        "note": [{"text": f"source: {sys_obs.source.value}"}],
                    },
                )
            )
            index += 1
        wanted = [c for c in wanted if c not in (systolic, diastolic)]

    for code in wanted:
        observation = state.latest(code)
        spec = codes.get(code)
        if observation is None or spec is None:
            continue
        resource = {
            "resourceType": "Observation",
            "id": f"{encounter_id}-obs-{index}",
            "status": "final",
            "code": {"coding": [{"system": systems.get("loinc"), "code": spec["loinc"]}]},
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "effectiveDateTime": observation.taken_at.isoformat(),
            "performer": [{"reference": practitioner_ref}],
            "valueQuantity": {
                "value": observation.value,
                "unit": spec["unit"],
                "system": "http://unitsofmeasure.org",
                "code": spec["unit"],
            },
            # Provenance survives the trip. A patient-reported reading must not
            # arrive downstream looking like a lab result.
            "note": [{"text": f"source: {observation.source.value}"}],
        }
        if spec.get("vital_sign"):
            resource["category"] = [_vital_signs_category()]
        entries.append(_entry("Observation", resource))
        index += 1

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
                    "encounter": {"reference": encounter_ref},
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
        "fullUrl": _urn(str(resource["id"])),
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
