"""Run the scenarios and capture everything the surface needs.

Every field on the page comes from here, and everything here comes from a real
`run_encounter`. Nothing is written by hand. The moment one number on that page
is a literal, the whole "every claim traceable" posture is gone — and this is
exactly the audience that will ask.
"""

from __future__ import annotations

import hashlib
import json
import os
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
_RUNTIME = None
_STORE_LOCK = threading.Lock()

# Bump when the shape of an encounter dict changes. It is part of the thread id,
# so a stored view built by older code is simply never found — the encounter
# re-runs rather than being handed to a renderer that no longer understands it.
VIEW_VERSION = 1

def _forced_fresh() -> bool:
    from service.store import forced_fresh

    return forced_fresh()


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


def runtime():
    """The durable runtime, loaded once per process.

    Unlike the queue and the audit log this one is shared between the three
    concurrent encounters, because it is also the thing they look themselves up
    in — rebuilding it per encounter would re-read every checkpoint the
    deployment has ever written, once per patient. Sharing is safe here in a way
    it is not for the queue: distinct thread ids mean distinct lists, and
    `setdefault` on the thread dict is atomic.
    """
    global _RUNTIME
    # store() outside the lock, not inside it: threading.Lock is not reentrant,
    # and taking it here and again in store() deadlocks the first caller.
    durable = store()
    with _STORE_LOCK:
        if _RUNTIME is None:
            _RUNTIME = durable.runtime()
    return _RUNTIME


def _reported_drafter(encounters, fallback: str) -> str:
    """Who actually drafted these encounters, taken from the encounters.

    A resumed run never calls the model, so the backend object still reports its
    *configured* name — `some/model` rather than the `some/model@served_by` a
    hosted backend rewrites itself to once it has an answer. The page would then
    under-report provenance on exactly the runs where the provenance is already
    on file. The encounters are the record of what happened; the live object is
    only this process's configuration, so the record wins.
    """
    for encounter in encounters:
        recorded = ((encounter.get("proposal") or {}).get("provenance") or [None])[0]
        if recorded:
            return recorded
    return fallback


CLEAR_MARKER = "CLINIC-HISTORY-CLEARED"


def clinic_history(limit: int = 24) -> list[dict]:
    """Visits run at /clinic in earlier sessions, newest first.

    The interactive page was the one part of the system that kept nothing: its
    results lived in a dict in the server process and its patients lived in the
    browser tab, so closing either one lost the work. They were being written to
    the store the whole time — nothing was reading them back.
    """
    since = _cleared_at()
    latest: dict[str, dict] = {}
    for history in runtime().checkpoints.values():
        for entry in reversed(history):
            if entry.step != "rendered" or not isinstance(entry.state, dict):
                continue
            view = entry.state
            if view.get("origin") != "clinic":
                break
            ran_at = view.get("ran_at") or ""
            if since and ran_at <= since:
                break
            # One card per patient: re-running the same record is the same
            # patient seen again, not a second patient.
            keep = latest.get(view.get("key"))
            if keep is None or ran_at > (keep.get("ran_at") or ""):
                latest[view.get("key")] = view
            break
    ordered = sorted(latest.values(), key=lambda v: v.get("ran_at") or "", reverse=True)
    return ordered[:limit]


def clear_clinic_history() -> str:
    """Hide what is on the page without deleting any of it.

    The store refuses UPDATE and DELETE — that is the point of it — so clearing
    is a marker written forward rather than history rewritten backwards. The
    visits stay on the record and remain replayable by `python -m tools.store`;
    the page simply starts after the marker. An audit log with a clear button
    that worked would not be an audit log.
    """
    at = datetime.now().isoformat()
    runtime().checkpoint(CLEAR_MARKER, "rendered", {"origin": "cleared", "ran_at": at})
    return at


