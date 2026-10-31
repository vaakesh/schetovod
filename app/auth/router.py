from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from auth.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from auth.dependencies import CurrentSession, CurrentUser
from auth.models import User
from auth.schemas import LoginRequest, UserSummary
from auth.service import AuthServiceDep

router = APIRouter()


@router.post(
    path="/auth/login",
    response_model=UserSummary,
)
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
) -> User:
    user, tokens = await service.login(
        payload=payload,
    )
    set_auth_cookies(
        response=response,
        tokens=tokens,
    )
    return user


@router.post(
    path="/auth/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def refresh(
    response: Response,
    service: AuthServiceDep,
    refresh_token: Annotated[
        str | None,
        Cookie(
            alias=REFRESH_COOKIE,
        ),
    ] = None,
) -> None:
    tokens = await service.refresh(
        refresh_token=refresh_token,
    )
    if tokens is not None:
        set_auth_cookies(
            response=response,
            tokens=tokens,
        )


@router.get(
    path="/auth/me",
    response_model=UserSummary,
)
async def me(user: CurrentUser) -> User:
    return user


@router.post(
    path="/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    response: Response,
    user_session: CurrentSession,
    service: AuthServiceDep,
) -> None:
    await service.logout(
        user_session=user_session,
    )
    clear_auth_cookies(
        response=response,
    )
