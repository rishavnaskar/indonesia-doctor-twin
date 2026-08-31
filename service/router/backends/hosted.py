"""A hosted, OpenAI-compatible chat backend.

Used through an aggregator so the model is a config string rather than a code
change — which is the point of having a router at all. Model choice measurably
changes how often a medical model capitulates under pressure, so it has to be
swappable and re-testable, not compiled in.

**The residency guard is the important part of this file.** Health data must be
processed in-country and a hosted endpoint is outside that boundary. This
backend therefore refuses to send any patient state not marked synthetic. The
prototype runs on generated patients, which is allowed; the day someone points
it at a real record, it fails closed rather than exporting a patient.

Stdlib only. The dependency list stays two packages long.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"

# A free model by default, so the prototype can be run end to end without a
# bill. Free models are weaker and rate-limited; that is a feature for this
# demo rather than a problem, because it exercises the strict parser and the
# gate rather than flattering them.
DEFAULT_MODEL = "minimax/minimax-m3:free"

# Free tiers are shared pools. A model is not "broken" when it returns 429 —
# it is busy, and the pool is shared with everyone else on the internet. A
# single hard-coded model therefore makes the whole prototype unrunnable at
# random times of day, which is a property of our configuration and not of the
# system under test. A chain degrades instead: try the next one, and record
# which one actually answered.
#
# These are candidates, not commitments. `--list-free` still queries live,
# because availability moves and a stale slug fails at demo time with a
# confusing 404.
DEFAULT_FALLBACKS: tuple[str, ...] = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "dots-studio/dots-3-note-preview:free",
    "google/gemma-4-31b-it:free",
    "openrouter/free",
)

# 429 from a shared pool usually clears in seconds. Two attempts, then move on;
# sitting in a long backoff loop against a saturated provider is slower than
# trying a different one.
RETRIES_PER_MODEL = 2
BACKOFF_S = 2.0


def _ssl_context() -> ssl.SSLContext:
    """Build a context with a real CA bundle.

    Python installed from python.org ships without root certificates on macOS,
    so the default context fails every HTTPS request with an opaque
    CERTIFICATE_VERIFY_FAILED. Prefer certifi's bundle when present; fall back
    to the system default otherwise. We never disable verification — an
    encrypted channel we do not authenticate is not a secure one, and this
    carries clinical data even when synthetic.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()


class ResidencyError(PermissionError):
    """Raised rather than returned. Never catchable by accident."""


class BackendError(RuntimeError):
    pass


class RateLimited(BackendError):
    """The pool is busy. Distinct from a broken request, because the response
    to it is different: wait or move, rather than fix."""


class TransientTransport(BackendError):
    """The connection failed in a way that says nothing about the request.

    A reset peer, a dropped socket, a timeout. Retryable for the same reason a
    429 is: nothing about the proposal changed. Kept distinct from BackendError
    because a connection reset misreported as a model failure is the same class
    of wrong conclusion as a truncation misreported as a parse failure.

    This also happens to be the failure mode a rural site sees constantly, which
    is the case the offline queue exists for.
    """


class TruncatedResponse(BackendError):
    """The model ran out of output budget mid-answer.

    Named separately because the failure it otherwise produces — half a JSON
    object reaching the parser — reads as "the model cannot follow the
    contract" when the real cause is our token budget. Misattributing a config
    bug to model quality is exactly the kind of wrong conclusion this
    prototype exists to avoid.
    """


