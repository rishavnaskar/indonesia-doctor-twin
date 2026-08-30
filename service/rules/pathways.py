"""Which pathway is this visit?

The engine runs one pathway at a time and does not know there are others. It
reads `rules.guideline`; selection swaps that field and every check, the
prompt, the reference reasoner and the referral-back drafter carry on unchanged.
That is the same trick that makes the country swappable, applied one level down.

Selection is deterministic and comes from the pack: each pathway declares an
`applies_to` predicate, and `pathway_order` decides who wins when more than one
matches. Order is a clinical judgement — which problem leads when a patient has
both — so it belongs in the pack, not in an if-statement here.

Matching no pathway is not an error. It is a handoff: this patient has nothing
we are built to help with, and saying so is a correct answer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from service.rules.predicates import Context, PredicateError, evaluate


@dataclass(frozen=True)
class PathwayChoice:
    name: str | None
    reason: str = ""

    @property
    def matched(self) -> bool:
        return self.name is not None


def select(rules, state) -> PathwayChoice:
    context = Context(state)
    tried: list[str] = []

    for name in rules.pathway_order:
        pathway = rules.pathways.get(name)
        if not pathway:
            continue
        predicate = pathway.get("applies_to")
        if predicate is None:
            # A pathway with no entry condition claims everyone. Legal, and it
            # is why order matters, but it must be a deliberate pack decision
            # rather than an omission that silently swallows every patient.
            return PathwayChoice(name, "pathway declares no entry condition")
        try:
            if evaluate(predicate, context):
                return PathwayChoice(name, f"matched {name}")
        except PredicateError as exc:
            # Fail closed, as everywhere else: an unreadable rule does not
            # quietly admit a patient to a pathway.
            tried.append(f"{name} (rule error: {exc})")
            continue
        tried.append(name)

    return PathwayChoice(
        None,
        "No pathway covers this patient"
        + (f" (considered: {', '.join(tried)})" if tried else "")
        + ".",
    )


def with_pathway(rules, name: str):
    """A view of the rule set with one pathway in force.

    Returns a copy rather than mutating, so two encounters running concurrently
    on different pathways cannot tread on each other.
    """
    if name not in rules.pathways:
        raise KeyError(f"unknown pathway {name!r}. Known: {sorted(rules.pathways)}")
    return replace(rules, guideline=rules.pathways[name])
