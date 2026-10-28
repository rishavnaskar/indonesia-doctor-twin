"""The two `tools.live` modes that make no model call.

Both answer a question about the run rather than performing one: which free
models are answering right now, and what exactly would be sent. Neither needs
a key, neither costs anything, and both exit before the runner starts - which
is the whole reason they are worth keeping apart from it. `live.py` is about
spending money carefully; this file is about not spending any.
"""

from __future__ import annotations

from datagen.synthetic import make_patient


def list_free() -> int:
    """Models that cost nothing right now, queried live rather than hard-coded.

    Availability moves. A stale slug fails at demo time with a confusing 404,
    so the list is never baked into the source.
    """
    from service.router.backends.hosted import list_free_models

    print("\n  Free models available right now (queried live, not hard-coded):\n")
    for model in list_free_models():
        mark = "json" if model["structured"] else "    "
        print(f"    [{mark}] {model['id']:<52} ctx {model['context']:,}")
    print("\n  [json] = advertises structured output. Prefer those; the others")
    print("  still work, because the strict parser does not trust either.\n")
    print("  Use with: python -m tools.live --n 5 --model <id>\n")
    return 0


def show_prompt(rules, site) -> int:
    """Exactly what would be sent, for a representative patient.

    A prompt nobody can read is a prompt nobody reviews, and this one carries
    the guideline the draft is supposed to follow.
    """
    from service.reason import prompt as prompt_module
    from service.rules.predicates import Context
    from service.rules.targets import resolve_target

    state = make_patient(900, controlled=False)
    target = resolve_target(rules.guideline, Context(state)).target
    print("\n--- system ---\n" + prompt_module.system_prompt())
    print("\n--- user (truncated) ---")
    print(prompt_module.build_user_prompt(state, rules, site, target)[:1500] + "\n...")
    return 0
