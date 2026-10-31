from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import contains_eager

from auth.models import User, UserSession
from core.db import SessionDep


class AuthRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def get_user(
        self,
        user_id: int,
    ) -> User | None:
        return await self.session.get(
            entity=User,
            ident=user_id,
        )

    async def get_user_by_login(
        self,
        login: str,
    ) -> User | None:
        return await self.session.scalar(
            statement=select(
                User,
            ).where(
                User.login == login,
            ),
        )

    async def add_user(
        self,
        user: User,
    ) -> None:
        self.session.add(
            instance=user,
        )
        await self.session.flush()

    async def add_session(
        self,
        user_session: UserSession,
    ) -> None:
        self.session.add(
            instance=user_session,
        )
        await self.session.flush()

    async def get_active_session(
        self,
        session_id: int,
        moment: datetime,
    ) -> UserSession | None:
        """the session with its user, read on every request of the api"""
        return await self.session.scalar(
            statement=select(
                UserSession,
            )
            .join(
                UserSession.user,
            )
            .options(
                contains_eager(
                    UserSession.user,
                ),
            )
            .where(
                UserSession.id == session_id,
                UserSession.revoked_at.is_(
                    None,
                ),
                UserSession.expires_at > moment,
                User.is_active,
            ),
        )

    async def lock_session(
        self,
        session_id: int,
    ) -> UserSession | None:
        """two tabs exchange the same refresh token one after the other"""
        return await self.session.scalar(
            statement=select(
                UserSession,
            )
            .where(
                UserSession.id == session_id,
            )
            .with_for_update(),
        )

    async def delete_stale_sessions(
        self,
        user_id: int,
        moment: datetime,
    ) -> None:
        await self.session.execute(
            statement=delete(
                UserSession,
            ).where(
                UserSession.user_id == user_id,
                or_(
                    UserSession.expires_at <= moment,
                    UserSession.revoked_at.is_not(
                        None,
                    ),
                ),
            ),
        )

    async def revoke_sessions(
        self,
        user_id: int,
        moment: datetime,
    ) -> None:
        await self.session.execute(
            statement=update(
                UserSession,
            )
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(
                    None,
                ),
            )
            .values(
                revoked_at=moment,
            ),
        )


AuthRepositoryDep = Annotated[
    AuthRepository,
    Depends(
        dependency=AuthRepository,
    ),
]
