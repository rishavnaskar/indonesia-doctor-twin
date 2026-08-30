"""The second-model review.

Every test here is about a constraint rather than a capability. A critic that
can only lower confidence is a safeguard; one that can raise it is a model with
veto over the abstention floor.
"""

from __future__ import annotations

import json

import pytest

from service.contracts.proposal import (
    Assessment,
    ChangeAction,
    MedicationChange,
    Proposal,
    Provenance,
    Recommendation,
)
from service.packs.loader import load_pack
from service.reason.critic import CriticReviewedReasoner
from datagen.synthetic import make_patient


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def _draft(confidence=0.9):
    return Proposal(
        assessment=Assessment("uncontrolled"),
        recommendation=Recommendation("titrate_up"),
        bp_trend_summary="rising",
        target_used=None,
        confidence=confidence,
        provenance=Provenance(model="m@1", prompt_template="p@1", corpus="c@1"),
        medication_changes=[
            MedicationChange(ChangeAction("increase"), "amlodipine", 10.0, 1, "above target", "c")
        ],
    )


class Inner:
    def __init__(self, proposal):
        self.proposal = proposal

    def propose(self, state, rules, site=None):
        return self.proposal


class Critic:
    """A critic backend returning a scripted verdict, or raising."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.saw_schema = None
        self.saw_egress = None

    def complete(self, system, user, *, allow_egress, schema=None):
        self.saw_schema = schema
        self.saw_egress = allow_egress
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return json.dumps(self.verdict)


def _run(rules, proposal, verdict):
    state = make_patient(3, controlled=False)
    state.is_synthetic = True
    critic = Critic(verdict)
    result = CriticReviewedReasoner(Inner(proposal), critic).propose(
        state, rules, rules.sites["SITE-A"]
    )
    return result, critic


def test_a_worried_critic_lowers_the_confidence(rules):
    result, _ = _run(rules, _draft(0.9), {"acceptable_as_drafted": 0.3,
                                          "concerns": ["ignores the falling eGFR"]})
    assert result.confidence == pytest.approx(0.3)
    assert "ignores the falling eGFR" in result.uncertainty_notes


def test_a_happy_critic_cannot_raise_it(rules):
    """The constraint that makes this safe to have at all. There is no path by
    which a critic's approval rescues a draft the drafter was unsure of."""
    result, _ = _run(rules, _draft(0.4), {"acceptable_as_drafted": 1.0, "concerns": []})
    assert result.confidence == pytest.approx(0.4)


def test_a_critic_that_fails_leaves_the_draft_marked_unreviewed(rules):
    """An advisory component being down is not a reason to deny care. Silently
    treating an unreviewed draft as a reviewed one would make the safeguard
    unfalsifiable, which is worse than not having it."""
    result, _ = _run(rules, _draft(0.9), RuntimeError("rate limited"))
    assert result.confidence == pytest.approx(0.9)
    assert "unreviewed" in result.uncertainty_notes
    assert "RuntimeError" in result.uncertainty_notes


def test_an_unparseable_verdict_is_a_failure_not_a_pass(rules):
    class Junk(Critic):
        def complete(self, system, user, *, allow_egress, schema=None):
            return "I think it looks fine to me!"

    state = make_patient(3, controlled=False)
    state.is_synthetic = True
    result = CriticReviewedReasoner(Inner(_draft(0.9)), Junk(None)).propose(
        state, rules, rules.sites["SITE-A"]
    )
    assert "unreviewed" in result.uncertainty_notes


def test_a_score_outside_the_range_is_clamped_not_trusted(rules):
    result, _ = _run(rules, _draft(0.9), {"acceptable_as_drafted": 7.5})
    assert result.confidence == pytest.approx(0.9), "clamped to 1.0, so it cannot raise"
    result, _ = _run(rules, _draft(0.9), {"acceptable_as_drafted": -3})
    assert result.confidence == pytest.approx(0.0)


def test_the_critic_is_inside_the_residency_boundary(rules):
    """It is a second hosted call with the same patient in it. The guard applies
    identically or it is not a guard."""
    state = make_patient(3, controlled=False)
    state.is_synthetic = False
    critic = Critic({"acceptable_as_drafted": 0.5})
    CriticReviewedReasoner(Inner(_draft()), critic).propose(
        state, rules, rules.sites["SITE-A"]
    )
    assert critic.saw_egress is False, "a real record must not be sent for review either"


def test_it_changes_nothing_the_gate_reads_except_confidence(rules):
    """It is not the gate and cannot become one."""
    original = _draft(0.9)
    result, _ = _run(rules, original, {"acceptable_as_drafted": 0.1, "concerns": ["bad"]})
    assert result.recommendation is original.recommendation
    assert result.medication_changes == original.medication_changes
    assert result.provenance == original.provenance


def test_a_fenced_verdict_is_still_read(rules):
    class Fenced(Critic):
        def complete(self, system, user, *, allow_egress, schema=None):
            return '```json\n{"acceptable_as_drafted": 0.25}\n```'

    state = make_patient(3, controlled=False)
    state.is_synthetic = True
    result = CriticReviewedReasoner(Inner(_draft(0.9)), Fenced(None)).propose(
        state, rules, rules.sites["SITE-A"]
    )
    assert result.confidence == pytest.approx(0.25)
