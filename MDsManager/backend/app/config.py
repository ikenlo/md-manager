from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DB_PATH = (PROJECT_DIR / "data" / "mds.db").as_posix()
DEFAULT_MEDIA_DIR = (PROJECT_DIR / "media").as_posix()
FRONTEND_DIST = (PROJECT_DIR / "frontend" / "dist").as_posix()

LOCAL_HOSTS = ("localhost", "127.0.0.1")


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env").as_posix(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    encryption_key: str = Field(..., alias="ENCRYPTION_KEY")
    db_path: str = Field(DEFAULT_DB_PATH, alias="DB_PATH")
    cors_origins: str = Field("http://localhost:5173,http://localhost:8000", alias="CORS_ORIGINS")
    session_ttl_days: int = Field(7, alias="SESSION_TTL_DAYS")

    app_env: Literal["development", "production"] = Field("development", alias="APP_ENV")
    # Домени, з якими приймаємо запити (крім localhost/127.0.0.1), через кому
    allowed_hosts: str = Field("", alias="ALLOWED_HOSTS")
    # Від кого довіряємо CF-Connecting-IP / X-Forwarded-Proto (cloudflared на цій машині)
    trusted_proxies: str = Field("127.0.0.1,::1", alias="TRUSTED_PROXIES")
    login_rate_limit: str = Field("5/15minutes", alias="LOGIN_RATE_LIMIT")

    # Диспетчер (Фаза 2). MOCK_META=true — без реальних викликів Meta Graph API
    mock_meta: bool = Field(True, alias="MOCK_META")
    # false — воркер черги не стартує (тести, разові скрипти)
    outbound_worker_enabled: bool = Field(True, alias="OUTBOUND_WORKER_ENABLED")
    outbound_interval_seconds: int = Field(30, ge=1, alias="OUTBOUND_INTERVAL_SECONDS")
    max_outbound_retries: int = Field(5, ge=1, alias="MAX_OUTBOUND_RETRIES")
    # Пауза перед повтором = база × номер спроби (60, 120, 180 … с)
    outbound_retry_base_seconds: int = Field(60, ge=1, alias="OUTBOUND_RETRY_BASE_SECONDS")
    # Вкладення з Meta зберігаються локально (лише прямі слеші)
    media_dir: str = Field(DEFAULT_MEDIA_DIR, alias="MEDIA_DIR")

    # AI: локальна LLM через Ollama (Фаза 3). MOCK_OLLAMA=true — без звернень до Ollama
    ollama_enabled: bool = Field(True, alias="OLLAMA_ENABLED")
    mock_ollama: bool = Field(True, alias="MOCK_OLLAMA")
    ollama_host: str = Field("http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field("qwen3:14b", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(120, ge=1, alias="OLLAMA_TIMEOUT_SECONDS")
    ollama_temperature: float = Field(0.7, ge=0, le=2, alias="OLLAMA_TEMPERATURE")
    ollama_num_ctx: int = Field(8192, ge=512, alias="OLLAMA_NUM_CTX")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)

    @property
    def allowed_host_list(self) -> list[str]:
        return [*LOCAL_HOSTS, *_split(self.allowed_hosts)]

    @property
    def trusted_proxy_list(self) -> list[str]:
        return _split(self.trusted_proxies)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.replace(chr(92), '/')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
