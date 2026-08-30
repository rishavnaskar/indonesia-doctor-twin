"""A wire format for patients, between the browser and PatientState.

A boundary, not a second model. PatientState stays canonical; this converts to
and from it and validates on the way in.

**`is_synthetic` is never inferred.** It arrives as an explicit boolean and
defaults to False, because real-until-proven-otherwise is the safe direction for
the one flag that decides whether a record may cross the residency boundary. A
record someone typed in or uploaded is not synthetic just because it came from a
form — and if it is not marked, the hosted backend refuses to send it. That
refusal is the guard doing its job, and the surface shows it rather than hiding
it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from datagen.synthetic import TODAY, make_patient
from service.state.models import (
    Allergy,
    Diagnosis,
    Intolerance,
    Medication,
    Observation,
    PatientState,
    PriorEncounter,
    Source,
)


class PatientFormatError(ValueError):
    """Bad input from the browser. Reported, never guessed at."""


MAX_PATIENTS = 12


def to_wire(state: PatientState) -> dict[str, Any]:
    return {
        "patient_id": state.patient_id,
        "age": state.age,
        "sex": state.sex,
        "as_of": state.as_of.isoformat(),
        "is_synthetic": state.is_synthetic,
        "diagnoses": [d.code for d in state.diagnoses],
        "medications": [
            {
                "molecule": m.molecule,
                "mg_per_dose": m.mg_per_dose,
                "doses_per_day": m.doses_per_day,
            }
            for m in state.medications
        ],
        "observations": [
            {
                "code": o.code,
                "value": o.value,
                "age_days": (state.as_of - o.taken_at).days,
            }
            for o in state.observations
        ],
        "symptoms": {k: v for k, v in state.symptoms.items()},
        "flags": {k: v for k, v in state.flags.items()},
        "allergies": [a.substance for a in state.allergies],
        "intolerances": [
            {"molecule": i.molecule, "drug_class": i.drug_class,
             "age_days": (state.as_of - i.documented_at).days}
            for i in state.intolerances
        ],
        "history": [
            {"encounter_id": e.encounter_id,
             "age_days": (state.as_of - e.encounter_date).days,
             "sbp": e.sbp, "dbp": e.dbp, "decision": e.decision}
            for e in state.encounters
        ],
        "intake_notes": state.intake_notes,
    }


def _num(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PatientFormatError(f"{field}: expected a number, got {value!r}") from exc


def _int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PatientFormatError(f"{field}: expected a whole number, got {value!r}") from exc


_UNITS = {"sbp": "mmHg", "dbp": "mmHg", "k": "mmol/L", "egfr": "mL/min/1.73m2"}


def from_wire(raw: dict[str, Any]) -> PatientState:
    if not isinstance(raw, dict):
        raise PatientFormatError("a patient must be an object")

    as_of = TODAY
    if raw.get("as_of"):
        try:
            as_of = date.fromisoformat(str(raw["as_of"]))
        except ValueError as exc:
            raise PatientFormatError(f"as_of: {exc}") from exc

    state = PatientState(
        patient_id=str(raw.get("patient_id") or "UNTITLED"),
        age=_int(raw.get("age", 0), "age"),
        sex=str(raw.get("sex") or "U"),
        as_of=as_of,
        # Never inferred. See the module docstring.
        is_synthetic=bool(raw.get("is_synthetic", False)),
        intake_notes=str(raw.get("intake_notes") or ""),
    )

    for code in raw.get("diagnoses") or []:
        state.diagnoses.append(Diagnosis(code=str(code)))

    for row in raw.get("medications") or []:
        state.medications.append(
            Medication(
                molecule=str(row.get("molecule") or ""),
                mg_per_dose=_num(row.get("mg_per_dose"), "mg_per_dose"),
                doses_per_day=_int(row.get("doses_per_day", 1), "doses_per_day"),
                # A record typed into a form did not come from the hospital
                # system, and saying it did would be a provenance lie. The
                # distinction is load-bearing: a model may never treat a
                # patient-reported value as equivalent to a confirmed one.
                source=Source.CLINICIAN_ENTERED,
            )
        )

    for row in raw.get("observations") or []:
        code = str(row.get("code") or "")
        if not code:
            raise PatientFormatError("an observation needs a code")
        if row.get("value") in (None, ""):
            continue  # a measurement left blank is a measurement not taken
        state.observations.append(
            Observation(
                code=code,
                value=_num(row.get("value"), f"observation {code}"),
                unit=_UNITS.get(code, ""),
                taken_at=as_of - timedelta(days=_int(row.get("age_days", 0), "age_days")),
                source=Source.CLINICIAN_ENTERED,
            )
        )

    state.symptoms = {str(k): bool(v) for k, v in (raw.get("symptoms") or {}).items()}
    state.flags = {str(k): bool(v) for k, v in (raw.get("flags") or {}).items()}

    for substance in raw.get("allergies") or []:
        state.allergies.append(Allergy(substance=str(substance)))

    for row in raw.get("intolerances") or []:
        state.intolerances.append(
            Intolerance(
                molecule=str(row.get("molecule") or ""),
                drug_class=str(row.get("drug_class") or ""),
                documented_at=as_of - timedelta(days=_int(row.get("age_days", 0), "age_days")),
            )
        )

    for index, row in enumerate(raw.get("history") or [], start=1):
        state.encounters.append(
            PriorEncounter(
                encounter_id=str(row.get("encounter_id") or f"H{index}"),
                encounter_date=as_of - timedelta(days=_int(row.get("age_days", 90 * index),
                                                           "history age_days")),
                sbp=_num(row["sbp"], "history sbp") if row.get("sbp") else None,
                dbp=_num(row["dbp"], "history dbp") if row.get("dbp") else None,
                decision=str(row.get("decision") or "") or None,
            )
        )

    return state


def generate(n: int, seed: int = 0, profile: str = "clean") -> list[dict[str, Any]]:
    """A fresh cohort, marked synthetic because it is."""
    if n < 1 or n > MAX_PATIENTS:
        raise PatientFormatError(f"ask for between 1 and {MAX_PATIENTS} patients")
    out = []
    for index in range(n):
        state = make_patient(seed + index, profile=profile)
        state.is_synthetic = True
        state.patient_id = f"SYN-{seed + index:05d}"
        out.append(to_wire(state))
    return out
