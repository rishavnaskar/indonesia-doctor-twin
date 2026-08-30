"""The scripted journeys, in one place.

Both the terminal walkthrough and the demo surface run these. Two copies would
drift, and the first thing to drift would be the refusal ratio — which is the
one number the demo exists to show.

Four of six end in the system declining to do something. That is the point. A
demo where the assistant always has an answer is a demo of a system nobody
should deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from datagen.synthetic import make_patient
from service.contracts.proposal import MedicationChange
from service.state.models import Diagnosis, Medication, Observation, Source


@dataclass
class Scenario:
    key: str
    title: str
    note: str
    state: object
    site: dict
    tamper: Callable | None = None
    # What a reviewer should take from this one. Shown in the demo, not asserted
    # by the code — the outcome is whatever the system actually produces.
    watch_for: str = ""


def _ten_times(proposal) -> None:
    """Move the decimal point. The single most plausible model error there is."""
    if proposal.medication_changes:
        change = proposal.medication_changes[0]
        proposal.medication_changes = [
            MedicationChange(change.action, change.molecule,
                             (change.mg_per_dose or 5) * 10, change.doses_per_day,
                             "tampered for the demo", change.citation)
        ]


def build(rules) -> list[Scenario]:
    site_a, site_c = rules.sites["SITE-A"], rules.sites["SITE-C"]

    diabetic = make_patient(104, controlled=False)
    diabetic.flags.pop("has_dm", None)
    diabetic.diagnoses.append(Diagnosis(code="E11.9"))

    emergency = make_patient(105, controlled=False)
    emergency.observations.append(Observation("sbp", 206, "mmHg", emergency.as_of, Source.EMR))
    emergency.observations.append(Observation("dbp", 126, "mmHg", emergency.as_of, Source.EMR))
    emergency.symptoms["chest_pain"] = True

    # On maximum first-line therapy, so the ladder wants an ACE inhibitor. That
    # needs potassium and eGFR, and this site can run neither.
    remote = make_patient(106, controlled=False)
    remote.medications = [
        Medication(molecule="amlodipine", mg_per_dose=10.0, doses_per_day=1, source=Source.EMR)
    ]
    remote.observations = [o for o in remote.observations if o.code not in ("k", "egfr")]

    return [
        Scenario(
            "routine", "Controlled patient, routine review",
            "The common case. Continue, code, schedule.",
            make_patient(101, controlled=True), site_a,
            watch_for="No alert. Green is silent — the draft is simply present, "
                      "the way a prepared note would be, and the system does not "
                      "interrupt to say it found nothing. Most visits are green, "
                      "and that silence is what makes an amber worth reading.",
        ),
        Scenario(
            "titration", "Above target, titration drafted",
            "The draft a doctor accepts in one click.",
            make_patient(102, controlled=False), site_a,
            watch_for="The work the system actually saves: the draft, the code "
                      "and the follow-up interval are already filled in. The "
                      "doctor decides; they do not transcribe.",
        ),
        Scenario(
            "wrong_dose", "The same case, with the dose out by ten",
            "What the doctor sees when the model gets it wrong: nothing.",
            make_patient(102, controlled=False), site_a, tamper=_ten_times,
            watch_for="A decimal-point error is the most plausible failure there "
                      "is. The draft never reaches the clinician, and the reason "
                      "is in the audit view rather than on their screen.",
        ),
        Scenario(
            "no_target", "Diabetic patient, target not yet extracted",
            "Diabetes present only as a code. The system declines rather than guessing.",
            diabetic, site_a,
            watch_for="The comorbidity is present only as a diagnosis code, with "
                      "no flag set. The system notices, finds no target it is "
                      "entitled to use, and abstains instead of applying the "
                      "general adult one.",
        ),
        Scenario(
            "emergency", "Hypertensive emergency",
            "No draft. The clinician is alerted and the encounter leaves the pathway.",
            emergency, site_a,
            watch_for="The one case where the system interrupts a clinician who "
                      "has not asked. Red, and it cannot be dismissed without "
                      "acknowledgement.",
        ),
        Scenario(
            "remote_site", "Remote basic-tier site, plan needs a test it cannot run",
            "A plan is only a plan if this hospital can actually carry it out.",
            remote, site_c,
            watch_for="The plan is correct and undeliverable here. That is a "
                      "referral, not a recommendation — and getting this wrong "
                      "is how a tool loses a clinician's trust for good.",
        ),
    ]
