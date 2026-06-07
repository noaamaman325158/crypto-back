from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_db"

    # Auth
    secret_key: str = "dev-secret-key-change-in-prod"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Service-to-service
    internal_api_key: str = "dev-internal-key"

    # CoinGecko
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379"

    # App
    environment: str = "development"
    api_prefix: str = "/api/v1"


settings = Settings()
