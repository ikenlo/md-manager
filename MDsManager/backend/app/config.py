from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DB_PATH = (PROJECT_DIR / "data" / "mds.db").as_posix()
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
