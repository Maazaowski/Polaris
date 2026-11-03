"""Check that a provider key is accepted, without spending anything.

Both providers expose a list-models endpoint that is free and authenticated,
which is exactly the question the Settings page needs answered: "does this
key work?" rather than "is a key present?".
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from stencil.llm.config import normalize_provider

_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
}
_ANTHROPIC_VERSION = "2023-06-01"


@dataclass(frozen=True)
class ProbeResult:
    provider: str
    ok: bool
    status_code: int | None
    detail: str
    model_count: int | None = None


def probe_provider_key(provider: str, api_key: str, *, timeout: float = 15.0) -> ProbeResult:
    """Call the provider's list-models endpoint with ``api_key`` and report the outcome."""
    provider = normalize_provider(provider)
    if provider not in _ENDPOINTS:
        return ProbeResult(provider, False, None, f"Unknown provider: {provider}")
    if not api_key:
        return ProbeResult(provider, False, None, "No key is configured for this provider.")

    if provider == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": _ANTHROPIC_VERSION}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = httpx.get(_ENDPOINTS[provider], headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return ProbeResult(provider, False, None, f"Could not reach the provider: {type(exc).__name__}")

    if response.status_code == 200:
        count = None
        try:
            data = response.json().get("data")
            if isinstance(data, list):
                count = len(data)
        except ValueError:
            pass
        return ProbeResult(provider, True, 200, "Key accepted.", count)
    if response.status_code in (401, 403):
        return ProbeResult(provider, False, response.status_code, "The provider rejected this key.")
    return ProbeResult(
        provider, False, response.status_code, f"Unexpected response from the provider (HTTP {response.status_code})."
    )
