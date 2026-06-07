import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.watchlist import WatchlistItem


class WatchlistRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_watchlist(self, user_id: uuid.UUID) -> list[WatchlistItem]:
        result = await self.db.execute(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .options(selectinload(WatchlistItem.cryptocurrency))
            .order_by(WatchlistItem.added_at.desc())
        )
        return result.scalars().all()

    async def get_item(
        self, user_id: uuid.UUID, cryptocurrency_id: uuid.UUID
    ) -> WatchlistItem | None:
        result = await self.db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.cryptocurrency_id == cryptocurrency_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, user_id: uuid.UUID, cryptocurrency_id: uuid.UUID) -> WatchlistItem:
        item = WatchlistItem(user_id=user_id, cryptocurrency_id=cryptocurrency_id)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item, ["cryptocurrency"])
        return item

    async def remove(self, item: WatchlistItem) -> None:
        await self.db.delete(item)
        await self.db.flush()
