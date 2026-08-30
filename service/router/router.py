"""Model router.

No model name is committed anywhere except here. That is not tidiness: model
choice measurably swings how often a medical model capitulates to a confidently
wrong patient, so it has to be a config decision that can be changed and
re-evaluated, never a constant compiled into the reasoning layer.

Backends register themselves under a task name. Today the only registered
reasoner is the deterministic reference one. A hosted or local model
implements the same three-argument signature and the gate does not change.

Residency, restated because it is the constraint that decides hosting: patient
data is processed in-country. Frontier APIs are for offline work on
de-identified data — generating evaluation cases, grading, distillation — and
never sit in the live path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from service.contracts.proposal import Proposal


class Reasoner(Protocol):
    def __call__(self, state: Any, rules: Any, site: dict | None = None) -> Proposal: ...


@dataclass
class Router:
    backends: dict[str, Reasoner] = field(default_factory=dict)
    default: str = "reference"

    def register(self, name: str, reasoner: Reasoner) -> None:
        self.backends[name] = reasoner

    def get(self, name: str | None = None) -> Reasoner:
        key = name or self.default
        if key not in self.backends:
            raise KeyError(
                f"no reasoner registered as {key!r}. Registered: {sorted(self.backends)}"
            )
        return self.backends[key]

    def propose(self, state, rules, site=None, *, backend: str | None = None) -> Proposal:
        return self.get(backend)(state, rules, site)


def default_router() -> Router:
    from service.reason import reference

    router = Router()
    router.register("reference", reference.propose)
    return router


def router_with_model(model: str | None = None, **backend_kwargs) -> Router:
    """A router whose default backend is a hosted model.

    Deliberately not the default. The deterministic reasoner is what CI and the
    scorecard run against, because a test suite that costs money per run and
    varies between runs is neither a test suite nor a suite.
    """
    from service.reason.model_reasoner import register
    from service.router.backends.hosted import HostedChatBackend

    router = default_router()
    backend = HostedChatBackend(model=model or HostedChatBackend.model, **backend_kwargs)
    register(router, backend)
    router.default = "model"
    return router
