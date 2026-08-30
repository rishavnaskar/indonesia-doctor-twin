"""Finding text in the deployment language.

Two kinds of message reach a clinician. Some are authored in the pack — a red
flag's wording, an interaction rule's warning — and those simply carry a second
field. Others are composed by a check from values it computed: a dose against
its ceiling, a lab against its age limit. Those cannot be pre-written, so the
pack supplies a template and the check supplies the numbers.

Neither form puts a word of any language under /service. A pack that supplies no
template gets an untranslated finding, which the surface shows as such — a
visible gap rather than a silent English fallback that nobody notices for a
year.
"""

from __future__ import annotations

from typing import Any


def localise(rules: Any, rule_id: str | None, **params: Any) -> str:
    """The pack's wording for `rule_id`, formatted with `params`.

    Returns "" when the pack has nothing to say. A missing template is not an
    error: it is a translation that has not been written yet, and the finding
    still reaches the clinician in the language the engine composed.
    """
    if not rule_id:
        return ""
    catalogue = (getattr(rules, "guideline", {}) or {}).get("messages") or {}
    template = catalogue.get(rule_id)
    if not isinstance(template, str):
        return ""
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        # A template referring to a placeholder the check does not supply is a
        # pack bug. Show nothing rather than a half-substituted sentence with a
        # brace in it, which is how a clinician learns to distrust the panel.
        return ""
