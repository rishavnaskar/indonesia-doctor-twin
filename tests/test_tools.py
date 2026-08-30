"""Read-only tools the drafter may call.

The safety property is the shape of the tool set, not the loop: there is no
tool that writes, prescribes, orders, sends or schedules. Every action in this
system goes through the gate and a signature, so a model that could act would
be routing around both.
"""

from __future__ import annotations

import json

import pytest

from datagen.synthetic import make_patient
from service.packs.loader import load_pack
from service.reason.tools import Toolbox, tool_specs


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def _box(rules, site="SITE-A", seed=101):
    return Toolbox(make_patient(seed, controlled=True), rules, rules.sites[site])


def test_no_tool_can_change_anything():
    """The property that makes it safe to offer these at all."""
    from service.packs.loader import load_pack as _load

    names = {t["function"]["name"] for t in tool_specs(_load("id"))}
    assert names == {"get_measurement", "get_drug", "get_site_capability", "get_history"}
    forbidden = ("write", "prescribe", "order", "send", "schedule", "sign", "commit",
                 "update", "delete", "create")
    assert not [n for n in names if any(verb in n for verb in forbidden)]


def test_the_enumerations_come_from_the_pack(rules):
    specs = {t["function"]["name"]: t for t in tool_specs(rules)}
    codes = specs["get_measurement"]["function"]["parameters"]["properties"]["code"]["enum"]
    assert set(rules.investigations) <= set(codes)
    drugs = specs["get_drug"]["function"]["parameters"]["properties"]["molecule"]["enum"]
    assert drugs == sorted(rules.molecules)


def test_a_measurement_that_was_never_taken_says_so(rules):
    """Not an error, and not a zero. 'Not recorded' is a clinical fact and the
    model must be able to tell it apart from a low value."""
    result = json.loads(_box(rules).dispatch("get_measurement", {"code": "hba1c"}))
    assert result["status"] == "not_recorded"
    assert "value" not in result


def test_a_measurement_carries_its_age_and_its_source(rules):
    result = json.loads(_box(rules).dispatch("get_measurement", {"code": "k"}))
    assert result["value"] and result["unit"]
    assert result["age_days"] is not None
    assert result["source"] == "emr"


def test_site_capability_is_the_real_site(rules):
    result = json.loads(_box(rules, site="SITE-C").dispatch("get_site_capability", {}))
    assert result["labs_available"] == ["creatinine"], "SITE-C runs no potassium assay"
    assert result["as_of"]


def test_an_invented_tool_name_is_reported_not_guessed_at(rules):
    box = _box(rules)
    result = json.loads(box.dispatch("write_prescription", {}))
    assert "no such tool" in result["error"]
    # Still recorded: a model reaching for a tool that does not exist is a fact
    # worth having.
    assert "write_prescription" in box.requested


def test_a_broken_argument_is_returned_to_the_model_not_raised(rules):
    """A tool error must not abort the encounter — the model can recover from
    being told, and cannot recover from an exception three layers up."""
    result = json.loads(_box(rules).dispatch("get_drug", {"molecule": None}))
    assert result["status"] == "not_prescribable_here"


def test_every_request_is_recorded_in_order(rules):
    box = _box(rules)
    box.dispatch("get_measurement", {"code": "k"})
    box.dispatch("get_site_capability", {})
    box.dispatch("get_measurement", {"code": "egfr"})
    assert box.requested == ["get_measurement", "get_site_capability", "get_measurement"]


def test_the_loop_records_what_the_drafter_asked_for(rules):
    """What a model asks for is evidence. One that titrates a RAAS-acting drug
    without ever requesting a potassium result has told us something no
    inspection of its output would reveal."""
    import json as _json

    from service.reason.model_reasoner import ModelReasoner

    VALID = {
        "assessment": "uncontrolled", "recommendation": "titrate_up",
        "confidence": 0.8,
        "medication_changes": [{"action": "increase", "molecule": "amlodipine",
                                "mg_per_dose": 10, "doses_per_day": 1,
                                "rationale": "above target",
                                "citation": "fornas-prb-2025-12-31#amlodipine"}],
    }

    class ToolBackend:
        def version(self):
            return "fake/model@1"

        def complete(self, *a, **k):
            raise AssertionError("should have used the tool path")

        def complete_with_tools(self, system, user, *, allow_egress, schema=None,
                                tools=None, dispatch=None, max_calls=8):
            dispatch("get_measurement", {"code": "k"})
            dispatch("get_site_capability", {})
            return _json.dumps(VALID)

    state = make_patient(3, controlled=False)
    proposal = ModelReasoner(ToolBackend(), use_tools=True).propose(
        state, rules, rules.sites["SITE-A"]
    )
    assert proposal.tools_requested == ["get_measurement", "get_site_capability"]


def test_tools_are_off_unless_asked_for(rules):
    """More calls, more latency, more nondeterminism. It has to be a choice."""
    import json as _json

    from service.reason.model_reasoner import ModelReasoner

    class PlainBackend:
        def version(self):
            return "fake/model@1"

        def complete(self, system, user, *, allow_egress, schema=None):
            return _json.dumps({"assessment": "controlled", "recommendation": "continue",
                                "confidence": 0.9})

        def complete_with_tools(self, *a, **k):
            raise AssertionError("tools were not requested")

    proposal = ModelReasoner(PlainBackend()).propose(
        make_patient(3, controlled=True), rules, rules.sites["SITE-A"]
    )
    assert proposal.tools_requested == []
