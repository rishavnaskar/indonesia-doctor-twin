"""Findings in the deployment language.

The mechanism matters more than the coverage. A clinician in the deployment
country should read a red flag in their own language, and none of that text may
live under /service — which is the same rule that keeps a drug name out of the
engine, applied to the words a doctor reads.
"""

from __future__ import annotations

import pytest

from service.gate.messages import localise
from service.packs.loader import load_pack
from service.present.layer import Labels, present
from service.rules import pathways


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


def test_every_red_flag_is_translated(rules):
    """These are the findings that must be understood instantly."""
    for name in rules.pathway_order:
        pathway = pathways.with_pathway(rules, name).guideline
        untranslated = [
            rule["id"] for rule in pathway["red_flags"] if not rule.get("message_local")
        ]
        assert not untranslated, f"{name}: {untranslated}"


def test_a_composed_message_is_filled_from_the_pack_template(rules):
    text = localise(rules, "dose_per_dose", molecule="amlodipine", mg=100, max_mg=10)
    assert text and "amlodipine" in text and "100" in text
    assert "{" not in text


def test_a_missing_template_yields_nothing_rather_than_a_guess(rules):
    """Untranslated is a pack gap, and the finding still reaches the clinician
    in the language the engine composed."""
    assert localise(rules, "no_such_rule", a=1) == ""
    assert localise(rules, None) == ""


def test_a_template_missing_a_placeholder_shows_nothing(rules):
    """A half-substituted sentence with a brace in it is how a clinician learns
    to distrust the panel."""
    assert localise(rules, "dose_per_dose", molecule="amlodipine") == ""


def test_no_deployment_language_text_lives_under_service():
    """The same rule that keeps a drug name out of the engine, applied to the
    words a doctor reads."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "service"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in ("Segera", "Tekanan darah", "Gula darah", "tidak tersedia"):
            if marker in text:
                offenders.append(f"{path.name}: {marker}")
    assert not offenders, offenders


def _decision():
    from service.gate.types import Finding, GateDecision, Severity

    return GateDecision(findings=[
        Finding(check=1, check_name="red_flags", severity=Severity.BLOCK,
                message="Hypertensive emergency.", rule_id="R1",
                message_local="Kondisi darurat hipertensi."),
    ])


def test_english_leads_by_default_with_the_local_text_beneath(rules):
    """The people reading this build are reviewing it, not practising from it."""
    view = present("escalate", Labels.from_pack(rules.language), decision=_decision())
    assert view.lines[0].text == "Hypertensive emergency."
    assert view.lines[0].gloss == "Kondisi darurat hipertensi."


def test_a_deployed_clinic_flips_it_with_one_flag(rules):
    """A doctor in the deployment country should not read past a second
    language to reach the sentence that matters. Both strings are always
    carried; which leads is display, not storage."""
    from dataclasses import replace

    labels = replace(Labels.from_pack(rules.language), english_first=False)
    view = present("escalate", labels, decision=_decision())
    assert view.lines[0].text == "Kondisi darurat hipertensi."
    assert view.lines[0].gloss == "Hypertensive emergency."
    assert view.headline and view.headline != view.gloss


def test_an_untranslated_finding_is_visibly_untranslated(rules):
    from service.gate.types import Finding, GateDecision, Severity

    labels = Labels.from_pack(rules.language)
    decision = GateDecision(findings=[
        Finding(check=3, check_name="drug_safety", severity=Severity.BLOCK,
                message="Some finding with no translation.", rule_id="whatever"),
    ])
    line = present("abstain", labels, decision=decision).audit[0]
    assert line.text == "Some finding with no translation."
    assert line.gloss == "", "an empty gloss is the signal that nothing was translated"
