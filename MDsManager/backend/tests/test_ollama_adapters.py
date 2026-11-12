import asyncio

import pytest

from app.config import get_settings
from app.services.adapters import (
    MockOllamaAdapter,
    OllamaAdapter,
    OllamaDisabledError,
    OllamaError,
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


def test_factory_real_not_yet_available(monkeypatch):
    monkeypatch.setattr(get_settings(), "mock_ollama", False)
    with pytest.raises(NotImplementedError):
        get_ollama_adapter()


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
