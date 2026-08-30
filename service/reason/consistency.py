"""Self-consistency: draft it more than once and see whether it agrees.

The problem this fixes is specific. A proposal carries a `confidence`, gate
check 8 abstains below a floor, and until now that number was the model's own
opinion of itself — the weakest signal available, and one that is well known to
be poorly calibrated. A model that is confidently wrong states 0.95 exactly as
readily as a model that is confidently right.

Sampling the same prompt k times and measuring how often the samples land on the
same plan replaces that opinion with a measurement. Disagreement across samples
is evidence of uncertainty that the model cannot talk its way out of, because it
is computed from behaviour rather than read from a field.

Three decisions worth stating.

**Agreement is on the plan, not the prose.** Two samples that both say
"titrate up" to different doses have not agreed about anything a patient would
notice. The key is the recommendation plus the exact medication changes.

**Confidence is the minimum of the two signals, never a blend.** Neither source
may rescue the other. Five samples agreeing on an answer the model says it is
unsure of does not make it sure; a model asserting 0.95 while its samples
scatter is not to be believed. Taking the minimum is the fail-closed reading and
the only one defensible at a bedside.

**This is not a second gate.** It produces a proposal with a better-grounded
confidence and hands it to exactly the same nine checks. The gate stays plain
code, and check 8 does the abstaining it always did.

Same three-argument signature as every other reasoner, so it composes through
the router and nothing downstream knows it is there.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

from service.contracts.proposal import Proposal, Provenance


def decision_key(proposal: Proposal) -> tuple:
    """What two drafts must share to count as the same plan."""
    return (
        proposal.recommendation.value,
        tuple(sorted(
            (c.action.value, c.molecule, c.mg_per_dose or 0.0, c.doses_per_day or 0)
            for c in proposal.medication_changes
        )),
    )


@dataclass
class SelfConsistentReasoner:
    inner: Any
    samples: int = 3
    max_workers: int = 3
    # Shadow mode: measure agreement, record it, and do NOT let it touch the
    # confidence.
    #
    # This exists because the obvious experiment cannot answer its own question.
    # With agreement feeding the confidence, a low-agreement draft falls below
    # the abstention floor and never reaches a clinician — so "are unstable
    # drafts likelier to be wrong?" has no unstable drafts left to measure. The
    # mechanism removes exactly the cases the measurement needs. Observed: at
    # n=30, six unstable drafts, none of which reached the comparison.
    #
    # In shadow mode the draft proceeds on its stated confidence and the
    # agreement is recorded alongside. Only then can the two be correlated, and
    # only then is keeping self-consistency an evidenced decision rather than a
    # fashionable one.
    apply: bool = True

    @property
    def backend(self):
        # The router and the surfaces reach through for a version string.
        return getattr(self.inner, "backend", None)

    def __call__(self, state, rules, site=None):
        return self.propose(state, rules, site)

    def propose(self, state, rules, site: dict[str, Any] | None = None) -> Proposal:
        if self.samples <= 1:
            return self.inner.propose(state, rules, site)

        drafts: list[Proposal] = []
        failures: list[Exception] = []

        def once(_):
            return self.inner.propose(state, rules, site)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, self.samples)) as pool:
            for outcome in pool.map(_guard(once), range(self.samples)):
                if isinstance(outcome, Exception):
                    failures.append(outcome)
                else:
                    drafts.append(outcome)

        if not drafts:
            # Every sample failed. Nothing to be consistent about, and inventing
            # a proposal here would be the worst possible response.
            raise failures[0]

        groups: dict[tuple, list[Proposal]] = {}
        for draft in drafts:
            groups.setdefault(decision_key(draft), []).append(draft)

        modal = max(groups.values(), key=len)

        # Failed samples count against agreement rather than being discarded.
        # A model that cannot produce a parseable plan two times in five is
        # telling us something, and dropping those samples would hide it.
        agreement = len(modal) / self.samples
        stated = sum(d.confidence for d in modal) / len(modal)

        winner = modal[0]
        note = (
            f"Self-consistency: {len(modal)} of {self.samples} samples agreed on this plan "
            f"({len(groups)} distinct plan(s)"
            + (f", {len(failures)} sample(s) failed" if failures else "")
            + f"). Stated confidence {stated:.2f}, agreement {agreement:.2f}; "
            "the lower of the two is used."
        )

        return replace(
            winner,
            agreement=agreement,
            confidence=min(stated, agreement) if self.apply else winner.confidence,
            uncertainty_notes=(
                winner.uncertainty_notes + " " + note
                + ("" if self.apply else " [shadow: agreement measured, not applied]")
            ).strip(),
            provenance=_pin(winner.provenance, drafts),
        )


def _guard(fn):
    """Run a sample, returning the exception rather than raising it.

    A single bad sample must not abort the others: it is data about the model's
    reliability, and it belongs in the agreement denominator.
    """

    def wrapped(arg):
        try:
            return fn(arg)
        except Exception as exc:  # noqa: BLE001
            return exc

    return wrapped


def _pin(provenance: Provenance, drafts: list[Proposal]) -> Provenance:
    """Record every model that answered, not just the one that won.

    A fallback chain can serve different samples from different models. A pin
    naming only the winner would be a false audit trail in exactly the case
    where the trail matters most.
    """
    models = sorted({d.provenance.model for d in drafts})
    if len(models) == 1:
        return provenance
    return replace(provenance, model="+".join(models))
