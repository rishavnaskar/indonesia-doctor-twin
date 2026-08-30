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
    payload = html.split("const DATA = ", 1)[1].split(";\nlet current", 1)[0]
    data = json.loads(payload.replace("<\\/", "</"))
    assert data["total"] == 6
