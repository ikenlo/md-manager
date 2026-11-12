import asyncio
from datetime import date, timedelta

import pytest

from app.services.tools import TOOLS_SCHEMA, ToolError, execute_tool
from app.services.tools.implementations import create_appointment, get_services, get_slots


def test_tools_schema_has_3_functions():
    assert len(TOOLS_SCHEMA) == 3
    for t in TOOLS_SCHEMA:
        assert t["type"] == "function" and t["function"]["name"]
        assert t["function"]["parameters"]["type"] == "object"


def test_tools_schema_names():
    assert {t["function"]["name"] for t in TOOLS_SCHEMA} == {
        "get_services",
        "get_slots",
        "create_appointment",
    }


def test_get_services_returns_list():
    res = asyncio.run(get_services())
    assert len(res["services"]) >= 5
    for s in res["services"]:
        assert isinstance(s["name"], str) and s["name"]
        assert isinstance(s["price_uah"], int) and isinstance(s["duration_min"], int)


def test_get_services_has_manicure_and_haircut():
    names = {s["name"] for s in asyncio.run(get_services())["services"]}
    assert {"Манікюр", "Стрижка"} <= names


def test_get_slots_default_tomorrow():
    res = asyncio.run(get_slots())
    assert res["date"] == (date.today() + timedelta(days=1)).isoformat()
    assert len(res["slots"]) >= 3


def test_get_slots_specific_date():
    assert asyncio.run(get_slots("2026-12-01"))["date"] == "2026-12-01"


@pytest.mark.parametrize("bad", ["wrong", "2026-1-5", "2026-02-30", "01.12.2026"])
def test_get_slots_invalid_date(bad):
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        asyncio.run(get_slots(bad))


def test_create_appointment_success():
    res = asyncio.run(create_appointment("Манікюр", "2026-12-01", "10:00"))
    assert res["ok"] is True and res["booking_id"].startswith("mock_")
    assert (res["service_name"], res["date"], res["time"]) == ("Манікюр", "2026-12-01", "10:00")


@pytest.mark.parametrize("bad", ["25:00", "10-00", "9:30", ""])
def test_create_appointment_invalid_time(bad):
    with pytest.raises(ToolError):
        asyncio.run(create_appointment("Манікюр", "2026-12-01", bad))


def test_create_appointment_unknown_service():
    with pytest.raises(ToolError, match="Невідома послуга"):
        asyncio.run(create_appointment("Татуювання", "2026-12-01", "10:00"))


def test_execute_tool_unknown():
    assert asyncio.run(execute_tool("unknown", {})) == {"error": "Unknown tool: unknown"}


def test_execute_tool_get_services():
    assert "services" in asyncio.run(execute_tool("get_services", {}))


def test_execute_tool_handles_error():
    res = asyncio.run(execute_tool("create_appointment", {"service_name": ""}))
    assert set(res) == {"error"} and res["error"]
    res = asyncio.run(execute_tool("get_slots", {"date": "вчора"}))
    assert res == {"error": "Дата має бути у форматі YYYY-MM-DD"}


def test_execute_tool_accepts_json_string_and_none():
    assert asyncio.run(execute_tool("get_slots", '{"date": "2026-12-01"}'))["date"] == "2026-12-01"
    assert "slots" in asyncio.run(execute_tool("get_slots", None))
    assert "error" in asyncio.run(execute_tool("get_slots", "{bad"))
    assert "error" in asyncio.run(execute_tool("get_slots", ["2026-12-01"]))
