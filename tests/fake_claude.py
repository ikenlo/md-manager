"""Фейковий клієнт Claude: заскриптовані відповіді, запис усіх запитів."""

from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

_ids = itertools.count(1)


def text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def tool(name: str, **inp: Any) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=inp)


def thinking() -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking="", signature="sig")


def response(*blocks: SimpleNamespace, stop_reason: str | None = None) -> SimpleNamespace:
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=1000, output_tokens=100,
            cache_read_input_tokens=5000, cache_creation_input_tokens=0,
        ),
    )  # fmt: skip


Step = SimpleNamespace | Callable[[dict[str, Any]], SimpleNamespace]


class FakeClaude:
    def __init__(self, *steps: Step, delay: float = 0) -> None:
        self.steps = list(steps)
        self.requests: list[dict[str, Any]] = []
        self.delay = delay
        self.messages = self

    def add(self, *steps: Step) -> None:
        self.steps.extend(steps)

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        # копія messages: runner далі дописує в той самий список
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.steps:
            raise AssertionError("FakeClaude: неочікуваний виклик")
        step = self.steps.pop(0)
        return step(kwargs) if callable(step) else step

    # --- допоміжне для перевірок ------------------------------------------------

    def tool_results(self, i: int = -1) -> list[dict[str, Any]]:
        """Розпарсені tool_result з останнього user-повідомлення i-го запиту."""
        last = self.requests[i]["messages"][-1]
        return [
            {**json.loads(b["content"]), "_is_error": b["is_error"]}
            for b in last["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        ]

    def system_text(self, i: int = -1) -> str:
        return "\n".join(b["text"] for b in self.requests[i]["system"])
