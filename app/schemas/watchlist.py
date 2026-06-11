import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.cryptocurrency import CryptocurrencyResponse


class WatchlistAddRequest(BaseModel):
    cryptocurrency_id: uuid.UUID

    model_config = {
        "json_schema_extra": {
            "example": {"cryptocurrency_id": "6c3a7834-b309-478b-82b8-0982b7bab7a2"}
        }
    }


class WatchlistItemResponse(BaseModel):
    id: uuid.UUID
    added_at: datetime
    cryptocurrency: CryptocurrencyResponse

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "ad0fdda0-8e01-4008-9e5d-a2ae84d6e1b6",
                "added_at": "2024-01-15T10:30:00Z",
                "cryptocurrency": {
                    "id": "6c3a7834-b309-478b-82b8-0982b7bab7a2",
                    "external_id": "bitcoin",
                    "name": "Bitcoin",
                    "symbol": "btc",
                    "current_price": 62404.0,
                    "market_cap": 1251349545443.0,
                    "price_change_percentage_24h": 0.585,
                    "image_url": "https://coin-images.coingecko.com/coins/images/1/large/bitcoin.png",
                    "market_cap_rank": 1,
                    "last_updated_at": "2024-01-15T10:30:00Z",
                },
            }
        },
    }


class WatchlistResponse(BaseModel):
    items: list[WatchlistItemResponse]
    total: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "ad0fdda0-8e01-4008-9e5d-a2ae84d6e1b6",
                        "added_at": "2024-01-15T10:30:00Z",
                        "cryptocurrency": {
                            "id": "6c3a7834-b309-478b-82b8-0982b7bab7a2",
                            "external_id": "bitcoin",
                            "name": "Bitcoin",
                            "symbol": "btc",
                            "current_price": 62404.0,
                            "market_cap": 1251349545443.0,
                            "price_change_percentage_24h": 0.585,
                            "image_url": "https://coin-images.coingecko.com/coins/images/1/large/bitcoin.png",
                            "market_cap_rank": 1,
                            "last_updated_at": "2024-01-15T10:30:00Z",
                        },
                    }
                ],
                "total": 1,
            }
        }
    }
