from datetime import datetime

from auth.models import User, UserSession
from tests.fakes.store import FakeStore


def signed_in_user() -> User:
    return User(
        id=1,
        login="owner",
        password_hash="",
        is_active=True,
    )


class FakeAuth:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def get_user(
        self,
        user_id: int,
    ) -> User | None:
        return self.store.users.get(
            user_id,
        )

    async def get_user_by_login(
        self,
        login: str,
    ) -> User | None:
        for user in self.store.users.values():
            if user.login == login:
                return user
        return None

    async def add_user(
        self,
        user: User,
    ) -> None:
        user.id = self.store.new_id()
        self.store.users[user.id] = user

    async def add_session(
        self,
        user_session: UserSession,
    ) -> None:
        user_session.id = self.store.new_id()
        self.store.user_sessions[user_session.id] = user_session

    async def get_active_session(
        self,
        session_id: int,
        moment: datetime,
    ) -> UserSession | None:
        user_session = self.store.user_sessions.get(
            session_id,
        )
        if (
            user_session is None
            or user_session.revoked_at is not None
            or user_session.expires_at <= moment
        ):
            return None
        user = self.store.users[user_session.user_id]
        if not user.is_active:
            return None
        user_session.user = user
        return user_session

    async def lock_session(
        self,
        session_id: int,
    ) -> UserSession | None:
        return self.store.user_sessions.get(
            session_id,
        )

    async def delete_stale_sessions(
        self,
        user_id: int,
        moment: datetime,
    ) -> None:
        self.store.user_sessions = {
            key: item
            for key, item in self.store.user_sessions.items()
            if item.user_id != user_id
            or (item.expires_at > moment and item.revoked_at is None)
        }

    async def revoke_sessions(
        self,
        user_id: int,
        moment: datetime,
    ) -> None:
        for item in self.store.user_sessions.values():
            if item.user_id == user_id and item.revoked_at is None:
                item.revoked_at = moment
