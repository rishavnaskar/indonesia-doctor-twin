"""SPEC-V1 §5.3 — reconciliation.

One rule, and every test here is about it: discrepancies are surfaced, never
silently resolved. Both sources are routinely wrong in different ways, so a
system that picks a winner is guessing about what someone is currently
swallowing.
"""

from __future__ import annotations

import pytest

from datagen.synthetic import make_patient
from service.packs.loader import load_pack
from service.reconcile.engine import reconcile
from service.state.models import Medication, Source


class FakeIntake:
    def __init__(self, **answers):
        self.answers = answers


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def test_no_disagreement_produces_nothing(rules):
    assert not reconcile(make_patient(101, controlled=True), rules)


def test_a_different_dose_is_reported_and_neither_side_is_changed(rules):
    state = make_patient(101, controlled=True)
    recorded = state.medications[0]
    state.medications.append(
        Medication(recorded.molecule, recorded.mg_per_dose * 2, 1, Source.PATIENT_REPORTED)
    )
    result = reconcile(state, rules)

    found = [d for d in result.discrepancies if d.kind == "dose_differs"]
    assert len(found) == 1
    assert found[0].material
    assert found[0].record_says and found[0].patient_says
    # The record still says what it said.
    assert state.medications[0].mg_per_dose == recorded.mg_per_dose


def test_a_drug_the_record_does_not_have_is_flagged(rules):
    state = make_patient(101, controlled=True)
    state.medications.append(Medication("ibuprofen", 400.0, 3, Source.PATIENT_REPORTED))
    kinds = {d.kind for d in reconcile(state, rules).discrepancies}
    assert "not_in_record" in kinds


def test_silence_is_not_a_report_that_they_take_nothing(rules):
    """With no patient-reported list at all, the record's own entries must not
    be read as 'the patient did not mention this'."""
    state = make_patient(101, controlled=True)
    assert not any(
        d.kind == "missing_from_report" for d in reconcile(state, rules).discrepancies
    )


def test_a_drug_the_patient_did_not_mention_is_flagged_once_they_have_listed_something(rules):
    state = make_patient(101, controlled=True)
    state.medications.append(Medication("ibuprofen", 400.0, 3, Source.PATIENT_REPORTED))
    kinds = {d.kind for d in reconcile(state, rules).discrepancies}
    assert "missing_from_report" in kinds


def test_stopping_medication_is_material_and_removes_nothing(rules):
    state = make_patient(101, controlled=True)
    before = len(state.medications)
    result = reconcile(state, rules, FakeIntake(adherence="stopped"))
    stopped = [d for d in result.discrepancies if d.kind == "stopped_medication"]
    assert stopped and stopped[0].material
    assert len(state.medications) == before, "a patient's word never edits the record"


def test_an_outside_painkiller_only_interacts_when_the_record_warrants_it(rules):
    """The interaction comes from the pack's own rules, not from a hunch. An
    NSAID matters alongside an ACE inhibitor and not alongside a calcium
    channel blocker, and the surface should say which."""
    on_ccb = make_patient(102, controlled=False)
    on_ccb.medications = [Medication("amlodipine", 5.0, 1, Source.EMR)]
    quiet = reconcile(on_ccb, rules, FakeIntake(outside_medication="painkiller"))
    assert quiet.discrepancies[0].interacts_with == ()

    on_acei = make_patient(102, controlled=False)
    on_acei.medications = [Medication("captopril", 25.0, 2, Source.EMR)]
    loud = reconcile(on_acei, rules, FakeIntake(outside_medication="painkiller"))
    assert loud.discrepancies[0].interacts_with == ("captopril",)


def test_an_answer_of_none_is_not_a_discrepancy(rules):
    state = make_patient(101, controlled=True)
    result = reconcile(state, rules, FakeIntake(outside_medication="none", adherence="always"))
    assert not result.discrepancies


def test_phrasing_comes_from_the_pack(rules):
    state = make_patient(101, controlled=True)
    result = reconcile(state, rules, FakeIntake(adherence="stopped"))
    assert result.discrepancies[0].text
    stripped = load_pack("id")
    stripped.language = {}
    assert not reconcile(state, stripped, FakeIntake(adherence="stopped")).discrepancies


def test_a_material_discrepancy_reaches_the_clinician_as_amber(rules):
    """It is not a gate finding — nothing is wrong with the draft. It is a
    disagreement about what the patient is taking, and only the clinician can
    resolve it."""
    from service.present.layer import Band, Labels, present

    labels = Labels.from_pack(rules.language)
    state = make_patient(101, controlled=True)
    discrepancies = reconcile(state, rules, FakeIntake(adherence="stopped")).discrepancies

    quiet = present("committed", labels)
    assert quiet.band is Band.GREEN

    loud = present("committed", labels, discrepancies=tuple(discrepancies))
    assert loud.band is Band.AMBER
    assert loud.shows_draft, "the draft is annotated, not withheld"
    assert any("stopped" in line.text.lower() for line in loud.lines)


def test_discrepancies_survive_a_refusal(rules):
    """A patient who says they stopped their medication is the most useful
    thing the visit produced. Losing it because the gate declined to draft
    would be the worst possible trade."""
    from datetime import datetime

    from service.graph.runtime import InMemoryRuntime
    from service.graph.workflow import run_encounter
    from service.router.router import default_router

    minor = make_patient(1, controlled=True)
    minor.age = 14

    class Intake(FakeIntake):
        questions_for_clinician: list[str] = []

        def symptoms(self):
            return {}

    result = run_encounter(
        minor, rules, rules.sites["SITE-A"], default_router(), InMemoryRuntime(),
        thread_id="R1", now=datetime(2026, 8, 29, 10, 0),
        intake=Intake(adherence="stopped"),
    )
    assert result.outcome.value == "handoff"
    assert any(d.kind == "stopped_medication" for d in result.reconciliation.discrepancies)
