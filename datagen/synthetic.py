"""Synthetic patients.

The pipes are real; the patients are not. We have no client, no hospital and no
lawful basis to touch a real record, so every patient here is generated. Being
loud about which parts are fake is the whole discipline — the hospital system,
the formulary, the guideline rules and the interoperability path are all real.

Seeded and deterministic: the same seed gives the same cohort, so a scorecard
regression is a real change and never a reshuffle.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

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

TODAY = date(2026, 8, 29)

# The ladder the reference proposer walks. One molecule per class, each stocked
# at the primary evaluation site.
LADDER = [
    ("ccb_dihydropyridine", "amlodipine", 5.0, 1),
    ("acei", "captopril", 25.0, 2),
    ("thiazide", "hydrochlorothiazide", 25.0, 1),
]


def _obs(code, value, days_ago, source=Source.EMR, unit="") -> Observation:
    units = {"sbp": "mmHg", "dbp": "mmHg", "k": "mmol/L", "egfr": "mL/min/1.73m2"}
    return Observation(
        code=code,
        value=float(value),
        unit=unit or units.get(code, ""),
        taken_at=TODAY - timedelta(days=days_ago),
        source=source,
    )


def make_patient(
    seed: int,
    *,
    controlled: bool | None = None,
    profile: str = "clean",
) -> PatientState:
    """One established hypertension follow-up patient.

    profile:
      clean       - in scope, adult under 65, no comorbidity that blocks a target
      no_target   - in scope but in a group whose target we have not extracted
                    (diabetes, CKD, elderly). The system must abstain.
      excluded_*  - trips one of the hard exclusions
      stale_labs  - in scope, but potassium and eGFR are months old
    """
    rng = random.Random(seed)

    age = rng.randint(30, 63)
    sex = rng.choice(["M", "F"])
    flags: dict[str, bool] = {"on_antihypertensive_treatment": True}
    symptoms: dict[str, bool] = {}
    diagnoses = [Diagnosis(code="I10", onset=TODAY - timedelta(days=rng.randint(400, 3000)))]
    intolerances: list[Intolerance] = []
    allergies: list[Allergy] = []

    if controlled is None:
        controlled = rng.random() < 0.5

    if controlled:
        sbp, dbp = rng.randint(118, 136), rng.randint(72, 86)
    else:
        sbp, dbp = rng.randint(144, 172), rng.randint(92, 104)

    lab_age = 30
    observations = []

    # ---- profile adjustments ---------------------------------------------
    if profile == "no_target":
        which = rng.choice(["dm", "ckd", "elderly"])
        if which == "dm":
            flags["has_dm"] = True
            diagnoses.append(Diagnosis(code="E11.9"))
        elif which == "ckd":
            flags["has_ckd"] = True
            diagnoses.append(Diagnosis(code="N18.3"))
        else:
            age = rng.randint(65, 84)

    elif profile == "stale_labs":
        lab_age = rng.randint(120, 400)

    elif profile == "excluded_pregnancy":
        sex = "F"
        flags["pregnancy_positive"] = True

    elif profile == "excluded_minor":
        age = rng.randint(12, 17)

    elif profile == "excluded_first_presentation":
        flags["is_first_presentation"] = True

    elif profile == "excluded_secondary":
        diagnoses.append(Diagnosis(code="I15.0"))

    elif profile == "excluded_resistant":
        flags["resistant_hypertension"] = True

    elif profile == "excluded_renal":
        observations.append(_obs("egfr", rng.randint(12, 28), 20))

    elif profile == "excluded_other":
        flags[rng.choice(["active_oncology", "psychiatric_crisis", "controlled_substance_request"])] = True

    # ---- observations -----------------------------------------------------
    observations += [_obs("sbp", sbp, 0), _obs("dbp", dbp, 0)]
    for n, days in enumerate((90, 180, 270), start=1):
        observations.append(_obs("sbp", sbp + rng.randint(-6, 6), days))
        observations.append(_obs("dbp", dbp + rng.randint(-4, 4), days))

    observations.append(_obs("k", round(rng.uniform(3.6, 4.9), 1), lab_age))
    if profile != "excluded_renal":
        observations.append(_obs("egfr", rng.randint(62, 104), lab_age))

    # ---- current regimen --------------------------------------------------
    rungs = 1 if controlled else rng.randint(1, 2)
    medications = [
        Medication(
            molecule=molecule,
            mg_per_dose=mg,
            doses_per_day=per_day,
            source=Source.EMR,
            since=TODAY - timedelta(days=rng.randint(120, 900)),
            adherence_signal=rng.choice(["good", "good", "gaps"]),
        )
        for _, molecule, mg, per_day in LADDER[:rungs]
    ]

    encounters = [
        PriorEncounter(
            encounter_id=f"E{seed}-{n}",
            encounter_date=TODAY - timedelta(days=90 * n),
            sbp=float(sbp + rng.randint(-6, 6)),
            dbp=float(dbp + rng.randint(-4, 4)),
            # What was done last time is part of the picture, not decoration: a
            # patient still above target after two visits of "continue" is a
            # different case from one whose dose was raised last month.
            decision="continue" if controlled else rng.choice(["continue", "titrate_up"]),
            signed_by=f"PRAC-A-00{rng.randint(1, 2)}",
        )
        for n in range(1, 4)
    ]

    return PatientState(
        patient_id=f"SYN-{seed:05d}",
        age=age,
        sex=sex,
        as_of=TODAY,
        diagnoses=diagnoses,
        medications=medications,
        allergies=allergies,
        intolerances=intolerances,
        observations=observations,
        encounters=encounters,
        flags=flags,
        symptoms=symptoms,
        is_synthetic=True,
    )


def with_documented_acei_intolerance(state: PatientState, days_ago: int = 90) -> PatientState:
    """The one state in which an ARB becomes prescribable."""
    state.intolerances.append(
        Intolerance(
            molecule="captopril",
            drug_class="acei",
            documented_at=TODAY - timedelta(days=days_ago),
            reaction="persistent dry cough",
        )
    )
    state.medications = [m for m in state.medications if m.molecule != "captopril"]
    return state
