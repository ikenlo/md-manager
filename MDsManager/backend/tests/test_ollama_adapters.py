import asyncio
import json
import os

import httpx
import pytest

from app.config import get_settings
from app.services.adapters import (
    MockOllamaAdapter,
    OllamaAdapter,
    OllamaDisabledError,
    OllamaError,
    RealOllamaAdapter,
    get_ollama_adapter,
)


def chat(adapter, text, tools=None):
    return asyncio.run(adapter.chat([{"role": "user", "content": text}], tools))


def test_factory_returns_mock_by_default():
    adapter = get_ollama_adapter()
    assert isinstance(adapter, MockOllamaAdapter) and isinstance(adapter, OllamaAdapter)


def test_config_defaults():
    cfg = get_settings()
    assert cfg.ollama_host == "http://localhost:11434" and cfg.ollama_model == "qwen3:14b"
    assert (cfg.ollama_timeout_seconds, cfg.ollama_temperature, cfg.ollama_num_ctx) == (
        120,
        0.7,
        8192,
    )


def test_factory_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "ollama_enabled", False)
    with pytest.raises(OllamaDisabledError):
        get_ollama_adapter()


def test_factory_returns_real_when_mock_false(monkeypatch):
    monkeypatch.setattr(get_settings(), "mock_ollama", False)
    assert isinstance(get_ollama_adapter(), RealOllamaAdapter)


def test_mock_plain_reply():
    assert chat(MockOllamaAdapter(delay=0), "Привіт") == {
        "content": "Тестова відповідь від AI. 😊",
        "tool_calls": None,
    }


def test_mock_tool_call():
    res = chat(MockOllamaAdapter(delay=0), "покажи послуги __TOOL_CALL__")
    assert res["content"] == ""
    assert res["tool_calls"] == [{"function": {"name": "get_services", "arguments": {}}}]


def test_mock_failure_is_ollama_error():
    with pytest.raises(OllamaError, match="mock_llm_failure"):
        chat(MockOllamaAdapter(delay=0), "__FAIL__")


def test_mock_uses_last_message_and_handles_empty():
    adapter = MockOllamaAdapter(delay=0)
    msgs = [{"role": "user", "content": "__FAIL__"}, {"role": "assistant", "content": "ok"}]
    assert asyncio.run(adapter.chat(msgs))["content"].startswith("Тестова")
    assert asyncio.run(adapter.chat([]))["tool_calls"] is None


# --- RealOllamaAdapter (httpx.MockTransport замість мережі) ---


def real_with(handler) -> tuple[RealOllamaAdapter, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return RealOllamaAdapter(transport=httpx.MockTransport(wrapped)), seen


def ok(message: dict) -> httpx.Response:
    return httpx.Response(200, json={"model": "qwen3:14b", "message": message, "done": True})


def raise_(exc_type):
    def handler(request):
        raise exc_type("boom", request=request)

    return handler


def test_real_adapter_parses_response_and_sends_payload():
    adapter, seen = real_with(lambda r: ok({"role": "assistant", "content": "Привіт!"}))
    msgs = [{"role": "user", "content": "Привіт"}]
    assert asyncio.run(adapter.chat(msgs)) == {"content": "Привіт!", "tool_calls": None}

    req = seen[0]
    assert req.method == "POST" and str(req.url) == "http://localhost:11434/api/chat"
    body = json.loads(req.content)
    assert body == {
        "model": "qwen3:14b",
        "messages": msgs,
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 8192},
    }


def test_real_adapter_handles_tool_calls():
    calls = [{"function": {"name": "get_services", "arguments": {"category": "nails"}}}]
    tools = [{"type": "function", "function": {"name": "get_services", "parameters": {}}}]
    adapter, seen = real_with(
        lambda r: ok({"role": "assistant", "content": "", "tool_calls": calls})
    )
    res = asyncio.run(adapter.chat([{"role": "user", "content": "Послуги?"}], tools))
    assert res["tool_calls"] == calls and len(res["tool_calls"]) > 0
    assert json.loads(seen[0].content)["tools"] == tools


def test_real_adapter_strips_qwen_think_block():
    adapter, _ = real_with(
        lambda r: ok({"role": "assistant", "content": "<think>міркую…</think>\nДобрий день!"})
    )
    assert (
        asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))["content"] == "Добрий день!"
    )


def test_real_adapter_trailing_slash_in_host(monkeypatch):
    monkeypatch.setattr(get_settings(), "ollama_host", "http://gpu-pc:11434/")
    adapter, seen = real_with(lambda r: ok({"content": "ok"}))
    asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))
    assert str(seen[0].url) == "http://gpu-pc:11434/api/chat"


def test_real_adapter_connect_error():
    adapter, _ = real_with(raise_(httpx.ConnectError))
    with pytest.raises(OllamaError, match="недоступний"):
        asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))


def test_real_adapter_timeout():
    adapter, _ = real_with(raise_(httpx.ReadTimeout))
    with pytest.raises(OllamaError, match="таймаут"):
        asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))


def test_real_adapter_404_model_not_found():
    adapter, _ = real_with(lambda r: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(OllamaError, match="не знайдена") as e:
        asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))
    assert "ollama pull qwen3:14b" in str(e.value)


def test_real_adapter_other_http_error():
    adapter, _ = real_with(lambda r: httpx.Response(500, text="CUDA out of memory"))
    with pytest.raises(OllamaError, match="500.*CUDA"):
        asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))


def test_real_adapter_invalid_json():
    adapter, _ = real_with(lambda r: httpx.Response(200, text="not json"))
    with pytest.raises(OllamaError, match="JSON"):
        asyncio.run(adapter.chat([{"role": "user", "content": "x"}]))


def test_real_adapter_health():
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen3:14b"}, {"name": "qwen3:8b"}]})

    adapter, _ = real_with(handler)
    assert asyncio.run(adapter.health()) == {
        "ok": True,
        "host": "http://localhost:11434",
        "models": ["qwen3:14b", "qwen3:8b"],
        "model_available": True,
    }
    down, _ = real_with(raise_(httpx.ConnectError))
    res = asyncio.run(down.health())
    assert res["ok"] is False and res["error"]


def _ollama_available() -> bool:
    try:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        return httpx.get(f"{host}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not running")
def test_real_adapter_integration(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "ollama_host", os.getenv("OLLAMA_HOST", "http://localhost:11434")
    )
    if os.getenv("OLLAMA_MODEL"):
        monkeypatch.setattr(get_settings(), "ollama_model", os.environ["OLLAMA_MODEL"])
    adapter = RealOllamaAdapter()
    result = asyncio.run(adapter.chat([{"role": "user", "content": "Скажи 'тест'"}]))
    assert "тест" in result["content"].lower()
