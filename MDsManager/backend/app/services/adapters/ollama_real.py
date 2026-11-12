"""Справжня локальна LLM: Ollama HTTP API (POST /api/chat, stream=false)."""

import re
from typing import Any

import httpx

from app.config import get_settings
from app.services.adapters.ollama_base import ChatResult, OllamaAdapter, OllamaError

# Qwen3 у «режимі роздумів» на старих версіях Ollama повертає міркування прямо в content
_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class RealOllamaAdapter(OllamaAdapter):
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        cfg = get_settings()
        self.host = cfg.ollama_host.rstrip("/")
        self.model = cfg.ollama_model
        self.timeout = cfg.ollama_timeout_seconds
        self.temperature = cfg.ollama_temperature
        self.num_ctx = cfg.ollama_num_ctx
        # для тестів: httpx.MockTransport замість мережі
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools

        try:
            async with self._client(self.timeout) as client:
                response = await client.post(f"{self.host}/api/chat", json=payload)
        except httpx.ConnectError as e:
            raise OllamaError(
                f"Ollama недоступний на {self.host}. "
                "Запустіть 'ollama serve' і перевірте OLLAMA_HOST."
            ) from e
        except httpx.TimeoutException as e:
            raise OllamaError(
                f"Ollama таймаут ({self.timeout}s). "
                f"Модель {self.model} занадто повільна? Спробуйте меншу модель."
            ) from e
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama: помилка з'єднання ({type(e).__name__}: {e})") from e

        if response.status_code == 404:
            raise OllamaError(
                f"Модель {self.model} не знайдена. Виконайте 'ollama pull {self.model}'."
            )
        if response.status_code != 200:
            raise OllamaError(f"Ollama помилка {response.status_code}: {response.text[:500]}")

        try:
            data = response.json()
        except ValueError as e:
            raise OllamaError(f"Ollama повернув невалідний JSON: {response.text[:200]}") from e
        if not isinstance(data, dict) or not isinstance(data.get("message", {}), dict):
            raise OllamaError(f"Ollama повернув неочікувану відповідь: {response.text[:200]}")

        message = data.get("message") or {}
        content = _THINK.sub("", str(message.get("content") or "")).strip()
        tool_calls = message.get("tool_calls") or None
        return {"content": content, "tool_calls": tool_calls}

    async def health(self) -> dict[str, Any]:
        """Чи відповідає Ollama і які моделі завантажено (для /api/health у майбутньому)."""
        try:
            async with self._client(5) as client:
                r = await client.get(f"{self.host}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                return {
                    "ok": True,
                    "host": self.host,
                    "models": models,
                    "model_available": self.model in models,
                }
            return {"ok": False, "host": self.host, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"ok": False, "host": self.host, "error": str(e) or type(e).__name__}
