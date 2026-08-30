"""Gate check 9 — executable at this site, today.

These tests exist because of a real false refusal. A model asked for a
management plan wrote "Repeat potassium and eGFR in 90 days to monitor RAAS
safety" into `investigations`, and the check reported it as unavailable at a
site that runs potassium every day. The plan was fine; the field's contract was
underspecified, and the check turned that into a statement about the site that
was simply untrue.
"""

from __future__ import annotations

import pytest

from datagen.proposer import propose
from datagen.synthetic import make_patient
from service.gate.checks import c9_executable
from service.gate.types import GateContext, Severity
from service.packs.loader import load_pack


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def _run(rules, site_id, investigations):
    state = make_patient(1, controlled=True)
    proposal = propose(state, rules)
    proposal.investigations = list(investigations)
    proposal.medication_changes = []
    return c9_executable.run(
        GateContext(state=state, proposal=proposal, rules=rules, site=rules.sites[site_id])
    )


def test_a_test_the_site_runs_is_not_flagged(rules):
    assert _run(rules, "SITE-A", ["k", "egfr"]) == []


def test_a_known_test_the_site_cannot_run_is_a_referral(rules):
    """SITE-C has no potassium assay. The plan is right, the place is wrong."""
    findings = _run(rules, "SITE-C", ["k"])
    assert len(findings) == 1
    assert findings[0].rule_id == "test_unavailable"
    assert findings[0].converts_to_referral
    assert "SITE-C" in findings[0].message


def test_prose_in_the_investigations_field_is_a_malformed_proposal(rules):
    """The regression. A sentence is not an orderable test, and calling it
    'unavailable at SITE-A' asserts something false about SITE-A."""
    sentence = "Repeat potassium and eGFR in 90 days to monitor RAAS safety"
    findings = _run(rules, "SITE-A", [sentence])
    assert len(findings) == 1
    assert findings[0].rule_id == "unrecognised_investigation"
    assert findings[0].severity is Severity.BLOCK
    assert not findings[0].converts_to_referral, (
        "there is nowhere to refer a sentence to"
    )
    assert "not available at" not in findings[0].message


def test_the_two_failures_stay_distinct_at_a_site_missing_the_test(rules):
    findings = _run(rules, "SITE-C", ["k", "monitor renal function periodically"])
    assert {f.rule_id for f in findings} == {"test_unavailable", "unrecognised_investigation"}
    assert [f.converts_to_referral for f in findings] == [True, False]


def test_a_pack_whose_halves_disagree_fails_at_load(rules, tmp_path, monkeypatch):
    """A site offering a lab absent from the catalogue would silently never
    match, so it is a load-time error rather than a runtime surprise."""
    from service.packs import loader

    bad = dict(rules.sites["SITE-A"])
    bad["labs_available"] = ["k", "not_in_catalogue"]
    broken = loader.RuleSet(
        pack_id="x", version="1", review_status="unknown",
        molecules=rules.molecules, guideline=rules.guideline,
        sites={"SITE-A": bad}, investigations=rules.investigations,
    )
    with pytest.raises(loader.PackError, match="absent from the catalogue"):
        loader._validate(broken)


def _with_investigation(rules, site_id, codes):
    state = make_patient(1, controlled=True)
    proposal = propose(state, rules)
    proposal.investigations = list(codes)
    proposal.medication_changes = []
    return c9_executable.run(
        GateContext(state=state, proposal=proposal, rules=rules, site=rules.sites[site_id])
    )


def test_an_evidenced_capability_is_silent(rules):
    assert _with_investigation(rules, "SITE-A", ["k"]) == []


def test_a_capability_listed_but_never_performed_warns(rules):
    """Permenkes 6/2026 Art. 74: naming a service is no longer sufficient, you
    have to show it happened. SITE-A lists urine protein and has never recorded
    running one."""
    findings = _with_investigation(rules, "SITE-A", ["urine_protein"])
    assert len(findings) == 1
    assert findings[0].rule_id == "capability_unevidenced"
    assert findings[0].severity is Severity.WARN
    assert findings[0].citation


def test_stale_evidence_warns_with_the_age_named(rules):
    """SITE-B claims HbA1c and has not run one since mid-2025."""
    findings = _with_investigation(rules, "SITE-B", ["hba1c"])
    assert findings[0].rule_id == "capability_unevidenced"
    assert "days ago" in findings[0].message


def test_an_unevidenced_capability_warns_but_never_blocks(rules):
    """The plan may well be right and the test may well happen — the registry
    is what is doubtful, not the medicine. Blocking here would deny care over
    a records problem."""
    findings = _with_investigation(rules, "SITE-A", ["urine_protein"])
    assert not any(f.severity is Severity.BLOCK for f in findings)
    assert not any(f.converts_to_referral for f in findings)


def test_unavailable_still_beats_unevidenced(rules):
    """A test the site cannot run at all is a referral, not a paperwork note.
    The stronger finding must not be softened by the weaker one."""
    findings = _with_investigation(rules, "SITE-C", ["k"])
    assert {f.rule_id for f in findings} == {"test_unavailable"}
    assert findings[0].converts_to_referral