def _cleared_at() -> str:
    history = runtime().checkpoints.get(CLEAR_MARKER) or []
    stamps = [e.state.get("ran_at", "") for e in history
              if isinstance(e.state, dict) and e.state.get("origin") == "cleared"]
    return max(stamps) if stamps else ""


def _drafter_identity(router) -> str:
    """Who is drafting, named stably enough to key a cache on.

    Deliberately not `backend.version()`. That reports who *answered* — a
    hosted backend rewrites it to `model@served_by` after its first reply — so
    using it here would give the first encounter of a run a different key from
    the second, and no run would ever resume.

    The router's class is part of the key, because failing to name a backend is
    not itself a name. An earlier version returned "reference" whenever the
    lookup raised, which is how the reference reasoner reports itself — so a
    router that raises for a different reason, such as one that fails every
    draft, resumed the reference reasoner's successful results and reported
    zero failures. Two different drafters must never share a key.
    """
    kind = type(router).__name__
    try:
        backend = router.get(router.default).backend
    except (KeyError, AttributeError):
        return f"{kind}/reference"
    return f"{kind}/{getattr(backend, 'model', None) or backend.version()}"


def _thread_id(scenario, rules, router) -> str:
    """A thread id derived from everything that could change the answer.

    Content-addressed on purpose. Re-running `make` re-uses what is already in
    the store, and the moment any input moves — a pack edited, a different site,
    a real model swapped in for the reference reasoner, a different patient —
    the id moves with it and the encounter runs again. The pack enters as its
    content digest rather than its declared version, because the version is
    written by hand and an edit that forgets to bump it would otherwise replay a
    stale answer. So the demo is fast on
    the second run without ever showing a result that belongs to a question
    nobody asked.

    This is also what makes `make live` usable: nine model calls for this page
    the first time, none the second, and an edit to a guideline file costs them
    again. `tools/live.py` does the same for the run's other five.
    """
    material = json.dumps({
        "view": VIEW_VERSION,
        "scenario": scenario.key,
        "pack": f"{rules.pack_id}@{rules.version}+{rules.content_digest}",
        "site": scenario.site.get("site_id", ""),
        "drafter": _drafter_identity(router),
        "tampered": bool(scenario.tamper),
        # The patient itself, because /clinic builds them in the browser and two
        # patients under one scenario key are two different encounters.
        "patient": _plain(scenario.state),
    }, sort_keys=True, default=str)
    return f"DEMO-{scenario.key}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def _stored(thread_id: str) -> dict | None:
    """A finished encounter from a previous run, if this is the same question."""
    if _forced_fresh():
        return None
    history = runtime().checkpoints.get(thread_id) or []
    for entry in reversed(history):
        if entry.step == "rendered" and isinstance(entry.state, dict):
            return {**entry.state, "resumed": True}
    return None


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
        "patient_instructions_gloss": proposal.patient_instructions_en or gloss,
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
            "of the model, not of the patient's care. The doctor proceeds as "
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


