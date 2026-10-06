from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Petroil Project Manager API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    POSTGRES_USER: str = "petroil"
    POSTGRES_PASSWORD: str = "petroil"
    POSTGRES_DB: str = "petroil"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return URL.create(
            "postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
