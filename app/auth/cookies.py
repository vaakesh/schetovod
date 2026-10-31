from datetime import timedelta

from fastapi import Response

from auth.schemas import AuthTokens
from core.config import settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def set_auth_cookies(
    response: Response,
    tokens: AuthTokens,
) -> None:
    # strict: a request from another site comes without the cookies, this closes CSRF
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=tokens.access,
        max_age=int(
            timedelta(
                minutes=settings.auth_access_ttl_minutes,
            ).total_seconds(),
        ),
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    # sent only to the auth routes, the other requests do not carry it
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=tokens.refresh,
        max_age=int(
            timedelta(
                days=settings.auth_refresh_ttl_days,
            ).total_seconds(),
        ),
        path=settings.auth_refresh_cookie_path,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=settings.auth_refresh_cookie_path,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
