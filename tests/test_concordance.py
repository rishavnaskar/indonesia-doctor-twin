"""Plan concordance — the twin-fidelity metric.

The tests are mostly about what the number must NOT do: count an abstention as
a disagreement, or present a self-labelled run as evidence.
"""

from __future__ import annotations

from eval.concordance import Case, Concordance, report, score
from service.packs.loader import load_pack
from tools.demo.patients import generate


def _cases(n=6, label="continue"):
    return [Case(patient=p, adjudicated=label) for p in generate(n, seed=800)]


def test_abstention_is_not_disagreement():
    """A draft the gate refused never reached a clinician, so it can be neither
    concordant nor discordant. Folding abstentions into the denominator would
    let a system look better by abstaining on everything difficult."""
    result = Concordance(matched=6, differed=2, abstained=12)
    assert result.compared == 8
    assert result.rate == 75.0
    assert result.abstention_rate == 60.0


def test_an_empty_run_does_not_divide_by_zero():
    assert Concordance().rate == 0.0
    assert Concordance().abstention_rate == 0.0


def test_out_of_scope_visits_are_counted_apart():
    rules = load_pack("id")
    minor = generate(1, seed=900)[0]
    minor["age"] = 14
    result = score([Case(patient=minor, adjudicated="continue")], rules,
                   source="test", circular=True)
    assert result.out_of_scope == 1
    assert result.compared == 0


def test_disagreements_record_both_sides():
    """'We said X, the doctor said Y' is the useful output. A bare percentage
    tells a clinical lead nothing about where to look."""
    rules = load_pack("id")
    result = score(_cases(4, label="refer"), rules, source="test")
    assert result.differed >= 1
    assert all(len(pair) == 2 for pair in result.disagreements)
    assert any(theirs == "refer" for theirs, _ in result.disagreements)


def test_a_self_labelled_run_says_it_is_not_evidence():
    text = report(Concordance(matched=10, source="self-labelled", circular=True))
    assert "NOT EVIDENCE" in text
    assert "Set C" in text


def test_a_real_run_drops_the_circularity_warning_but_keeps_the_caveats():
    text = report(Concordance(matched=10, source="setc.json", circular=False))
    assert "NOT EVIDENCE" not in text
    assert "Abstentions are excluded" in text


def test_concordance_is_reported_never_gated():
    """SPEC §8.2. A system tuned to maximise agreement with historical practice
    reproduces historical mistakes."""
    text = report(Concordance(matched=1, differed=9, circular=False))
    assert "reported, not gated" in text
    # There is no bar, no pass/fail, and nothing here may fail a build.
    assert "FAIL" not in text and "PASS" not in text
