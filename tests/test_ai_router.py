"""Маршрутизатор моделей: Gemini для масової генерації, облік вартості, місячний бюджет."""

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
from aiogram.methods import SendPhoto
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import prices
from app.ai.budget import BudgetExceeded, month_start
from app.ai.gemini import GeminiClient, GeminiError
from app.ai.router import AiRouter, AiUnavailable
from app.config import Settings
from app.db.models import AiUsage
from tests.fake_claude import FakeClaude, response, text
from tests.tg_harness import ADMIN_CHAT, ADMIN_ID, TG

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeGemini:
    def __init__(self, status=200, body=None):
        self.requests: list[httpx.Request] = []
        self.status = status
        self.body = body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "quota exceeded"}})
        if self.body is not None:
            return httpx.Response(200, json=self.body)
        if "image" in request.url.path:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": "Ось фото"},
                {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(PNG).decode()}},
            ]}}]})  # fmt: skip
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "1. Варіант один\n2. Варіант два"}]}}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200,
                              "thoughtsTokenCount": 50},
        })  # fmt: skip

    def body_of(self, i=-1):
        return json.loads(self.requests[i].content)


@pytest.fixture
def fake():
    return FakeGemini()


@pytest.fixture
def settings():
    return Settings(_env_file=None, gemini_api_key="g-key", gemini_text_model="gem-text",
                    gemini_image_model="gem-image", admin_ids=[ADMIN_ID],
                    tg_admin_chat_id=ADMIN_CHAT)  # fmt: skip


@pytest.fixture(autouse=True)
def gemini_prices(monkeypatch):
    monkeypatch.setitem(prices.TEXT, "gem-text", (0.10, 0.40))
    monkeypatch.setitem(prices.IMAGE, "gem-image", 0.04)


def make_router(engine, settings, fake, claude=None):
    g = GeminiClient("g-key", httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    return AiRouter(engine, settings, gemini=g, claude=claude, clock=lambda: NOW)


async def test_bulk_text_goes_to_gemini_and_is_costed(engine, settings, fake):
    out = await make_router(engine, settings, fake).bulk_text("5 підписів до Reels про фарбування")
    assert out.provider == "gemini" and out.text.startswith("1. Варіант один")
    req = fake.requests[0]
    assert req.url.path == "/v1beta/models/gem-text:generateContent"
    assert req.headers["x-goog-api-key"] == "g-key"
    body = fake.body_of()
    assert "5 підписів до Reels" in body["contents"][0]["parts"][0]["text"]
    assert "M&D" in body["contents"][0]["parts"][0]["text"]
    with Session(engine) as s:
        row = s.scalar(select(AiUsage))
        assert (row.provider, row.kind, row.input_tokens, row.output_tokens) == (
            "gemini",
            "text",
            1000,
            250,
        )  # thinking-токени оплачуються як вихідні
        assert row.cost_usd == pytest.approx((1000 * 0.10 + 250 * 0.40) / 1e6)


async def test_falls_back_to_claude_haiku_without_gemini(engine):
    claude = FakeClaude(response(text("Текст від Claude")))
    r = AiRouter(engine, Settings(_env_file=None), claude=claude, clock=lambda: NOW)
    out = await r.bulk_text("ідеї акцій")
    assert out.provider == "anthropic" and out.model == "claude-haiku-5-5"
    assert claude.requests[0]["output_config"] == {"effort": "low"}


async def test_nothing_configured(engine):
    with pytest.raises(AiUnavailable):
        await AiRouter(engine, Settings(_env_file=None), clock=lambda: NOW).bulk_text("x")


async def test_budget_blocks_calls(engine, settings, fake):
    settings.ai_monthly_budget_usd = 1.0
    with Session(engine) as s, s.begin():
        s.add(AiUsage(provider="anthropic", kind="chat", model="m", cost_usd=0.999,
                      created_at=NOW))  # fmt: skip
        s.add(
            AiUsage(
                provider="anthropic",
                kind="chat",
                model="m",
                cost_usd=50.0,
                created_at=datetime(2026, 10, 31, 12, tzinfo=UTC),
            )
        )  # минулий місяць
    with pytest.raises(BudgetExceeded):
        await make_router(engine, settings, fake).image("манікюр")
    assert fake.requests == []
    assert month_start(NOW, settings.zone) == datetime(2026, 10, 31, 22, 0, tzinfo=UTC)


async def test_image_generation(engine, settings, fake):
    img, cost = await make_router(engine, settings, fake).image("нюдовий манікюр")
    assert img.data == PNG and img.mime_type == "image/png" and cost == 0.04
    body = fake.body_of()
    assert body["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
    with Session(engine) as s:
        row = s.scalar(select(AiUsage))
        assert (row.kind, row.units, row.cost_usd) == ("image", 1, 0.04)


async def test_gemini_errors(engine, settings):
    with pytest.raises(GeminiError) as e:
        await make_router(engine, settings, FakeGemini(status=429)).bulk_text("x")
    assert e.value.status == 429 and "quota" in e.value.message
    blocked = FakeGemini(body={"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(GeminiError, match="SAFETY"):
        await make_router(engine, settings, blocked).bulk_text("x")


def test_unknown_model_priced_high():
    assert prices.text_cost("unknown", 1_000_000, 0) == max(p for p, _ in prices.TEXT.values())
    assert prices.image_cost("unknown") == prices.UNKNOWN_IMAGE


# --- Telegram -------------------------------------------------------------------


@pytest.fixture
def tg(engine, settings, fake):
    t = TG(engine, settings, clock=lambda: NOW)
    t.dp["ai"] = make_router(engine, settings, fake)
    return t


async def test_gen_image_budget_commands(tg, engine):
    await tg.send("/gen 5 підписів до посту про стрижку", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    texts = tg.texts(ADMIN_CHAT)
    assert "1. Варіант один" in texts[-2] and "gem-text" in texts[-1]
    await tg.send("/image манікюр", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert any(isinstance(c, SendPhoto) for c in tg.session.calls)
    await tg.send("/budget", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    report = tg.last_text(ADMIN_CHAT)
    assert "gemini / text: 1 викл." in report and "gemini / image: 1 викл." in report
    await tg.send("/gen", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Формат" in tg.last_text(ADMIN_CHAT)


async def test_gen_ignored_for_non_admin(tg):
    await tg.send("/gen щось", user_id=777, chat_id=ADMIN_CHAT)
    assert tg.texts(ADMIN_CHAT) == []
