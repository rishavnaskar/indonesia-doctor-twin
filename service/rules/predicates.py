"""A very small predicate evaluator over patient state.

This is what lets the clinical rules live in a pack as data while the engine
stays country-agnostic — the "engine yes, rules no" split from BUILD.md §2b.

The single most important property here is that it **fails closed**. An
unrecognised key, a malformed rule, a bad operator: all raise. None of them
quietly evaluate to False. A red-flag rule that silently becomes "no red flag"
because someone fat-fingered a YAML key is exactly the failure this system
cannot have, and it is the kind of bug that is invisible in testing precisely
because it produces no output.

Stdlib only, by rule. No YAML, no framework, no model.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable

from service.state.models import PatientState


class PredicateError(ValueError):
    """A rule could not be evaluated. Always fatal, never swallowed."""


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

_COMPOSITES = ("all_of", "any_of", "none_of")

# primary key -> the companion keys it is allowed to carry
_LEAVES: dict[str, set[str]] = {
    "always": set(),
    "obs": {"op", "value"},
    "symptom": set(),
    "flag": set(),
    "age": set(),
    "diagnosis_prefix": set(),
    "obs_missing": set(),
    "obs_older_than_days": set(),
    "relative_fall": set(),
}


@dataclass(frozen=True)
class Context:
    state: PatientState


def evaluate(node: Any, ctx: Context) -> bool:
    if not isinstance(node, dict):
        raise PredicateError(f"predicate must be a mapping, got {type(node).__name__}: {node!r}")

    present = [k for k in node if k in _COMPOSITES or k in _LEAVES]
    if len(present) != 1:
        raise PredicateError(
            f"predicate needs exactly one primary key, found {present or list(node)} in {node!r}"
        )
    key = present[0]

    if key in _COMPOSITES:
        if set(node) != {key}:
            raise PredicateError(f"{key} takes no companion keys: {node!r}")
        children = node[key]
        if not isinstance(children, list) or not children:
            raise PredicateError(f"{key} needs a non-empty list: {node!r}")
        results = [evaluate(c, ctx) for c in children]
        if key == "all_of":
            return all(results)
        if key == "any_of":
            return any(results)
        return not any(results)  # none_of

    extra = set(node) - {key} - _LEAVES[key]
    if extra:
        raise PredicateError(f"unknown keys {sorted(extra)} on leaf {key!r}: {node!r}")

    return _leaf(key, node, ctx)


def _leaf(key: str, node: dict, ctx: Context) -> bool:
    st = ctx.state

    if key == "always":
        value = node["always"]
        if not isinstance(value, bool):
            raise PredicateError(f"always must be a boolean: {node!r}")
        return value

    if key == "obs":
        code = node["obs"]
        if "op" not in node or "value" not in node:
            raise PredicateError(f"obs needs op and value: {node!r}")
        obs = st.latest(code)
        if obs is None:
            # Absent data is not a positive finding. Missing values are the
            # sufficiency check's job (gate check 7), not a red flag's.
            return False
        return _compare(obs.value, node["op"], node["value"], node)

    if key == "symptom":
        return bool(st.symptoms.get(node["symptom"], False))

    if key == "flag":
        return bool(st.flags.get(node["flag"], False))

    if key == "age":
        spec = node["age"]
        if not isinstance(spec, dict) or "op" not in spec or "value" not in spec:
            raise PredicateError(f"age needs {{op, value}}: {node!r}")
        return _compare(st.age, spec["op"], spec["value"], node)

    if key == "diagnosis_prefix":
        return st.has_diagnosis_prefix(node["diagnosis_prefix"])

    if key == "obs_missing":
        return st.latest(node["obs_missing"]) is None

    if key == "obs_older_than_days":
        spec = node["obs_older_than_days"]
        if not isinstance(spec, dict) or "code" not in spec or "days" not in spec:
            raise PredicateError(f"obs_older_than_days needs {{code, days}}: {node!r}")
        age = st.observation_age_days(spec["code"])
        if age is None:
            return True  # absent counts as stale
        return age > spec["days"]

    if key == "relative_fall":
        spec = node["relative_fall"]
        if not isinstance(spec, dict) or "code" not in spec or "fraction" not in spec:
            raise PredicateError(f"relative_fall needs {{code, fraction}}: {node!r}")
        latest, prior = st.latest(spec["code"]), st.previous(spec["code"])
        if latest is None or prior is None or prior.value <= 0:
            return False
        return (prior.value - latest.value) / prior.value > float(spec["fraction"])

    raise PredicateError(f"unhandled leaf {key!r}")  # pragma: no cover


def _compare(left: Any, op: str, right: Any, node: dict) -> bool:
    fn = _OPS.get(op)
    if fn is None:
        raise PredicateError(f"unknown operator {op!r} in {node!r}")
    return bool(fn(left, right))
