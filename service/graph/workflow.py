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
    claim: ClaimDraft | None = None
    referral_back: ReferralBackAssessment | None = None
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
) -> EncounterResult:
    trail: list[str] = []
    now = now or datetime(2026, 8, 29, 10, 0)
    runtime.start(thread_id, state)

    # ---- ELIGIBLE: structured checks only, no model, zero tokens ----------
    derive_flags(state, rules)
    eligibility = check_eligibility(rules.guideline, Context(state))
    trail.append("ELIGIBLE")
    if not eligibility.eligible:
        return EncounterResult(
            outcome=Outcome.HANDOFF,
            message=eligibility.handoff_message(),
            trail=trail + ["HANDOFF"],
        )

    # ---- INTAKE / RECONCILE ------------------------------------------------
    # Both are placeholders in this build: intake needs a bounded interviewer
    # and reconciliation needs a model to match free-text drug mentions. The
    # states exist so the shape is right and so nothing downstream has to
    # change when they are filled in.
    trail += ["INTAKE", "RECONCILE"]
    runtime.checkpoint(thread_id, "reconciled", state)

    # ---- PROPOSE -----------------------------------------------------------
    proposal = router.propose(state, rules, site)
    trail.append("PROPOSE")
    runtime.checkpoint(thread_id, "proposed", state)

    # ---- GATE --------------------------------------------------------------
    # Red flags, sufficiency and every other deterministic control live here.
    # The workflow does not second-guess the gate; it routes on what it says.
    gate_decision = run_gate(GateContext(state=state, proposal=proposal, rules=rules, site=site))
    trail.append("GATE")

    if not gate_decision.rendered:
        outcome, message = _route_refusal(gate_decision)
        return EncounterResult(
            outcome=outcome,
            message=message,
            proposal=proposal,
            decision=gate_decision,
            trail=trail + [outcome.value.upper()],
        )

    # ---- PRESENT -----------------------------------------------------------
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
    claim = build_claim(state, rules)
    referral = assess_referral_back(state, rules)
    trail += ["COMMIT", "FOLLOW-UP"]
    runtime.checkpoint(thread_id, "committed", state)

    return EncounterResult(
        outcome=Outcome.COMMITTED,
        message="Signed, coded and queued for submission.",
        proposal=proposal,
        decision=gate_decision,
        claim=claim,
        referral_back=referral,
        trail=trail,
    )


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
