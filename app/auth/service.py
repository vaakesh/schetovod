from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends

from auth.models import User, UserSession
from auth.repository import AuthRepositoryDep
from auth.schemas import AuthTokens, LoginRequest
from auth.security import (
    DUMMY_HASH,
    create_access_token,
    create_refresh_token,
    hash_password,
    new_jti,
    normalize_login,
    read_access_token,
    read_refresh_token,
    verify_password,
)
from core.config import now, settings
from core.http import unauthorized

# the tabs of one browser share the cookie and may exchange it at the same moment,
# the slower one finds the token already replaced
REFRESH_GRACE = timedelta(
    seconds=30,
)


def session_expiry(moment: datetime) -> datetime:
    return moment + timedelta(
        days=settings.auth_refresh_ttl_days,
    )


def issue_tokens(user_session: UserSession) -> AuthTokens:
    return AuthTokens(
        access=create_access_token(
            user_id=user_session.user_id,
            session_id=user_session.id,
        ),
        refresh=create_refresh_token(
            user_id=user_session.user_id,
            session_id=user_session.id,
            jti=user_session.refresh_jti,
        ),
    )


class AuthService:
    def __init__(
        self,
        auth: AuthRepositoryDep,
    ) -> None:
        self.auth = auth

    async def login(
        self,
        payload: LoginRequest,
    ) -> tuple[User, AuthTokens]:
        user = await self.auth.get_user_by_login(
            login=normalize_login(
                login=payload.login,
            ),
        )
        # the hash takes tens of milliseconds, other requests must not wait for it
        verified = await asyncio.to_thread(
            verify_password,
            password_hash=DUMMY_HASH if user is None else user.password_hash,
            password=payload.password,
        )
        if user is None or not verified or not user.is_active:
            unauthorized(
                detail="Неверный логин или пароль",
            )

        moment = now()
        await self.auth.delete_stale_sessions(
            user_id=user.id,
            moment=moment,
        )
        user_session = UserSession(
            user_id=user.id,
            refresh_jti=new_jti(),
            expires_at=session_expiry(
                moment=moment,
            ),
        )
        await self.auth.add_session(
            user_session=user_session,
        )
        await self.auth.commit()
        return user, issue_tokens(
            user_session=user_session,
        )

    async def current_session(
        self,
        access_token: str | None,
    ) -> UserSession:
        session_id = (
            None
            if access_token is None
            else read_access_token(
                token=access_token,
            )
        )
        if session_id is None:
            unauthorized()
        user_session = await self.auth.get_active_session(
            session_id=session_id,
            moment=now(),
        )
        if user_session is None:
            unauthorized()
        return user_session

    async def refresh(
        self,
        refresh_token: str | None,
    ) -> AuthTokens | None:
        """new tokens, None when another tab has just received them"""
        claims = (
            None
            if refresh_token is None
            else read_refresh_token(
                token=refresh_token,
            )
        )
        if claims is None:
            unauthorized()
        user_session = await self.auth.lock_session(
            session_id=claims.session_id,
        )
        moment = now()
        if (
            user_session is None
            or user_session.revoked_at is not None
            or user_session.expires_at <= moment
        ):
            unauthorized()
        user = await self.auth.get_user(
            user_id=user_session.user_id,
        )
        if user is None or not user.is_active:
            unauthorized()

        if claims.jti != user_session.refresh_jti:
            if (
                claims.jti == user_session.previous_refresh_jti
                and user_session.rotated_at is not None
                and moment - user_session.rotated_at <= REFRESH_GRACE
            ):
                return None
            # an old token came back: it was stolen, or the thief was first
            user_session.revoked_at = moment
            await self.auth.commit()
            unauthorized()

        user_session.previous_refresh_jti = user_session.refresh_jti
        user_session.refresh_jti = new_jti()
        user_session.rotated_at = moment
        user_session.expires_at = session_expiry(
            moment=moment,
        )
        await self.auth.commit()
        return issue_tokens(
            user_session=user_session,
        )

    async def logout(
        self,
        user_session: UserSession,
    ) -> None:
        user_session.revoked_at = now()
        await self.auth.commit()

    async def save_user(
        self,
        login: str,
        password: str,
    ) -> bool:
        """creates the user or sets a new password, True for a new user"""
        normalized = normalize_login(
            login=login,
        )
        password_hash = await asyncio.to_thread(
            hash_password,
            password=password,
        )
        user = await self.auth.get_user_by_login(
            login=normalized,
        )
        if user is None:
            await self.auth.add_user(
                user=User(
                    login=normalized,
                    password_hash=password_hash,
                ),
            )
            await self.auth.commit()
            return True

        user.password_hash = password_hash
        # whoever signed in with the old password is signed out
        await self.auth.revoke_sessions(
            user_id=user.id,
            moment=now(),
        )
        await self.auth.commit()
        return False


AuthServiceDep = Annotated[
    AuthService,
    Depends(
        dependency=AuthService,
    ),
]
