from datetime import date, datetime
from pathlib import Path
from typing import Literal
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
    # without it a photo upload is refused before any call to OpenAI
    include_api_openai: bool = False
    # the key is read from a file, in docker it is mounted as a secret
    openai_token_file: Path = REPO_ROOT / ".openai-token"
    openai_model: str = "gpt-6-luna"
    openai_reasoning_effort: Literal[
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ] = "high"
    openai_image_crops: bool = True
    # a long reasoning over several pages takes minutes
    openai_timeout: float = 600

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
