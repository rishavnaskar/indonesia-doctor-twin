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

from service.gate.checks import catalogue as check_catalogue
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.gate.types import Severity
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


def _patient(state, site, rules) -> dict:
    """Everything a reader needs to judge the case for themselves.

    The earlier version showed a patient id, an age and one blood pressure,
    which is not a clinical picture — it is a row. Someone asked to evaluate
    whether a refusal was correct cannot do it without the history, the current
    symptoms, the drugs and how stale the labs are.
    """
    glossary = rules.glossary
    codes = glossary.get("diagnoses") or {}
    obs_terms = glossary.get("observations") or {}
    symptom_terms = glossary.get("symptoms") or {}
    flag_terms = glossary.get("flags") or {}
    class_terms = glossary.get("drug_classes") or {}

    sbp, dbp = state.latest("sbp"), state.latest("dbp")

    observations = []
    seen: set[str] = set()
    for obs in sorted(state.observations, key=lambda o: o.taken_at, reverse=True):
        if obs.code in seen:
            continue
        seen.add(obs.code)
        term = obs_terms.get(obs.code) or {}
        age_days = state.observation_age_days(obs.code)
        observations.append({
            "code": obs.code,
            "label": term.get("label", obs.code),
            "plain": term.get("plain", ""),
            "value": obs.value,
            "unit": obs.unit or term.get("unit", ""),
            "taken_at": obs.taken_at.isoformat(),
            "age_days": age_days,
            "source": _plain(obs.source),
            # Staleness is a clinical fact here, not a display detail: the
            # sufficiency check refuses to advise on measurements past their age.
            "stale": bool(age_days is not None and age_days > 90),
        })

    history = [
        {
            "encounter_id": e.encounter_id,
            "date": e.encounter_date.isoformat(),
            "sbp": round(e.sbp) if e.sbp else None,
            "dbp": round(e.dbp) if e.dbp else None,
            "decision": e.decision or "",
            "signed_by": e.signed_by or "",
        }
        for e in sorted(state.encounters, key=lambda e: e.encounter_date, reverse=True)
    ]

    return {
        "patient_id": state.patient_id,
        "age": state.age,
        "sex": {"M": "Male", "F": "Female"}.get(state.sex, state.sex),
        "as_of": state.as_of.isoformat(),
        "sbp": round(sbp.value) if sbp else None,
        "dbp": round(dbp.value) if dbp else None,
        "medications": [
            {
                "text": f"{m.molecule} {m.mg_per_dose:g} mg x{m.doses_per_day}/day",
                "molecule": m.molecule,
                "drug_class": rules.drug_class_of(m.molecule) or "",
                "class_label": (class_terms.get(rules.drug_class_of(m.molecule) or "") or {})
                                .get("label", ""),
                "plain": (class_terms.get(rules.drug_class_of(m.molecule) or "") or {})
                          .get("plain", ""),
                "since": m.since.isoformat() if m.since else None,
                "source": _plain(m.source),
            }
            for m in state.medications
        ],
        "diagnoses": [
            {
                "code": d.code,
                # Fall back to the three-character category when the specific
                # code is not in the glossary: "E11.9" still reads as diabetes.
                "plain": codes.get(d.code) or codes.get(d.code.split(".")[0], ""),
                "onset": d.onset.isoformat() if d.onset else None,
                "status": d.status,
            }
            for d in state.diagnoses
        ],
        "symptoms": [
            {"code": k, "plain": symptom_terms.get(k, k.replace("_", " "))}
            for k, v in sorted(state.symptoms.items()) if v
        ],
        "symptoms_denied": [
            {"code": k, "plain": symptom_terms.get(k, k.replace("_", " "))}
            for k, v in sorted(state.symptoms.items()) if not v
        ],
        "flags": [
            {"code": k, "plain": flag_terms.get(k, k.replace("_", " "))}
            for k, v in sorted(state.flags.items()) if v
        ],
        "allergies": [
            {"substance": a.substance, "reaction": a.reaction or ""} for a in state.allergies
        ],
        "intolerances": [
            {
                "molecule": i.molecule,
                "drug_class": i.drug_class,
                "class_label": (class_terms.get(i.drug_class) or {}).get("label", i.drug_class),
                "documented_at": i.documented_at.isoformat(),
                "reaction": i.reaction or "",
            }
            for i in state.intolerances
        ],
        "observations": observations,
        "history": history,
        "site_id": site["site_id"],
        "site_label": site.get("label", ""),
        "site_tier": site.get("tier", ""),
        "site_as_of": site.get("as_of", ""),
        "labs_available": sorted(site.get("labs_available") or []),
        "stocked": sorted(site.get("stocked_molecules") or []),
    }


