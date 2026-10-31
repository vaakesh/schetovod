from typing import Annotated

from fastapi import Cookie, Depends

from auth.cookies import ACCESS_COOKIE
from auth.models import User, UserSession
from auth.service import AuthServiceDep


async def get_current_session(
    service: AuthServiceDep,
    access_token: Annotated[
        str | None,
        Cookie(
            alias=ACCESS_COOKIE,
        ),
    ] = None,
) -> UserSession:
    return await service.current_session(
        access_token=access_token,
    )


CurrentSession = Annotated[
    UserSession,
    Depends(
        dependency=get_current_session,
    ),
]


async def get_current_user(user_session: CurrentSession) -> User:
    return user_session.user


CurrentUser = Annotated[
    User,
    Depends(
        dependency=get_current_user,
    ),
]
