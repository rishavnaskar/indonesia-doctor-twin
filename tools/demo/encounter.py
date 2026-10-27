"""One encounter: run it, or replay it if the same question was answered before.

The single place both surfaces go through. The scripted page and /clinic drive
the identical pipeline, because a demo whose interactive mode took a different
path through the system would be demonstrating something other than the system.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from service.gate.checks import catalogue as check_catalogue
from service.gate.types import Severity
from service.graph.workflow import Outcome, run_encounter
from service.present.layer import present
from service.signing import Signer
from tools.demo.resume import Tampered, stored, thread_id_for
from tools.demo.store_access import runtime, store
from tools.demo.wire import failed_encounter, patient_view, plain, proposal_view

NOW = datetime(2026, 8, 29, 10, 0)


def _encounter(
    scenario, rules, labels, router, on_step=None, *, resume=True, extra: dict | None = None
) -> dict:
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
            scenario.state,
            rules,
            scenario.site,
            effective,
            runtime(),
            thread_id=thread_id,
            signer=Signer(practitioner, True),
            audit=audit_log,
            queue=queue,
            now=NOW,
            on_step=on_step,
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
        result.outcome.value,
        labels,
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
            {"id": e.exclusion_id, "label": e.label, "reason": e.reason} for e in result.exclusions
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
                        "kind": d.kind,
                        "text": d.text,
                        "gloss": d.gloss,
                        "molecule": d.molecule,
                        "record_says": d.record_says,
                        "patient_says": d.patient_says,
                        "interacts_with": list(d.interacts_with),
                        "material": d.material,
                    }
                    for d in result.reconciliation.discrepancies
                ],
                "findings": [
                    f.rule_id or f.check_name
                    for f in (result.decision.findings if result.decision else [])
                    if f.check == entry["number"]
                ],
                "blocked": any(
                    f.check == entry["number"] and f.severity is Severity.BLOCK
                    for f in (result.decision.findings if result.decision else [])
                ),
            }
            for entry in check_catalogue()
        ],
        "discrepancies": [
            {
                "kind": d.kind,
                "text": d.text,
                "gloss": d.gloss,
                "molecule": d.molecule,
                "record_says": d.record_says,
                "patient_says": d.patient_says,
                "interacts_with": list(d.interacts_with),
                "material": d.material,
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
                {
                    "code": c,
                    "plain": (rules.glossary.get("diagnoses") or {}).get(
                        c, (rules.glossary.get("diagnoses") or {}).get(c.split(".")[0], "")
                    ),
                }
                for c in result.claim.codes
            ],
        }
        if result.claim
        else None,
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
