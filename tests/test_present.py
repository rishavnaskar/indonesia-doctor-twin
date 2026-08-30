"""SPEC-V1 §5.8 — the clinician surface.

The tests that matter here are the ones about silence. It is easy to write a
presentation layer that is correct about what to say and wrong about when to
say nothing, and the second failure is the one that gets the system ignored.
"""

from __future__ import annotations

import pytest

from service.gate.types import Finding, GateDecision, Severity
from service.packs.loader import load_pack
from service.present.layer import Band, Labels, present


@pytest.fixture(scope="module")
def labels() -> Labels:
    return Labels.from_pack(load_pack("id").language)


def _finding(severity=Severity.BLOCK, *, check=3, referral=False, rule_id="X1"):
    return Finding(
        check=check,
        check_name="test_check",
        severity=severity,
        message="something happened",
        rule_id=rule_id,
        citation="cite-1",
        converts_to_referral=referral,
    )


def test_clean_encounter_is_green_and_silent(labels):
    p = present("committed", labels, decision=GateDecision())
    assert p.band is Band.GREEN
    assert p.silent
    assert p.lines == ()
    assert p.shows_draft
    assert not p.requires_acknowledgement


def test_warning_is_amber_and_still_shows_the_draft(labels):
    decision = GateDecision(findings=[_finding(Severity.WARN)])
    p = present("committed", labels, decision=decision)
    assert p.band is Band.AMBER
    assert not p.silent
    assert len(p.lines) == 1
    assert p.shows_draft, "a warning annotates a draft, it does not withhold it"
    assert not p.requires_acknowledgement


def test_red_flag_is_red_and_must_be_acknowledged(labels):
    decision = GateDecision(findings=[_finding(check=1, rule_id="R1")])
    p = present("escalate", labels, decision=decision)
    assert p.band is Band.RED
    assert p.requires_acknowledgement
    assert not p.shows_draft


def test_undeliverable_plan_is_red_because_it_is_a_referral(labels):
    """A plan this site cannot carry out is not a bad plan and must not be
    swallowed. The alternative is a patient sent home waiting for a test that
    will never be run here."""
    decision = GateDecision(findings=[_finding(check=9, referral=True)])
    p = present("abstain", labels, decision=decision)
    assert p.band is Band.RED
    assert p.requires_acknowledgement
    assert all(line.rule_id for line in p.lines)


def test_plain_abstention_stays_silent(labels):
    """The gate refused and there is nothing the clinician must act on, so the
    clinician is not interrupted. This is the direction to fail in."""
    decision = GateDecision(findings=[_finding()])
    p = present("abstain", labels, decision=decision)
    assert p.band is Band.GREEN
    assert p.silent
    assert p.lines == ()
    assert not p.shows_draft, "a refused draft is never rendered"


def test_silence_is_not_ignorance(labels):
    """Green shows nothing, but must still record what it concluded. A silent
    system with an empty audit trail is indistinguishable from a broken one."""
    decision = GateDecision(findings=[_finding(), _finding(Severity.WARN)])
    p = present("abstain", labels, decision=decision)
    assert p.silent
    assert len(p.audit) == 2
    assert {line.rule_id for line in p.audit} == {"X1"}


def test_every_line_carries_its_provenance(labels):
    decision = GateDecision(findings=[_finding(Severity.WARN)])
    p = present("committed", labels, decision=decision)
    line = p.lines[0]
    assert line.rule_id == "X1"
    assert line.citation == "cite-1"
    assert line.check == 3


def test_request_info_asks_the_questions_it_has(labels):
    p = present("request_info", labels, questions=("potassium?", "eGFR?"))
    assert p.band is Band.AMBER
    assert [line.text for line in p.lines] == ["potassium?", "eGFR?"]


def test_handoff_is_amber_without_a_draft(labels):
    p = present("handoff", labels, decision=GateDecision())
    assert p.band is Band.AMBER
    assert not p.shows_draft


def test_labels_come_from_the_pack_not_the_engine(labels):
    """If this ever passes with the pack's presentation block deleted, the
    engine has started writing display text and the country boundary has
    leaked."""
    empty = Labels.from_pack({})
    p = present("escalate", empty, decision=GateDecision(findings=[_finding(check=1)]))
    assert p.headline.startswith("<missing label")
    assert not labels.headline("escalate").startswith("<missing label")


def test_a_missing_gate_decision_does_not_crash(labels):
    p = present("committed", labels, decision=None)
    assert p.band is Band.GREEN
    assert p.audit == ()
