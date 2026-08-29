"""The encounter workflow, end to end.

The tests worth having here are the ones about *routing*: which terminal state
a patient reaches, and whether anything with clinical effect escaped without a
signature.
"""

from datetime import datetime

import pytest

from datagen.synthetic import make_patient
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.router.router import default_router
from service.signing import AuditLog, SignatureRefused, Signer
from service.state.models import Diagnosis, Observation, Source

NOW = datetime(2026, 8, 29, 10, 0)


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def _run(rules, state, site="SITE-A", signer_id="PRAC-A-001", **kwargs):
    audit = kwargs.pop("audit", AuditLog())
    return (
        run_encounter(
            state, rules, rules.sites[site], default_router(), InMemoryRuntime(),
            thread_id="t", signer=Signer(signer_id, True), audit=audit, now=NOW, **kwargs
        ),
        audit,
    )


def test_a_routine_visit_reaches_a_signed_coded_encounter(rules):
    result, audit = _run(rules, make_patient(201, controlled=True))
    assert result.outcome is Outcome.COMMITTED
    assert result.claim.primary.code == "I10"
    assert len(audit.records) == 1


def test_an_excluded_patient_never_reaches_the_model(rules):
    result, audit = _run(rules, make_patient(202, profile="excluded_pregnancy"))
    assert result.outcome is Outcome.HANDOFF
    assert result.proposal is None, "an excluded encounter must cost zero tokens"
    assert result.trail == ["ELIGIBLE", "HANDOFF"]
    assert not audit.records


def test_a_red_flag_escalates_and_drafts_nothing(rules):
    state = make_patient(203, controlled=False)
    state.observations.append(Observation("sbp", 210, "mmHg", state.as_of, Source.EMR))
    state.observations.append(Observation("dbp", 130, "mmHg", state.as_of, Source.EMR))
    state.symptoms["chest_pain"] = True
    result, audit = _run(rules, state)
    assert result.outcome is Outcome.ESCALATE
    assert not audit.records, "nothing may be signed on an escalated encounter"


def test_missing_labs_produce_a_request_not_a_plan(rules):
    state = make_patient(204, controlled=False)
    state.medications = [m for m in state.medications if m.molecule == "amlodipine"]
    state.medications[0] = type(state.medications[0])(
        molecule="amlodipine", mg_per_dose=10.0, doses_per_day=1, source=Source.EMR
    )
    state.observations = [o for o in state.observations if o.code not in ("k", "egfr")]
    result, _ = _run(rules, state)
    assert result.outcome in (Outcome.REQUEST_INFO, Outcome.ABSTAIN)
    assert result.claim is None


def test_a_coded_only_comorbidity_declines(rules):
    state = make_patient(205, controlled=False)
    state.flags.pop("has_dm", None)
    state.diagnoses.append(Diagnosis(code="E11.9"))
    result, audit = _run(rules, state)
    assert result.outcome is Outcome.ABSTAIN
    assert not audit.records


def test_nothing_is_committed_without_a_signer(rules):
    result = run_encounter(
        make_patient(206, controlled=True), rules, rules.sites["SITE-A"],
        default_router(), InMemoryRuntime(), thread_id="t", signer=None, now=NOW,
    )
    assert result.outcome is Outcome.PRESENTED
    assert result.claim is None, "no coding happens before a signature"


def test_a_rejected_draft_emits_nothing(rules):
    result, audit = _run(rules, make_patient(207, controlled=True), decision="rejected")
    assert result.claim is None
    assert audit.records[0].decision == "rejected"


def test_a_signature_from_another_site_is_refused(rules):
    """Caught a real mistake in the demo script before it caught a real one here."""
    with pytest.raises(SignatureRefused):
        _run(rules, make_patient(208, controlled=True), site="SITE-C",
             signer_id="PRAC-A-001")


def test_secondary_codes_carry_their_evidence(rules):
    state = make_patient(209, controlled=True)
    state.diagnoses.append(Diagnosis(code="E78.5"))
    result, _ = _run(rules, state)
    assert result.claim.secondary
    assert all(d.evidence_ref for d in result.claim.secondary)


def test_referral_back_is_drafted_only_when_stability_criteria_hold(rules):
    stable, _ = _run(rules, make_patient(210, controlled=True))
    assert stable.referral_back.eligible
    assert "RUJUK BALIK" in stable.referral_back.draft

    unstable, _ = _run(rules, make_patient(211, controlled=False))
    if unstable.outcome is Outcome.COMMITTED:
        assert not unstable.referral_back.eligible
