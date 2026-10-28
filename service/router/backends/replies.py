"""Reading what the provider sent back.

Split out of `hosted.py`, which is about making the call and guarding
residency. This is the other half: deciding what a reply means. The two
concerns drifted apart as the error handling grew, and the error handling grew
because almost everything surprising about this provider is in its replies
rather than in its status codes.

Both functions here are pure: a body in, an answer or an exception out. That
is what makes them cheap to test against a recorded reply, which matters more
than usual given that each one exists because of a failure observed in a live
run rather than a case somebody imagined.
"""

from __future__ import annotations

import json

from service.router.backends.transport import (
    BackendError,
    RateLimited,
    TruncatedResponse,
)


def raise_if_error_body(body: dict, model: str) -> None:
    """An error arriving with HTTP 200.

    This provider returns rate limits and upstream failures as a 200 with an
    `error` object in the body at least as often as it returns a 4xx. Only the
    status code was being checked, so those fell through to the content reader
    and surfaced as "unexpected response shape" - which is both useless to read
    and, worse, silent: the fallback chain never fired, because nothing had
    raised RateLimited.
    """
    error = body.get("error")
    if not isinstance(error, dict):
        return
    message = str(error.get("message") or error)
    code = error.get("code")
    metadata = error.get("metadata") or {}
    raw = str(metadata.get("raw") or "")
    # Hyphens and spacing vary between providers and between messages from the
    # same provider: "rate limit", "rate-limited", "ratelimit". Match the word,
    # not the punctuation - the first version of this missed "temporarily
    # rate-limited upstream" and silently stopped the chain falling through,
    # which is the exact failure it was written to fix.
    haystack = f"{message} {raw}".lower().replace("-", " ").replace("_", " ")
    if code == 429 or "rate limit" in haystack or "quota" in haystack:
        raise RateLimited(f"{model}: {(raw or message)[:150]}")
    raise BackendError(f"{model}: {message[:200]}")


def read_content(body: dict, *, model: str, max_tokens: int) -> str:
    """Pull the assistant text out, and refuse an empty one.

    Some reasoning models return `content: null` and put everything in a
    `reasoning` field. Returning that null downstream produces a parser crash
    three layers away from the cause, so it is caught here and named.

    `model` and `max_tokens` are what was asked for; the reply usually names
    the model that actually answered and that name is preferred, because in a
    fallback chain the two differ and only the second one is useful to read.
    """
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BackendError(f"unexpected response shape: {json.dumps(body)[:300]}") from exc

    answered = body.get("model", model)

    if body["choices"][0].get("finish_reason") == "length":
        details = (body.get("usage") or {}).get("completion_tokens_details") or {}
        spent = details.get("reasoning_tokens", "?")
        raise TruncatedResponse(
            f"{answered} hit the {max_tokens}-token "
            f"output budget mid-answer ({spent} of it went to reasoning). "
            "This is our budget, not the model failing the contract. Raise "
            "max_tokens rather than reading it as a parse failure."
        )

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    reasoning = message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        # Not silently accepted as an answer: it is the model thinking, not the
        # model answering. Handed to the strict parser, which will reject it
        # unless it genuinely contains the contract.
        return reasoning

    raise BackendError(
        f"{answered} returned an empty message "
        f"(finish_reason={body['choices'][0].get('finish_reason')!r}). "
        "Nothing to parse."
    )
