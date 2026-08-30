"""Synthetic patients.

The pipes are real; the patients are not. Synthetic data is the only lawful
basis this system runs on, so every patient here is generated — and being loud
about which parts are fabricated is the discipline. The formulary, the guideline
rules, the site capability registry and the interoperability path are all real.

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

# What the reference proposer walks, mirrored here so a generated patient's
# regimen sits somewhere sensible on it.
LADDER = [
    ("ccb_dihydropyridine", "amlodipine", [5.0, 10.0], 1),
    ("acei", "captopril", [12.5, 25.0], 2),
    ("thiazide", "hydrochlorothiazide", [12.5, 25.0], 1),
]

# Alternatives at the same rung, so 400 patients are not all on the same three
# drugs. Every one is on the pack's prescribable list.
ALTERNATIVES = {
    "captopril": [("lisinopril", [5.0, 10.0, 20.0], 1), ("ramipril", [2.5, 5.0], 1)],
    "amlodipine": [],
    "hydrochlorothiazide": [],
}

# Comorbidities that do not block a target and do not exclude. They exist so
# secondary coding, and the reader, have something to work with.
SAFE_COMORBIDITY = [("E78.5", "has_dyslipidaemia"), ("I11.9", None)]

# Complaints that are not red flags. A cohort where nobody ever reports anything
# is not a cohort of well people, it is a cohort nobody asked.
BENIGN_SYMPTOMS = ["cough", "dizziness", "swelling"]


def _obs(code, value, days_ago, source=Source.EMR, unit="") -> Observation:
    units = {"sbp": "mmHg", "dbp": "mmHg", "k": "mmol/L",
             "egfr": "mL/min/1.73m2", "hba1c": "%"}
    return Observation(
        code=code,
        value=float(value),
        unit=unit or units.get(code, ""),
        taken_at=TODAY - timedelta(days=days_ago),
        source=source,
    )


def _regimen(rng, rungs: int) -> list[Medication]:
    """A plausible regimen `rungs` deep, with the molecule and dose varied.

    Never places an ACE inhibitor and an ARB together — that is interaction X1,
    and a generated patient who already violates a blocking rule would make the
    false-block rate measure the generator rather than the gate.
    """
    out = []
    for _, molecule, doses, per_day in LADDER[:rungs]:
        options = [(molecule, doses, per_day)] + ALTERNATIVES.get(molecule, [])
        chosen, dose_options, chosen_per_day = rng.choice(options)
        out.append(
            Medication(
                molecule=chosen,
                mg_per_dose=rng.choice(dose_options),
                doses_per_day=chosen_per_day,
                source=Source.EMR,
                since=TODAY - timedelta(days=rng.randint(60, 1400)),
                adherence_signal=rng.choice(["good", "good", "good", "gaps", "unknown"]),
            )
        )
    return out


DM_LADDER = [("metformin", [500.0, 850.0, 1000.0], 2), ("glimepiride", [1.0, 2.0], 1)]


def make_diabetic(seed: int, *, controlled: bool | None = None,
                  profile: str = "clean") -> PatientState:
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
    diagnoses = [Diagnosis(code=rng.choice(["E11.9", "E11.6", "E11.8"]),
                           onset=TODAY - timedelta(days=rng.randint(300, 5000)))]
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

    observations = [_obs("hba1c", hba1c, lab_age),
                    _obs("egfr", egfr_value, lab_age)]
    for n in range(1, rng.randint(2, 5)):
        drift = round(rng.uniform(-0.5, 0.5), 1)
        prior = min(hba1c + drift, 6.9) if controlled else max(hba1c + drift, 7.1)
        observations.append(_obs("hba1c", round(prior, 1), lab_age + 120 * n))

    medications = [
        Medication(molecule=molecule, mg_per_dose=rng.choice(doses),
                   doses_per_day=per_day, source=Source.EMR,
                   since=TODAY - timedelta(days=rng.randint(90, 1600)),
                   adherence_signal=rng.choice(["good", "good", "gaps"]))
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
            PriorEncounter(encounter_id=f"D{seed}-{n}",
                           encounter_date=TODAY - timedelta(days=120 * n),
                           decision=rng.choice(["continue", "titrate_up"]),
                           signed_by=f"PRAC-A-00{rng.randint(1, 2)}")
            for n in range(1, 4)
        ],
        flags=flags,
        symptoms=symptoms,
        is_synthetic=True,
    )


def make_patient(
    seed: int,
    *,
    controlled: bool | None = None,
    profile: str = "clean",
) -> PatientState:
    """One follow-up patient, generated.

    `profile` selects the shape of the case; everything else varies with the
    seed. The variation is the point: a cohort where every patient is 45, on
    amlodipine alone, with no symptoms and no allergies, tests the pipeline
    against one patient four hundred times.

    Seeded and deterministic — the same seed gives the same person, so a
    scorecard regression is a real change and never a reshuffle.

    `clean` is deliberately kept inside the pathway's bounds: adult under 65, no
    comorbidity that blocks a target, no exclusion, no red flag. Anything that
    should stop the system has its own profile, because a clean set that
    quietly contains blockers measures the generator rather than the gate.
    """
    rng = random.Random(seed)

    age = rng.randint(18, 64)
    sex = rng.choice(["M", "F"])
    flags: dict[str, bool] = {"on_antihypertensive_treatment": True}
    symptoms: dict[str, bool] = {}
    diagnoses = [Diagnosis(code="I10", onset=TODAY - timedelta(days=rng.randint(200, 4000)))]
    intolerances: list[Intolerance] = []
    allergies: list[Allergy] = []
    observations: list[Observation] = []

    if controlled is None:
        controlled = rng.random() < 0.5

    if controlled:
        sbp, dbp = rng.randint(112, 138), rng.randint(66, 88)
    else:
        sbp, dbp = rng.randint(142, 178), rng.randint(88, 108)

    lab_age = rng.randint(5, 80)
    k_value = round(rng.uniform(3.5, 5.1), 1)
    egfr_value = rng.randint(46, 112)
    rungs = 1 if controlled else rng.randint(1, 2)

    # A third of patients report something, and in a clean case it is benign.
    if rng.random() < 0.34:
        symptoms[rng.choice(BENIGN_SYMPTOMS)] = True

    # One in six carries a painkiller allergy. Never a drug this pathway would
    # propose, so it varies the record without blocking a correct plan.
    if rng.random() < 0.17:
        allergies.append(Allergy(substance=rng.choice(["ibuprofen", "diclofenac"]),
                                 reaction=rng.choice(["rash", "wheeze", None])))

    # One in four has a second coded condition, which is what gives the claim
    # draft a secondary code to find.
    if rng.random() < 0.25:
        code, flag = rng.choice(SAFE_COMORBIDITY)
        diagnoses.append(Diagnosis(code=code))
        if flag:
            flags[flag] = True

    # ---- profile adjustments ---------------------------------------------
    forced_max_first_line = False
    if profile == "no_target":
        which = rng.choice(["dm", "ckd", "elderly"])
        if which == "dm":
            flags["has_dm"] = True
            diagnoses.append(Diagnosis(code="E11.9"))
        elif which == "ckd":
            flags["has_ckd"] = True
            diagnoses.append(Diagnosis(code="N18.3"))
        else:
            age = rng.randint(65, 88)

    elif profile == "stale_labs":
        lab_age = rng.randint(120, 500)
        # Above target and already at the top of the first rung, so the ladder
        # wants an ACE inhibitor — which is what makes stale potassium and eGFR
        # matter. On a controlled patient the correct plan is "continue", which
        # needs no labs and would make this entry look broken.
        controlled = False
        sbp, dbp = rng.randint(146, 172), rng.randint(92, 106)
        rungs = 1
        forced_max_first_line = True

    elif profile == "red_flag":
        sbp, dbp = rng.randint(182, 215), rng.randint(118, 132)
        symptoms[rng.choice(["chest_pain", "dyspnoea", "severe_headache",
                             "visual_disturbance", "focal_neurological_deficit"])] = True

    elif profile == "hyperkalaemia":
        k_value = round(rng.uniform(5.6, 6.4), 1)
        rungs = 2  # on a RAAS-acting drug, which is what makes it matter

    elif profile == "acei_intolerant":
        intolerances.append(Intolerance(
            molecule="captopril", drug_class="acei",
            documented_at=TODAY - timedelta(days=rng.randint(40, 700)),
            reaction="persistent dry cough"))
        rungs = 1  # on the CCB only; the ACE inhibitor was stopped

    elif profile == "polypharmacy":
        rungs = 3
        controlled = False

    elif profile == "excluded_pregnancy":
        sex = "F"
        age = rng.randint(19, 41)
        flags["pregnancy_positive"] = True

    elif profile == "excluded_minor":
        age = rng.randint(11, 17)

    elif profile == "excluded_first_presentation":
        flags["is_first_presentation"] = True

    elif profile == "excluded_secondary":
        diagnoses.append(Diagnosis(code="I15.0"))

    elif profile == "excluded_resistant":
        flags["resistant_hypertension"] = True
        rungs = 3

    elif profile == "excluded_renal":
        egfr_value = rng.randint(9, 28)

    elif profile == "excluded_other":
        flags[rng.choice(["active_oncology", "psychiatric_crisis",
                          "controlled_substance_request"])] = True

    # ---- observations -----------------------------------------------------
    observations += [_obs("sbp", sbp, 0), _obs("dbp", dbp, 0)]
    # Between two and five prior visits, so the history is not a fixed shape.
    #
    # Drift is clamped so it cannot cross the line that defines the cohort: a
    # "controlled" patient whose earlier readings wander above target is not a
    # controlled patient, and the referral-back rule counts consecutive
    # at-target visits off exactly this history.
    for n in range(1, rng.randint(3, 6)):
        prior_sbp = sbp + rng.randint(-9, 9)
        prior_dbp = dbp + rng.randint(-6, 6)
        if controlled:
            prior_sbp, prior_dbp = min(prior_sbp, 138), min(prior_dbp, 88)
        else:
            prior_sbp, prior_dbp = max(prior_sbp, 142), max(prior_dbp, 90)
        observations.append(_obs("sbp", prior_sbp, 90 * n))
        observations.append(_obs("dbp", prior_dbp, 90 * n))

    observations.append(_obs("k", k_value, lab_age))
    observations.append(_obs("egfr", egfr_value, lab_age))
    if rng.random() < 0.3:
        observations.append(_obs("creatinine", round(rng.uniform(0.7, 1.3), 2),
                                 lab_age, unit="mg/dL"))

    medications = _regimen(rng, rungs)
    if forced_max_first_line and medications:
        first = medications[0]
        medications[0] = Medication(
            molecule="amlodipine", mg_per_dose=10.0, doses_per_day=1,
            source=first.source, since=first.since,
            adherence_signal=first.adherence_signal,
        )

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
