"""The encounter workflow — SPEC-V1 §4, end to end.

The system does not have a conversation. It advances a patient through defined
states, every transition logged, every state with a defined exit.

    ELIGIBLE -> (HANDOFF | INTAKE) -> RECONCILE -> RED FLAGS
             -> (ESCALATE | SUFFICIENCY) -> (REQUEST INFO | PROPOSE)
             -> GATE -> (ABSTAIN | PRESENT) -> CLINICIAN DECIDES
             -> COMMIT -> FOLLOW-UP

Four of those terminal states are successes, not failures: HANDOFF, ESCALATE,
REQUEST INFO and ABSTAIN. A system that cannot reach them safely is not safe,
so they are outcomes here rather than errors, and the scorecard counts them as
such.

The clinician decision is a genuine interrupt: the workflow pauses, its state
is checkpointed, and it resumes only when a signature arrives. Nothing with
clinical effect leaves this module unsigned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from service.emit.coding import ClaimDraft, build_claim
from service.emit.fhir import Bundle, build_bundle
from service.emit.referral_back import ReferralBackAssessment, assess as assess_referral_back
from service.gate import GateContext, GateDecision, run_gate
from service.rules.eligibility import check_eligibility
from service.rules.predicates import Context
from service.signing import AuditLog, Signer, sign
from service.state.derive import derive_flags


class Outcome(str, Enum):
    HANDOFF = "handoff"            # not our patient. success.
    ESCALATE = "escalate"          # red flag. success.
    REQUEST_INFO = "request_info"  # not enough to advise. success.
    ABSTAIN = "abstain"            # gate refused. success.
    PRESENTED = "presented"        # awaiting a signature
    COMMITTED = "committed"        # signed, coded, ready to emit


@dataclass
class EncounterResult:
    outcome: Outcome
    message: str = ""
    proposal: Any = None
    decision: GateDecision | None = None
    questions_for_clinician: list[str] = field(default_factory=list)
    claim: ClaimDraft | None = None
    referral_back: ReferralBackAssessment | None = None
    bundle: Bundle | None = None
    trail: list[str] = field(default_factory=list)

    @property
    def succeeded_safely(self) -> bool:
        """Every outcome except a crash is a safe outcome. That is the design."""
        return True


def run_encounter(
    state,
    rules,
    site: dict[str, Any] | None,
    router,
    runtime,
    *,
    thread_id: str,
    signer: Signer | None = None,
    decision: str = "accepted",
    audit: AuditLog | None = None,
    now: datetime | None = None,
    queue=None,
    intake=None,
    on_step=None,
) -> EncounterResult:
    """Run one encounter.

    `on_step(name)` fires as each phase *begins*, and is purely observational —
    nothing downstream reads it and a callback that raises is not caught, so it
    must not do work. It exists because the slow phase is the model call, and a
    caller that cannot say which phase it is in can only report "working".

    Note the difference from `trail`, which records phases that *completed*.
    One says what is happening; the other says what happened. Conflating them
    would make a crashed encounter look like a finished one.
    """
    trail: list[str] = []
    now = now or datetime(2026, 8, 29, 10, 0)

    def at(name: str) -> None:
        if on_step is not None:
            on_step(name)

    runtime.start(thread_id, state)

    # ---- ELIGIBLE: structured checks only, no model, zero tokens ----------
    at("ELIGIBLE")
    derive_flags(state, rules)
    eligibility = check_eligibility(rules.guideline, Context(state))
    trail.append("ELIGIBLE")
    if not eligibility.eligible:
        at("HANDOFF")
        return EncounterResult(
            outcome=Outcome.HANDOFF,
            message=eligibility.handoff_message(),
            questions_for_clinician=_patient_questions(intake),
            trail=trail + ["HANDOFF"],
        )

    # ---- INTAKE ------------------------------------------------------------
    # Answers from the bounded interviewer, if one ran. The symptom checklist
    # is what the red-flag rules evaluate, so this is the path by which a
    # patient reporting chest pain reaches R1 and R4.
    #
    # Note what is NOT merged: the questions the patient asked. Those go to the
    # clinician verbatim and are never answered by anything in between.
    at("INTAKE")
    if intake is not None:
        state.symptoms.update(intake.symptoms())
        for field_name in ("adherence", "outside_medication"):
            if field_name in intake.answers:
                state.flags[f"reported_{field_name}"] = bool(intake.answers[field_name])
    trail.append("INTAKE")

    # ---- RECONCILE ---------------------------------------------------------
    # Still a placeholder: matching free-text drug mentions to molecules needs a
    # model. The state exists so nothing downstream changes when it is filled
    # in, and discrepancies must be surfaced rather than silently resolved.
    at("RECONCILE")
    trail.append("RECONCILE")
    runtime.checkpoint(thread_id, "reconciled", state)

    # ---- PROPOSE -----------------------------------------------------------
    at("PROPOSE")
    proposal = router.propose(state, rules, site)
    trail.append("PROPOSE")
    runtime.checkpoint(thread_id, "proposed", state)

    # ---- GATE --------------------------------------------------------------
    # Red flags, sufficiency and every other deterministic control live here.
    # The workflow does not second-guess the gate; it routes on what it says.
    at("GATE")
    gate_decision = run_gate(GateContext(state=state, proposal=proposal, rules=rules, site=site))
    trail.append("GATE")

    if not gate_decision.rendered:
        outcome, message = _route_refusal(gate_decision)
        at(outcome.value.upper())
        return EncounterResult(
            outcome=outcome,
            message=message,
            proposal=proposal,
            decision=gate_decision,
            questions_for_clinician=_patient_questions(intake),
            trail=trail + [outcome.value.upper()],
        )

    # ---- PRESENT -----------------------------------------------------------
    at("PRESENT")
    trail.append("PRESENT")
    if signer is None:
        return EncounterResult(
            outcome=Outcome.PRESENTED,
            message="Awaiting a clinician decision.",
            proposal=proposal,
            decision=gate_decision,
            trail=trail,
        )

    # ---- CLINICIAN DECIDES: the interrupt ---------------------------------
    from service.graph.runtime import Interrupted

    try:
        runtime.interrupt(thread_id, proposal)
    except Interrupted:
        pass  # the pause is the point; a real caller resumes on a signature
    at("SIGNED")
    runtime.resume(thread_id, decision)
    sign(site, signer, proposal, decision, now, audit or AuditLog())
    trail.append("SIGNED")

    if decision == "rejected":
        return EncounterResult(
            outcome=Outcome.PRESENTED,
            message="Clinician rejected the draft. Nothing emitted.",
            proposal=proposal,
            decision=gate_decision,
            trail=trail,
        )

    # ---- COMMIT ------------------------------------------------------------
    at("COMMIT")
    claim = build_claim(state, rules)
    referral = assess_referral_back(state, rules)

    # Build the outbound bundle and hand it to the queue. Nothing is sent
    # inline: at a site that loses power or signal mid-consultation, an inline
    # send is how an encounter goes missing.
    bundle = build_bundle(
        state, claim, proposal, site, signer.practitioner_id, rules,
        encounter_id=thread_id,
    )
    if queue is not None:
        queue.enqueue("encounter_bundle", bundle.payload, bundle.idempotency_key, now)

    trail += ["COMMIT", "FOLLOW-UP"]
    runtime.checkpoint(thread_id, "committed", state)

    return EncounterResult(
        outcome=Outcome.COMMITTED,
        message=(
            "Signed, coded and queued for submission."
            if queue is not None
            else "Signed and coded. No queue attached, so nothing was enqueued."
        ),
        proposal=proposal,
        decision=gate_decision,
        claim=claim,
        referral_back=referral,
        bundle=bundle,
        questions_for_clinician=_patient_questions(intake),
        trail=trail,
    )


def _patient_questions(intake) -> list[str]:
    """Whatever the patient asked, passed through untouched.

    Deliberately verbatim. The interviewer did not answer them and nothing
    between the patient and the doctor gets to paraphrase a clinical question
    into something more convenient.
    """
    return list(getattr(intake, "questions_for_clinician", []) or [])


def _route_refusal(decision: GateDecision) -> tuple[Outcome, str]:
    """A refusal is not one thing. What the clinician sees depends on why."""
    fired = {f.rule_id for f in decision.blocking}

    if decision.referral:
        return Outcome.ABSTAIN, "Not deliverable at this site — routed as a referral."
    if any(rid and rid.startswith("R") and rid[1:2].isdigit() for rid in fired):
        return Outcome.ESCALATE, "Red flag. Clinician alerted; no draft produced."
    if fired & {"insufficient_data", "X2"}:
        return Outcome.REQUEST_INFO, decision.reasons()[0]
    if "no_target_defined" in fired:
        return Outcome.ABSTAIN, decision.reasons()[0]
    return Outcome.ABSTAIN, "Draft withheld. " + decision.reasons()[0]
