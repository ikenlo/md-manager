import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
        [call("create_appointment", booking), text("Передала адміністратору на підтвердження")]
    )
    result = run(adapter)
    assert result["needs_approval"] is True
    pb = result["proposed_booking"]
    assert pb["service_name"] == "Манікюр" and pb["tool"] == "create_appointment"
    assert (pb["date"], pb["time"]) == ("2026-12-01", "10:00")
    assert pb["arguments"] == booking
    assert result["intent"] == "booking" and result["iterations"] == 2
    assert result["content"] == "Передала адміністратору на підтвердження"

    tool_result = result["tool_calls_history"][0]["result"]
    assert tool_result["pending_approval"] is True
    assert tool_result["args"] == booking and tool_result["tool"] == "create_appointment"
    assert "ok" not in tool_result and "booking_id" not in tool_result  # не виконано
    # модель отримала pending_approval і пояснення, що запис ще не створено
    sent_tool_msg = adapter.calls[1][0][-1]
    assert (
        sent_tool_msg["role"] == "tool" and '"pending_approval": true' in sent_tool_msg["content"]
    )
    assert "НЕ створено" in sent_tool_msg["content"]


def test_run_agent_write_tool_is_not_executed(monkeypatch):
    import app.services.tools.registry as registry

    async def boom(**_):
        raise AssertionError("create_appointment must not run inside the agent")

    monkeypatch.setitem(registry.TOOLS, "create_appointment", boom)
    booking = {"service_name": "Стрижка", "date": "2026-12-02", "time": "13:00"}
    result = run(SequentialAdapter([call("create_appointment", booking), text("Передала")]))
    assert result["needs_approval"] is True


def test_run_agent_booking_missing_args():
    adapter = SequentialAdapter(
        [call("create_appointment", {"service_name": "Манікюр"}), text("На яку дату й час?")]
    )
    result = run(adapter)
    err = result["tool_calls_history"][0]["result"]["error"]
    assert "Missing" in err and "date" in err and "time" in err
    assert result["needs_approval"] is False and result["proposed_booking"] is None
    assert result["intent"] == "question"


def test_run_agent_booking_unknown_service_not_proposed():
    bad = {"service_name": "Татуювання", "date": "2026-12-01", "time": "10:00"}
    result = run(SequentialAdapter([call("create_appointment", bad), text("Такої послуги немає")]))
    assert "Невідома послуга" in result["tool_calls_history"][0]["result"]["error"]
    assert result["needs_approval"] is False


def test_run_agent_booking_at_iteration_limit_says_pending():
    booking = {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"}
    result = run(SequentialAdapter([call("create_appointment", booking)]), max_iterations=1)
    assert result["needs_approval"] is True and result["intent"] == "booking"
    assert "підтвердження" in result["content"]


class FailingAdapter(OllamaAdapter):
    """Відповідає по черзі, а після відповідей — OllamaError."""

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.call_count = 0

    async def chat(self, messages, tools=None):
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        raise OllamaError("Connection refused")


def test_run_agent_ollama_error_fallback():
    result = asyncio.run(run_agent([{"role": "user", "content": "hi"}], adapter=FailingAdapter()))
    assert result["content"] == "Вибачте, тимчасово не можу відповісти. Передам менеджеру."
    assert result["intent"] == "escalate"
    assert result["needs_approval"] is False and result["proposed_booking"] is None
    assert result["error"] == "Connection refused"
    assert result["iterations"] == 1


def test_run_agent_ollama_error_preserves_history():
    bad = FailingAdapter([call("get_services")])
    result = run(bad)
    assert result["iterations"] == 2
    assert len(result["tool_calls_history"]) == 1
    assert result["tool_calls_history"][0]["name"] == "get_services"
    assert result["intent"] == "escalate"
    assert result["content"] == "Вибачте, тимчасово не можу відповісти. Передам менеджеру."


def test_run_agent_ollama_error_drops_pending_booking():
    booking = {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"}
    result = run(FailingAdapter([call("create_appointment", booking)]))
    # клієнт не отримав підтвердження — пропозицію не показуємо на погодження
    assert result["needs_approval"] is False and result["intent"] == "escalate"


def test_run_agent_get_services_still_executes():
    result = run(SequentialAdapter([call("get_services"), text("Ось послуги")]))
    res = result["tool_calls_history"][0]["result"]
    assert "services" in res and "pending_approval" not in res
    assert result["needs_approval"] is False


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


def test_run_agent_llm_error_is_caught_and_works_with_mock():
    failed = run(MockOllamaAdapter(delay=0), [{"role": "user", "content": "__FAIL__"}])
    assert failed["intent"] == "escalate" and "mock_llm_failure" in failed["error"]
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
