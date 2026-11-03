"""The Settings "Test key" call: a free list-models probe, never a stored-key leak."""

import httpx
from fastapi.testclient import TestClient

from polaris import secrets
from polaris.llm import probe
from polaris.main import app


class _Response:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_probe_accepts_a_200_and_counts_models(monkeypatch):
    seen = {}

    def fake_get(url, *, headers, timeout):
        seen["url"], seen["headers"] = url, headers
        return _Response(200, {"data": [{"id": "a"}, {"id": "b"}]})

    monkeypatch.setattr(probe.httpx, "get", fake_get)

    result = probe.probe_provider_key("anthropic", "sk-ant-test")

    assert result.ok and result.model_count == 2
    assert seen["url"].startswith("https://api.anthropic.com/")
    assert seen["headers"]["x-api-key"] == "sk-ant-test"
    assert "anthropic-version" in seen["headers"]


def test_probe_reports_rejection_and_network_errors(monkeypatch):
    monkeypatch.setattr(probe.httpx, "get", lambda *a, **k: _Response(401))
    rejected = probe.probe_provider_key("openai", "sk-bad")
    assert not rejected.ok and rejected.status_code == 401 and "rejected" in rejected.detail

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(probe.httpx, "get", boom)
    offline = probe.probe_provider_key("openai", "sk-x")
    assert not offline.ok and offline.status_code is None and "ConnectError" in offline.detail

    assert not probe.probe_provider_key("openai", "").ok


def test_endpoint_uses_the_configured_key_and_never_returns_it(isolated_db, monkeypatch):
    monkeypatch.setattr(secrets, "get_provider_key", lambda provider: "sk-live-secret")
    monkeypatch.setattr(
        probe, "probe_provider_key",
        lambda provider, key, **kw: probe.ProbeResult(provider, key == "sk-live-secret", 200, "Key accepted.", 3),
    )
    import polaris.api.settings as settings_api

    monkeypatch.setattr(settings_api, "probe_provider_key", probe.probe_provider_key)

    response = TestClient(app).post("/api/v1/settings/keys/test", json={"provider": "openai"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["model_count"] == 3
    assert "sk-live-secret" not in response.text

    assert TestClient(app).post("/api/v1/settings/keys/test", json={"provider": "nope"}).status_code == 400
