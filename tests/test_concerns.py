"""The drafter's own channel for raising something.

The deterministic red flags decide the floor and are not negotiable: a rule
with a defined threshold has perfect recall on the pattern it names, and a
model doing that job at ninety-nine percent is strictly worse. But a rule only
catches what somebody enumerated, and seven red flags is seven patterns.

Every test here is about the asymmetry that makes it safe to let a model speak:
a concern can only ever add.
"""

from __future__ import annotations

import pytest

from service.contracts.proposal import Concern, Urgency
from service.gate.types import Finding, GateDecision, Severity
from service.packs.loader import load_pack
from service.present.layer import Band, Labels, present


@pytest.fixture(scope="module")
def labels():
    return Labels.from_pack(load_pack("id").language)


def _red():
    return GateDecision(findings=[Finding(
        check=1, check_name="red_flags", severity=Severity.BLOCK,
        message="Hypertensive emergency.", rule_id="R1")])


def _blocked():
    return GateDecision(findings=[Finding(
        check=3, check_name="drug_safety", severity=Severity.BLOCK,
        message="Dose exceeds the maximum.", rule_id="dose_daily")])


def test_a_quiet_visit_stays_quiet_without_a_concern(labels):
    view = present("committed", labels)
    assert view.band is Band.GREEN and view.silent


def test_a_mention_lifts_a_silent_visit_to_amber(labels):
    """Silence is what the concern is objecting to, so a green visit that gains
    one needs a headline as well as a band."""
    view = present("committed", labels,
                   concerns=(Concern("Blood pressure creeping up across three visits"),))
    assert view.band is Band.AMBER
    assert view.headline and not view.silent
    assert any("creeping up" in line.text for line in view.lines)
    assert view.shows_draft, "a concern annotates the draft, it does not withhold it"


def test_an_escalate_concern_reaches_red_and_must_be_acknowledged(labels):
    view = present("committed", labels,
                   concerns=(Concern("eGFR has fallen at every visit this year",
                                     Urgency.ESCALATE),))
    assert view.band is Band.RED
    assert view.requires_acknowledgement


def test_a_concern_can_never_lower_the_band(labels):
    """The property that makes this safe. A model that could quieten an alert
    would be a model with veto over the safety rules."""
    with_concern = present("escalate", labels, decision=_red(),
                           concerns=(Concern("looks fine to me"),))
    without = present("escalate", labels, decision=_red())
    assert with_concern.band is Band.RED is without.band
    assert with_concern.requires_acknowledgement
    assert not with_concern.shows_draft, "a refused draft stays refused"


def test_a_concern_cannot_turn_a_refusal_into_a_draft(labels):
    view = present("abstain", labels, decision=_blocked(),
                   concerns=(Concern("I still think this is right", Urgency.ESCALATE),))
    assert view.shows_draft is False


def test_a_concern_can_break_the_silence_of_an_abstention(labels):
    """The case this exists for. The gate refused and said nothing to the
    clinician; the drafter noticed something the rules never asked about."""
    quiet = present("abstain", labels, decision=_blocked())
    assert quiet.band is Band.GREEN and quiet.silent

    loud = present("abstain", labels, decision=_blocked(),
                   concerns=(Concern("Weight loss and thirst across two visits",
                                     Urgency.ESCALATE),))
    assert loud.band is Band.RED
    assert not loud.silent


def test_concerns_are_always_in_the_audit_trail(labels):
    view = present("committed", labels, concerns=(Concern("something"),))
    assert any("something" in line.text for line in view.audit)


def test_a_bare_string_concern_does_not_get_promoted():
    """Sloppy output must not be able to shout."""
    from service.contracts.proposal import Provenance
    from service.reason.parse import to_proposal

    proposal = to_proposal(
        {"assessment": "controlled", "recommendation": "continue", "confidence": 0.9,
         "concerns": ["something odd"]},
        Provenance(model="m@1", prompt_template="p@1", corpus="c@1"),
    )
    assert proposal.concerns[0].urgency is Urgency.MENTION


def test_an_unknown_urgency_is_refused_rather_than_defaulted():
    """Defaulting it either way is a guess about how loud to be."""
    from service.contracts.proposal import Provenance
    from service.reason.parse import ProposalParseError, to_proposal

    with pytest.raises(ProposalParseError, match="urgency"):
        to_proposal(
            {"assessment": "controlled", "recommendation": "continue", "confidence": 0.9,
             "concerns": [{"text": "x", "urgency": "panic"}]},
            Provenance(model="m@1", prompt_template="p@1", corpus="c@1"),
        )
