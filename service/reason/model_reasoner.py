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
from service.reason.schema import proposal_schema
from service.rules.predicates import Context
from service.rules.targets import resolve_target


class ModelReasoner:
    def __init__(self, backend, *, corpus_version: str | None = None, use_tools: bool = False):
        self.backend = backend
        self._corpus_version = corpus_version
        # When on, the drafter asks for what it needs instead of being handed
        # the whole pack. Every tool is read-only.
        self.use_tools = use_tools

    def __call__(self, state, rules, site: dict[str, Any] | None = None):
        return self.propose(state, rules, site)

    def propose(self, state, rules, site: dict[str, Any] | None = None):
        resolution = resolve_target(rules.guideline, Context(state))

        wants_tools = self.use_tools and hasattr(self.backend, "complete_with_tools")
        system = prompt_module.system_prompt()
        user = prompt_module.build_user_prompt(
            state, rules, site, resolution.target,
            withhold_tool_served=wants_tools,
        )

        # The guard: only generated patients may cross the boundary.
        toolbox = None
        if wants_tools:
            from service.reason.tools import MAX_CALLS, Toolbox, tool_specs

            toolbox = Toolbox(state, rules, site)
            raw = self.backend.complete_with_tools(
                system, user,
                allow_egress=bool(state.is_synthetic),
                schema=proposal_schema(rules),
                tools=tool_specs(rules),
                dispatch=toolbox.dispatch,
                max_calls=MAX_CALLS,
            )
        else:
            raw = self.backend.complete(
                system, user,
                allow_egress=bool(state.is_synthetic),
                schema=proposal_schema(rules),
            )

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
        proposal = to_proposal(parsed, provenance)
        if toolbox is not None:
            proposal.tools_requested = list(toolbox.requested)
        return proposal


def register(router, backend, name: str = "model") -> None:
    router.register(name, ModelReasoner(backend))