def _encounter(scenario, rules, labels, router, on_step=None, *, resume=True,
               extra: dict | None = None) -> dict:
    """Run one encounter, or replay it if the same question was answered before.

    `resume=False` for `/clinic`, and the distinction is not arbitrary. The
    scripted page is a *report* of a run, so serving a stored one is right. A
    patient built in the browser and run with a button is an *action*, and an
    action that silently returns an earlier answer looks broken — especially on
    camera, with a live model that was expected to visibly think. Two runs of
    the same patient at different times are also genuinely two encounters, so
    they get two thread ids rather than appending to one.
    """
    # The surface used to run every encounter through an in-memory runtime and
    # an unbacked audit log, so a demo produced nothing that outlived the tab.
    # That made the persistence story a claim in a document rather than
    # something you could restart the process and go looking for.
    durable = store()
    thread_id = _thread_id(scenario, rules, router)

    if resume:
        # If this exact question has been answered before, hand back the answer.
        # A checkpoint whose only use is proving a checkpoint exists is
        # decoration; this is the runtime being load-bearing.
        already = _stored(thread_id)
        if already is not None:
            if on_step is not None:
                on_step("RESUMED")
            return already
    else:
        thread_id = f"{thread_id}-{uuid4().hex[:8]}"

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
            scenario.state, rules, scenario.site, effective, runtime(),
            thread_id=thread_id,
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

    rendered = {
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
        "resumed": False,
        # Microseconds, not seconds. `ran_at` orders the restored list and is
        # compared against the clear marker, and at second resolution a clear
        # followed immediately by a run discarded the run — the two stamps were
        # equal and the filter is "after the marker".
        "ran_at": datetime.now().isoformat(),
        **(extra or {}),
    }

    # What the clinician was actually shown, kept with the rest of the record.
    # Two jobs, and the second is the one that justifies it being here rather
    # than in a cache: a later run finds it and skips the work, and "what did
    # the doctor see" stops being a question only a screenshot can answer.
    runtime().checkpoint(thread_id, "rendered", rendered)
    return rendered


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
    # Whether the *caller* named a drafter, captured before the default is
    # applied. The concurrency decision below used to read `router is None`
    # after this line had made that impossible, so every run went wide —
    # including reference-reasoner runs, where three threads buy nothing and
    # cost the deterministic ordering that a restored list is sorted by.
    drafter_named = router is not None
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
                title=f"{state.patient_id} · {state.age}, {state.sex}",
                note=f"Built in the browser, run at {site_id}.",
                state=state,
                site=site,
                watch_for="",
            )
            encounter = _encounter(
                scenario, rules, labels, router, on_step=step, resume=False,
                # Stored with the encounter so the page can be rebuilt from the
                # store alone. `wire` is the patient exactly as the browser
                # submitted it, which is what makes a restored visit editable
                # and re-runnable rather than a read-only picture of one.
                extra={"origin": "clinic", "site_id": site_id, "wire": wire},
            )
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
    workers = 1 if not drafter_named else min(MAX_CONCURRENT_ENCOUNTERS, len(wire_patients))
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
        "hosted": os.environ.get("CLINICIAN_HOSTED", "") == "1",
        "reset_allowed": reset_allowed(),
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
    if is_model:
        reasoner = _reported_drafter(encounters, reasoner)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": NOW.isoformat(),
        # Read after the encounters ran, so the counts include them. The page
        # states where this deployment keeps its state, because "durable" is
        # the kind of claim that should be checkable from the thing itself.
        "store": store().summary(),
        # Set by the container. A public deployment says so on the page: this
        # document argues that health data must be processed in-country, and a
        # demo on foreign infrastructure has to answer that rather than hope
        # nobody asks. The answer is that every record here is synthetic and the
        # residency guard structurally refuses anything else.
        "hosted": os.environ.get("CLINICIAN_HOSTED", "") == "1",
        "reset_allowed": reset_allowed(),
        # How many of the encounters below came back from the store rather than
        # being run again. On a second `make live` this is the whole page, and
        # zero model calls.
        "resumed": sum(1 for e in encounters if e.get("resumed")),
        # Every pathway the pack carries, named by the pack. The surface used to
        # hard-code "adult hypertension", which was the first of two and became
        # wrong the moment a second one shipped — above four diabetes encounters.
        "pathways": [
            {"name": name, "label": (rules.pathways[name] or {}).get("label") or name}
            for name in (rules.pathway_order or list(rules.pathways))
        ],
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


def reset_allowed() -> bool:
    """Whether the surface is permitted to destroy the store.

    Off on a hosted deployment unless explicitly switched on, because the public
    demo is a link anyone can open and a wipe button on it is one misclick away
    from emptying the store under whoever is reading at the time. Locally it is
    on, since that is the machine whose data it is.

    Set CLINICIAN_ALLOW_RESET=1 to enable it anywhere, or =0 to refuse it
    everywhere including locally.
    """
    explicit = os.environ.get("CLINICIAN_ALLOW_RESET")
    if explicit is not None:
        return explicit == "1"
    return os.environ.get("CLINICIAN_HOSTED", "") != "1"


