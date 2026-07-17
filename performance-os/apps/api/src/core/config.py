from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379"

    clerk_jwks_url: str  # e.g. https://your-app.clerk.accounts.dev/.well-known/jwks.json
    clerk_publishable_key: str = ""

    garmin_session_encryption_key: str  # generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