def _proposal(proposal, rules) -> dict | None:
    if proposal is None:
        return None
    glossary = rules.glossary
    classes = glossary.get("drug_classes") or {}
    instructions = proposal.patient_instructions
    gloss = ""
    for key, text in (rules.guideline.get("patient_instructions") or {}).items():
        if text == instructions:
            gloss = (rules.guideline.get("patient_instructions_gloss") or {}).get(key, "")
            break
    return {
        "recommendation_plain": (glossary.get("recommendations") or {}).get(
            _plain(proposal.recommendation), ""),
        "assessment_plain": (glossary.get("assessments") or {}).get(
            _plain(proposal.assessment), ""),
        "patient_instructions_gloss": gloss,
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
                "class_label": (classes.get(rules.drug_class_of(c.molecule) or "") or {})
                                .get("label", ""),
                "class_plain": (classes.get(rules.drug_class_of(c.molecule) or "") or {})
                                .get("plain", ""),
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


class _Tampered:
    """A router that corrupts the draft on its way out.

    Used to plant the errors the gate is supposed to catch. Holds no state of
    its own and never touches the router it wraps, so concurrent encounters
    cannot interfere with each other.
    """

    def __init__(self, router, tamper):
        self._router = router
        self._tamper = tamper

    def __getattr__(self, name):
        return getattr(self._router, name)

    def propose(self, state, rules, site=None, **kwargs):
        proposal = self._router.propose(state, rules, site, **kwargs)
        self._tamper(proposal)
        return proposal


def _failed(scenario, rules, exc: Exception) -> dict:
    """An encounter the drafter could not complete. Not a clinical outcome."""
    return {
        "key": scenario.key,
        "title": scenario.title,
        "note": scenario.note,
        "watch_for": scenario.watch_for,
        "patient": _patient(scenario.state, scenario.site, rules),
        "outcome": "drafter_failed",
        "outcome_plain": (
            "The drafter could not produce a usable proposal, so nothing reached "
            "the safety checks and nothing reached the doctor. This is a failure "
            "of the model, not of the patient's care — the doctor proceeds as "
            "they would without the system."
        ),
        "committed": False,
        "error": f"{type(exc).__name__}: {exc}",
        "trail": ["ELIGIBLE", "INTAKE", "RECONCILE", "PROPOSE"],
        "presentation": {
            "band": "green", "band_label": "", "headline": "", "gloss": "",
            "silent": True, "shows_draft": False, "requires_acknowledgement": False,
            "lines": [], "audit": [],
        },
        "checks": [{**entry, "findings": [], "blocked": False} for entry in check_catalogue()],
        "findings": [],
        "proposal": None,
        "claim": None,
        "signature": None,
        "questions": [],
    }


def _encounter(scenario, rules, labels, router) -> dict:
    audit_log = AuditLog()
    practitioner = scenario.site["practitioners"][0]["practitioner_id"]

    # A tampering scenario used to swap router.propose in place and swap it back
    # in a finally. That mutates state shared with every other caller, which was
    # already wrong when two requests overlapped and is plainly wrong now that a
    # background thread builds the page. Wrap the router instead.
    effective = _Tampered(router, scenario.tamper) if scenario.tamper else router

    try:
        result = run_encounter(
            scenario.state, rules, scenario.site, effective, InMemoryRuntime(),
            thread_id=f"DEMO-{scenario.key}",
            signer=Signer(practitioner, True),
            audit=audit_log, now=NOW,
        )
    except Exception as exc:  # noqa: BLE001
        # A model that returns unparseable output, refuses, gets rate-limited or
        # runs out of token budget is a normal event when the drafter is a weak
        # free model — and it is exactly the event this architecture is meant to
        # survive. It belongs on the page as one failed encounter, never as a
        # dead page: a demo that dies on the first bad JSON is a worse advert
        # than a demo that shows the failure being contained.
        return _failed(scenario, rules, exc)

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
        "patient": _patient(scenario.state, scenario.site, rules),
        "outcome": result.outcome.value,
        "outcome_plain": (rules.glossary.get("outcomes") or {}).get(result.outcome.value, ""),
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
        "checks": [
            {
                **entry,
                "findings": [f.rule_id or f.check_name
                             for f in (result.decision.findings if result.decision else [])
                             if f.check == entry["number"]],
                "blocked": any(
                    f.check == entry["number"] and f.severity is Severity.BLOCK
                    for f in (result.decision.findings if result.decision else [])
                ),
            }
            for entry in check_catalogue()
        ],
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
        "proposal": _proposal(result.proposal, rules),
        "claim": {
            "codes": [
                {"code": c,
                 "plain": (rules.glossary.get("diagnoses") or {}).get(
                     c, (rules.glossary.get("diagnoses") or {}).get(c.split(".")[0], ""))}
                for c in result.claim.codes
            ],
        } if result.claim else None,
        "signature": signature,
        "questions": list(result.questions_for_clinician),
    }


def collect(pack_id: str = "id", router=None, on_progress=None) -> dict:
    """Run every scenario and return the whole page's data.

    `on_progress(done, total, title, outcome)` is called after each encounter.
    A live run makes one model call per scenario and can take minutes on a
    rate-limited free tier; a surface that says nothing for that long is
    indistinguishable from one that has hung.
    """
    rules = load_pack(pack_id)
    labels = Labels.from_pack(rules.language)
    router = router or default_router()

    scenarios = scenario_module.build(rules)
    encounters = []
    for index, scenario in enumerate(scenarios, start=1):
        encounter = _encounter(scenario, rules, labels, router)
        encounters.append(encounter)
        if on_progress:
            on_progress(index, len(scenarios), scenario.title,
                        encounter.get("error") or encounter["outcome"])

    reasoner = "rule-following reference reasoner (no AI model)"
    is_model = False
    try:
        reasoner = router.get(router.default).backend.version()
        is_model = True
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
        "is_model": is_model,
        "glossary": rules.glossary,
        "checks": check_catalogue(),
        "encounters": encounters,
        "declined": sum(
            1 for e in encounters if not e["committed"] and not e.get("error")
        ),
        "drafter_failures": sum(1 for e in encounters if e.get("error")),
        "total": len(encounters),
    }
