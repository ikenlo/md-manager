"""Імітація Meta для розробки й тестів (MOCK_META=true): нічого не йде назовні."""

import asyncio
import base64
from pathlib import Path
from uuid import uuid4

from app.services.adapters.base import MetaAdapter, MetaChannel, SendResult, UserProfile

# Повідомлення з таким початком «не доходять» — для перевірки повторів (/api/_test/…)
FAIL_MARKER = "__FAIL__"

# JPEG 1×1 px (колір фону інтерфейсу)
DUMMY_JPG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERX"
    "RTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2Nj"
    "Y2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAA"
    "AAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk"
    "M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKT"
    "lJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QA"
    "HwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh"
    "cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp"
    "anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDuqKKKQH//2Q=="
)


class MockMetaAdapter(MetaAdapter):
    def __init__(self, send_delay: float = 1.0) -> None:
        self.send_delay = send_delay

    async def send_message(self, recipient_id: str, text: str, channel: MetaChannel) -> SendResult:
        await asyncio.sleep(self.send_delay)
        if text.startswith(FAIL_MARKER):
            raise RuntimeError("mock failure")
        return {"external_id": f"mock_{uuid4().hex}", "status": "sent"}

    async def download_attachment(self, url: str, dest_path: str) -> bool:
        def write() -> None:
            path = Path(dest_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(DUMMY_JPG)

        await asyncio.to_thread(write)
        return True

    async def get_user_profile(self, user_id: str, channel: MetaChannel) -> UserProfile:
        return {"name": "Test User", "username": "test_user", "avatar_url": None}
