"""The hosted backend's HTTP contract, with no network and no key.

What is tested here is the behaviour around the call: what the request carries,
and what happens when a provider rejects part of it. Not the provider.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from service.router.backends.hosted import BackendError, HostedChatBackend

ANSWER = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


class _Transport:
    """Stands in for urlopen. Records every request and replays scripted replies.

    Each reply is either a dict (a 200 with that body) or an HTTPError to raise.
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent: list[dict] = []

    def __call__(self, request, **kwargs):
        self.sent.append(json.loads(request.data.decode("utf-8")))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Response(reply)


class _Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _rejects_response_format() -> urllib.error.HTTPError:
    detail = json.dumps({"error": {"message": "response_format is not supported"}})
    return urllib.error.HTTPError(
        "https://example.invalid", 400, "Bad Request", {},
        io.BytesIO(detail.encode("utf-8")),
    )


@pytest.fixture
def backend():
    return HostedChatBackend(model="some/model", fallbacks=())


def test_a_provider_that_rejects_a_schema_is_retried_without_one(backend, monkeypatch):
    """The documented degradation, which for a while raised NameError instead.

    `_post` read a `json_mode` name it has never had, so a 400 naming
    response_format crashed on the line meant to recover from it. Nothing
    caught it: reaching the line needs a provider that rejects the field, and
    the suite had no reason to simulate one. It does now.
    """
    transport = _Transport(_rejects_response_format(), ANSWER)
    monkeypatch.setattr("urllib.request.urlopen", transport)

    body = backend._post("some/model", "sys", "usr", "k", mode="schema", schema=SCHEMA)

    assert body == ANSWER
    assert transport.sent[0]["response_format"]["type"] == "json_schema"
    # One notch weaker, not straight to nothing: a provider may reject a strict
    # schema and still honour plain JSON mode.
    assert transport.sent[1]["response_format"] == {"type": "json_object"}


def test_the_degradation_bottoms_out_rather_than_looping(backend, monkeypatch):
    transport = _Transport(
        _rejects_response_format(), _rejects_response_format(), ANSWER,
    )
    monkeypatch.setattr("urllib.request.urlopen", transport)

    body = backend._post("some/model", "sys", "usr", "k", mode="schema", schema=SCHEMA)

    assert body == ANSWER
    assert "response_format" not in transport.sent[2]


def test_a_400_about_anything_else_is_raised(backend, monkeypatch):
    """Degrading on every 400 would hide a bad request as a model limitation."""
    detail = json.dumps({"error": {"message": "context length exceeded"}})
    error = urllib.error.HTTPError(
        "https://example.invalid", 400, "Bad Request", {},
        io.BytesIO(detail.encode("utf-8")),
    )
    monkeypatch.setattr("urllib.request.urlopen", _Transport(error))

    with pytest.raises(BackendError, match="context length"):
        backend._post("some/model", "sys", "usr", "k", mode="schema", schema=SCHEMA)


def test_off_mode_sends_no_response_format(backend, monkeypatch):
    transport = _Transport(ANSWER)
    monkeypatch.setattr("urllib.request.urlopen", transport)

    backend._post("some/model", "sys", "usr", "k", mode="off")

    assert "response_format" not in transport.sent[0]
