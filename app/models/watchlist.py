import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "cryptocurrency_id", name="uq_user_crypto"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    cryptocurrency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cryptocurrencies.id", ondelete="CASCADE")
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="watchlist")  # noqa: F821
    cryptocurrency: Mapped["Cryptocurrency"] = relationship(  # noqa: F821
        "Cryptocurrency", back_populates="watchlist_items"
    )
