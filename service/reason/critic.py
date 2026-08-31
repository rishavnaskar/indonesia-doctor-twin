"""A second model, reviewing the first one's draft.

The nine checks catch rule violations: a dose out of range, a drug not on the
list, a citation that does not resolve. They cannot catch a draft that breaks no
rule and is still poor — a rationale that does not follow from the numbers, a
plan that ignores something in the history, an instruction a patient could not
act on. Those are judgement failures, and a rule engine has no judgement.

So: ask a model. With one constraint that makes it safe to do so.

**The critic can only ever lower confidence, never raise it.** It returns a
score, and the proposal keeps the minimum of what it had and what the critic
gave. There is no path by which a critic's approval rescues a draft the drafter
was unsure of, or by which two models agreeing produces more certainty than
either had alone. A model that could raise confidence would be a model with veto
over the abstention floor, which is precisely the authority nothing here is
allowed to have.

**It is not the gate and cannot become one.** The gate is plain code, runs
after this, and is unaffected by anything the critic says. The critic adjusts a
number the gate then reads. If it were allowed to block or to pass, it would be
a model deciding what a clinician sees, and the whole argument of this system is
that no model does that.

**An unreviewed draft must never look like a reviewed one.** If the critic
fails — unavailable, rate-limited, unparseable — the draft continues, because an
advisory component being down is not a reason to deny care. But it is recorded
as unreviewed. Silently treating the two as equivalent would make the safeguard
unfalsifiable, which is worse than not having it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

VERSION = "critic@0.1.0"

_SCHEMA = {
    "type": "object",
    "properties": {
        "acceptable_as_drafted": {"type": "number", "minimum": 0, "maximum": 1},
        "concerns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["acceptable_as_drafted"],
    "additionalProperties": False,
}


def system_prompt() -> str:
    return (
        "You review a colleague's draft plan before a doctor sees it. You are "
        "not writing the plan and you must not rewrite it.\n\n"
        "Answer one question: would a careful clinician accept this draft as "
        "written, for this patient, given the record below?\n\n"
        "Score `acceptable_as_drafted` from 0 to 1. Use the low end freely. "
        "A draft that breaks no explicit rule can still be poor: a rationale "
        "that does not follow from the numbers, a plan that ignores something "
        "in the history, an instruction the patient could not act on. Those are "
        "what you are looking for.\n\n"
        "Separate rules already check dosing, drug availability, interactions, "
        "citations and site capability. Do not spend your answer on those; "
        "assume they are handled and look at judgement.\n\n"
        "List specific concerns. An empty list means you found none, not that "
        "you did not look. Reply with JSON only."
    )


def build_prompt(context: str, proposal_json: str) -> str:
    return (
        f"{context}\n\n"
        "--- the draft under review ---\n"
        f"{proposal_json}\n"
    )


@dataclass
class CriticReviewedReasoner:
    inner: Any
    critic_backend: Any

    @property
    def backend(self):
        return getattr(self.inner, "backend", None)

    def __call__(self, state, rules, site=None):
        return self.propose(state, rules, site)

    def propose(self, state, rules, site: dict[str, Any] | None = None):
        from service.reason import prompt as prompt_module
        from service.rules.predicates import Context
        from service.rules.targets import resolve_target

        proposal = self.inner.propose(state, rules, site)

        target = resolve_target(rules.guideline, Context(state)).target
        context = prompt_module.build_user_prompt(state, rules, site, target)
        draft = json.dumps(_summarise(proposal), indent=2)

        try:
            raw = self.critic_backend.complete(
                system_prompt(),
                build_prompt(context, draft),
                allow_egress=bool(state.is_synthetic),
                schema=_SCHEMA,
            )
            verdict = json.loads(_strip(raw))
            score = float(verdict["acceptable_as_drafted"])
            concerns = [str(c) for c in (verdict.get("concerns") or [])]
        except Exception as exc:  # noqa: BLE001
            # Advisory. Being down is not a reason to deny care — but the draft
            # is marked unreviewed so nothing downstream can mistake it for one
            # that passed.
            return replace(
                proposal,
                uncertainty_notes=(
                    proposal.uncertainty_notes
                    + f" Second-model review did not run ({type(exc).__name__}); "
                      "this draft is unreviewed."
                ).strip(),
            )

        score = max(0.0, min(1.0, score))
        note = f"Second-model review scored this {score:.2f} as drafted."
        if concerns:
            note += " Concerns: " + "; ".join(concerns)

        return replace(
            proposal,
            # Minimum, always. A critic that could raise confidence would hold a
            # veto over the abstention floor.
            confidence=min(proposal.confidence, score),
            uncertainty_notes=(proposal.uncertainty_notes + " " + note).strip(),
        )


def _summarise(proposal) -> dict:
    """What the critic sees. The plan, not our internal bookkeeping."""
    return {
        "assessment": proposal.assessment.value,
        "recommendation": proposal.recommendation.value,
        "bp_trend_summary": proposal.bp_trend_summary,
        "medication_changes": [
            {
                "action": c.action.value,
                "molecule": c.molecule,
                "mg_per_dose": c.mg_per_dose,
                "doses_per_day": c.doses_per_day,
                "rationale": c.rationale,
            }
            for c in proposal.medication_changes
        ],
        "investigations": list(proposal.investigations),
        "patient_instructions": proposal.patient_instructions,
        "follow_up_interval_days": proposal.follow_up_interval_days,
        "stated_confidence": proposal.confidence,
    }


def _strip(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()
