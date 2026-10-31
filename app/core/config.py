from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# .env lives in the repo root, next to compose.yml
REPO_ROOT = (
    Path(
        __file__,
    )
    .resolve()
    .parent.parent.parent
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
    openai_api_token: SecretStr = SecretStr(
        secret_value="",
    )
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
    openai_proxy_url: str = ""
    # without it the shifts and the receipts of the till can not be loaded
    aqsi_api_integration: str = ""
    # the broker of the background tasks
    redis_url: str = "redis://localhost:6379/0"
    # signs the tokens, a new value signs everyone out
    jwt_secret: SecretStr = Field(
        min_length=32,
    )
    # a browser drops a secure cookie over plain http everywhere except localhost
    auth_cookie_secure: bool = True
    # the path in the browser: nginx strips the /api prefix before the backend
    auth_refresh_cookie_path: str = "/api/auth"
    auth_access_ttl_minutes: int = 15
    # moves forward on every refresh, a week of absence does not sign the user out
    auth_refresh_ttl_days: int = 30

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


def now() -> datetime:
    """the current moment, stored with its time zone"""
    return datetime.now(
        tz=UTC,
    )


def today() -> date:
    """the current date in the shop's time zone, not the server's"""
    return datetime.now(
        tz=ZoneInfo(
            key=settings.timezone,
        ),
    ).date()
