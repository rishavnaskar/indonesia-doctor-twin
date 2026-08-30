"""The demo surface is generated from real runs, and that is the property worth
testing. A page with a hand-written number on it would undo the whole
"every claim traceable" posture in front of exactly the audience that checks."""

from __future__ import annotations

import json
import re

from tools.demo.render import render
from tools.demo.run import collect


def test_every_scenario_runs_and_is_captured():
    data = collect()
    assert len(data["encounters"]) == data["total"] == 6
    for encounter in data["encounters"]:
        assert encounter["outcome"]
        assert encounter["presentation"]["band"] in ("green", "amber", "red")
        assert encounter["patient"]["patient_id"]


def test_the_refusal_ratio_is_counted_not_asserted():
    data = collect()
    expected = sum(1 for e in data["encounters"] if not e["committed"])
    assert data["declined"] == expected
    assert data["declined"] >= 1, (
        "a demo where the assistant always has an answer is a demo of a system "
        "nobody should deploy"
    )


def test_a_silent_encounter_still_carries_its_audit_trail():
    """Silence is not ignorance. A silent system with an empty audit trail is
    indistinguishable from a broken one."""
    data = collect()
    silent_refusals = [
        e for e in data["encounters"]
        if e["presentation"]["silent"] and e["findings"]
    ]
    assert silent_refusals, "expected at least one refusal the clinician never sees"
    for encounter in silent_refusals:
        assert encounter["presentation"]["audit"]
        assert not encounter["presentation"]["lines"]


def test_page_is_self_contained():
    """No CDN, no external font, no analytics. A demo that phones out while the
    document argues for data residency is an own goal."""
    html = render(collect())
    external = re.findall(r'(?:src|href)\s*=\s*["\'](https?:)?//', html)
    assert not external, f"page reaches outside itself: {external}"
    assert "<script>" in html and "</html>" in html


def test_page_embeds_valid_json_and_escapes_it():
    html = render(collect())
    # Take the DATA assignment's own line, so this does not break every time the
    # line after it is edited.
    payload = html.split("const DATA = ", 1)[1].split("\n", 1)[0].rstrip(";")
    data = json.loads(payload.replace("<\\/", "</"))
    assert data["total"] == 6


def test_one_bad_draft_does_not_take_down_the_page():
    """A weak free model returning unusable output is a normal event. It belongs
    on the page as one failed visit, never as a dead page — a demo that dies on
    the first bad JSON is a worse advert than one that shows the failure being
    contained."""
    from service.reason.parse import ProposalParseError
    from tools.demo.run import collect as collect_run

    class AlwaysFails:
        default = "model"

        def get(self, *args, **kwargs):
            raise KeyError("no backend")

        def propose(self, *args, **kwargs):
            raise ProposalParseError("bad target_used: simulated")

    data = collect_run(router=AlwaysFails())
    assert data["total"] == 6
    assert data["drafter_failures"] == 6
    # A model failure is not a clinical refusal, and conflating them would
    # inflate the one number this page exists to report.
    assert data["declined"] == 0
    assert all(e["error"] for e in data["encounters"])
    assert render(data)
