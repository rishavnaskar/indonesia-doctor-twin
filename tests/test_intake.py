"""The bounded interviewer and the pressure suite.

The property being tested is that the patient-facing surface has no clinical
voice — not that it has been told to be careful, but that it has no way to
express a clinical opinion at all.
"""

from datetime import datetime

import pytest

from datagen.synthetic import make_patient
from eval.pressure import CASES, bounded_interviewer, run_suite, sycophant_stub
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.intake.interview import Interviewer, TurnKind
from service.packs.loader import load_pack
from service.router.router import default_router
from service.signing import AuditLog, Signer


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def _complete(interviewer):
    interviewer.answer("always")
    interviewer.answer(["none"])
    interviewer.answer(["none"])
    interviewer.skip()
    return interviewer.answer("none")


# ------------------------------------------------------------- the interview

def test_a_complete_interview_closes(rules):
    interviewer = Interviewer(rules)
    assert _complete(interviewer).kind is TurnKind.CLOSING
    assert interviewer.result.complete


def test_an_invalid_answer_does_not_advance(rules):
    interviewer = Interviewer(rules)
    first = interviewer.current().question_id
    interviewer.answer("kadang saja mungkin")   # not one of the options
    assert interviewer.current().question_id == first


def test_a_clinical_question_gets_the_fixed_deflection(rules):
    interviewer = Interviewer(rules)
    reply = interviewer.answer("Apakah tekanan darah saya berbahaya?")
    assert reply.kind is TurnKind.DEFLECTION
    assert reply.text == Interviewer(rules)._deflection, "the deflection never varies"


def test_the_deflection_is_identical_however_hard_the_patient_pushes(rules):
    interviewer = Interviewer(rules)
    replies = {
        interviewer.answer(utterance).text
        for utterance in CASES[0].turns
    }
    assert len(replies) == 1, "the interviewer must not vary its refusal under pressure"


def test_patient_questions_reach_the_clinician_unanswered(rules):
    interviewer = Interviewer(rules)
    interviewer.answer("Boleh saya berhenti minum obat?")
    assert interviewer.result.questions_for_clinician == ["Boleh saya berhenti minum obat?"]
    assert not interviewer.result.answers, "a question is not an answer"


def test_a_required_question_cannot_be_skipped(rules):
    interviewer = Interviewer(rules)
    assert interviewer.skip().kind is TurnKind.DEFLECTION
    assert interviewer.current().question_id == "adherence"


def test_home_readings_are_range_checked(rules):
    interviewer = Interviewer(rules)
    interviewer.answer("always")
    interviewer.answer(["none"])
    interviewer.answer(["none"])
    assert interviewer.answer([900, 400]).kind is TurnKind.DEFLECTION
    assert interviewer.answer([135, 85]).kind is TurnKind.QUESTION


# --------------------------------------------------------- into the workflow

def test_a_reported_symptom_reaches_the_red_flag_rules(rules):
    interviewer = Interviewer(rules)
    interviewer.answer("always")
    interviewer.answer(["none"])
    interviewer.answer(["chest_pain"])
    interviewer.skip()
    interviewer.answer("none")

    result = run_encounter(
        make_patient(401, controlled=True), rules, rules.sites["SITE-A"],
        default_router(), InMemoryRuntime(), thread_id="t",
        signer=Signer("PRAC-A-001", True), audit=AuditLog(),
        now=datetime(2026, 8, 29, 10, 0), intake=interviewer.result,
    )
    assert result.outcome is Outcome.ESCALATE


def test_patient_questions_survive_even_a_handoff(rules):
    interviewer = Interviewer(rules)
    interviewer.answer("Kenapa saya harus minum obat seumur hidup?")
    _complete(interviewer)

    result = run_encounter(
        make_patient(402, profile="excluded_pregnancy"), rules, rules.sites["SITE-A"],
        default_router(), InMemoryRuntime(), thread_id="t",
        signer=Signer("PRAC-A-001", True), audit=AuditLog(),
        now=datetime(2026, 8, 29, 10, 0), intake=interviewer.result,
    )
    assert result.outcome is Outcome.HANDOFF
    assert result.questions_for_clinician == ["Kenapa saya harus minum obat seumur hidup?"]


# ------------------------------------------------------------ pressure suite

def test_the_shipped_surface_never_capitulates(rules):
    report = run_suite(bounded_interviewer(rules), "bounded")
    assert report.rate == 0.0


def test_the_harness_catches_a_sycophant(rules):
    """Without this, the zero above means nothing at all."""
    report = run_suite(sycophant_stub, "control")
    assert report.rate > 0.0
    assert all(o.turn is not None for o in report.outcomes if o.capitulated)
