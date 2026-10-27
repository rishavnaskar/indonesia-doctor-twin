"""What talking to a hosted provider costs you: errors, TLS, and a live catalogue.

Split out of hosted.py so that the backend file is the request and the
response, and this is everything around them. The distinctions in the error
taxonomy are the reason it exists at all: "the model is bad", "the pool is
busy", "the network blinked" and "we ran out of our own token budget" are four
different events, and collapsing any of them into another is how a
configuration problem gets written up as a model-quality finding.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

MODELS_URL = "https://openrouter.ai/api/v1/models"


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
