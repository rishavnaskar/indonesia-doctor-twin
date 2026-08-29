"""Derived problem flags.

SPEC-V1 §3 lists problem_flags as derived, and this is where they are derived.
The mapping from diagnosis codes to clinical flags is national configuration,
so it lives in the pack.

The reason this matters more than it looks: target resolution abstains for
patients with diabetes or chronic kidney disease, and if that abstention keys
only off a flag that some upstream system forgot to set, a patient whose
comorbidity exists purely as a diagnosis code gets the general adult target
instead of silence. The pack predicates therefore match on flag *or* code, and
this function closes the same gap from the other side.

Flags already set to True are never cleared. Something upstream may know
something the codes do not.
"""

from __future__ import annotations


def derive_flags(state, rules) -> dict[str, bool]:
    mapping = rules.guideline.get("problem_flags") or []
    for row in mapping:
        flag = row["flag"]
        if state.flags.get(flag):
            continue
        prefixes = row.get("any_diagnosis_prefix") or []
        if any(state.has_diagnosis_prefix(p) for p in prefixes):
            state.flags[flag] = True
    return state.flags
