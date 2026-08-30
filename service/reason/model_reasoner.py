"""A model-backed reasoner.

Implements exactly the same signature as the deterministic reference reasoner —
`propose(state, rules, site) -> Proposal` — which is the whole architectural
claim made concrete: the model is a component behind an interface, not the
system. Swapping it changes one config line, and the gate, the workflow, the
signature line and the scorecard are all untouched.

What the model is allowed to do here is narrow on purpose. It drafts. It does
not decide, it does not talk to the patient, and everything it produces is
re-checked by rules it cannot see or influence. If it hallucinates a drug, gate
check 5 blocks it; an invented citation dies at check 6; an unsafe dose at
check 3. The model is the least trusted component in the system and is
positioned accordingly.
"""

from __future__ import annotations

from typing import Any

from service.contracts.proposal import Provenance
from service.reason import prompt as prompt_module
from service.reason.parse import ProposalParseError, extract_json, to_proposal
from service.rules.predicates import Context
from service.rules.targets import resolve_target


class ModelReasoner:
    def __init__(self, backend, *, corpus_version: str | None = None):
        self.backend = backend
        self._corpus_version = corpus_version

    def __call__(self, state, rules, site: dict[str, Any] | None = None):
        return self.propose(state, rules, site)

    def propose(self, state, rules, site: dict[str, Any] | None = None):
        resolution = resolve_target(rules.guideline, Context(state))

        system = prompt_module.system_prompt()
        user = prompt_module.build_user_prompt(state, rules, site, resolution.target)

        # The guard: only generated patients may cross the boundary.
        raw = self.backend.complete(system, user, allow_egress=bool(state.is_synthetic))

        # Provenance is built *after* the answer, never before. A backend may
        # fall back to a different model when one is rate-limited, and an alias
        # resolves to a concrete snapshot only in the response. Pinning ahead of
        # the call records what we intended to ask, which is not what happened.
        provenance = Provenance(
            model=self.backend.version(),
            prompt_template=prompt_module.VERSION,
            corpus=f"{self._corpus_version or rules.guideline.get('version', 'unknown')}@1",
        )

        parsed = extract_json(raw)
        return to_proposal(parsed, provenance)


def register(router, backend, name: str = "model") -> None:
    router.register(name, ModelReasoner(backend))
