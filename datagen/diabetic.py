"""Synthetic patients for the second pathway: type 2 diabetes follow-up.

Separate from `synthetic.py` for the same reason the pathway itself is two
pack files and no engine code - a second disease should cost a second
generator, not a wider first one. The primitives both share (observations,
regimen ladders, the fixed TODAY) stay in `synthetic.py`; what is specific to
this disease is here.

Seeded and deterministic, like everything else in this package: the same seed
gives the same patient, so a scorecard regression is a real change and never a
reshuffle.
"""

from __future__ import annotations

import random
from datetime import timedelta

from datagen.synthetic import TODAY, _obs
from service.state.models import (
    Allergy,
    Diagnosis,
    Medication,
    PatientState,
    PriorEncounter,
    Source,
)

DM_LADDER = [("metformin", [500.0, 850.0, 1000.0], 2), ("glimepiride", [1.0, 2.0], 1)]


def make_diabetic(
    seed: int, *, controlled: bool | None = None, profile: str = "clean"
) -> PatientState:
    """One type 2 diabetes follow-up patient.

    The same shape as make_patient and deliberately not folded into it: the two
    pathways measure different things, carry different comorbidity risks and
    exclude on different rules, and a single function with a pathway flag would
    become a thicket of branches nobody could read.
    """
    rng = random.Random(seed)

    age = rng.randint(28, 64)
    flags: dict[str, bool] = {"has_dm": True}
    symptoms: dict[str, bool] = {}
    diagnoses = [
        Diagnosis(
            code=rng.choice(["E11.9", "E11.6", "E11.8"]),
            onset=TODAY - timedelta(days=rng.randint(300, 5000)),
        )
    ]
    allergies: list[Allergy] = []

    if controlled is None:
        controlled = rng.random() < 0.5
    hba1c = round(rng.uniform(5.9, 6.9), 1) if controlled else round(rng.uniform(7.1, 9.6), 1)

    lab_age = rng.randint(10, 150)
    egfr_value = rng.randint(48, 110)
    rungs = 1 if controlled else rng.randint(1, 2)

    if rng.random() < 0.3:
        symptoms[rng.choice(["dizziness", "swelling"])] = True
    if rng.random() < 0.2:
        diagnoses.append(Diagnosis(code="E78.5"))
    if rng.random() < 0.15:
        allergies.append(Allergy(substance="ibuprofen", reaction="rash"))

    if profile == "no_target":
        if rng.random() < 0.5:
            age = rng.randint(65, 86)
        else:
            flags["has_ckd"] = True
            diagnoses.append(Diagnosis(code="N18.3"))
    elif profile == "stale_labs":
        lab_age = rng.randint(200, 600)
    elif profile == "red_flag":
        symptoms[rng.choice(["hypoglycaemia", "vomiting", "dyspnoea"])] = True
    elif profile == "excluded_insulin":
        flags["on_insulin"] = True
    elif profile == "excluded_renal":
        egfr_value = rng.randint(9, 28)
    elif profile == "excluded_first_presentation":
        flags["is_first_presentation"] = True

    observations = [_obs("hba1c", hba1c, lab_age), _obs("egfr", egfr_value, lab_age)]
    for n in range(1, rng.randint(2, 5)):
        drift = round(rng.uniform(-0.5, 0.5), 1)
        prior = min(hba1c + drift, 6.9) if controlled else max(hba1c + drift, 7.1)
        observations.append(_obs("hba1c", round(prior, 1), lab_age + 120 * n))

    medications = [
        Medication(
            molecule=molecule,
            mg_per_dose=rng.choice(doses),
            doses_per_day=per_day,
            source=Source.EMR,
            since=TODAY - timedelta(days=rng.randint(90, 1600)),
            adherence_signal=rng.choice(["good", "good", "gaps"]),
        )
        for molecule, doses, per_day in DM_LADDER[:rungs]
    ]

    return PatientState(
        patient_id=f"SYN-DM-{seed:05d}",
        age=age,
        sex=rng.choice(["M", "F"]),
        as_of=TODAY,
        diagnoses=diagnoses,
        medications=medications,
        allergies=allergies,
        observations=observations,
        encounters=[
            PriorEncounter(
                encounter_id=f"D{seed}-{n}",
                encounter_date=TODAY - timedelta(days=120 * n),
                decision=rng.choice(["continue", "titrate_up"]),
                signed_by=f"PRAC-A-00{rng.randint(1, 2)}",
            )
            for n in range(1, 4)
        ],
        flags=flags,
        symptoms=symptoms,
        is_synthetic=True,
    )
