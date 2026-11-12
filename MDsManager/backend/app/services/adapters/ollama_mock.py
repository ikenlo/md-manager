"""Імітація LLM для розробки й тестів (MOCK_OLLAMA=true): Ollama не потрібна.

Маркери в останньому повідомленні:
- `__FAIL__` — виняток OllamaError (перевірка обробки збоїв);
- `__TOOL_CALL__` — виклик інструмента `get_services` замість тексту.
"""

import asyncio
from typing import Any

from app.services.adapters.ollama_base import ChatResult, OllamaAdapter, OllamaError

FAIL_MARKER = "__FAIL__"
TOOL_CALL_MARKER = "__TOOL_CALL__"
MOCK_REPLY = "Тестова відповідь від AI. 😊"


class MockOllamaAdapter(OllamaAdapter):
    def __init__(self, delay: float = 0.5) -> None:
        self.delay = delay

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        await asyncio.sleep(self.delay)
        last = str(messages[-1].get("content") or "") if messages else ""

        if FAIL_MARKER in last:
            raise OllamaError("mock_llm_failure: simulated LLM error")

        if TOOL_CALL_MARKER in last:
            return {
                "content": "",
                "tool_calls": [{"function": {"name": "get_services", "arguments": {}}}],
            }

        return {"content": MOCK_REPLY, "tool_calls": None}
