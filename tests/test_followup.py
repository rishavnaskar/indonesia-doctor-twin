"""SPEC-V1 §5.11 — the between-visit loop.

The tests are about the confirmation rule. Everything else here is storage with
provenance; that rule is the one clinical judgement in the module, and getting
it wrong in either direction kills the channel — alarm on every noisy reading
and the clinic stops looking, alarm on none and it is decoration.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from datagen.synthetic import TODAY, make_patient
from service.followup.loop import Action, ingest, refill_check
from service.packs.loader import load_pack
from service.rules import pathways
from service.state.models import Observation, Source


@pytest.fixture(scope="module")
def rules():
    return pathways.with_pathway(load_pack("id"), "hypertension")


def _reading(code, value, source, days_ago=0):
    return Observation(code, float(value), "mmHg", TODAY - timedelta(days=days_ago), source)


def _calm(seed=700):
    state = make_patient(seed, controlled=True)
    state.symptoms = {}
    return state


def test_an_ordinary_reading_is_just_stored(rules):
    state = _calm()
    result = ingest(state, rules, [_reading("sbp", 128, Source.PATIENT_REPORTED)])
    assert [e.action for e in result.events] == [Action.ACCEPT]
    assert not result.escalated
    assert state.observations[-1].source is Source.PATIENT_REPORTED


def test_readings_keep_the_provenance_they_arrived_with(rules):
    """Retrofitting `source` onto readings already stored is exactly the
    mistake SPEC §3 exists to prevent."""
    state = _calm()
    ingest(state, rules, [
        _reading("sbp", 130, Source.PATIENT_REPORTED),
        _reading("sbp", 132, Source.DEVICE),
    ])
    assert [o.source for o in state.observations[-2:]] == [
        Source.PATIENT_REPORTED, Source.DEVICE
    ]


def test_one_alarming_self_reported_reading_asks_for_a_repeat(rules):
    """Home readings carry noise a clinic reading does not. Firing on a single
    unconfirmed value would train a clinic to ignore the channel in a month."""
    state = _calm()
    result = ingest(state, rules, [_reading("sbp", 215, Source.PATIENT_REPORTED)])
    event = result.events[0]
    assert event.action is Action.CONFIRM
    assert not result.escalated
    assert result.awaiting_confirmation
    assert event.instruction, "the patient must be told what to do"
    assert event.instruction_gloss


def test_a_confirmed_self_reported_outlier_escalates(rules):
    state = _calm()
    first = ingest(state, rules, [_reading("sbp", 215, Source.PATIENT_REPORTED)])
    assert first.events[0].action is Action.CONFIRM

    second = ingest(state, rules, [_reading("sbp", 212, Source.PATIENT_REPORTED)])
    assert second.events[0].action is Action.ESCALATE
    assert second.escalated
    assert second.events[0].rule_id


def test_a_device_reading_is_trusted_immediately(rules):
    """A connected cuff is not subject to technique error in the same way, and
    treating it as noisy would waste the one channel with good provenance."""
    state = _calm()
    result = ingest(state, rules, [_reading("sbp", 215, Source.DEVICE)])
    assert result.events[0].action is Action.ESCALATE


def test_a_clinic_reading_corroborates_a_home_one(rules):
    state = _calm()
    state.observations.append(_reading("sbp", 210, Source.EMR))
    result = ingest(state, rules, [_reading("sbp", 214, Source.PATIENT_REPORTED)])
    assert result.events[0].action is Action.ESCALATE


def test_a_stale_repeat_does_not_count_as_confirmation(rules):
    """A reading from last month is not a repeat, it is a separate event."""
    state = _calm()
    state.observations.append(_reading("sbp", 216, Source.PATIENT_REPORTED, days_ago=40))
    result = ingest(state, rules, [_reading("sbp", 215, Source.PATIENT_REPORTED)])
    assert result.events[0].action is Action.CONFIRM


def test_escalation_uses_the_pathway_that_is_in_force(rules):
    """No model touches this path: it is the same red-flag predicates the gate
    runs, applied to readings that arrived from home."""
    dm = pathways.with_pathway(load_pack("id"), "diabetes")
    state = _calm()
    state.symptoms = {"hypoglycaemia": True}
    result = ingest(state, dm, [Observation("hba1c", 7.4, "%", TODAY, Source.DEVICE)])
    assert result.events[0].action is Action.ESCALATE
    assert result.events[0].rule_id == "D3"


def test_a_missed_refill_is_reported(rules):
    """Twelve dispensing touchpoints a year against four visits. The next visit
    would otherwise discover this months later."""
    event = refill_check(_calm(), rules,
                         last_collected=date(2026, 6, 1), now=date(2026, 8, 29))
    assert event is not None
    assert event.action is Action.REFILL_GAP
    assert "days ago" in event.reason


def test_a_refill_inside_the_grace_window_is_not_a_signal(rules):
    assert refill_check(_calm(), rules,
                        last_collected=date(2026, 8, 5), now=date(2026, 8, 29)) is None


def test_no_refill_history_is_not_a_missed_refill(rules):
    """Absence of data is not evidence of non-adherence."""
    assert refill_check(_calm(), rules, last_collected=None, now=date(2026, 8, 29)) is None
