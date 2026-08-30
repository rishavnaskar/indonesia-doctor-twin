"""Run the scenarios and capture everything the surface needs.

Every field on the page comes from here, and everything here comes from a real
`run_encounter`. Nothing is written by hand. The moment one number on that page
is a literal, the whole "every claim traceable" posture is gone — and this is
exactly the audience that will ask.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.present.layer import Labels, present
from service.router.router import default_router
from service.signing import AuditLog, Signer
from tools import scenarios as scenario_module

NOW = datetime(2026, 8, 29, 10, 0)


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value") and hasattr(value, "name"):  # Enum
        return value.value
    return value


def _patient(state, site) -> dict:
    sbp, dbp = state.latest("sbp"), state.latest("dbp")
    return {
        "patient_id": state.patient_id,
        "age": state.age,
        "sbp": round(sbp.value) if sbp else None,
        "dbp": round(dbp.value) if dbp else None,
        "medications": [
            f"{m.molecule} {m.mg_per_dose:g} mg x{m.doses_per_day}"
            for m in state.medications
        ],
        "diagnoses": [d.code for d in state.diagnoses],
        "site_id": site["site_id"],
        "site_label": site.get("label", ""),
        "site_tier": site.get("tier", ""),
        "site_as_of": site.get("as_of", ""),
        "labs_available": sorted(site.get("labs_available") or []),
    }


def _proposal(proposal) -> dict | None:
    if proposal is None:
        return None
    return {
        "assessment": _plain(proposal.assessment),
        "recommendation": _plain(proposal.recommendation),
        "bp_trend_summary": proposal.bp_trend_summary,
        "confidence": proposal.confidence,
        "medication_changes": [
            {
                "action": _plain(c.action),
                "molecule": c.molecule,
                "mg_per_dose": c.mg_per_dose,
                "doses_per_day": c.doses_per_day,
                "rationale": c.rationale,
                "citation": c.citation,
            }
            for c in proposal.medication_changes
        ],
        "investigations": list(proposal.investigations),
        "patient_instructions": proposal.patient_instructions,
        "follow_up_interval_days": proposal.follow_up_interval_days,
        "uncertainty_notes": proposal.uncertainty_notes,
        "provenance": [
            proposal.provenance.model,
            proposal.provenance.prompt_template,
            proposal.provenance.corpus,
        ],
    }


def _encounter(scenario, rules, labels, router) -> dict:
    audit_log = AuditLog()
    practitioner = scenario.site["practitioners"][0]["practitioner_id"]

    original = router.propose
    if scenario.tamper is not None:
        def tampered(state, rs, site=None, **kwargs):
            proposal = original(state, rs, site)
            scenario.tamper(proposal)
            return proposal
        router.propose = tampered  # type: ignore[method-assign]

    try:
        result = run_encounter(
            scenario.state, rules, scenario.site, router, InMemoryRuntime(),
            thread_id=f"DEMO-{scenario.key}",
            signer=Signer(practitioner, True),
            audit=audit_log, now=NOW,
        )
    finally:
        router.propose = original  # type: ignore[method-assign]

    view = present(
        result.outcome.value, labels,
        decision=result.decision,
        questions=tuple(result.questions_for_clinician),
    )

    signature = None
    if audit_log.records:
        record = audit_log.records[-1]
        signature = {
            "practitioner_id": record.practitioner_id,
            "role": record.role,
            "licence_expires": record.licence_expires.isoformat(),
            "decision": record.decision,
            "signed_at": record.signed_at.isoformat(),
            "provenance": list(record.proposal_provenance),
        }

    return {
        "key": scenario.key,
        "title": scenario.title,
        "note": scenario.note,
        "watch_for": scenario.watch_for,
        "patient": _patient(scenario.state, scenario.site),
        "outcome": result.outcome.value,
        "committed": result.outcome is Outcome.COMMITTED,
        "trail": list(result.trail),
        "presentation": {
            "band": view.band.value,
            "band_label": labels.band(view.band),
            "headline": view.headline,
            "gloss": view.gloss,
            "silent": view.silent,
            "shows_draft": view.shows_draft,
            "requires_acknowledgement": view.requires_acknowledgement,
            "lines": [_plain(line) for line in view.lines],
            "audit": [_plain(line) for line in view.audit],
        },
        "findings": [
            {
                "check": f.check,
                "check_name": f.check_name,
                "severity": _plain(f.severity),
                "message": f.message,
                "rule_id": f.rule_id,
                "citation": f.citation,
                "converts_to_referral": f.converts_to_referral,
            }
            for f in (result.decision.findings if result.decision else [])
        ],
        "proposal": _proposal(result.proposal),
        "claim": {
            "codes": list(result.claim.codes),
        } if result.claim else None,
        "signature": signature,
        "questions": list(result.questions_for_clinician),
    }


def collect(pack_id: str = "id", router=None) -> dict:
    """Run every scenario and return the whole page's data."""
    rules = load_pack(pack_id)
    labels = Labels.from_pack(rules.language)
    router = router or default_router()

    encounters = [
        _encounter(scenario, rules, labels, router)
        for scenario in scenario_module.build(rules)
    ]

    reasoner = "deterministic reference reasoner (no model)"
    try:
        reasoner = router.get(router.default).backend.version()
    except (KeyError, AttributeError):
        pass

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": NOW.isoformat(),
        "pack": {
            "pack_id": rules.pack_id,
            "version": rules.version,
            "review_status": rules.review_status,
            "molecule_count": len(rules.molecules),
            "site_count": len(rules.sites),
            "language": rules.language.get("output_language", ""),
        },
        "reasoner": reasoner,
        "encounters": encounters,
        "declined": sum(1 for e in encounters if not e["committed"]),
        "total": len(encounters),
    }
