import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cryptocurrency import Cryptocurrency


class CryptoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(
        self, page: int = 1, per_page: int = 50, sort_by: str = "market_cap_rank"
    ) -> tuple[list[Cryptocurrency], int]:
        offset = (page - 1) * per_page
        count_result = await self.db.execute(select(func.count()).select_from(Cryptocurrency))
        total = count_result.scalar_one()

        order_col = getattr(Cryptocurrency, sort_by, Cryptocurrency.market_cap_rank)
        result = await self.db.execute(
            select(Cryptocurrency).order_by(order_col).offset(offset).limit(per_page)
        )
        return list(result.scalars().all()), total

    async def get_by_id(self, crypto_id: uuid.UUID) -> Cryptocurrency | None:
        result = await self.db.execute(
            select(Cryptocurrency).where(Cryptocurrency.id == crypto_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Cryptocurrency | None:
        result = await self.db.execute(
            select(Cryptocurrency).where(Cryptocurrency.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_top_movers(self, limit: int = 5) -> tuple[list[Cryptocurrency], list[Cryptocurrency]]:
        """Returns (gainers, losers) sorted by 24h price change, excluding nulls."""
        base = (
            select(Cryptocurrency)
            .where(Cryptocurrency.price_change_percentage_24h.is_not(None))
        )
        gainers_result = await self.db.execute(
            base.order_by(Cryptocurrency.price_change_percentage_24h.desc()).limit(limit)
        )
        losers_result = await self.db.execute(
            base.order_by(Cryptocurrency.price_change_percentage_24h.asc()).limit(limit)
        )
        return list(gainers_result.scalars().all()), list(losers_result.scalars().all())

    async def upsert_many(self, coins: list[dict]) -> int:
        """Upsert coins by external_id. Returns count of rows affected."""
        if not coins:
            return 0

        for coin in coins:
            coin["last_updated_at"] = datetime.now(timezone.utc)

        stmt = insert(Cryptocurrency).values(coins)
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_id"],
            set_={
                "name": stmt.excluded.name,
                "symbol": stmt.excluded.symbol,
                "current_price": stmt.excluded.current_price,
                "market_cap": stmt.excluded.market_cap,
                "price_change_percentage_24h": stmt.excluded.price_change_percentage_24h,
                "image_url": stmt.excluded.image_url,
                "market_cap_rank": stmt.excluded.market_cap_rank,
                "last_updated_at": stmt.excluded.last_updated_at,
                # Must be updated on conflict too — data_age_seconds is derived
                # from last_refreshed_at. Omitting it here freezes the age at the
                # first insert and makes CoinDataStale alerts fire as false positives.
                "last_refreshed_at": stmt.excluded.last_refreshed_at,
            },
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount
