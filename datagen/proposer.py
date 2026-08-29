"""A reference proposer — the stand-in for the model.

BUILD.md Phase 1 says to run the spine with a deliberately stupid model and
hard-code the clinical logic if you have to, because the point is the plumbing.
This is that. It is rule-driven, deterministic, and produces a well-formed
Proposal for a patient state.

**Read this before quoting any score built on it.** This proposer follows the
same guideline the gate checks against, so it passes the gate essentially by
construction. That proves the pipeline runs and the contracts hold. It proves
nothing clinical whatsoever. The number that means something comes from Set C —
real retrospective visits, blind-scored by Indonesian physicians — and no score
from Set A or Set B should ever be presented as clinical validation.

When a real model lands behind the router, it implements this same interface and
the gate does not change.
"""

from __future__ import annotations

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

REFERENCE_PROVENANCE = Provenance(
    model="reference-rule-proposer@0.1.0",
    prompt_template="none@0.1.0",
    corpus="id-htn-2026-08@1",
)

# class -> (molecule, starting mg, doses per day)
LADDER = [
    ("ccb_dihydropyridine", "amlodipine", 5.0, 1),
    ("acei", "captopril", 25.0, 2),
    ("thiazide", "hydrochlorothiazide", 25.0, 1),
]


def propose(state, rules) -> Proposal:
    guideline = rules.guideline
    resolution = resolve_target(guideline, Context(state))

    sbp = state.latest("sbp")
    dbp = state.latest("dbp")
    sbp_v = sbp.value if sbp else None
    dbp_v = dbp.value if dbp else None

    trend = _trend(state)

    # When no target is defined we still emit a proposal, because the gate is
    # what refuses — not the proposer. Belt and braces: the refusal is tested,
    # not assumed.
    if not resolution.defined:
        return Proposal(
            assessment=Assessment.UNCONTROLLED,
            recommendation=Recommendation.REFER,
            bp_trend_summary=trend,
            target_used=None,
            confidence=0.5,
            provenance=REFERENCE_PROVENANCE,
            uncertainty_notes="No target defined for this patient group.",
        )

    target = resolution.target
    at_target = (
        sbp_v is not None and dbp_v is not None
        and sbp_v < target.sbp_lt and dbp_v < target.dbp_lt
    )

    target_used = Target(sbp_lt=target.sbp_lt, dbp_lt=target.dbp_lt, citation=target.citation)
    assertions = [
        Assertion(
            text=f"Target for this patient is below {target.sbp_lt:.0f}/{target.dbp_lt:.0f} mmHg.",
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
            provenance=REFERENCE_PROVENANCE,
            assertions=assertions,
            patient_instructions="Lanjutkan obat seperti biasa. Kontrol kembali sesuai jadwal.",
            follow_up_interval_days=90,
        )

    change = _next_step(state, rules)
    if change is None:
        return Proposal(
            assessment=Assessment.UNCONTROLLED,
            recommendation=Recommendation.REFER,
            bp_trend_summary=trend,
            target_used=target_used,
            confidence=0.75,
            provenance=REFERENCE_PROVENANCE,
            assertions=assertions,
            uncertainty_notes="Ladder exhausted at this site; specialist review.",
            follow_up_interval_days=30,
        )

    recommendation = (
        Recommendation.TITRATE_UP if change.action is ChangeAction.INCREASE
        else Recommendation.ADD_AGENT
    )

    return Proposal(
        assessment=Assessment.UNCONTROLLED,
        recommendation=recommendation,
        bp_trend_summary=trend,
        target_used=target_used,
        confidence=0.85,
        provenance=REFERENCE_PROVENANCE,
        medication_changes=[change],
        assertions=assertions,
        patient_instructions="Minum obat setiap hari. Kontrol ulang dalam 4 minggu.",
        follow_up_interval_days=28,
    )


def _next_step(state, rules) -> MedicationChange | None:
    """Increase what is already there before adding anything new."""
    current = {m.molecule: m for m in state.medications}

    for _, molecule, _, _ in LADDER:
        med = current.get(molecule)
        if med is None:
            continue
        mol = rules.molecules.get(molecule)
        if mol is None:
            continue
        max_daily = mol.dosing.get("max_mg_daily")
        max_per_dose = mol.dosing.get("max_mg_per_dose")
        if max_daily is None or med.mg_daily >= max_daily:
            continue
        stepped = min(med.mg_per_dose * 2, max_per_dose or med.mg_per_dose * 2)
        if stepped * med.doses_per_day > max_daily or stepped <= med.mg_per_dose:
            continue
        return MedicationChange(
            action=ChangeAction.INCREASE,
            molecule=molecule,
            mg_per_dose=stepped,
            doses_per_day=med.doses_per_day,
            rationale="Above target on the current dose; titrate before adding an agent.",
            citation=mol.citation,
        )

    for _, molecule, mg, per_day in LADDER:
        if molecule in current:
            continue
        mol = rules.molecules.get(molecule)
        if mol is None:
            continue
        return MedicationChange(
            action=ChangeAction.START,
            molecule=molecule,
            mg_per_dose=mg,
            doses_per_day=per_day,
            rationale="Above target on maximum tolerated existing therapy; add an agent.",
            citation=mol.citation,
        )

    return None


def _trend(state) -> str:
    series = state.bp_series(limit=4)
    if not series:
        return "No blood-pressure readings recorded."
    parts = [
        f"{d.isoformat()} {int(s)}/{int(dv)}"
        for d, s, dv in series
        if s is not None and dv is not None
    ]
    return "Recent readings: " + ", ".join(parts) + "."