@dataclass
class HostedChatBackend:
    model: str = DEFAULT_MODEL
    fallbacks: tuple[str, ...] = DEFAULT_FALLBACKS
    base_url: str = DEFAULT_BASE_URL
    api_key_env: str = "OPENROUTER_API_KEY"
    timeout_s: float = 90.0
    # Reasoning models spend this budget on thinking before they write a word,
    # and that spend counts here. Measured: a follow-up draft burned ~1,900
    # tokens reasoning, so a 2,000 budget left ~80 for the answer and truncated
    # every longer case. Output tokens are free on this tier; a budget too
    # small is not.
    max_tokens: int = 8000
    temperature: float = 0.0
    json_mode: bool = True

    # The model that actually answered and who served it, both as reported by
    # the API — not what we asked for. Populated on every successful call.
    _answered_by: str | None = field(default=None, init=False, repr=False)

    def version(self) -> str:
        """The provenance pin: `model@served_by`.

        Two facts, because both matter for reproducing a clinical decision.
        The slug says which weights; the upstream provider says whose serving
        stack ran them, and the same slug on two providers can differ in
        quantisation, sampling defaults and context handling.

        Before any call this returns the bare slug, with no `@`. That is
        deliberate: the gate's provenance check then rejects any proposal
        assembled without a real answer behind it, rather than accepting a
        placeholder that looks like a pin.
        """
        return self._answered_by or self.model

    @property
    def chain(self) -> list[str]:
        seen: list[str] = []
        for name in (self.model, *self.fallbacks):
            if name not in seen:
                seen.append(name)
        return seen

    def complete(self, system: str, user: str, *, allow_egress: bool,
                 schema: dict | None = None) -> str:
        if not allow_egress:
            raise ResidencyError(
                "Refusing to send patient data to a hosted endpoint. Only "
                "synthetic records may leave the residency boundary."
            )

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise BackendError(
                f"{self.api_key_env} is not set. Put it in .env (gitignored) "
                "or export it."
            )

        busy: list[str] = []
        for model in self.chain:
            try:
                body = self._call_model(model, system, user, api_key, schema)
                self._raise_if_error_body(body, model)
            except (RateLimited, TransientTransport):
                busy.append(model)
                continue
            served_by = body.get("provider") or "unknown-provider"
            self._answered_by = f"{body.get('model') or model}@{served_by}"
            return self._content(body)

        raise RateLimited(
            "every model in the chain is rate-limited upstream "
            f"({', '.join(busy)}). These are shared free pools, so this is "
            "load, not a bad key. Run `python -m tools.live --list-free` to see what is answering "
            "now and pass --model, or retry in a minute."
        )

    def complete_with_tools(self, system: str, user: str, *, allow_egress: bool,
                            schema: dict | None = None, tools: list | None = None,
                            dispatch=None, max_calls: int = 8) -> str:
        """Let the model ask for what it needs before it drafts.

        A bounded loop: every tool is read-only, the count is capped, and the
        loop ends by producing text. There is no tool that changes anything, so
        the worst a runaway loop can do is waste calls.
        """
        if not tools or dispatch is None:
            return self.complete(system, user, allow_egress=allow_egress, schema=schema)

        if not allow_egress:
            raise ResidencyError(
                "Refusing to send patient data to a hosted endpoint. Only "
                "synthetic records may leave the residency boundary."
            )
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise BackendError(f"{self.api_key_env} is not set.")

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        for _ in range(max_calls):
            body = self._post_messages(messages, api_key, tools=tools)
            self._raise_if_error_body(body, self.model)
            message = body["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                self._answered_by = (
                    f"{body.get('model') or self.model}"
                    f"@{body.get('provider') or 'unknown-provider'}"
                )
                return self._content(body)

            messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": calls,
            })
            for call in calls:
                function = call.get("function") or {}
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": dispatch(function.get("name", ""), arguments),
                })

        # Out of budget. Ask once more, without tools, so the loop ends in a
        # draft rather than in silence.
        messages.append({
            "role": "user",
            "content": "No more lookups. Answer now with the proposal JSON only.",
        })
        body = self._post_messages(messages, api_key, tools=None, schema=schema)
        self._answered_by = (
            f"{body.get('model') or self.model}@{body.get('provider') or 'unknown-provider'}"
        )
        return self._content(body)

    def _post_messages(self, messages: list, api_key: str, *, tools=None,
                       schema: dict | None = None) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
        elif schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "proposal", "strict": True, "schema": schema},
            }

        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_s, context=_ssl_context()
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code == 429:
                raise RateLimited(f"{self.model}: {_reason(detail)}") from exc
            raise BackendError(f"HTTP {exc.code} from {self.model}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise TransientTransport(f"{type(exc).__name__}: {exc}") from exc

    def _call_model(self, model: str, system: str, user: str, api_key: str,
                    schema: dict | None = None) -> dict:
        # Strongest enforcement first, degrading on refusal. A schema the
        # provider enforces removes a whole class of failure — a live run
        # produced `titraate_up`, correctly rejected by the parser at the cost
        # of a wasted call — but support is uneven, and a 400 for asking is not
        # a reason to give up on the model.
        mode = "schema" if (schema and self.json_mode) else (
            "object" if self.json_mode else "off")
        for attempt in range(RETRIES_PER_MODEL):
            try:
                return self._post(model, system, user, api_key, mode=mode, schema=schema)
            except (RateLimited, TransientTransport) as exc:
                if attempt + 1 >= RETRIES_PER_MODEL:
                    raise
                time.sleep(getattr(exc, "retry_after", None) or BACKOFF_S * (attempt + 1))
        raise AssertionError("unreachable")

    @staticmethod
    def _raise_if_error_body(body: dict, model: str) -> None:
        """An error arriving with HTTP 200.

        This provider returns rate limits and upstream failures as a 200 with an
        `error` object in the body at least as often as it returns a 4xx. Only
        the status code was being checked, so those fell through to the content
        reader and surfaced as "unexpected response shape" — which is both
        useless to read and, worse, silent: the fallback chain never fired,
        because nothing had raised RateLimited.
        """
        error = body.get("error")
        if not isinstance(error, dict):
            return
        message = str(error.get("message") or error)
        code = error.get("code")
        metadata = error.get("metadata") or {}
        raw = str(metadata.get("raw") or "")
        # Hyphens and spacing vary between providers and between messages from
        # the same provider: "rate limit", "rate-limited", "ratelimit". Match
        # the word, not the punctuation — the first version of this missed
        # "temporarily rate-limited upstream" and silently stopped the chain
        # falling through, which is the exact failure it was written to fix.
        haystack = f"{message} {raw}".lower().replace("-", " ").replace("_", " ")
        if code == 429 or "rate limit" in haystack or "quota" in haystack:
            raise RateLimited(f"{model}: {(raw or message)[:150]}")
        raise BackendError(f"{model}: {message[:200]}")

    def _content(self, body: dict) -> str:
        """Pull the assistant text out, and refuse an empty one.

        Some reasoning models return `content: null` and put everything in a
        `reasoning` field. Returning that null downstream produces a parser
        crash three layers away from the cause, so it is caught here and named.
        """
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"unexpected response shape: {json.dumps(body)[:300]}") from exc

        if body["choices"][0].get("finish_reason") == "length":
            details = (body.get("usage") or {}).get("completion_tokens_details") or {}
            spent = details.get("reasoning_tokens", "?")
            raise TruncatedResponse(
                f"{body.get('model', self.model)} hit the {self.max_tokens}-token "
                f"output budget mid-answer ({spent} of it went to reasoning). "
                "This is our budget, not the model failing the contract. Raise "
                "max_tokens rather than reading it as a parse failure."
            )

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content

        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            # Not silently accepted as an answer: it is the model thinking, not
            # the model answering. Handed to the strict parser, which will
            # reject it unless it genuinely contains the contract.
            return reasoning

        raise BackendError(
            f"{body.get('model', self.model)} returned an empty message "
            f"(finish_reason={body['choices'][0].get('finish_reason')!r}). "
            "Nothing to parse."
        )

    def _post(
        self, model: str, system: str, user: str, api_key: str, *,
        mode: str = "object", schema: dict | None = None,
    ) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if mode == "schema" and schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "proposal", "strict": True, "schema": schema},
            }
        elif mode == "object":
            payload["response_format"] = {"type": "json_object"}

        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_s, context=_ssl_context()
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code == 429:
                limited = RateLimited(f"{model}: {_reason(detail)}")
                limited.retry_after = _retry_after(exc)  # type: ignore[attr-defined]
                raise limited from exc
            # Many free models do not implement response_format and reject the
            # whole request over it. Retry once without, then lean on the strict
            # parser — which is there precisely because JSON mode is a
            # convenience and never a guarantee.
            if json_mode and exc.code == 400 and "response_format" in detail:
                return self._post(model, system, user, api_key, json_mode=False)
            raise BackendError(f"HTTP {exc.code} from {model}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TransientTransport(f"network error talking to {model}: {exc.reason}") from exc
        except (TimeoutError, ConnectionError) as exc:
            # ConnectionResetError and friends are OSError but NOT URLError, so
            # they escape the handler above and surface as an unhandled crash
            # mid-clinic. Observed in a live run.
            raise TransientTransport(f"{type(exc).__name__} talking to {model}: {exc}") from exc


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    try:
        return float(exc.headers.get("Retry-After"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _reason(detail: str) -> str:
    """Dig the human-readable half out of a nested provider error."""
    try:
        error = json.loads(detail).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return detail[:120]
    meta = error.get("metadata") or {}
    provider = meta.get("provider_name")
    raw = meta.get("raw")
    if isinstance(raw, str) and raw:
        return f"{raw[:150]}"
    return f"{error.get('message', 'rate limited')}" + (f" ({provider})" if provider else "")


def list_free_models(timeout_s: float = 25.0) -> list[dict]:
    """Ask which models are free right now, rather than hard-coding slugs.

    Availability changes, and a stale list in a source file is worse than no
    list at all: it fails at demo time with a confusing 404.
    """
    request = urllib.request.Request(MODELS_URL, headers={"User-Agent": "ai-clinician/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_s, context=_ssl_context()) as response:
        data = json.loads(response.read().decode("utf-8"))

    free = []
    for model in data.get("data", []):
        pricing = model.get("pricing") or {}
        try:
            if float(pricing.get("prompt", 1)) or float(pricing.get("completion", 1)):
                continue
        except (TypeError, ValueError):
            continue
        free.append(
            {
                "id": model["id"],
                "context": model.get("context_length") or 0,
                "structured": "response_format" in (model.get("supported_parameters") or []),
            }
        )
    return sorted(free, key=lambda m: (not m["structured"], -m["context"]))
