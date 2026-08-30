"""A reference reasoner. Pack-driven, deterministic, no model.

This is the "deliberately stupid model" the build plan calls for: it produces a
well-formed Proposal so the rest of the spine can be exercised, and it reads
every clinical value — the escalation ladder, the doses, the target — from the
pack rather than from code. That constraint is what made it a legitimate
placeholder rather than a prototype-shaped lie, and the prediction has since
been tested: a real model now sits behind the same router, implementing this
same three-argument signature, and nothing downstream changed. It also survived
a second pathway, which it drafts for without a line of disease-specific code.

It is still the default, and not as a stepping stone. CI and the scorecard run
against it because a suite that costs money per run and varies between runs is
neither a test suite nor a suite, and because a deterministic baseline is the
only way to tell a model regression from a plumbing one.

What this proves and does not prove is worth restating where the code is,
because a score is easier to quote than a caveat. It follows the same guideline
the gate checks against, so it passes the gate close to by construction. That
demonstrates the pipeline and the contracts. It demonstrates nothing clinical.
"""

from __future__ import annotations

from typing import Any

from service.contracts.proposal import (
    Assertion,
    Assessment,
    ChangeAction,
    MedicationChange,
    Proposal,
    Provenance,
    Recommendation,
    Target,
)
from service.rules.predicates import Context
from service.rules.targets import resolve_target

NAME = "reference-rule-reasoner"
VERSION = "0.1.0"


def _provenance(rules) -> Provenance:
    corpus_version = rules.guideline.get("version", "unknown")
    return Provenance(
        model=f"{NAME}@{VERSION}",
        prompt_template=f"none@{VERSION}",
        corpus=f"{corpus_version}@1",
    )


def propose(state, rules, site: dict[str, Any] | None = None) -> Proposal:
    provenance = _provenance(rules)
    resolution = resolve_target(rules.guideline, Context(state))
    trend = _trend(state)

    # Even with no target we still emit. The gate is what refuses, not the
    # reasoner — so the refusal is exercised rather than assumed.
    if not resolution.defined:
        return Proposal(
            assessment=Assessment.UNCONTROLLED,
            recommendation=Recommendation.REFER,
            bp_trend_summary=trend,
            target_used=None,
            confidence=0.5,
            provenance=provenance,
            uncertainty_notes=resolution.reason or "No target defined.",
        )

    target = resolution.target
    sbp, dbp = state.latest("sbp"), state.latest("dbp")
    # Control is "every measurement this pathway targets is below its
    # threshold". Reading the codes from the target rather than naming sbp and
    # dbp is what lets a second pathway, whose target is one HbA1c, use the
    # identical reasoner.
    readings = {code: state.latest(code) for code in target.thresholds}
    at_target = all(
        observation is not None and observation.value < target.thresholds[code]
        for code, observation in readings.items()
    )

    target_used = Target(dict(target.thresholds), target.citation)
    assertions = [
        Assertion(
            text=f"Target for this patient is {target.describe()}.",
            citation=target.citation,
        )
    ]

    if at_target:
        return Proposal(
            assessment=Assessment.CONTROLLED,
            recommendation=Recommendation.CONTINUE,
            bp_trend_summary=trend,
            target_used=target_used,
            confidence=0.9,
            provenance=provenance,
            assertions=assertions,
            patient_instructions=_instructions(rules, "controlled"),
            follow_up_interval_days=90,
        )

    change = _next_step(state, rules, site)
    if change is None:
        return Proposal(
            assessment=Assessment.UNCONTROLLED,
            recommendation=Recommendation.REFER,
            bp_trend_summary=trend,
            target_used=target_used,
            confidence=0.75,
            provenance=provenance,
            assertions=assertions,
            uncertainty_notes="Ladder exhausted at this site; specialist review.",
            follow_up_interval_days=30,
        )

    recommendation = (
        Recommendation.TITRATE_UP
        if change.action is ChangeAction.INCREASE
        else Recommendation.ADD_AGENT
    )
    return Proposal(
        investigations=_required_investigations(state, rules, change),
        assessment=Assessment.UNCONTROLLED,
        recommendation=recommendation,
        bp_trend_summary=trend,
        target_used=target_used,
        confidence=0.85,
        provenance=provenance,
        medication_changes=[change],
        assertions=assertions,
        patient_instructions=_instructions(rules, "uncontrolled"),
        follow_up_interval_days=28,
    )


def _next_step(state, rules, site) -> MedicationChange | None:
    ladder = rules.guideline.get("escalation_ladder") or {}
    steps = ladder.get("steps") or []
    titrate_first = ladder.get("policy") == "titrate_before_adding"
    current = {m.molecule: m for m in state.medications}
    stocked = set((site or {}).get("stocked_molecules") or [])

    if titrate_first:
        for step in steps:
            molecule = step.get("preferred_molecule")
            med = current.get(molecule)
            mol = rules.molecules.get(molecule)
            if med is None or mol is None:
                continue
            max_daily = mol.dosing.get("max_mg_daily")
            max_per_dose = mol.dosing.get("max_mg_per_dose")
            if max_daily is None or med.mg_daily >= max_daily:
                continue
            stepped = min(med.mg_per_dose * 2, max_per_dose or med.mg_per_dose * 2)
            if stepped <= med.mg_per_dose or stepped * med.doses_per_day > max_daily:
                continue
            return MedicationChange(
                action=ChangeAction.INCREASE,
                molecule=molecule,
                mg_per_dose=stepped,
                doses_per_day=med.doses_per_day,
                rationale="Above target on the current dose; titrate before adding.",
                citation=mol.citation,
            )

    for step in steps:
        molecule = step.get("preferred_molecule")
        if molecule in current:
            continue
        mol = rules.molecules.get(molecule)
        if mol is None:
            continue
        # Prefer something the site can actually dispense. Gate check 9 would
        # catch it anyway, but proposing an available drug is better than
        # proposing a referral we did not need.
        if stocked and molecule not in stocked:
            continue
        return MedicationChange(
            action=ChangeAction.START,
            molecule=molecule,
            mg_per_dose=float(step.get("start_mg")),
            doses_per_day=int(step.get("doses_per_day", 1)),
            rationale="Above target on maximum tolerated existing therapy; add an agent.",
            citation=mol.citation,
        )

    return None


def _required_investigations(state, rules, change) -> list[str]:
    """Ask for the labs this change depends on, rather than assuming them.

    A proposal that quietly relies on a potassium nobody has measured is worse
    than one that says it needs one. Naming the requirement also lets the gate
    decide whether this site can actually run the test — at a basic-tier
    hospital that turns a follow-up plan into a referral, which is the honest
    answer rather than an order nobody can fill.
    """
    sufficiency = rules.guideline.get("sufficiency") or {}
    required = sufficiency.get("required_for_raas_action") or []
    drug_class = rules.drug_class_of(change.molecule)
    if drug_class not in ("acei", "arb", "mra"):
        return []

    wanted = []
    for row in required:
        code = row["code"]
        age = state.observation_age_days(code)
        if age is None or age > int(row.get("max_age_days", 90)):
            wanted.append(code)
    return wanted


def _instructions(rules, situation: str) -> str:
    templates = (rules.guideline.get("patient_instructions") or {})
    return templates.get(situation, "")


def _trend(state) -> str:
    series = state.bp_series(limit=4)
    if not series:
        return "No readings recorded."
    parts = [
        f"{day.isoformat()} {int(s)}/{int(d)}"
        for day, s, d in series
        if s is not None and d is not None
    ]
    return "Recent readings: " + ", ".join(parts) + "."
