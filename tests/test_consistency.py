"""Self-consistency.

The point of these tests is that the confidence number stops being the model's
opinion of itself and becomes a measurement of its behaviour.
"""

from __future__ import annotations

import pytest

from service.contracts.proposal import (
    Assessment,
    ChangeAction,
    MedicationChange,
    Proposal,
    Provenance,
    Recommendation,
)
from service.reason.consistency import SelfConsistentReasoner, decision_key

PROV = Provenance(model="m@1", prompt_template="p@1", corpus="c@1")


def _draft(recommendation="titrate_up", mg=10.0, confidence=0.9, model="m@1"):
    return Proposal(
        assessment=Assessment("uncontrolled"),
        recommendation=Recommendation(recommendation),
        bp_trend_summary="",
        target_used=None,
        confidence=confidence,
        provenance=Provenance(model=model, prompt_template="p@1", corpus="c@1"),
        medication_changes=[
            MedicationChange(ChangeAction("increase"), "amlodipine", mg, 1, "", "cite")
        ],
    )


class Scripted:
    """A reasoner that returns a fixed sequence, raising where told to."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def propose(self, state, rules, site=None):
        outcome = self.outcomes[self.calls % len(self.outcomes)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_two_plans_differing_only_in_dose_are_not_the_same_plan():
    """A patient would notice. So the agreement key must."""
    assert decision_key(_draft(mg=10.0)) != decision_key(_draft(mg=5.0))
    assert decision_key(_draft(mg=10.0)) == decision_key(_draft(mg=10.0))


def test_unanimous_samples_keep_the_stated_confidence():
    reasoner = SelfConsistentReasoner(Scripted(_draft(confidence=0.9)), samples=3)
    result = reasoner.propose(None, None)
    assert result.confidence == pytest.approx(0.9)
    assert "3 of 3" in result.uncertainty_notes


def test_scattered_samples_collapse_the_confidence_below_the_floor():
    """The case this exists for: a model asserting 0.95 while its samples
    disagree. The stated number is not to be believed and the gate must see
    that."""
    reasoner = SelfConsistentReasoner(
        Scripted(_draft(mg=10.0, confidence=0.95),
                 _draft(mg=5.0, confidence=0.95),
                 _draft(recommendation="add_agent", confidence=0.95)),
        samples=3,
    )
    result = reasoner.propose(None, None)
    assert result.confidence == pytest.approx(1 / 3)
    assert result.confidence < 0.70, "below the pack's abstention floor"


def test_agreement_cannot_rescue_a_model_that_says_it_is_unsure():
    """Five samples agreeing on an answer the model is unsure of does not make
    it sure. The minimum is taken, never a blend."""
    reasoner = SelfConsistentReasoner(Scripted(_draft(confidence=0.4)), samples=5)
    assert reasoner.propose(None, None).confidence == pytest.approx(0.4)


def test_a_failed_sample_counts_against_agreement_rather_than_vanishing():
    """A model that cannot produce a parseable plan two times in four is telling
    us something. Dropping those samples would hide it."""
    reasoner = SelfConsistentReasoner(
        Scripted(_draft(), ValueError("bad json"), _draft(), ValueError("bad json")),
        samples=4,
    )
    result = reasoner.propose(None, None)
    assert result.confidence == pytest.approx(0.5)
    assert "2 sample(s) failed" in result.uncertainty_notes


def test_every_sample_failing_raises_rather_than_inventing_a_plan():
    reasoner = SelfConsistentReasoner(Scripted(ValueError("bad json")), samples=3)
    with pytest.raises(ValueError):
        reasoner.propose(None, None)


def test_one_sample_is_a_passthrough():
    inner = Scripted(_draft(confidence=0.88))
    result = SelfConsistentReasoner(inner, samples=1).propose(None, None)
    assert result.confidence == pytest.approx(0.88)
    assert inner.calls == 1


def test_the_pin_names_every_model_that_answered():
    """A fallback chain can serve different samples from different models. A pin
    naming only the winner would be a false audit trail in exactly the case
    where the trail matters most."""
    reasoner = SelfConsistentReasoner(
        Scripted(_draft(model="a@1"), _draft(model="b@1")), samples=2
    )
    pin = reasoner.propose(None, None).provenance.model
    assert pin == "a@1+b@1"
    assert "@" in pin, "gate check 6 requires a version in every pin"


def test_it_is_not_a_second_gate():
    """It hands the same nine checks a better-grounded number, and blocks
    nothing itself."""
    reasoner = SelfConsistentReasoner(
        Scripted(_draft(mg=10.0), _draft(mg=5.0), _draft(mg=2.5)), samples=3
    )
    result = reasoner.propose(None, None)
    assert isinstance(result, Proposal)
    assert result.medication_changes, "it returns a plan; the gate decides its fate"


def test_shadow_mode_measures_without_applying():
    """The obvious experiment cannot answer its own question. With agreement
    feeding the confidence, a low-agreement draft falls below the abstention
    floor and never reaches a clinician — so 'are unstable drafts likelier to
    be wrong?' has no unstable drafts left to measure. Observed at n=30: six
    unstable drafts, none of which reached the comparison."""
    scattered = Scripted(_draft(mg=10.0, confidence=0.95),
                         _draft(mg=5.0, confidence=0.95),
                         _draft(recommendation="add_agent", confidence=0.95))

    applied = SelfConsistentReasoner(scattered, samples=3, apply=True).propose(None, None)
    assert applied.confidence == pytest.approx(1 / 3)

    shadow = SelfConsistentReasoner(
        Scripted(_draft(mg=10.0, confidence=0.95),
                 _draft(mg=5.0, confidence=0.95),
                 _draft(recommendation="add_agent", confidence=0.95)),
        samples=3, apply=False,
    ).propose(None, None)
    assert shadow.confidence == pytest.approx(0.95), "untouched, so the draft proceeds"
    assert shadow.agreement == pytest.approx(1 / 3), "but the instability is recorded"
    assert "shadow" in shadow.uncertainty_notes
