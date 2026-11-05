"""Налаштування з .env. Секрети читаються лише тут."""

from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"
    ai_effort: str = "medium"  # low | medium | high
    ai_timeout_s: float = 30.0
    ai_max_tool_calls: int = 8
    ai_history_messages: int = 20

    # Instagram
    ig_access_token: str = ""
    ig_app_secret: str = ""
    ig_verify_token: str = ""

    # Telegram
    tg_bot_token: str = ""
    tg_admin_chat_id: int = 0
    tg_webhook_secret: str = ""
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # Інфраструктура
    public_url: str = ""  # https://bot.example.com → вебхуки; порожньо → long polling
    database_url: str = "sqlite:///./data/mds.db"
    tz: str = "Europe/Kyiv"

    # Бізнес-правила
    min_lead_min: int = 60
    slot_step_min: int = 15
    max_slots: int = 6
    handoff_auto_resume_hours: int = 12

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> object:
        # ADMIN_IDS=123,456 у .env
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        if isinstance(v, int):
            return [v]
        return v

    @field_validator("tg_admin_chat_id", mode="before")
    @classmethod
    def _empty_int(cls, v: object) -> object:
        return 0 if v == "" else v

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


@lru_cache
def get_settings() -> Settings:
    return Settings()
