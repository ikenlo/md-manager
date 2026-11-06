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

    # Інші моделі для дешевої генерації контенту (Gemini API, ai.google.dev)
    gemini_api_key: str = ""
    # Масові тексти: найдешевша модель для нових проєктів ($0.25 / $1.50 за 1M токенів, 11.2026)
    gemini_text_model: str = "gemini-3.1-flash-lite"
    # Картинки: ≈ $0.034 за 1K (11.2026)
    gemini_image_model: str = "gemini-nano-banana-2.1"
    ai_monthly_budget_usd: float = 0.0  # 0 — без ліміту

    # Meta Graph API: аналітика Instagram/Facebook і реклама (токен System User з Business Manager)
    meta_api_version: str = "v26.0"
    meta_token: str = ""
    meta_ig_user_id: str = ""  # Instagram professional account ID
    meta_ad_account_id: str = ""  # без префікса act_
    meta_page_id: str = ""  # сторінка Facebook (перегляди, залучення)
    ad_currency: str = "UAH"

    # Google Ads API (developers.google.com/google-ads/api): OAuth-клієнт + refresh token власника
    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_customer_id: str = ""  # 10 цифр без дефісів
    google_ads_login_customer_id: str = ""  # MCC-акаунт, якщо доступ через нього
    google_ads_api_version: str = "v22"

    # AI-аналітик (Claude): щоденний звіт із порадами і контент-план на місяць
    analyst_model: str = "claude-opus-5-5"
    analyst_effort: str = "medium"  # low | medium | high
    analyst_daily: bool = True  # щодня о 07:05 Київ після збору аналітики

    # Контент-план: 1 пост на тиждень + сторіс раз на N днів; фото дає власник, AI підправляє
    content_post_weekday: int = 3  # 0 — понеділок … 3 — четвер
    content_post_time: str = "18:00"
    content_story_every_days: int = 2
    content_story_time: str = "11:00"
    content_plan_auto_day: int = 25  # цього числа — ідеї на наступний місяць (0 — вимкнено)
    media_dir: str = "./data/media"  # фото салону й оброблені версії

    # Вхід у MDS Manager: логіни MDS Connect (якщо задано MDS_URL); без MDS — пароль власника
    panel_password: str = ""
    # підпис cookie сесії (openssl rand -hex 32); порожньо → сесії діють до перезапуску
    session_secret: str = ""
    session_days: int = 14

    # Instagram
    ig_access_token: str = ""
    ig_app_secret: str = ""
    ig_verify_token: str = ""

    # Telegram
    tg_bot_token: str = ""
    tg_admin_chat_id: int = 0
    tg_webhook_secret: str = ""
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # MDS Connect — джерело правди для записів (порожньо → локальна БД записів)
    mds_url: str = ""  # https://m-d-production.up.railway.app
    mds_token: str = ""  # той самий, що MDS_INTEGRATION_TOKEN у MDS Connect
    tg_bot_username: str = ""  # для посилань з мітками: t.me/<username>?start=<мітка>

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
    def google_ads_enabled(self) -> bool:
        return all(
            (
                self.google_ads_developer_token,
                self.google_ads_client_id,
                self.google_ads_client_secret,
                self.google_ads_refresh_token,
                self.google_ads_customer_id,
            )
        )

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


@lru_cache
def get_settings() -> Settings:
    return Settings()
