from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin


class CrmClient(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "crm_clients"

    name: Mapped[str] = mapped_column(String(255))
    instagram_handle: Mapped[str | None] = mapped_column(String(64), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    # копійки
    total_spent: Mapped[int] = mapped_column(Integer, default=0)
    visits_count: Mapped[int] = mapped_column(Integer, default=0)
    # Meta: ідентифікатори відправника (PSID / IGSID) — по них зводимо вхідні з клієнтом
    meta_ig_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    meta_fb_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    username: Mapped[str | None] = mapped_column(String(100))
    # профіль недоступний (приватний акаунт / не дав згоди) — ім'я тимчасове
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    links: Mapped[list["ClientLink"]] = relationship(
        back_populates="crm_client", cascade="all, delete-orphan", passive_deletes=True
    )


class ClientLink(IdMixin, TimestampMixin, Base):
    __tablename__ = "client_links"

    crm_client_id: Mapped[int] = mapped_column(
        ForeignKey("crm_clients.id", ondelete="CASCADE"), index=True
    )
    connect_client_id: Mapped[str] = mapped_column(String(64), index=True)

    crm_client: Mapped[CrmClient] = relationship(back_populates="links")
