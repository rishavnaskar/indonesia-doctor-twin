"""Two pathways, one engine.

These tests exist to hold the claim the second pathway was built to test: that
the engine is pathway-agnostic and a new disease is data rather than a release.
If any of them start needing a special case for one disease, the claim has
stopped being true.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from datagen.synthetic import TODAY, make_patient
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.router.router import default_router
from service.rules import pathways
from service.rules.predicates import Context
from service.rules.targets import resolve_target
from service.signing import AuditLog, Signer
from service.state.models import Diagnosis, Medication, Observation, Source

NOW = datetime(2026, 8, 29, 10, 0)


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def _diabetic(seed=400, hba1c=8.2, egfr=88, age=52, mg=500, doses=2, **flags):
    state = make_patient(seed, controlled=True)
    state.age = age
    state.diagnoses = [Diagnosis(code="E11.9")]
    state.flags = {"has_dm": True, **flags}
    state.observations = [
        Observation("hba1c", hba1c, "%", TODAY, Source.EMR),
        Observation("egfr", egfr, "mL/min/1.73m2", TODAY - timedelta(days=20), Source.EMR),
    ]
    state.medications = [Medication("metformin", float(mg), doses, Source.EMR)]
    return state


def _run(rules, state, site_id="SITE-A"):
    site = rules.sites[site_id]
    return run_encounter(
        state, rules, site, default_router(), InMemoryRuntime(),
        thread_id="P1", signer=Signer(site["practitioners"][0]["practitioner_id"], True),
        audit=AuditLog(), now=NOW,
    )


def test_each_patient_routes_to_their_own_pathway(rules):
    assert pathways.select(rules, _diabetic()).name == "diabetes"
    assert pathways.select(rules, make_patient(301)).name == "hypertension"


def test_order_decides_when_both_could_claim_a_patient(rules):
    """Which problem leads is a clinical judgement, so it lives in the pack."""
    both = _diabetic()
    both.diagnoses.append(Diagnosis(code="I10"))
    assert rules.pathway_order[0] == "hypertension"
    assert pathways.select(rules, both).name == "hypertension"


def test_a_patient_no_pathway_covers_is_handed_off_not_crashed(rules):
    orphan = make_patient(500, controlled=True)
    orphan.diagnoses = [Diagnosis(code="J45")]
    orphan.flags = {}
    orphan.medications = []
    choice = pathways.select(rules, orphan)
    assert not choice.matched
    assert "No pathway" in choice.reason

    result = _run(rules, orphan)
    assert result.outcome is Outcome.HANDOFF
    assert result.proposal is None, "an unrouted encounter must cost zero tokens"


def test_the_pathway_view_does_not_mutate_the_pack(rules):
    """Two encounters on different pathways must not tread on each other."""
    before = rules.guideline["version"]
    view = pathways.with_pathway(rules, "diabetes")
    assert view.guideline["version"] != before
    assert rules.guideline["version"] == before


def test_a_target_is_not_always_a_blood_pressure(rules):
    """The contract that the second pathway broke, now generalised."""
    htn = pathways.with_pathway(rules, "hypertension")
    dm2 = pathways.with_pathway(rules, "diabetes")
    assert set(resolve_target(htn.guideline, Context(make_patient(301))).target.thresholds) \
        == {"sbp", "dbp"}
    assert set(resolve_target(dm2.guideline, Context(_diabetic())).target.thresholds) \
        == {"hba1c"}


def test_the_same_engine_drafts_titrates_and_escalates_for_diabetes(rules):
    at_target = _run(rules, _diabetic(hba1c=6.4))
    assert at_target.outcome is Outcome.COMMITTED
    assert at_target.proposal.recommendation.value == "continue"

    titrate = _run(rules, _diabetic(hba1c=8.2, mg=500, doses=2))
    assert titrate.proposal.recommendation.value == "titrate_up"
    assert titrate.proposal.medication_changes[0].molecule == "metformin"

    add = _run(rules, _diabetic(hba1c=8.2, mg=1000, doses=2))
    assert add.proposal.recommendation.value == "add_agent"
    assert add.proposal.medication_changes[0].molecule == "glimepiride"


def test_the_site_that_cannot_deliver_refers_on_this_pathway_too(rules):
    """SITE-C stocks metformin and not glimepiride, so the ladder runs out —
    the same shape of answer the hypertension pathway gives there."""
    result = _run(rules, _diabetic(hba1c=8.2, mg=1000, doses=2), site_id="SITE-C")
    assert result.proposal.recommendation.value == "refer"
    assert result.proposal.medication_changes == []


def test_this_pathway_abstains_on_groups_whose_target_it_has_not_extracted(rules):
    result = _run(rules, _diabetic(hba1c=8.2, age=70))
    assert result.outcome is Outcome.ABSTAIN
    assert "no_target_defined" in {f.rule_id for f in result.decision.blocking}


def test_its_own_red_flags_route_it_out(rules):
    hypo = _diabetic(hba1c=7.4)
    hypo.symptoms = {"hypoglycaemia": True}
    result = _run(rules, hypo)
    assert result.outcome is Outcome.ESCALATE
    assert "D3" in {f.rule_id for f in result.decision.blocking}


def test_its_own_exclusions_hand_off_before_any_draft(rules):
    result = _run(rules, _diabetic(egfr=22))
    assert result.outcome is Outcome.HANDOFF
    assert result.proposal is None


def test_a_ladder_step_missing_a_field_fails_at_load_not_at_a_bedside(rules):
    """Found by getting the step shape wrong on the new pathway: a missing key
    surfaced as a TypeError inside the reasoner, three layers from the cause and
    only for the patients unlucky enough to reach that rung."""
    import copy

    from service.packs import loader

    broken = copy.deepcopy(rules)
    broken.pathways = copy.deepcopy(rules.pathways)
    broken.pathways["diabetes"]["escalation_ladder"]["steps"][0].pop("start_mg")
    with pytest.raises(loader.PackError, match="missing"):
        loader._validate(broken)
