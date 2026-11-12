"""Інтерфейс до локальної LLM (Qwen3 через Ollama).

Сервіси AI працюють лише з `OllamaAdapter`; реалізацію дає `factory.get_ollama_adapter()`.
"""

from abc import ABC, abstractmethod
from typing import Any, TypedDict


class ChatResult(TypedDict):
    content: str
    # [{"function": {"name": str, "arguments": dict}}] або None
    tool_calls: list[dict[str, Any]] | None


class OllamaError(RuntimeError):
    """Помилка LLM: мережа, таймаут, відповідь не того формату."""


class OllamaDisabledError(OllamaError):
    """AI вимкнено налаштуванням OLLAMA_ENABLED=false."""


class OllamaAdapter(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        """Надсилає діалог моделі й повертає {"content": str, "tool_calls": list | None}.

        messages: [{"role": "system"|"user"|"assistant"|"tool", "content": str}]
        tools: JSON-схеми функцій у форматі function-calling Ollama.
        Помилка → OllamaError.
        """
