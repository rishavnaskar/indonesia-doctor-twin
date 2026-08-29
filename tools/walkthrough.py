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
from service.state.models import Diagnosis, Medication, Observation, Source

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


def main() -> None:
    rules = load_pack("id")
    site_a, site_c = rules.sites["SITE-A"], rules.sites["SITE-C"]

    print("\n  AI clinician — adult hypertension follow-up")
    print("  Synthetic patients. No model in the loop. Every rule from the pack.")

    # 1 — the ordinary case
    show("1. Controlled patient, routine review",
         "The common case. Continue, code, schedule.",
         make_patient(101, controlled=True), rules, site_a)

    # 2 — the useful case
    show("2. Above target, titration drafted",
         "The draft a doctor accepts in one click.",
         make_patient(102, controlled=False), rules, site_a)

    # 3 — the safety case
    def ten_times(proposal):
        if proposal.medication_changes:
            change = proposal.medication_changes[0]
            proposal.medication_changes = [
                MedicationChange(change.action, change.molecule,
                                 (change.mg_per_dose or 5) * 10, change.doses_per_day,
                                 "tampered for the demo", change.citation)
            ]
    show("3. The same case, with the dose out by ten",
         "What the doctor sees when the model gets it wrong: nothing.",
         make_patient(102, controlled=False), rules, site_a, tamper=ten_times)

    # 4 — the honest case
    diabetic = make_patient(104, controlled=False)
    diabetic.flags.pop("has_dm", None)
    diabetic.diagnoses.append(Diagnosis(code="E11.9"))
    show("4. Diabetic patient, target not yet extracted",
         "Diabetes present only as a code. The system declines rather than guessing.",
         diabetic, rules, site_a)

    # 5 — the emergency
    emergency = make_patient(105, controlled=False)
    emergency.observations.append(Observation("sbp", 206, "mmHg", emergency.as_of, Source.EMR))
    emergency.observations.append(Observation("dbp", 126, "mmHg", emergency.as_of, Source.EMR))
    emergency.symptoms["chest_pain"] = True
    show("5. Hypertensive emergency",
         "No draft. The clinician is alerted and the encounter leaves the pathway.",
         emergency, rules, site_a)

    # 6 — the site that cannot deliver the plan
    # On maximum first-line therapy, so the ladder wants an ACE inhibitor. That
    # needs potassium and eGFR, and this site cannot run either.
    remote = make_patient(106, controlled=False)
    remote.medications = [
        Medication(molecule="amlodipine", mg_per_dose=10.0, doses_per_day=1,
                   source=Source.EMR)
    ]
    remote.observations = [o for o in remote.observations if o.code not in ("k", "egfr")]
    show("6. Remote basic-tier site, plan needs a test it cannot run",
         "A plan is only a plan if this hospital can actually carry it out.",
         remote, rules, site_c)

    declined = sum(1 for o in OUTCOMES if o is not Outcome.COMMITTED)
    print(f"\n{RULE}")
    print(f"  {declined} of {len(OUTCOMES)} ended without a recommendation. "
          "That is the system working,")
    print("  not the system failing. Each refusal names its own reason.")
    print(f"{RULE}\n")


if __name__ == "__main__":
    main()
