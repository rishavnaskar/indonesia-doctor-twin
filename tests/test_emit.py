"""Emission and the offline queue.

The properties under test are the ones that decide whether a remote hospital can
use this at all: nothing lost across a power cut, nothing duplicated across a
retry, and provenance surviving the trip outward.
"""

import json
from datetime import datetime

import pytest

from datagen.synthetic import make_patient
from service.emit.coding import CodedDiagnosis, build_claim
from service.emit.fhir import build_bundle
from service.emit.queue import ItemStatus, OutboundQueue
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.router.router import default_router
from service.signing import AuditLog, Signer
from service.state.models import Diagnosis

NOW = datetime(2026, 8, 29, 10, 0)


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


# ------------------------------------------------------------------ coding

def test_a_code_without_evidence_cannot_be_constructed(rules):
    """Not a policy. Not representable."""
    with pytest.raises(ValueError, match="evidence"):
        CodedDiagnosis(code="E11.9", label="t2dm", primary=False, evidence_ref="")


def test_secondary_codes_come_only_from_the_recorded_problem_list(rules):
    state = make_patient(301, controlled=True)
    claim = build_claim(state, rules)
    assert claim.primary.code == "I10"
    # Not "there are none" — generated patients now carry real comorbidities.
    # The invariant is that every secondary code points at something already in
    # the record. A code without a supporting entry is upcoding.
    recorded = {d.code for d in state.diagnoses}
    for secondary in claim.secondary:
        assert secondary.code in recorded
        assert secondary.evidence_ref == f"problem-list:{secondary.code}"

    before = {d.code for d in claim.secondary}
    state.diagnoses.append(Diagnosis(code="N18.3"))
    claim = build_claim(state, rules)
    after = {d.code for d in claim.secondary}
    # Adding one condition adds exactly one code, and disturbs none of the rest.
    assert after - before == {"N18.3"}
    assert before <= after


# -------------------------------------------------------------------- fhir

def test_bundle_carries_evidence_and_provenance(rules):
    state = make_patient(302, controlled=True)
    claim = build_claim(state, rules)
    bundle = build_bundle(state, claim, None, rules.sites["SITE-A"], "PRAC-A-001",
                          rules, encounter_id="E1")

    resources = [e["resource"] for e in bundle.payload["entry"]]
    conditions = [r for r in resources if r["resourceType"] == "Condition"]
    observations = [r for r in resources if r["resourceType"] == "Observation"]

    assert all("evidence:" in c["note"][0]["text"] for c in conditions)
    # A patient-reported reading must not arrive looking like a lab result.
    assert all("source:" in o["note"][0]["text"] for o in observations)


def test_the_same_content_produces_the_same_key(rules):
    state = make_patient(303, controlled=True)
    claim = build_claim(state, rules)
    args = (state, claim, None, rules.sites["SITE-A"], "PRAC-A-001", rules)
    first = build_bundle(*args, encounter_id="E1")
    second = build_bundle(*args, encounter_id="E1")
    assert first.idempotency_key == second.idempotency_key


def test_changed_content_produces_a_different_key(rules):
    state = make_patient(304, controlled=True)
    before = build_bundle(state, build_claim(state, rules), None,
                          rules.sites["SITE-A"], "PRAC-A-001", rules, encounter_id="E1")
    state.diagnoses.append(Diagnosis(code="E78.5"))
    after = build_bundle(state, build_claim(state, rules), None,
                         rules.sites["SITE-A"], "PRAC-A-001", rules, encounter_id="E1")
    assert before.idempotency_key != after.idempotency_key, (
        "a correction must not be swallowed as a duplicate"
    )


# ------------------------------------------------------------------- queue

def test_replaying_an_encounter_does_not_duplicate_it(tmp_path):
    queue = OutboundQueue(path=tmp_path / "q.jsonl")
    for _ in range(5):
        queue.enqueue("bundle", {"a": 1}, "enc-1:abc", NOW)
    assert len(queue) == 1


def test_a_failed_send_stays_pending_rather_than_vanishing(tmp_path):
    queue = OutboundQueue(path=tmp_path / "q.jsonl")
    queue.enqueue("bundle", {"a": 1}, "enc-1:abc", NOW)

    def offline(item):
        raise ConnectionError("no network")

    result = queue.drain(offline)
    assert result == {"sent": 0, "failed": 1, "still_pending": 1}
    assert queue.pending()[0].attempts == 1


def test_one_unreachable_item_does_not_block_the_rest(tmp_path):
    queue = OutboundQueue(path=tmp_path / "q.jsonl")
    queue.enqueue("bundle", {"n": 1}, "a", NOW)
    queue.enqueue("bundle", {"n": 2}, "b", NOW)

    def flaky(item):
        if item.idempotency_key == "a":
            raise ConnectionError("stuck")

    result = queue.drain(flaky)
    assert result["sent"] == 1 and result["still_pending"] == 1


def test_the_queue_survives_a_power_cut(tmp_path):
    path = tmp_path / "q.jsonl"
    queue = OutboundQueue(path=path)
    queue.enqueue("bundle", {"a": 1}, "enc-1:abc", NOW)
    queue.enqueue("bundle", {"b": 2}, "enc-2:def", NOW)
    queue.drain(lambda item: None, max_items=1)

    # Process dies here. Nothing else is graceful about a power cut.
    restarted = OutboundQueue(path=path)
    assert len(restarted) == 2
    assert len(restarted.pending()) == 1
    assert restarted.items["enc-1:abc"].status is ItemStatus.SENT


def test_a_committed_encounter_is_enqueued_exactly_once(rules, tmp_path):
    queue = OutboundQueue(path=tmp_path / "q.jsonl")
    state = make_patient(305, controlled=True)
    result = run_encounter(
        state, rules, rules.sites["SITE-A"], default_router(), InMemoryRuntime(),
        thread_id="ENC-9", signer=Signer("PRAC-A-001", True), audit=AuditLog(),
        now=NOW, queue=queue,
    )
    assert result.outcome is Outcome.COMMITTED
    assert len(queue) == 1
    assert json.loads(queue.pending()[0].to_json())["kind"] == "encounter_bundle"


def test_a_refused_encounter_enqueues_nothing(rules, tmp_path):
    queue = OutboundQueue(path=tmp_path / "q.jsonl")
    state = make_patient(306, controlled=False)
    state.diagnoses.append(Diagnosis(code="E11.9"))
    result = run_encounter(
        state, rules, rules.sites["SITE-A"], default_router(), InMemoryRuntime(),
        thread_id="ENC-10", signer=Signer("PRAC-A-001", True), audit=AuditLog(),
        now=NOW, queue=queue,
    )
    assert result.outcome is Outcome.ABSTAIN
    assert len(queue) == 0
