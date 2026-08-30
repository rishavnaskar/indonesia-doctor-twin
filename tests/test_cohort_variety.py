"""The generated cohort has to be a cohort.

Four hundred patients who are all 45, on amlodipine alone, with no symptoms and
no allergies, test the pipeline against one patient four hundred times. These
tests exist because that is exactly what the generator used to produce: two
medication sets, one diagnosis, zero symptoms, zero allergies.

The bars are deliberately low. They are a floor against collapse, not a
specification of the distribution.
"""

from __future__ import annotations

import pytest

from datagen.synthetic import make_diabetic, make_patient
from service.packs.loader import load_pack
from tools.demo.patients import generate
from tools.demo.run import run_patients, vocabulary

COHORT = [make_patient(seed) for seed in range(300)]


def _distinct(attr):
    return {attr(p) for p in COHORT}


def test_regimens_vary():
    sets = _distinct(lambda p: tuple(sorted(m.molecule for m in p.medications)))
    assert len(sets) >= 4, sets


def test_doses_vary_within_a_molecule():
    doses = {m.mg_per_dose for p in COHORT for m in p.medications if m.molecule == "amlodipine"}
    assert len(doses) >= 2, doses


def test_the_problem_list_is_not_one_code_for_everybody():
    assert len(_distinct(lambda p: tuple(sorted(d.code for d in p.diagnoses)))) >= 3


def test_some_patients_report_something():
    """A cohort where nobody ever reports anything is not a cohort of well
    people, it is a cohort nobody asked."""
    reported = [p for p in COHORT if any(p.symptoms.values())]
    assert len(reported) >= 30


def test_a_clean_cohort_reports_nothing_alarming():
    """Benign complaints only. A red flag hiding in the clean set would make the
    false-block rate measure the generator rather than the gate."""
    red = {"chest_pain", "dyspnoea", "severe_headache", "visual_disturbance",
           "focal_neurological_deficit", "syncope", "altered_consciousness"}
    assert not [p for p in COHORT if red & {k for k, v in p.symptoms.items() if v}]


def test_some_patients_have_allergies():
    assert len([p for p in COHORT if p.allergies]) >= 20


def test_ages_span_the_pathway():
    ages = _distinct(lambda p: p.age)
    assert min(ages) < 25 and max(ages) > 55
    assert max(ages) < 65, "65+ has no extracted target and belongs to no_target"


def test_histories_are_not_all_the_same_length():
    assert len(_distinct(lambda p: len(p.series(("sbp",), limit=12)))) >= 3


def test_lab_staleness_varies():
    assert len(_distinct(lambda p: p.observation_age_days("k"))) >= 20


def test_a_controlled_patient_is_controlled_across_their_history():
    """The referral-back rule counts consecutive at-target visits off this
    history, so drift must not cross the line that defines the cohort."""
    for seed in range(60):
        patient = make_patient(seed, controlled=True)
        for _, values in patient.series(("sbp", "dbp"), limit=12):
            assert values.get("sbp", 0) <= 138 and values.get("dbp", 0) <= 88


def test_the_same_seed_is_the_same_person():
    a, b = make_patient(77), make_patient(77)
    assert a.age == b.age and a.sex == b.sex
    assert [m.molecule for m in a.medications] == [m.molecule for m in b.medications]
    assert [o.value for o in a.observations] == [o.value for o in b.observations]


def test_the_diabetes_cohort_varies_too():
    cohort = [make_diabetic(seed) for seed in range(120)]
    assert len({tuple(sorted(m.molecule for m in p.medications)) for p in cohort}) >= 2
    values = {p.latest("hba1c").value for p in cohort}
    assert len(values) >= 15


@pytest.mark.parametrize("profile,expected", [
    ("clean", "committed"),
    ("red_flag", "escalate"),
    ("hyperkalaemia", "escalate"),
    ("excluded_minor", "handoff"),
    ("excluded_first_presentation", "handoff"),
    ("dm:clean", "committed"),
    ("dm:red_flag", "escalate"),
    ("dm:excluded_insulin", "handoff"),
])
def test_every_offered_profile_lands_where_it_says(profile, expected):
    """A dropdown entry that does not do what its label says is worse than no
    entry: someone demonstrating the system will pick it and be surprised."""
    encounters = run_patients(generate(2, seed=4100, profile=profile),
                              site_id="SITE-A")["encounters"]
    assert [e["outcome"] for e in encounters] == [expected, expected]


def test_every_profile_in_the_dropdown_can_actually_be_generated():
    for entry in vocabulary()["profiles"]:
        assert generate(1, seed=7000, profile=entry["key"]), entry["key"]
