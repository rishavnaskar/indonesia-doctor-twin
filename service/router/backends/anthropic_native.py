"""A native Anthropic backend.

Two backends exist for one reason: a router with a single implementation is a
claim, not an architecture. Swapping between this and the aggregator backend is
a config change, and everything downstream — the gate, the workflow, the
signature line, the scorecard — is untouched by it. That is the whole
architectural argument, demonstrated rather than asserted.

This one can do something the OpenAI-compatible path cannot: constrain the
response to a JSON schema at the API level, so a malformed proposal becomes
close to impossible rather than merely caught afterwards. The strict parser
stays anyway. Defence in depth is the pattern everywhere else in this system
and there is no reason to abandon it at the one boundary we do not control.

The residency guard is identical to the other backend and is not optional here
either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL = "claude-opus-5"


class ResidencyError(PermissionError):
    """Raised rather than returned. Never catchable by accident."""


class BackendError(RuntimeError):
    pass


class ModelRefusal(BackendError):
    """The model's safety classifiers declined.

    Worth its own type. A refusal is not a crash and not a bad draft — it is the
    model saying no, which routes to the same place our own refusals do: the
    clinician sees nothing and the encounter ends in ABSTAIN.
    """


# Constrains the response at the API level. Kept deliberately loose on
# `required`: the strict parser handles absent fields, and over-constraining
# pushes a model into inventing a value rather than omitting one — which is
# exactly the failure mode this system exists to avoid.
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assessment": {"type": "string", "enum": ["controlled", "uncontrolled", "over_treated"]},
        "recommendation": {
            "type": "string",
            "enum": [
                "continue", "titrate_up", "titrate_down",
                "add_agent", "switch_agent", "refer",
            ],
        },
        "bp_trend_summary": {"type": "string"},
        "target_used": {
            "type": "object",
            "properties": {
                "sbp_lt": {"type": "number"},
                "dbp_lt": {"type": "number"},
                "citation": {"type": "string"},
            },
            "required": ["sbp_lt", "dbp_lt", "citation"],
            "additionalProperties": False,
        },
        "medication_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "stop", "increase", "decrease", "continue"],
                    },
                    "molecule": {"type": "string"},
                    "mg_per_dose": {"type": "number"},
                    "doses_per_day": {"type": "integer"},
                    "rationale": {"type": "string"},
                    "citation": {"type": "string"},
                },
                "required": ["action", "molecule", "rationale", "citation"],
                "additionalProperties": False,
            },
        },
        "investigations": {"type": "array", "items": {"type": "string"}},
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citation": {"type": "string"},
                },
                "required": ["text", "citation"],
                "additionalProperties": False,
            },
        },
        "patient_instructions": {"type": "string"},
        "follow_up_interval_days": {"type": "integer"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "uncertainty_notes": {"type": "string"},
    },
    "required": ["assessment", "recommendation", "confidence"],
    "additionalProperties": False,
}


@dataclass
class AnthropicBackend:
    model: str = DEFAULT_MODEL
    max_tokens: int = 16000
    timeout_s: float = 120.0
    thinking: bool = True
    effort: str | None = None
    _client: Any = field(default=None, repr=False)

    def version(self) -> str:
        return self.model

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise BackendError(
                "the anthropic package is not installed — "
                "pip install -r requirements-model.txt"
            ) from exc
        # Zero-arg constructor: resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
        # or a CLI auth profile. We never read or hold the key ourselves.
        self._client = anthropic.Anthropic(timeout=self.timeout_s)
        return self._client

    def complete(self, system: str, user: str, *, allow_egress: bool) -> str:
        if not allow_egress:
            raise ResidencyError(
                "Refusing to send patient data to a hosted endpoint. Only "
                "synthetic records may leave the residency boundary."
            )

        client = self._get_client()

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA}
            },
        }
        if self.thinking:
            request["thinking"] = {"type": "adaptive"}
        if self.effort:
            request["output_config"]["effort"] = self.effort

        try:
            response = client.messages.create(**request)
        except Exception as exc:  # noqa: BLE001 - surfaced with context, never swallowed
            raise BackendError(f"{type(exc).__name__}: {exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise ModelRefusal(f"the model declined this request (category: {category})")

        # With thinking enabled the response carries thinking blocks first, so
        # take the text block rather than the first block.
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text

        raise BackendError("response contained no text block")