def reset_everything() -> dict:
    """Destroy the store and drop every cache built from it.

    Resetting the store alone would leave this process serving encounters that
    no longer exist anywhere, which looks like the reset silently failed. The
    runtime is cached per process and the scripted page is cached in the build,
    so both have to go with it.
    """
    global _RUNTIME, _STORE

    counts = store().reset()
    with _STORE_LOCK:
        # Both are process-cached and both are built from what was just
        # destroyed. A runtime holding a connection to an emptied database is
        # fine; one holding checkpoints that no longer exist is not.
        _RUNTIME = None
        _STORE = None
    return counts


def _can_sign(site, practitioner, when, Signer, verify_signer, SignatureRefused) -> str | None:
    """None if this practitioner could sign here today, else why not."""
    try:
        verify_signer(site, Signer(practitioner_id=practitioner["practitioner_id"],
                                   authenticated=True), when)
    except SignatureRefused as refusal:
        return str(refusal)
    return None


def sites_view(pack_id: str = "id") -> dict:
    """Every site the registry knows, and what each can actually do.

    Exists because gate check 9 is the least legible thing the demo does. A
    reader watching SITE-C refuse a plan is told the site cannot run the assay,
    and has no way to see that for themselves, so the most interesting refusal
    in the system reads as an assertion rather than a consequence.

    Everything here is read from the pack. The staleness verdicts come from the
    gate's own `evidence_gap`, so the page cannot tell a reviewer something the
    check disagrees with.
    """
    from datetime import date

    from service.gate.checks.c9_executable import evidence_gap
    from service.signing import SignatureRefused, Signer, verify_signer

    rules = load_pack(pack_id)
    catalogue = rules.investigations or {}
    prescribable = sorted(rules.molecules)
    max_age = (rules.evidence_policy or {}).get("max_age_days")
    today = date.today()

    sites = []
    for site in rules.sites.values():
        labs = set(site.get("labs_available") or [])
        stocked = set(site.get("stocked_molecules") or [])
        sites.append({
            "site_id": site["site_id"],
            "label": site.get("label", ""),
            "tier": site.get("tier", ""),
            "service_group": site.get("service_group", ""),
            "continuous_24h": bool((site.get("hours") or {}).get("continuous_24h")),
            "as_of": site.get("as_of", ""),
            "diagnoses": list(site.get("diagnoses") or []),
            # Asked of the signature line itself rather than by comparing dates
            # here. SITE-A carries a practitioner whose licence lapsed in
            # February, and a page that lists them as though they could sign
            # would contradict the one rule this system enforces hardest.
            "practitioners": [
                {**p, "can_sign": _can_sign(site, p, today,
                                            Signer, verify_signer, SignatureRefused)}
                for p in (site.get("practitioners") or [])
            ],
            "equipment": list(site.get("equipment") or []),
            # Both lists are rendered against the full vocabulary rather than
            # alone, because "SITE-C runs creatinine" is a fact and "SITE-C runs
            # creatinine and nothing else" is the one that explains a referral.
            "labs": [
                {"code": code, "label": label, "available": code in labs,
                 "gap": evidence_gap(site, code, max_age=max_age, today=today)
                        if code in labs else None}
                for code, label in sorted(catalogue.items())
            ],
            "molecules": [
                {"molecule": m, "stocked": m in stocked} for m in prescribable
            ],
        })

    sites.sort(key=lambda s: s["site_id"])
    return {
        "pack": f"{rules.pack_id}@{rules.version}",
        "evidence_max_age_days": max_age,
        "investigations": [{"code": c, "label": label}
                           for c, label in sorted(catalogue.items())],
        "molecules": prescribable,
        "sites": sites,
    }
