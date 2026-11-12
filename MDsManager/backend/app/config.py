from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DB_PATH = (PROJECT_DIR / "data" / "mds.db").as_posix()


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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.replace(chr(92), '/')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
