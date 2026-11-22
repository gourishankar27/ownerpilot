"""Explicit HTTP protocol fixtures; real Ollama evidence lives under Phase 3 results."""

import httpx
import pytest

from api.procurement_agent.provider import LocalModel


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://cloud.example",
        "http://localhost@evil.test",
        "http://127.0.0.1:11434/path",
        "http://localhost:11434?url=evil",
        "file:///secret",
        "http://localhost:11434#fragment",
    ],
)
def test_agent_ssrf_boundary(monkeypatch, endpoint):
    monkeypatch.setenv("PROCUREMENT_AGENT_URL", endpoint)
    with pytest.raises(ValueError):
        LocalModel()


def transport(kind):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": []
                    if kind == "missing"
                    else [
                        {
                            "name": "qwen3:8b",
                            "digest": "explicit-digest",
                            **({"remote_host": "cloud"} if kind == "remote" else {}),
                        }
                    ]
                },
            )
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "capabilities": ["completion"]
                    if kind == "no_tools"
                    else ["completion", "tools"]
                },
            )
        if kind == "timeout":
            raise httpx.ReadTimeout("Explicit fixture timeout")
        if kind == "oversized":
            return httpx.Response(200, content=b"x" * 65537)
        if kind == "malformed":
            return httpx.Response(200, content=b"not JSON")
        return httpx.Response(
            200,
            json={
                "model": "qwen3:8b",
                "message": {
                    "role": "assistant",
                    "content": "private reasoning must not be persisted",
                    "thinking": "private thinking",
                    "tool_calls": [
                        {"function": {"name": "get_approved_rfq", "arguments": {}}}
                    ],
                },
            },
        )

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("kind", ["missing", "remote", "no_tools"])
def test_model_capability_blocked_honestly(monkeypatch, kind):
    monkeypatch.setenv("PROCUREMENT_AGENT_MODEL", "qwen3:8b")
    with pytest.raises(ValueError):
        LocalModel(transport(kind)).health()


def test_native_action_retained_reasoning_discarded(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_AGENT_MODEL", "qwen3:8b")
    message, summary = LocalModel(transport("native")).chat([], [], "explicit-digest")
    assert message["tool_calls"][0]["function"]["name"] == "get_approved_rfq"
    assert message["content"] == "" and "thinking" not in message and summary is None


@pytest.mark.parametrize(
    "kind,error",
    [
        ("timeout", httpx.ReadTimeout),
        ("oversized", ValueError),
        ("malformed", ValueError),
    ],
)
def test_provider_limits_and_errors(monkeypatch, kind, error):
    monkeypatch.setenv("PROCUREMENT_AGENT_MODEL", "qwen3:8b")
    with pytest.raises(error):
        LocalModel(transport(kind)).chat([], [], "explicit-digest")
