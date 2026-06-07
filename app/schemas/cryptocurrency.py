import uuid
from datetime import datetime

from pydantic import BaseModel


class CryptocurrencyResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    name: str
    symbol: str
    current_price: float | None
    market_cap: float | None
    price_change_percentage_24h: float | None
    image_url: str | None
    market_cap_rank: int | None
    last_updated_at: datetime | None

    model_config = {"from_attributes": True}


class PaginatedCoinsResponse(BaseModel):
    data: list[CryptocurrencyResponse]
    total: int
    page: int
    per_page: int


class PricePoint(BaseModel):
    timestamp: datetime
    price: float


class HistoryResponse(BaseModel):
    coin_id: str
    days: int
    prices: list[PricePoint]


class RefreshResponse(BaseModel):
    updated: int
    message: str


class InsightResponse(BaseModel):
    coin_id: str
    insight: str
    generated_at: datetime
    cached: bool = False
