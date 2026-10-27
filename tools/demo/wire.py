"""Encounters, patients and failures as plain JSON the browser can hold.

Every dict the surface renders is built here, and every one of them comes from
a real run. The moment one number on that page is a literal, the "every claim
traceable" posture is gone, and this is exactly the audience that will ask.

The failure shells matter as much as the success path. A record that cannot be
read, a drafter that returns garbage and a residency refusal are three
different events, and describing any of them as another would be a false
statement about what happened.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from service.gate.checks import catalogue as check_catalogue


def plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value") and hasattr(value, "name"):  # Enum
        return value.value
    return value


def patient_view(state, site, rules) -> dict:
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
        observations.append(
            {
                "code": obs.code,
                "label": term.get("label", obs.code),
                "plain": term.get("plain", ""),
                "value": obs.value,
                "unit": obs.unit or term.get("unit", ""),
                "taken_at": obs.taken_at.isoformat(),
                "age_days": age_days,
                "source": plain(obs.source),
                # Staleness is a clinical fact here, not a display detail: the
                # sufficiency check refuses to advise on measurements past their age.
                "stale": bool(age_days is not None and age_days > 90),
            }
        )

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
                "class_label": (class_terms.get(rules.drug_class_of(m.molecule) or "") or {}).get(
                    "label", ""
                ),
                "plain": (class_terms.get(rules.drug_class_of(m.molecule) or "") or {}).get(
                    "plain", ""
                ),
                "since": m.since.isoformat() if m.since else None,
                "source": plain(m.source),
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
            for k, v in sorted(state.symptoms.items())
            if v
        ],
        "symptoms_denied": [
            {"code": k, "plain": symptom_terms.get(k, k.replace("_", " "))}
            for k, v in sorted(state.symptoms.items())
            if not v
        ],
        "flags": [
            {"code": k, "plain": flag_terms.get(k, k.replace("_", " "))}
            for k, v in sorted(state.flags.items())
            if v
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
        "evidence": [
            {
                "service": row.get("service"),
                "label": (obs_terms.get(row.get("service")) or {}).get("label", row.get("service")),
                "last_performed": row.get("last_performed"),
                "volume_30d": row.get("volume_30d"),
            }
            for row in (site.get("evidence_ref") or [])
        ],
    }


def proposal_view(proposal, rules) -> dict | None:
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
            plain(proposal.recommendation), ""
        ),
        "assessment_plain": (glossary.get("assessments") or {}).get(plain(proposal.assessment), ""),
        "patient_instructions_gloss": proposal.patient_instructions_en or gloss,
        "concerns": [
            {"text": c.text, "urgency": c.urgency.value, "citation": c.citation}
            for c in proposal.concerns
        ],
        "assessment": plain(proposal.assessment),
        "recommendation": plain(proposal.recommendation),
        "bp_trend_summary": proposal.bp_trend_summary,
        "confidence": proposal.confidence,
        "medication_changes": [
            {
                "action": plain(c.action),
                "molecule": c.molecule,
                "mg_per_dose": c.mg_per_dose,
                "doses_per_day": c.doses_per_day,
                "rationale": c.rationale,
                "citation": c.citation,
                "class_label": (classes.get(rules.drug_class_of(c.molecule) or "") or {}).get(
                    "label", ""
                ),
                "class_plain": (classes.get(rules.drug_class_of(c.molecule) or "") or {}).get(
                    "plain", ""
                ),
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


def unreadable_record(wire: dict, index: int, rules, site, exc: Exception) -> dict:
    """A record that could not be read at all. Named, not silently dropped."""
    identifier = str(wire.get("patient_id") or f"record {index}")
    return {
        "key": identifier,
        "title": identifier,
        "note": "This record could not be read.",
        "watch_for": "",
        "patient": {
            "patient_id": identifier,
            "age": None,
            "sex": "",
            "as_of": "",
            "sbp": None,
            "dbp": None,
            "medications": [],
            "diagnoses": [],
            "symptoms": [],
            "symptoms_denied": [],
            "flags": [],
            "allergies": [],
            "intolerances": [],
            "observations": [],
            "history": [],
            "site_id": site.get("site_id", ""),
            "site_label": site.get("label", ""),
            "site_tier": site.get("tier", ""),
            "site_as_of": site.get("as_of", ""),
            "labs_available": [],
            "stocked": [],
            "evidence": [],
        },
        "outcome": "unreadable",
        "outcome_plain": (
            "The record itself could not be read, so nothing ran. This is a "
            "problem with the input, not with the patient or the system."
        ),
        "committed": False,
        "error": f"{type(exc).__name__}: {exc}",
        "message": "",
        "exclusions": [],
        "discrepancies": [],
        "trail": [],
        "presentation": {
            "band": "green",
            "band_label": "",
            "headline": "",
            "gloss": "",
            "silent": True,
            "shows_draft": False,
            "requires_acknowledgement": False,
            "lines": [],
            "audit": [],
        },
        "checks": [{**entry, "findings": [], "blocked": False} for entry in check_catalogue()],
        "findings": [],
        "proposal": None,
        "claim": None,
        "signature": None,
        "questions": [],
    }


def failed_encounter(scenario, rules, exc: Exception) -> dict:
    """An encounter the drafter could not complete. Not a clinical outcome.

    A residency refusal is separated from a model failure because they are not
    the same event and describing one as the other is a false statement about
    what happened. Nothing was sent: the guard refused before a request was
    built. Reporting that as "the model returned something unusable" would
    misdescribe the one behaviour this system most wants understood.
    """
    residency = type(exc).__name__ == "ResidencyError"
    if residency:
        return {
            **failed_shell(scenario, rules),
            "outcome": "residency_refused",
            "outcome_plain": (
                "This record is not marked synthetic, so it was refused before any "
                "request was built. Nothing left the machine. Health data must be "
                "processed in-country, and a hosted model sits outside that boundary."
            ),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        **failed_shell(scenario, rules),
        "outcome": "drafter_failed",
        "outcome_plain": (
            "The drafter could not produce a usable proposal, so nothing reached "
            "the safety checks and nothing reached the doctor. This is a failure "
            "of the model, not of the patient's care. The doctor proceeds as "
            "they would without the system."
        ),
        "error": f"{type(exc).__name__}: {exc}",
    }


def failed_shell(scenario, rules) -> dict:
    """The fields every failed encounter carries, whatever failed."""
    return {
        "key": scenario.key,
        "title": scenario.title,
        "note": scenario.note,
        "watch_for": scenario.watch_for,
        "patient": patient_view(scenario.state, scenario.site, rules),
        "committed": False,
        "trail": ["ROUTE", "ELIGIBLE", "INTAKE", "RECONCILE", "PROPOSE"],
        "presentation": {
            "band": "green",
            "band_label": "",
            "headline": "",
            "gloss": "",
            "silent": True,
            "shows_draft": False,
            "requires_acknowledgement": False,
            "lines": [],
            "audit": [],
        },
        "checks": [{**entry, "findings": [], "blocked": False} for entry in check_catalogue()],
        "message": "",
        "exclusions": [],
        "discrepancies": [],
        "findings": [],
        "proposal": None,
        "claim": None,
        "signature": None,
        "questions": [],
    }
