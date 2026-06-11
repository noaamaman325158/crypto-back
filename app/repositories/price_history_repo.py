from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_history import PriceHistory, RefreshDeadLetter


class PriceHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def append_price_snapshot(self, external_id: str, price: float, recorded_at: datetime) -> None:
        self.db.add(PriceHistory(external_id=external_id, price=price, recorded_at=recorded_at))
        await self.db.flush()

    async def get_history(
        self, external_id: str, days: int
    ) -> list[PriceHistory]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(PriceHistory)
            .where(
                PriceHistory.external_id == external_id,
                PriceHistory.recorded_at >= since,
            )
            .order_by(PriceHistory.recorded_at.asc())
        )
        return list(result.scalars().all())

    async def purge_old_history(self, keep_days: int = 90) -> int:
        """Delete rows older than keep_days. Called by the worker after each run."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        result = await self.db.execute(
            delete(PriceHistory).where(PriceHistory.recorded_at < cutoff)
        )
        await self.db.flush()
        return result.rowcount

    async def write_dead_letter(self, batch_page: int, error: str) -> None:
        self.db.add(RefreshDeadLetter(batch_page=batch_page, error=error[:2000]))
        await self.db.flush()
