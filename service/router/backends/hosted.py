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
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"


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

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

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
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise BackendError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"network error: {exc.reason}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"unexpected response shape: {json.dumps(body)[:300]}") from exc
