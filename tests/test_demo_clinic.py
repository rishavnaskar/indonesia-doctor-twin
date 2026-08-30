"""The interactive surface: patients built or uploaded in the browser.

The tests that matter here are about the residency boundary. Everything else is
plumbing; that one is a legal constraint expressed in code, and an interactive
demo is exactly where someone would casually paste in a real record.
"""

from __future__ import annotations

import pytest

from tools.demo.patients import PatientFormatError, from_wire, generate, to_wire
from tools.demo.run import run_patients, vocabulary


def test_generated_patients_are_marked_synthetic_because_they_are():
    rows = generate(3, seed=99)
    assert len(rows) == 3
    assert all(r["is_synthetic"] for r in rows)


def test_an_uploaded_record_is_not_synthetic_unless_it_says_so():
    """Real-until-proven-otherwise, for the one flag that decides whether a
    record may cross the residency boundary. A record is not synthetic just
    because it arrived through a form."""
    row = generate(1, seed=1)[0]
    del row["is_synthetic"]
    assert from_wire(row).is_synthetic is False


def test_an_unmarked_record_cannot_reach_a_hosted_model():
    """The guard refuses before the request is built, not after. This is the
    single most important behaviour on the interactive page."""
    from service.router.backends.hosted import HostedChatBackend, ResidencyError

    with pytest.raises(ResidencyError):
        HostedChatBackend().complete("sys", "user", allow_egress=False)


def test_a_residency_refusal_is_contained_to_one_visit():
    """It must show up as a failed encounter with its own words, never as a
    dead page."""
    from service.reason.model_reasoner import ModelReasoner
    from service.router.backends.hosted import HostedChatBackend
    from service.router.router import default_router

    router = default_router()
    router.register("model", ModelReasoner(HostedChatBackend()))
    router.default = "model"

    row = generate(1, seed=7)[0]
    row["is_synthetic"] = False
    result = run_patients([row], site_id="SITE-A", router=router)

    assert result["total"] == 1
    assert result["drafter_failures"] == 1
    assert "ResidencyError" in result["encounters"][0]["error"]


def test_a_hand_built_emergency_routes_out_of_the_pathway():
    patient = {
        "patient_id": "HAND-1", "age": 58, "sex": "M", "is_synthetic": True,
        "diagnoses": ["I10"],
        "medications": [{"molecule": "amlodipine", "mg_per_dose": 5, "doses_per_day": 1}],
        "observations": [
            {"code": "sbp", "value": 212, "age_days": 0},
            {"code": "dbp", "value": 130, "age_days": 0},
        ],
        "symptoms": {"chest_pain": True},
        "flags": {"on_antihypertensive_treatment": True},
    }
    result = run_patients([patient], site_id="SITE-A")
    encounter = result["encounters"][0]
    assert encounter["outcome"] == "escalate"
    assert encounter["presentation"]["band"] == "red"
    assert {f["rule_id"] for f in encounter["findings"]} >= {"R1"}


def test_the_same_missing_lab_means_different_things_at_different_hospitals():
    """The point of the interactive surface, and the clearest thing on it.

    A patient on maximum first-line therapy needs an ACE inhibitor next, which
    needs recent potassium and eGFR. With those missing, the *correct* answer
    depends on what the hospital can do: SITE-A can run both, so the system asks
    for them. SITE-C cannot, so asking would strand the patient — it is a
    referral instead. Same patient, same gap, two right answers."""
    patient = {
        "patient_id": "MOVE-1", "age": 60, "sex": "M", "is_synthetic": True,
        "diagnoses": ["I10"],
        "medications": [{"molecule": "amlodipine", "mg_per_dose": 10, "doses_per_day": 1}],
        "observations": [
            {"code": "sbp", "value": 162, "age_days": 0},
            {"code": "dbp", "value": 99, "age_days": 0},
        ],
        "flags": {"on_antihypertensive_treatment": True},
    }
    at_a = run_patients([patient], site_id="SITE-A")["encounters"][0]
    at_c = run_patients([patient], site_id="SITE-C")["encounters"][0]

    assert at_a["outcome"] == "request_info"
    assert not any(f["converts_to_referral"] for f in at_a["findings"])

    assert at_c["outcome"] == "abstain"
    assert any(f["converts_to_referral"] for f in at_c["findings"])
    assert {f["rule_id"] for f in at_c["findings"]} >= {"test_unavailable"}


