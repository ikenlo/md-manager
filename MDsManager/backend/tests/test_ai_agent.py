import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.adapters.ollama_base import OllamaAdapter, OllamaError
from app.services.adapters.ollama_mock import MockOllamaAdapter
from app.services.ai_agent import (
    FALLBACK_REPLY,
    MAX_TOOL_LOOP,
    _detect_intent,
    build_messages_from_dialogue,
    run_agent,
)
from app.services.ai_prompt import load_sales_prompt
from app.services.tools import TOOLS_SCHEMA


class SequentialAdapter(OllamaAdapter):
    """Повертає наперед задані відповіді по черзі; запам'ятовує, що отримав."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.calls: list[tuple[list, list | None]] = []

    async def chat(self, messages, tools=None):
        if self.call_count >= len(self.responses):
            raise Exception("SequentialAdapter exhausted")
        self.calls.append(([dict(m) for m in messages], tools))
        self.call_count += 1
        return self.responses[self.call_count - 1]


def text(content):
    return {"content": content, "tool_calls": None}


def call(name, arguments=None, content=""):
    return {
        "content": content,
        "tool_calls": [{"function": {"name": name, "arguments": arguments or {}}}],
    }


USER = [{"role": "user", "content": "Привіт"}]


def run(adapter, messages=USER, **kw):
    return asyncio.run(run_agent(messages, adapter=adapter, **kw))


def test_run_agent_simple_response():
    adapter = SequentialAdapter([text("Вітаю! Чим допомогти?")])
    result = run(adapter)
    assert result["content"] == "Вітаю! Чим допомогти?"
    assert result["iterations"] == 1
    assert result["tool_calls_history"] == []
    assert result["needs_approval"] is False and result["proposed_booking"] is None
    assert result["intent"] == "question"
    # системний промпт першим, інструменти передано
    sent, tools = adapter.calls[0]
    assert sent[0] == {"role": "system", "content": load_sales_prompt()} and sent[1:] == USER
    assert tools == TOOLS_SCHEMA


def test_run_agent_with_tool_call_get_services():
    adapter = SequentialAdapter(
        [
            call("get_services", content="Зараз перевірю..."),
            text("Ось наші послуги: манікюр 350, стрижка 250."),
        ]
    )
    result = run(adapter, [{"role": "user", "content": "Які послуги?"}])
    assert result["iterations"] == 2
    assert len(result["tool_calls_history"]) == 1
    assert result["tool_calls_history"][0]["name"] == "get_services"
    assert "services" in result["tool_calls_history"][0]["result"]
    assert result["needs_approval"] is False and result["intent"] == "question"
    # друга відповідь моделі отримала результат інструмента
    second = adapter.calls[1][0]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"]
    assert second[-1]["role"] == "tool" and second[-1]["name"] == "get_services"
    assert "Манікюр" in second[-1]["content"]  # ensure_ascii=False


def test_run_agent_with_booking_needs_approval():
    booking = {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"}
    adapter = SequentialAdapter(
        [call("create_appointment", booking), text("Записала вас на манікюр 1 грудня о 10:00!")]
    )
    result = run(adapter)
    assert result["needs_approval"] is True
    pb = result["proposed_booking"]
    assert (pb["service_name"], pb["date"], pb["time"]) == ("Манікюр", "2026-12-01", "10:00")
    assert pb["result"]["ok"] is True
    assert result["intent"] == "booking"


def test_run_agent_max_iterations_stops():
    adapter = SequentialAdapter([call("get_services", content="Перевіряю…")] * 5)
    result = run(adapter, max_iterations=3)
    assert result["iterations"] == 3 and adapter.call_count == 3
    assert len(result["tool_calls_history"]) == 3
    assert result["content"] == "Перевіряю…"


def test_run_agent_max_iterations_without_text_uses_fallback():
    adapter = SequentialAdapter([call("get_services")] * 5)
    result = run(adapter, max_iterations=2)
    assert result["content"] == FALLBACK_REPLY and result["intent"] == "escalate"


def test_run_agent_invalid_tool_args_string():
    adapter = SequentialAdapter(
        [call("get_slots", '{"date": "2026-12-01"}'), text("Є час о 10:30")]
    )
    result = run(adapter)
    entry = result["tool_calls_history"][0]
    assert entry["arguments"]["date"] == "2026-12-01" and entry["result"]["date"] == "2026-12-01"


def test_run_agent_invalid_tool_args_not_dict():
    adapter = SequentialAdapter([call("get_slots", "not a dict"), text("Ось вільні слоти")])
    result = run(adapter)
    assert result["iterations"] >= 1
    entry = result["tool_calls_history"][0]
    assert entry["arguments"] == {}
    assert entry["result"]["date"] == (datetime.now().date() + timedelta(days=1)).isoformat()


def test_run_agent_tool_error_continues():
    bad = {"service_name": "Манікюр", "date": "wrong", "time": "10:00"}
    adapter = SequentialAdapter(
        [call("create_appointment", bad), text("Уточніть, будь ласка, дату")]
    )
    result = run(adapter)
    assert "error" in result["tool_calls_history"][0]["result"]
    assert result["needs_approval"] is False and result["proposed_booking"] is None
    assert result["content"] == "Уточніть, будь ласка, дату"


def test_run_agent_limits_tool_calls_per_response():
    many = {
        "content": "",
        "tool_calls": [{"function": {"name": "get_services", "arguments": {}}}] * 5,
    }
    adapter = SequentialAdapter([many, text("Готово")])
    result = run(adapter)
    assert len(result["tool_calls_history"]) == MAX_TOOL_LOOP


def test_run_agent_skips_malformed_tool_call():
    adapter = SequentialAdapter(
        [{"content": "", "tool_calls": [{"oops": 1}, {"function": {}}]}, text("Добре")]
    )
    result = run(adapter)
    assert result["tool_calls_history"] == [] and result["content"] == "Добре"


def test_run_agent_propagates_llm_error_and_works_with_mock():
    with pytest.raises(OllamaError):
        run(MockOllamaAdapter(delay=0), [{"role": "user", "content": "__FAIL__"}])
    ok = run(MockOllamaAdapter(delay=0))
    assert ok["content"].startswith("Тестова") and ok["intent"] == "question"


def test_detect_intent_escalate():
    assert _detect_intent(False, "Зараз покличу менеджера", []) == "escalate"


def test_detect_intent_booking():
    assert _detect_intent(True, "Записала", []) == "booking"


def test_detect_intent_unknown():
    assert _detect_intent(False, "", []) == "unknown"


def test_build_messages_from_dialogue():
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    msgs = [
        SimpleNamespace(
            id=4, sender_type="agent", content="Вітаю!", created_at=t0 + timedelta(minutes=1)
        ),
        SimpleNamespace(id=1, sender_type="client", content="Привіт", created_at=t0),
        SimpleNamespace(
            id=5,
            sender_type="system",
            content="Створено запис",
            created_at=t0 + timedelta(minutes=2),
        ),
        SimpleNamespace(
            id=6, sender_type="human", content="Так, є час", created_at=t0 + timedelta(minutes=3)
        ),
        SimpleNamespace(
            id=7, sender_type="client", content="", created_at=t0 + timedelta(minutes=4)
        ),
        SimpleNamespace(
            id=8, sender_type="client", content="Дякую", created_at=t0 + timedelta(minutes=5)
        ),
    ]
    dialogue = SimpleNamespace(messages=msgs)
    assert build_messages_from_dialogue(dialogue) == [
        {"role": "user", "content": "Привіт"},
        {"role": "assistant", "content": "Вітаю!"},
        {"role": "assistant", "content": "Так, є час"},
        {"role": "user", "content": "Дякую"},
    ]
    # limit рахує останні повідомлення до фільтрації
    assert build_messages_from_dialogue(dialogue, limit=2) == [{"role": "user", "content": "Дякую"}]
