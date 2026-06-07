import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.cryptocurrency import CryptocurrencyResponse


class WatchlistAddRequest(BaseModel):
    cryptocurrency_id: uuid.UUID


class WatchlistItemResponse(BaseModel):
    id: uuid.UUID
    added_at: datetime
    cryptocurrency: CryptocurrencyResponse

    model_config = {"from_attributes": True}


class WatchlistResponse(BaseModel):
    items: list[WatchlistItemResponse]
    total: int