def test_a_measurement_left_blank_is_a_measurement_not_taken():
    row = {"patient_id": "B", "age": 50, "sex": "M", "is_synthetic": True,
           "observations": [{"code": "k", "value": ""}, {"code": "sbp", "value": 150}]}
    state = from_wire(row)
    assert state.latest("k") is None
    assert state.latest("sbp") is not None


def test_bad_input_is_reported_not_guessed_at():
    with pytest.raises(PatientFormatError, match="age"):
        from_wire({"patient_id": "X", "age": "middle-aged"})
    with pytest.raises(PatientFormatError, match="between 1 and"):
        generate(99)


def test_the_form_vocabulary_comes_from_the_pack():
    """Hard-coding a drug list or a symptom set in the page would put the
    country back into the engine by the back door."""
    vocab = vocabulary()
    assert {m["molecule"] for m in vocab["molecules"]}
    assert {s["site_id"] for s in vocab["sites"]} == {"SITE-A", "SITE-B", "SITE-C"}
    assert any(s["code"] == "chest_pain" for s in vocab["symptoms"])
    assert len(vocab["checks"]) == 9


def test_wire_roundtrip_preserves_what_the_gate_reads():
    original = from_wire(generate(1, seed=3)[0])
    again = from_wire(to_wire(original))
    assert again.age == original.age
    assert again.is_synthetic == original.is_synthetic
    assert len(again.medications) == len(original.medications)
    assert again.latest("sbp").value == original.latest("sbp").value


def test_the_workflow_reports_the_phase_it_is_entering():
    """The slow phase is the model call, so a caller that cannot say which
    phase it is in can only report 'working' — which is what a hung process
    reports too."""
    from datetime import datetime

    from datagen.synthetic import make_patient
    from service.graph.runtime import InMemoryRuntime
    from service.graph.workflow import run_encounter
    from service.packs.loader import load_pack
    from service.router.router import default_router
    from service.signing import AuditLog, Signer

    rules = load_pack("id")
    seen: list[str] = []
    result = run_encounter(
        make_patient(101, controlled=True), rules, rules.sites["SITE-A"],
        default_router(), InMemoryRuntime(), thread_id="T",
        signer=Signer("PRAC-A-001", True), audit=AuditLog(),
        now=datetime(2026, 8, 29, 10, 0), on_step=seen.append,
    )
    assert seen[:6] == ["ROUTE", "ELIGIBLE", "INTAKE", "RECONCILE", "PROPOSE", "GATE"]
    # `on_step` says what is starting; `trail` says what finished. Conflating
    # them would make a crashed encounter look like a completed one.
    assert "FOLLOW-UP" in result.trail
    assert "FOLLOW-UP" not in seen


def test_a_step_signal_fires_for_an_encounter_that_leaves_the_pathway():
    from datetime import datetime

    from datagen.synthetic import make_patient
    from service.graph.runtime import InMemoryRuntime
    from service.graph.workflow import run_encounter
    from service.packs.loader import load_pack
    from service.router.router import default_router

    rules = load_pack("id")
    minor = make_patient(1, controlled=True)
    minor.age = 14
    seen: list[str] = []
    run_encounter(minor, rules, rules.sites["SITE-A"], default_router(),
                  InMemoryRuntime(), thread_id="T2",
                  now=datetime(2026, 8, 29, 10, 0), on_step=seen.append)
    assert seen[-1] == "HANDOFF"


def test_each_result_carries_what_the_audit_panel_needs():
    """'How do I know it actually checked?' has to be answerable per patient,
    without leaving the page."""
    result = run_patients(generate(1, seed=11), site_id="SITE-A")
    encounter = result["encounters"][0]
    assert len(encounter["checks"]) == 9
    assert all("title" in c and "description" in c for c in encounter["checks"])
    assert encounter["trail"]
    assert encounter["patient"]["labs_available"]
    assert encounter["patient"]["stocked"]
    provenance = encounter["proposal"]["provenance"]
    assert all("@" in pin for pin in provenance)
