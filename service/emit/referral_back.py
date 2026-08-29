"""The referral-back draft.

When a chronic patient is genuinely stable, the specialist is meant to issue a
referral-back letter moving them to primary care, with their chronic
prescription attached. The payer's own checklist has three conditions — the
right diagnosis, genuinely stable, the right drugs — and all three are
answerable from structured state, so the letter can be drafted the moment they
hold.

Why this is worth building rather than a nice-to-have: stable follow-ups are
low-tariff visits occupying the scarcest resource in the network, which is
specialist time. Drafting the letter the moment the criteria hold frees those
slots, and does it in the direction the payer is already pushing. It also
exercises exactly the machinery everything else is built on — deterministic
criteria, a drafted document, one signature — with no model anywhere.

It is drafted, never issued. Like everything else here it waits for a
signature.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReferralBackAssessment:
    eligible: bool
    met: list[str] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)
    draft: str | None = None


def assess(state, rules) -> ReferralBackAssessment:
    config = rules.guideline.get("referral_back") or {}
    if not config.get("enabled"):
        return ReferralBackAssessment(eligible=False, unmet=["referral-back is not enabled"])

    criteria = config.get("criteria") or {}
    met: list[str] = []
    unmet: list[str] = []

    # 1 — the right diagnosis
    prefix = ((criteria.get("right_diagnosis") or {}).get("predicate") or {}).get(
        "diagnosis_prefix"
    )
    if prefix and state.has_diagnosis_prefix(prefix):
        met.append(f"confirmed primary diagnosis ({prefix})")
    else:
        unmet.append("no confirmed primary diagnosis for this programme")

    # 2 — genuinely stable
    stable_cfg = criteria.get("truly_stable") or {}
    needed = int(stable_cfg.get("consecutive_at_target_visits", 3))
    target = _target(rules, state)
    if target is None:
        unmet.append("no defined target, so stability cannot be judged")
    else:
        streak = _at_target_streak(state, target)
        if streak >= needed:
            met.append(f"at target for {streak} consecutive visits (needs {needed})")
        else:
            unmet.append(f"at target for {streak} of the {needed} visits required")

    # 3 — the right drugs
    offenders = [
        m.molecule for m in state.medications if not rules.is_prescribable(m.molecule)
    ]
    if offenders:
        unmet.append(f"regimen includes items outside the programme list: {', '.join(offenders)}")
    else:
        met.append("entire regimen is on the programme list")

    eligible = not unmet
    return ReferralBackAssessment(
        eligible=eligible,
        met=met,
        unmet=unmet,
        draft=_draft(state) if eligible else None,
    )


def _target(rules, state):
    from service.rules.predicates import Context
    from service.rules.targets import resolve_target

    resolution = resolve_target(rules.guideline, Context(state))
    return resolution.target if resolution.defined else None


def _at_target_streak(state, target) -> int:
    """Consecutive most-recent visits at target, newest first."""
    streak = 0
    readings = list(reversed(state.bp_series(limit=12)))
    for _, sbp, dbp in readings:
        if sbp is None or dbp is None:
            break
        if sbp < target.sbp_lt and dbp < target.dbp_lt:
            streak += 1
        else:
            break
    return streak


def _draft(state) -> str:
    medications = ", ".join(
        f"{m.molecule} {m.mg_per_dose:g} mg {m.doses_per_day}x/hari"
        for m in state.medications
    )
    return (
        "SURAT RUJUK BALIK (draf — menunggu tanda tangan dokter spesialis)\n"
        f"Pasien: {state.patient_id}\n"
        f"Tanggal: {state.as_of.isoformat()}\n"
        "Kondisi: stabil dan terkontrol, memenuhi kriteria rujuk balik.\n"
        f"Obat rutin: {medications}\n"
        "Mohon dilanjutkan pengambilan obat rutin di FKTP sesuai program."
    )
