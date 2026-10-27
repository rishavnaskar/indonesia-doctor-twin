"""Run the scenarios and capture everything the surface needs.

Every field on the page comes from here, and everything here comes from a real
`run_encounter`. Nothing is written by hand.

This module is the orchestration only. What it was also doing, and no longer
does, lives next door:

  * store_access.py  the process-wide store and runtime, and reset
  * resume.py        the thread id, and what is already in the store
  * wire.py          encounters, patients and failures as plain JSON
  * history.py       what /clinic ran in earlier sessions
  * catalogue.py     the pack read out for the browser and for /sites

The names below are re-exported from here because callers have always imported
them from `tools.demo.run`, and moving a function is not a reason to break
them.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from service.gate.checks import catalogue as check_catalogue
from service.gate.types import Severity
from service.graph.workflow import Outcome, run_encounter
from service.logging import get_logger
from service.packs.loader import load_pack
from service.present.layer import Labels, present
from service.router.router import default_router
from service.signing import Signer
from tools import scenarios as scenario_module
from tools.demo.catalogue import sites_view, vocabulary
from tools.demo.history import clear_clinic_history, clinic_history
from tools.demo.resume import VIEW_VERSION, Tampered, stored, thread_id_for
from tools.demo.store_access import forced_fresh, reset_allowed, reset_everything, runtime, store
from tools.demo.wire import (
    failed_encounter,
    patient_view,
    plain,
    proposal_view,
    unreadable_record,
)

__all__ = [
    "MAX_CONCURRENT_ENCOUNTERS",
    "NOW",
    "VIEW_VERSION",
    "clear_clinic_history",
    "clinic_history",
    "collect",
    "compare_sites",
    "forced_fresh",
    "reset_allowed",
    "reset_everything",
    "run_patients",
    "runtime",
    "sites_view",
    "store",
    "vocabulary",
]

log = get_logger(__name__)

NOW = datetime(2026, 8, 29, 10, 0)

# Free tiers are shared pools, so this stays small: the point is to overlap the
# waiting, not to win a race against everyone else on the internet.
MAX_CONCURRENT_ENCOUNTERS = 3


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
    thread_id = thread_id_for(scenario, rules, router)

    if resume:
        # If this exact question has been answered before, hand back the answer.
        # A checkpoint whose only use is proving a checkpoint exists is
        # decoration; this is the runtime being load-bearing.
        already = stored(thread_id)
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
    effective = Tampered(router, scenario.tamper) if scenario.tamper else router

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
        return failed_encounter(scenario, rules, exc)

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
        "patient": patient_view(scenario.state, scenario.site, rules),
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
            "lines": [plain(line) for line in view.lines],
            "audit": [plain(line) for line in view.audit],
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
                "severity": plain(f.severity),
                "message": f.message,
                "message_local": f.message_local,
                "rule_id": f.rule_id,
                "citation": f.citation,
                "converts_to_referral": f.converts_to_referral,
            }
            for f in (result.decision.findings if result.decision else [])
        ],
        "proposal": proposal_view(result.proposal, rules),
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
            encounter = unreadable_record(wire, index, rules, site, exc)
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
    keys = list(by_site[next(iter(by_site))])
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


