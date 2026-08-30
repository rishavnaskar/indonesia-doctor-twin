"""End-to-end walkthrough: waiting room to signed, coded encounter.

Five scripted journeys, chosen so that four of them end in the system declining
to do something. That ratio is the point. A demo where the assistant always has
an answer is a demo of a system nobody should deploy.

    python -m tools.walkthrough
"""

from __future__ import annotations

from datetime import datetime

from datagen.synthetic import make_patient
from service.contracts.proposal import ChangeAction, MedicationChange
from service.graph.runtime import InMemoryRuntime
from service.graph.workflow import Outcome, run_encounter
from service.packs.loader import load_pack
from service.router.router import default_router
from service.signing import AuditLog, Signer
from service.emit.queue import OutboundQueue
from service.state.models import Diagnosis, Medication, Observation, Source
from tools.scenarios import build as build_scenarios

NOW = datetime(2026, 8, 29, 10, 0)
RULE = "─" * 74

ICONS = {
    Outcome.COMMITTED: "signed",
    Outcome.HANDOFF: "handed off",
    Outcome.ESCALATE: "escalated",
    Outcome.REQUEST_INFO: "asked for information",
    Outcome.ABSTAIN: "declined",
    Outcome.PRESENTED: "presented",
}


OUTCOMES: list[Outcome] = []


def show(title: str, note: str, state, rules, site, *, tamper=None) -> None:
    router, runtime, audit = default_router(), InMemoryRuntime(), AuditLog()

    print(f"\n{RULE}\n  {title}\n  {note}\n{RULE}")
    sbp, dbp = state.latest("sbp"), state.latest("dbp")
    if sbp and dbp:
        print(f"  patient   {state.patient_id}, {state.age}, BP {sbp.value:.0f}/{dbp.value:.0f}")
    print(f"  regimen   {', '.join(m.molecule for m in state.medications) or 'none'}")
    print(f"  site      {site['site_id']} ({site['tier']}), stock as of {site['as_of']}")

    # Each site has its own roster, and a signature from elsewhere is refused.
    # This caught a mistake in an earlier version of this very script, which is
    # a fair advertisement for enforcing it in software.
    practitioner = site["practitioners"][0]["practitioner_id"]

    original = router.propose
    if tamper is not None:
        def tampered(st, rs, sit=None, **kw):
            proposal = original(st, rs, sit)
            tamper(proposal)
            return proposal
        router.propose = tampered

    result = run_encounter(
        state, rules, site, router, runtime,
        thread_id=title, signer=Signer(practitioner, True),
        audit=audit, now=NOW,
    )

    OUTCOMES.append(result.outcome)
    print(f"\n  path      {' > '.join(result.trail)}")
    print(f"  outcome   {ICONS[result.outcome].upper()}")

    if result.decision and result.decision.blocking:
        print("\n  the gate refused, and said why:")
        for reason in result.decision.reasons():
            print(f"    - {reason}")
    elif result.message:
        print(f"  note      {result.message}")

    if result.outcome is Outcome.COMMITTED:
        proposal = result.proposal
        print(f"\n  draft     {proposal.recommendation.value}")
        for change in proposal.medication_changes:
            print(f"            {change.action.value} {change.molecule} "
                  f"{change.mg_per_dose:g} mg x{change.doses_per_day}/day")
        print(f"  follow-up in {proposal.follow_up_interval_days} days")
        if result.claim:
            secondary = ", ".join(f"{d.code} ({d.evidence_ref})" for d in result.claim.secondary)
            print(f"  coded     primary {result.claim.primary.code}"
                  + (f"; secondary {secondary}" if secondary else "; no secondary codes"))
        if result.referral_back and result.referral_back.eligible:
            print("  referral  stability criteria met — referral-back letter drafted")
        print(f"  signed by {audit.records[-1].practitioner_id} "
              f"({audit.records[-1].role}), licence to "
              f"{audit.records[-1].licence_expires}")
        print(f"  provenance {' | '.join(audit.records[-1].proposal_provenance)}")


def offline_demo(rules, site) -> None:
    """Pull the cable mid-consultation and prove nothing is lost or duplicated."""
    import tempfile
    from pathlib import Path

    print(f"\n{RULE}\n  7. The network drops mid-clinic\n"
          "  One site in five has unreliable connectivity. This is the normal case.\n"
          f"{RULE}")

    path = Path(tempfile.mkdtemp()) / "outbound.jsonl"
    queue = OutboundQueue(path=path)

    for n in range(3):
        state = make_patient(300 + n, controlled=True)
        run_encounter(
            state, rules, site, default_router(), InMemoryRuntime(),
            thread_id=f"OFF-{n}", signer=Signer(site["practitioners"][0]["practitioner_id"], True),
            audit=AuditLog(), now=NOW, queue=queue,
        )
    print(f"  three encounters seen with no network   queued: {len(queue)}")

    def offline(item):
        raise ConnectionError("no route to host")

    result = queue.drain(offline)
    print(f"  attempted to send while still offline   {result}")

    reopened = OutboundQueue(path=path)
    print(f"  power cut, process restarted            recovered: {len(reopened)}, "
          f"pending: {len(reopened.pending())}")

    result = reopened.drain(lambda item: None)
    print(f"  network returns                         {result}")

    replay = OutboundQueue(path=path)
    before = len(replay)
    for n in range(3):
        state = make_patient(300 + n, controlled=True)
        run_encounter(
            state, rules, site, default_router(), InMemoryRuntime(),
            thread_id=f"OFF-{n}", signer=Signer(site["practitioners"][0]["practitioner_id"], True),
            audit=AuditLog(), now=NOW, queue=replay,
        )
    print(f"  same encounters replayed after recovery queue still {len(replay)} "
          f"(was {before}) — no duplicates in the national record")


def main() -> None:
    """Every scenario in tools/scenarios.py, in order.

    The list used to be written out again here. It drifted the moment a second
    pathway added three scenarios: this script kept reporting "4 of 6" while the
    demo surface, reading the shared list, reported 5 of 9. Two copies of the
    refusal ratio is precisely the failure the shared module was created to
    prevent, and it happened anyway because the module was added without this
    caller being moved onto it.
    """
    rules = load_pack("id")

    print("\n  AI clinician — synthetic patients, no model in the loop.")
    print("  Every rule from the pack. Two pathways, one engine.")

    for index, scenario in enumerate(build_scenarios(rules), start=1):
        show(f"{index}. {scenario.title}", scenario.note,
             scenario.state, rules, scenario.site, tamper=scenario.tamper)

    offline_demo(rules, rules.sites["SITE-A"])

    declined = sum(1 for o in OUTCOMES if o is not Outcome.COMMITTED)
    print(f"\n{RULE}")
    print(f"  {declined} of {len(OUTCOMES)} ended without a recommendation. "
          "That is the system working,")
    print("  not the system failing. Each refusal names its own reason.")
    print(f"{RULE}\n")


if __name__ == "__main__":
    main()
