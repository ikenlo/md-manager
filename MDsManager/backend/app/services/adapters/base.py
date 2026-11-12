"""Інтерфейс до Meta (Instagram Direct, Facebook Messenger).

Сервіси диспетчера працюють лише з `MetaAdapter`;
конкретну реалізацію дає `factory.get_meta_adapter()`.
"""

from abc import ABC, abstractmethod
from typing import TypedDict

MetaChannel = str  # "instagram" | "facebook"


class SendResult(TypedDict):
    external_id: str  # mid від Meta
    status: str  # "sent" | "failed"


class UserProfile(TypedDict):
    name: str
    username: str
    avatar_url: str | None


class MetaAdapter(ABC):
    @abstractmethod
    async def send_message(self, recipient_id: str, text: str, channel: MetaChannel) -> SendResult:
        """Надсилає текст отримувачу (IGSID / PSID). Помилка мережі/API → виняток."""

    @abstractmethod
    async def download_attachment(self, url: str, dest_path: str) -> bool:
        """Завантажує вкладення в dest_path (каталоги створює сам). True — успіх."""

    @abstractmethod
    async def get_user_profile(self, user_id: str, channel: MetaChannel) -> UserProfile:
        """Ім'я, нікнейм і аватар відправника."""
