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
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"

# A free model by default, so the prototype can be run end to end without a
# bill. Free models are weaker and rate-limited; that is a feature for this
# demo rather than a problem, because it exercises the strict parser and the
# gate rather than flattering them.
DEFAULT_MODEL = "google/gemma-4-31b-it:free"


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


@dataclass
class HostedChatBackend:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key_env: str = "OPENROUTER_API_KEY"
    timeout_s: float = 90.0
    max_tokens: int = 2000
    temperature: float = 0.0
    json_mode: bool = True

    def version(self) -> str:
        return self.model

    def complete(self, system: str, user: str, *, allow_egress: bool) -> str:
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

        body = self._post(system, user, api_key, json_mode=self.json_mode)

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"unexpected response shape: {json.dumps(body)[:300]}") from exc

    def _post(self, system: str, user: str, api_key: str, *, json_mode: bool) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
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
            # Many free models do not implement response_format and reject the
            # whole request over it. Retry once without, then lean on the strict
            # parser — which is there precisely because JSON mode is a
            # convenience and never a guarantee.
            if json_mode and exc.code == 400 and "response_format" in detail:
                return self._post(system, user, api_key, json_mode=False)
            raise BackendError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"network error: {exc.reason}") from exc


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
