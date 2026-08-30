"""The native Anthropic backend, with a mocked client.

No key, no network, no spend. What is being tested is the contract around the
SDK call — the guard, refusal handling, and content extraction — not the SDK
itself.
"""

import pytest

from service.router.backends.anthropic_native import (
    PROPOSAL_SCHEMA,
    AnthropicBackend,
    ModelRefusal,
    ResidencyError,
)


class Block:
    def __init__(self, type_, text=None):
        self.type = type_
        self.text = text


class FakeResponse:
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def _backend(response, **kwargs):
    return AnthropicBackend(_client=FakeClient(response), **kwargs)


def test_the_guard_runs_before_the_client_is_touched():
    backend = AnthropicBackend(_client=None)
    with pytest.raises(ResidencyError):
        backend.complete("s", "u", allow_egress=False)


def test_the_text_block_is_returned_past_thinking_blocks():
    """With thinking on, the text is not the first block."""
    response = FakeResponse([Block("thinking"), Block("text", '{"ok": true}')])
    assert _backend(response).complete("s", "u", allow_egress=True) == '{"ok": true}'


def test_a_refusal_is_its_own_error_not_a_crash():
    class Details:
        category = "medical"

    response = FakeResponse([], stop_reason="refusal", stop_details=Details())
    with pytest.raises(ModelRefusal, match="medical"):
        _backend(response).complete("s", "u", allow_egress=True)


def test_the_response_is_schema_constrained():
    backend = _backend(FakeResponse([Block("text", "{}")]))
    backend.complete("s", "u", allow_egress=True)
    request = backend._client.messages.last_request
    fmt = request["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"] is PROPOSAL_SCHEMA
    assert request["thinking"] == {"type": "adaptive"}


def test_thinking_can_be_turned_off():
    backend = _backend(FakeResponse([Block("text", "{}")]), thinking=False)
    backend.complete("s", "u", allow_egress=True)
    assert "thinking" not in backend._client.messages.last_request


def test_the_schema_permits_omission_rather_than_forcing_invention():
    """Over-constraining pushes a model to invent a value instead of omitting one."""
    assert set(PROPOSAL_SCHEMA["required"]) == {"assessment", "recommendation", "confidence"}
    assert "medication_changes" not in PROPOSAL_SCHEMA["required"]


def test_an_sdk_error_is_wrapped_with_context():
    from service.router.backends.anthropic_native import BackendError

    with pytest.raises(BackendError, match="ValueError"):
        _backend(ValueError("boom")).complete("s", "u", allow_egress=True)


def test_both_backends_satisfy_the_same_interface():
    """The swappability claim, asserted."""
    from service.router.router import build_backend

    for provider in ("anthropic", "openrouter"):
        backend = build_backend(provider)
        assert callable(backend.complete)
        assert isinstance(backend.version(), str)
