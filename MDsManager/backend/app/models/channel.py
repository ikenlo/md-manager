from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin

CHANNEL_TYPES = ("instagram", "facebook", "telegram")
WEBHOOK_STATUSES = ("active", "error", "expired", "inactive")


class Channel(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "channels"

    channel_type: Mapped[str] = mapped_column(String(32))
    account_name: Mapped[str] = mapped_column(String(255))
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="disconnected")
    # Meta: сторінка Facebook і пов'язаний Instagram-акаунт
    meta_page_id: Mapped[str | None] = mapped_column(String(64))
    meta_ig_id: Mapped[str | None] = mapped_column(String(64))
    webhook_status: Mapped[str] = mapped_column(
        String(20), default="inactive", server_default="inactive"
    )

    def set_access_token(self, token: str | None) -> None:
        from app.services.crypto import encrypt

        self.access_token_encrypted = encrypt(token) if token else None

    def get_access_token(self) -> str | None:
        from app.services.crypto import decrypt

        return decrypt(self.access_token_encrypted) if self.access_token_encrypted else None
