from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from core.config import now, settings

ALGORITHM = "HS256"

hasher = PasswordHasher()
# verified when the login is unknown, so the answer takes as long as for a known one
DUMMY_HASH = hasher.hash(
    password="unknown login",
)


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(
    frozen=True,
)
class RefreshClaims:
    session_id: int
    jti: str


def normalize_login(login: str) -> str:
    return login.strip().lower()


def hash_password(password: str) -> str:
    return hasher.hash(
        password=password,
    )


def verify_password(
    password_hash: str,
    password: str,
) -> bool:
    try:
        return hasher.verify(
            hash=password_hash,
            password=password,
        )
    except VerificationError:
        return False


def new_jti() -> str:
    return uuid4().hex


def encode(
    claims: dict[str, Any],
    lifetime: timedelta,
) -> str:
    return jwt.encode(
        payload={
            **claims,
            "exp": int(
                (now() + lifetime).timestamp(),
            ),
        },
        key=settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )


def create_access_token(
    user_id: int,
    session_id: int,
) -> str:
    return encode(
        claims={
            "sub": str(
                user_id,
            ),
            "sid": session_id,
            "type": TokenType.ACCESS,
        },
        lifetime=timedelta(
            minutes=settings.auth_access_ttl_minutes,
        ),
    )


def create_refresh_token(
    user_id: int,
    session_id: int,
    jti: str,
) -> str:
    return encode(
        claims={
            "sub": str(
                user_id,
            ),
            "sid": session_id,
            "jti": jti,
            "type": TokenType.REFRESH,
        },
        lifetime=timedelta(
            days=settings.auth_refresh_ttl_days,
        ),
    )


def decode(
    token: str,
    token_type: TokenType,
) -> dict[str, Any] | None:
    try:
        claims = jwt.decode(
            jwt=token,
            key=settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={
                "require": ["exp", "sub", "sid", "type"],
            },
        )
    except jwt.InvalidTokenError:
        return None
    # a refresh token lives for a month, it must not open the api
    return claims if claims["type"] == token_type else None


def read_access_token(token: str) -> int | None:
    """the id of the session the token belongs to, None for a bad token"""
    claims = decode(
        token=token,
        token_type=TokenType.ACCESS,
    )
    return None if claims is None else claims["sid"]


def read_refresh_token(token: str) -> RefreshClaims | None:
    claims = decode(
        token=token,
        token_type=TokenType.REFRESH,
    )
    if claims is None or "jti" not in claims:
        return None
    return RefreshClaims(
        session_id=claims["sid"],
        jti=claims["jti"],
    )
