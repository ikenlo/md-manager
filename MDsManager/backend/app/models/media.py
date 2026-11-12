from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import CreatedMixin, IdMixin


class MediaAsset(IdMixin, CreatedMixin, Base):
    """Файл вкладення, збережений локально (MEDIA_DIR); meta_url — звідки завантажено."""

    __tablename__ = "media_assets"

    dialogue_id: Mapped[int] = mapped_column(
        ForeignKey("dialogues.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    meta_url: Mapped[str | None] = mapped_column(String(1000))
