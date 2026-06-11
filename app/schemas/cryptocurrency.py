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
    data_age_seconds: int | None = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
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
            }
        },
    }


class PaginatedCoinsResponse(BaseModel):
    data: list[CryptocurrencyResponse]
    total: int
    page: int
    per_page: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "data": [
                    {
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
                    }
                ],
                "total": 100,
                "page": 1,
                "per_page": 50,
            }
        }
    }


class PricePoint(BaseModel):
    timestamp: datetime
    price: float

    model_config = {
        "json_schema_extra": {
            "example": {"timestamp": "2024-01-15T10:30:00Z", "price": 62404.0}
        }
    }


class HistoryResponse(BaseModel):
    coin_id: str
    days: int
    prices: list[PricePoint]

    model_config = {
        "json_schema_extra": {
            "example": {
                "coin_id": "bitcoin",
                "days": 30,
                "prices": [
                    {"timestamp": "2023-12-16T00:00:00Z", "price": 41983.0},
                    {"timestamp": "2024-01-15T00:00:00Z", "price": 62404.0},
                ],
            }
        }
    }


class RefreshResponse(BaseModel):
    updated: int
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {"updated": 100, "message": "Refreshed 100 cryptocurrencies from CoinGecko"}
        }
    }


class TopMoversResponse(BaseModel):
    gainers: list[CryptocurrencyResponse]
    losers: list[CryptocurrencyResponse]

    model_config = {
        "json_schema_extra": {
            "example": {
                "gainers": [
                    {
                        "id": "6c3a7834-b309-478b-82b8-0982b7bab7a2",
                        "external_id": "bitcoin",
                        "name": "Bitcoin",
                        "symbol": "btc",
                        "current_price": 62404.0,
                        "market_cap": 1251349545443.0,
                        "price_change_percentage_24h": 8.5,
                        "image_url": "https://coin-images.coingecko.com/coins/images/1/large/bitcoin.png",
                        "market_cap_rank": 1,
                        "last_updated_at": "2024-01-15T10:30:00Z",
                    }
                ],
                "losers": [
                    {
                        "id": "950db1ac-8549-42f9-ade1-a96c3f194483",
                        "external_id": "ethereum",
                        "name": "Ethereum",
                        "symbol": "eth",
                        "current_price": 1636.07,
                        "market_cap": 197603888325.0,
                        "price_change_percentage_24h": -5.2,
                        "image_url": "https://coin-images.coingecko.com/coins/images/279/large/ethereum.png",
                        "market_cap_rank": 2,
                        "last_updated_at": "2024-01-15T10:30:00Z",
                    }
                ],
            }
        }
    }


class InsightResponse(BaseModel):
    coin_id: str
    insight: str
    generated_at: datetime
    cached: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "coin_id": "bitcoin",
                "insight": "Bitcoin has shown strong upward momentum over the past 30 days, rising from $41,983 to $62,404 — a 48.6% gain. The price broke through the $60,000 resistance level on January 10th with elevated volume, suggesting institutional accumulation. Key support now sits at $58,000.",
                "generated_at": "2024-01-15T10:30:00Z",
                "cached": False,
            }
        }
    }
