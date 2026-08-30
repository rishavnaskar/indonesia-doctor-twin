"""Run the scenarios and capture everything the surface needs.

Every field on the page comes from here, and everything here comes from a real
`run_encounter`. Nothing is written by hand. The moment one number on that page
is a literal, the whole "every claim traceable" posture is gone — and this is
exactly the audience that will ask.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from service.gate.checks import catalogue as check_catalogue

from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.gate.types import Severity
from service.present.layer import Labels, present
from service.router.router import default_router
from service.signing import AuditLog, Signer
from tools import scenarios as scenario_module

NOW = datetime(2026, 8, 29, 10, 0)

# Free tiers are shared pools, so this stays small: the point is to overlap the
# waiting, not to win a race against everyone else on the internet.
MAX_CONCURRENT_ENCOUNTERS = 3

_STORE = None
_STORE_LOCK = threading.Lock()


def store():
    """The deployment's durable store — Postgres if one is reachable, else files.

    Opened once per process and shared, because the connection is the expensive
    part. The objects built *from* it are per-encounter: three encounters run
    concurrently, and a queue shared between threads has a read-then-write in
    `enqueue` that nothing here would notice going wrong. Rebuilding costs a
    reload of a table that a demo keeps small.
    """
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            from service.store import Store

            _STORE = Store()
    return _STORE


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
        "evidence": [
            {"service": row.get("service"),
             "label": (obs_terms.get(row.get("service")) or {}).get("label", row.get("service")),
             "last_performed": row.get("last_performed"),
             "volume_30d": row.get("volume_30d")}
            for row in (site.get("evidence_ref") or [])
        ],
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
        "concerns": [
            {"text": c.text, "urgency": c.urgency.value, "citation": c.citation}
            for c in proposal.concerns
        ],
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


def _unreadable(wire: dict, index: int, rules, site, exc: Exception) -> dict:
    """A record that could not be read at all. Named, not silently dropped."""
    identifier = str(wire.get("patient_id") or f"record {index}")
    return {
        "key": identifier,
        "title": identifier,
        "note": "This record could not be read.",
        "watch_for": "",
        "patient": {
            "patient_id": identifier, "age": None, "sex": "", "as_of": "",
            "sbp": None, "dbp": None, "medications": [], "diagnoses": [],
            "symptoms": [], "symptoms_denied": [], "flags": [], "allergies": [],
            "intolerances": [], "observations": [], "history": [],
            "site_id": site.get("site_id", ""), "site_label": site.get("label", ""),
            "site_tier": site.get("tier", ""), "site_as_of": site.get("as_of", ""),
            "labs_available": [], "stocked": [], "evidence": [],
        },
        "outcome": "unreadable",
        "outcome_plain": (
            "The record itself could not be read, so nothing ran. This is a "
            "problem with the input, not with the patient or the system."
        ),
        "committed": False,
        "error": f"{type(exc).__name__}: {exc}",
        "message": "", "exclusions": [], "discrepancies": [],
        "trail": [],
        "presentation": {
            "band": "green", "band_label": "", "headline": "", "gloss": "",
            "silent": True, "shows_draft": False, "requires_acknowledgement": False,
            "lines": [], "audit": [],
        },
        "checks": [{**entry, "findings": [], "blocked": False} for entry in check_catalogue()],
        "findings": [], "proposal": None, "claim": None, "signature": None,
        "questions": [],
    }


def _failed(scenario, rules, exc: Exception) -> dict:
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
            **_failed_shell(scenario, rules),
            "outcome": "residency_refused",
            "outcome_plain": (
                "This record is not marked synthetic, so it was refused before any "
                "request was built. Nothing left the machine. Health data must be "
                "processed in-country, and a hosted model sits outside that boundary."
            ),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        **_failed_shell(scenario, rules),
        "outcome": "drafter_failed",
        "outcome_plain": (
            "The drafter could not produce a usable proposal, so nothing reached "
            "the safety checks and nothing reached the doctor. This is a failure "
            "of the model, not of the patient's care — the doctor proceeds as "
            "they would without the system."
        ),
        "error": f"{type(exc).__name__}: {exc}",
    }


def _failed_shell(scenario, rules) -> dict:
    """The fields every failed encounter carries, whatever failed."""
    return {
        "key": scenario.key,
        "title": scenario.title,
        "note": scenario.note,
        "watch_for": scenario.watch_for,
        "patient": _patient(scenario.state, scenario.site, rules),
        "committed": False,
        "trail": ["ROUTE", "ELIGIBLE", "INTAKE", "RECONCILE", "PROPOSE"],
        "presentation": {
            "band": "green", "band_label": "", "headline": "", "gloss": "",
            "silent": True, "shows_draft": False, "requires_acknowledgement": False,
            "lines": [], "audit": [],
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


def _encounter(scenario, rules, labels, router, on_step=None) -> dict:
    # The surface used to run every encounter through an in-memory runtime and
    # an unbacked audit log, so a demo produced nothing that outlived the tab.
    # That made the persistence story a claim in a document rather than
    # something you could restart the process and go looking for.
    durable = store()
    runtime = durable.runtime()
    audit_log = durable.audit_log()
    queue = durable.outbound()

    # How many signatures existed before this encounter, so the view below reads
    # this encounter's record rather than the last one anybody wrote.
    signed_before = len(audit_log.records)
    practitioner = scenario.site["practitioners"][0]["practitioner_id"]

    # A tampering scenario used to swap router.propose in place and swap it back
    # in a finally. That mutates state shared with every other caller, which was
    # already wrong when two requests overlapped and is plainly wrong now that a
    # background thread builds the page. Wrap the router instead.
    effective = _Tampered(router, scenario.tamper) if scenario.tamper else router

    try:
        result = run_encounter(
            scenario.state, rules, scenario.site, effective, runtime,
            thread_id=f"DEMO-{scenario.key}-{uuid4().hex[:8]}",
            signer=Signer(practitioner, True),
            audit=audit_log, queue=queue, now=NOW, on_step=on_step,
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
        discrepancies=tuple(result.reconciliation.discrepancies),
        concerns=tuple(getattr(result.proposal, "concerns", ()) or ()),
    )

    signature = None
    if len(audit_log.records) > signed_before:
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
        "message": result.message,
        "exclusions": [
            {"id": e.exclusion_id, "label": e.label, "reason": e.reason}
            for e in result.exclusions
        ],
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
                "discrepancies": [
            {
                "kind": d.kind, "text": d.text, "gloss": d.gloss,
                "molecule": d.molecule, "record_says": d.record_says,
                "patient_says": d.patient_says,
                "interacts_with": list(d.interacts_with), "material": d.material,
            }
            for d in result.reconciliation.discrepancies
        ],
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
        "discrepancies": [
            {
                "kind": d.kind, "text": d.text, "gloss": d.gloss,
                "molecule": d.molecule, "record_says": d.record_says,
                "patient_says": d.patient_says,
                "interacts_with": list(d.interacts_with), "material": d.material,
            }
            for d in result.reconciliation.discrepancies
        ],
        "findings": [
            {
                "check": f.check,
                "check_name": f.check_name,
                "severity": _plain(f.severity),
                "message": f.message,
                "message_local": f.message_local,
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


def run_patients(
    wire_patients: list[dict],
    site_id: str = "SITE-A",
    pack_id: str = "id",
    router=None,
    on_progress=None,
    on_step=None,
) -> dict:
    """Run patients the user built or uploaded, through the identical pipeline.

    Deliberately the same `_encounter` the scripted scenarios use. A demo whose
    interactive mode takes a different path through the system is demonstrating
    something other than the system.
    """
    from tools.demo.patients import from_wire
    from tools.scenarios import Scenario

    rules = load_pack(pack_id)
    labels = Labels.from_pack(rules.language)
    router = router or default_router()

    if site_id not in rules.sites:
        raise KeyError(f"unknown site {site_id!r}. Known: {sorted(rules.sites)}")
    site = rules.sites[site_id]

    def one(item: tuple[int, dict]) -> dict:
        index, wire = item
        step = (lambda name, i=index: on_step(i, name)) if on_step else None
        try:
            state = from_wire(wire)
        except Exception as exc:  # noqa: BLE001
            # Contained to one visit. Rejecting a whole cohort because one
            # pasted record has a bad age is the same failure already fixed for
            # drafters, and it is worse here: the reader cannot tell which
            # record was the problem.
            encounter = _unreadable(wire, index, rules, site, exc)
        else:
            scenario = Scenario(
                key=state.patient_id,
                title=f"{state.patient_id} — {state.age}, {state.sex}",
                note=f"Built in the browser, run at {site_id}.",
                state=state,
                site=site,
                watch_for="",
            )
            encounter = _encounter(scenario, rules, labels, router, on_step=step)
        if on_progress:
            on_progress(index, len(wire_patients),
                        encounter.get("title") or str(index),
                        encounter.get("error") or encounter["outcome"])
        return encounter

    # Encounters are independent — separate patients, separate state, no shared
    # mutable anything since the tampering router stopped monkeypatching. Run
    # them together.
    #
    # This is a demo-latency fix and nothing more: measured at up to two minutes
    # per patient against a free reasoning model, three patients sequentially is
    # six minutes of a silent screen. Concurrency is modest because the free
    # tiers are shared pools and hammering one earns a 429 for everybody.
    workers = 1 if router is None else min(MAX_CONCURRENT_ENCOUNTERS, len(wire_patients))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            encounters = list(pool.map(one, enumerate(wire_patients, start=1)))
    else:
        encounters = [one(item) for item in enumerate(wire_patients, start=1)]

    reasoner = "rule-following reference reasoner (no AI model)"
    is_model = False
    try:
        reasoner = router.get(router.default).backend.version()
        is_model = True
    except (KeyError, AttributeError):
        pass

    return {
        "encounters": encounters,
        "reasoner": reasoner,
        "is_model": is_model,
        "declined": sum(1 for e in encounters if not e["committed"] and not e.get("error")),
        "drafter_failures": sum(1 for e in encounters if e["outcome"] == "drafter_failed"),
        "unreadable": sum(1 for e in encounters if e["outcome"] == "unreadable"),
        "residency_refused": sum(1 for e in encounters if e["outcome"] == "residency_refused"),
        "total": len(encounters),
    }


def compare_sites(wire_patients: list[dict], pack_id: str = "id", router=None) -> dict:
    """The same patients at every hospital, side by side.

    The single clearest thing this system does is give two different right
    answers to the same patient depending on where they are standing — ask for
    the test where it can be run, refer where it cannot. Reaching that through a
    dropdown, twice, means most people never see it.
    """
    rules = load_pack(pack_id)
    by_site = {}
    for site_id in rules.sites:
        result = run_patients(wire_patients, site_id=site_id, pack_id=pack_id, router=router)
        by_site[site_id] = {
            e["key"]: {
                "outcome": e["outcome"],
                "band": e["presentation"]["band"],
                "reasons": [f["message"] for f in e["findings"] if f["severity"] == "block"],
                "recommendation": (e["proposal"] or {}).get("recommendation"),
            }
            for e in result["encounters"]
        }
    keys = [e for e in by_site[next(iter(by_site))]]
    return {
        "sites": [
            {"site_id": s["site_id"], "label": s.get("label", ""), "tier": s.get("tier", "")}
            for s in rules.sites.values()
        ],
        "patients": keys,
        "by_site": by_site,
        # The rows worth looking at: same patient, different answer.
        "divergent": [
            key for key in keys
            if len({by_site[s][key]["outcome"] for s in by_site}) > 1
        ],
    }


def vocabulary(pack_id: str = "id") -> dict:
    """What the browser needs to build a patient form.

    Read from the pack rather than written into the page, for the same reason
    everything else clinical is: a drug list, a symptom set and a site roster are
    national vocabulary, and hard-coding them in JavaScript would put the country
    back into the engine by the back door.
    """
    rules = load_pack(pack_id)
    glossary = rules.glossary
    return {
        "molecules": [
            {"molecule": name, "drug_class": mol.drug_class,
             "forms_mg": mol.forms_mg,
             "label": (glossary.get("drug_classes") or {}).get(mol.drug_class, {}).get("label", "")}
            for name, mol in sorted(rules.molecules.items())
        ],
        "sites": [
            {"site_id": s["site_id"], "label": s.get("label", ""), "tier": s.get("tier", ""),
             "labs_available": sorted(s.get("labs_available") or []),
             "stocked": sorted(s.get("stocked_molecules") or [])}
            for s in rules.sites.values()
        ],
        "symptoms": [
            {"code": k, "plain": v} for k, v in sorted((glossary.get("symptoms") or {}).items())
        ],
        "flags": [
            {"code": k, "plain": v} for k, v in sorted((glossary.get("flags") or {}).items())
        ],
        "observations": [
            {"code": k, "label": v.get("label", k), "unit": v.get("unit", ""),
             "plain": v.get("plain", "")}
            for k, v in (glossary.get("observations") or {}).items()
        ],
        "diagnoses": glossary.get("diagnoses") or {},
        # Grouped, because a flat list of fifteen gives no sense of which ones
        # are supposed to produce a draft and which are supposed to refuse.
        "profiles": [
            {"key": "clean", "label": "Blood pressure · in scope, should draft"},
            {"key": "polypharmacy", "label": "Blood pressure · already on three drugs"},
            {"key": "acei_intolerant", "label": "Blood pressure · documented ACE-inhibitor intolerance"},
            {"key": "no_target", "label": "Blood pressure · group whose target is not extracted"},
            {"key": "stale_labs", "label": "Blood pressure · labs months out of date"},
            {"key": "hyperkalaemia", "label": "Blood pressure · potassium too high"},
            {"key": "red_flag", "label": "Blood pressure · red flag present"},
            {"key": "excluded_pregnancy", "label": "Blood pressure · pregnant"},
            {"key": "excluded_minor", "label": "Blood pressure · under 18"},
            {"key": "excluded_renal", "label": "Blood pressure · severe kidney impairment"},
            {"key": "excluded_secondary", "label": "Blood pressure · secondary hypertension"},
            {"key": "excluded_resistant", "label": "Blood pressure · resistant hypertension"},
            {"key": "excluded_first_presentation", "label": "Blood pressure · first presentation"},
            {"key": "dm:clean", "label": "Diabetes · in scope, should draft"},
            {"key": "dm:no_target", "label": "Diabetes · group whose target is not extracted"},
            {"key": "dm:stale_labs", "label": "Diabetes · HbA1c months out of date"},
            {"key": "dm:red_flag", "label": "Diabetes · red flag present"},
            {"key": "dm:excluded_insulin", "label": "Diabetes · already on insulin"},
            {"key": "dm:excluded_renal", "label": "Diabetes · severe kidney impairment"},
        ],
        "pack": {"pack_id": rules.pack_id, "version": rules.version,
                 "language": rules.language.get("output_language", "")},
        "glossary": glossary,
        "checks": check_catalogue(),
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
        # Read after the encounters ran, so the counts include them. The page
        # states where this deployment keeps its state, because "durable" is
        # the kind of claim that should be checkable from the thing itself.
        "store": store().summary(),
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
