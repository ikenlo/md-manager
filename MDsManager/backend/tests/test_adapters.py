import asyncio
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.adapters.base import MetaAdapter
from app.services.adapters.factory import get_meta_adapter
from app.services.adapters.mock import MockMetaAdapter


def test_factory_returns_mock_by_default():
    adapter = get_meta_adapter()
    assert isinstance(adapter, MockMetaAdapter)
    assert isinstance(adapter, MetaAdapter)


def test_factory_real_not_implemented(monkeypatch):
    monkeypatch.setattr(get_settings(), "mock_meta", False)
    with pytest.raises(NotImplementedError):
        get_meta_adapter()


def test_mock_send_message_returns_unique_ids():
    adapter = MockMetaAdapter(send_delay=0)

    async def go():
        return await asyncio.gather(
            adapter.send_message("ig-1", "Вітаю", "instagram"),
            adapter.send_message("ig-1", "Вітаю", "instagram"),
        )

    a, b = asyncio.run(go())
    assert a["status"] == b["status"] == "sent"
    assert a["external_id"].startswith("mock_") and a["external_id"] != b["external_id"]


def test_mock_send_message_waits_one_second_by_default():
    assert MockMetaAdapter().send_delay == 1.0


def test_mock_download_attachment_writes_jpeg(tmp_path: Path):
    dest = tmp_path / "nested" / "a.jpg"
    assert asyncio.run(MockMetaAdapter().download_attachment("https://x/y.jpg", str(dest)))
    data = dest.read_bytes()
    # SOI … EOI, а в заголовку SOF0 — висота й ширина 1×1
    assert data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    sof = data.index(b"\xff\xc0")
    assert data[sof + 5 : sof + 9] == b"\x00\x01\x00\x01"


def test_mock_user_profile():
    profile = asyncio.run(MockMetaAdapter().get_user_profile("ig-1", "instagram"))
    assert profile == {"name": "Test User", "username": "test_user", "avatar_url": None}
