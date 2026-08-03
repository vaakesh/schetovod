from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# .env and .openai-token live in the repo root, next to docker-compose.yml
REPO_ROOT = (
    Path(
        __file__,
    )
    .resolve()
    .parent.parent
)
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore",
    )

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int
    # the shop's day, ledger dates and the future date check follow it
    timezone: str = "Europe/Moscow"

    @property
    def database_url(self) -> URL:
        # URL.create escapes special characters in the password
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()


def today() -> date:
    """the current date in the shop's time zone, not the server's"""
    return datetime.now(
        tz=ZoneInfo(
            key=settings.timezone,
        ),
    ).date()
