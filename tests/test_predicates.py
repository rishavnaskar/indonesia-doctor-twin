"""The predicate evaluator fails closed.

This is the most important test in the file. A rule engine that silently
evaluates a malformed red-flag rule to False produces no output, no error and no
alert — the failure is invisible precisely when it matters.
"""

from datetime import date

import pytest

from service.rules.predicates import Context, PredicateError, evaluate
from service.state.models import Observation, PatientState, Source


def _state(**kwargs):
    base = dict(patient_id="T", age=50, sex="F", as_of=date(2026, 8, 29))
    base.update(kwargs)
    return PatientState(**base)


def _obs(code, value, day=29):
    return Observation(code, value, "mmHg", date(2026, 8, day), Source.EMR)


def test_unknown_key_raises():
    with pytest.raises(PredicateError):
        evaluate({"blood_pressure_over": 140}, Context(_state()))


def test_typo_in_operator_raises():
    state = _state(observations=[_obs("sbp", 150)])
    with pytest.raises(PredicateError):
        evaluate({"obs": "sbp", "op": "=>", "value": 140}, Context(state))


def test_extra_key_on_leaf_raises():
    with pytest.raises(PredicateError):
        evaluate({"flag": "has_dm", "value": True}, Context(_state()))


def test_composite_with_no_children_raises():
    with pytest.raises(PredicateError):
        evaluate({"all_of": []}, Context(_state()))


def test_missing_observation_is_not_a_positive_finding():
    # Absent data must not read as "threshold not crossed" in a way that
    # invents a finding; it reads as no finding, and sufficiency catches it.
    assert evaluate({"obs": "sbp", "op": ">=", "value": 180}, Context(_state())) is False


def test_none_of_semantics():
    state = _state(symptoms={"chest_pain": True})
    assert evaluate({"none_of": [{"symptom": "chest_pain"}]}, Context(state)) is False
    assert evaluate({"none_of": [{"symptom": "syncope"}]}, Context(state)) is True


def test_relative_fall_needs_two_readings():
    one = _state(observations=[Observation("egfr", 90, "", date(2026, 5, 1), Source.EMR)])
    assert evaluate({"relative_fall": {"code": "egfr", "fraction": 0.3}}, Context(one)) is False

    two = _state(
        observations=[
            Observation("egfr", 90, "", date(2026, 5, 1), Source.EMR),
            Observation("egfr", 55, "", date(2026, 8, 1), Source.EMR),
        ]
    )
    assert evaluate({"relative_fall": {"code": "egfr", "fraction": 0.3}}, Context(two)) is True
